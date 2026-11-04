"""Bộ mô phỏng analyzer Modbus TCP (FC03/FC04) để demo - không cần thiết bị thật.

Bản đồ thanh ghi (float32, big-endian word order):
 0 pH | 2 Temp | 4 TSS | 6 COD | 8 NH4+ | 10 Flow out 1 | 100 trạng thái COD (0 đo, 1 hiệu chuẩn, 2 lỗi)
"""
from __future__ import annotations
import asyncio
import math
import random
import struct
import time

BASE = {0: (7.2, 0.3), 2: (29.0, 1.5), 4: (35.0, 10.0), 6: (60.0, 30.0), 8: (3.0, 1.5), 10: (120.0, 15.0)}


class Sim:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.status = {100: 0}

    def registers(self) -> dict[int, int]:
        t = time.time()
        regs = {}
        for addr, (base, amp) in BASE.items():
            v = base + amp * math.sin(t / 600 + addr) + self.rng.uniform(-amp, amp) * 0.15
            hi, lo = struct.unpack(">HH", struct.pack(">f", v))
            regs[addr], regs[addr + 1] = hi, lo
        regs.update(self.status)
        return regs


async def _handle(reader, writer, sim: Sim):
    try:
        while True:
            hdr = await reader.readexactly(7)
            tid, pid, length, unit = struct.unpack(">HHHB", hdr)
            pdu = await reader.readexactly(length - 1)
            fc = pdu[0]
            if fc in (3, 4):
                addr, cnt = struct.unpack(">HH", pdu[1:5])
                regs = sim.registers()
                data = b"".join(struct.pack(">H", regs.get(addr + i, 0)) for i in range(cnt))
                resp = bytes([fc, len(data)]) + data
            else:
                resp = bytes([fc | 0x80, 1])
            writer.write(struct.pack(">HHHB", tid, 0, len(resp) + 1, unit) + resp)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError):
        pass
    finally:
        writer.close()


async def serve(host="0.0.0.0", port=5020, sim: Sim | None = None):
    sim = sim or Sim()
    srv = await asyncio.start_server(lambda r, w: _handle(r, w, sim), host, port)
    print(f"[sim] Modbus TCP simulator tại {host}:{port}")
    async with srv:
        await srv.serve_forever()


def run(host="0.0.0.0", port=5020):
    asyncio.run(serve(host, port))
