import struct
import pytest
from qtlink.modbus_reader import decode, scale, read_device

def regs_f(v):
    return list(struct.unpack(">HH", struct.pack(">f", v)))

def test_float32_big_little():
    assert decode(regs_f(7.25), "float32") == 7.25
    assert decode(list(reversed(regs_f(7.25))), "float32", "little") == 7.25

def test_int_types():
    assert decode([0xFFFF], "int16") == -1
    assert decode([0xFFFF], "uint16") == 65535
    assert decode([0x0001, 0x0000], "uint32") == 65536

def test_scale_offset():
    assert scale(725, {"scale": 0.01}) == pytest.approx(7.25)
    assert scale(100, {"scale": 0.1, "offset": -5}) == pytest.approx(5)

def test_scale_4_20ma_linear():
    tag = {"raw_min": 4000, "raw_max": 20000, "eng_min": 0, "eng_max": 14}
    assert scale(12000, tag) == pytest.approx(7.0)
    assert scale(4000, tag) == 0

def test_read_against_simulator():
    import asyncio, threading, time, socket
    from qtlink import simulator
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    threading.Thread(target=lambda: asyncio.run(simulator.serve("127.0.0.1", port)), daemon=True).start()
    time.sleep(0.5)
    dev = {"name": "a", "type": "tcp", "host": "127.0.0.1", "port": port}
    res = read_device(dev, [{"param": "pH", "register": 0, "unit": "-"}, {"param": "COD", "register": 6, "unit": "mg/L", "status_register": 100}])
    assert res["pH"]["ok"] and 5 < res["pH"]["value"] < 10
    assert res["COD"]["ok"] and not res["COD"]["calibrating"]

def test_unreachable_device_is_fault():
    res = read_device({"name": "x", "host": "127.0.0.1", "port": 1, "timeout": 0.3}, [{"param": "pH", "register": 0}])
    assert res["pH"]["ok"] is False
