"""Đọc analyzer qua Modbus TCP/RTU và chuyển đổi thang đo."""
from __future__ import annotations
import logging
import struct
from typing import Any

log = logging.getLogger(__name__)
REG_COUNT = {"int16": 1, "uint16": 1, "int32": 2, "uint32": 2, "float32": 2}


def decode(regs: list[int], dtype: str = "float32", word_order: str = "big") -> float:
    if dtype not in REG_COUNT:
        raise ValueError(f"data_type không hỗ trợ: {dtype}")
    regs = list(regs[:REG_COUNT[dtype]])
    if word_order == "little":
        regs.reverse()
    raw = b"".join(struct.pack(">H", r & 0xFFFF) for r in regs)
    fmt = {"int16": ">h", "uint16": ">H", "int32": ">i", "uint32": ">I", "float32": ">f"}[dtype]
    return float(struct.unpack(fmt, raw)[0])


def scale(raw: float, tag: dict) -> float:
    """value = raw * scale + offset; hoặc nội suy tuyến tính raw_min..raw_max -> eng_min..eng_max (4-20mA)."""
    if "raw_min" in tag and "raw_max" in tag:
        r0, r1 = float(tag["raw_min"]), float(tag["raw_max"])
        e0, e1 = float(tag.get("eng_min", 0)), float(tag["eng_max"])
        return e0 + (raw - r0) * (e1 - e0) / (r1 - r0)
    return raw * float(tag.get("scale", 1.0)) + float(tag.get("offset", 0.0))


def make_client(dev: dict):
    from pymodbus.client import ModbusSerialClient, ModbusTcpClient
    if dev.get("type", "tcp") == "tcp":
        return ModbusTcpClient(dev["host"], port=int(dev.get("port", 502)), timeout=float(dev.get("timeout", 2)))
    return ModbusSerialClient(port=dev["serial_port"], baudrate=int(dev.get("baudrate", 9600)),
                              parity=dev.get("parity", "N"), stopbits=int(dev.get("stopbits", 1)),
                              bytesize=int(dev.get("bytesize", 8)), timeout=float(dev.get("timeout", 2)))


def read_device(dev: dict, tags: list[dict], client=None) -> dict[str, dict[str, Any]]:
    """Trả về {param: {value, ok, calibrating}} cho các tag thuộc thiết bị."""
    out: dict[str, dict[str, Any]] = {}
    own = client is None
    client = client or make_client(dev)
    try:
        connected = client.connect()
        for tag in tags:
            res = {"value": None, "ok": False, "calibrating": False}
            if connected:
                try:
                    res["value"] = _read_tag(client, dev, tag)
                    res["ok"] = True
                    if "status_register" in tag:
                        st = _read_raw(client, dev, tag["status_register"], 1, tag.get("function", "holding"))
                        res["calibrating"] = st[0] == int(tag.get("calib_value", 1))
                        res["ok"] = st[0] != int(tag.get("fault_value", 2))
                except Exception as e:  # noqa: BLE001
                    log.warning("Đọc %s lỗi: %s", tag["param"], e)
            out[tag["param"]] = res
    finally:
        if own:
            client.close()
    return out


def _read_raw(client, dev, address: int, count: int, function: str) -> list[int]:
    unit = int(dev.get("unit_id", 1))
    fn = client.read_input_registers if function == "input" else client.read_holding_registers
    rr = fn(int(address), count=count, device_id=unit)
    if rr.isError():
        raise IOError(str(rr))
    return list(rr.registers)


def _read_tag(client, dev, tag) -> float:
    dt = tag.get("data_type", "float32")
    regs = _read_raw(client, dev, tag["register"], REG_COUNT[dt], tag.get("function", "holding"))
    return scale(decode(regs, dt, tag.get("word_order", "big")), tag)
