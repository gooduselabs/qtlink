"""Output profiles, sinks (HTTP, InfluxDB, MQTT) and the shared store-and-forward queue."""
import asyncio, json, os, socket, threading, time
from datetime import datetime, timedelta

import pytest

from qtlink import config, formats, sinks, testservers, tt10
from qtlink.engine import Engine
from qtlink.modbus_reader import _read_tag

T = datetime(2026, 11, 4, 10, 5)
ST = {"station": "SITE01", "province": "BN", "facility": "GULB", "name": "Demo"}
RECS = [tt10.Record("pH", 7.123, "-", T), tt10.Record("COD", None, "mg/L", T, tt10.STATUS_FAULT)]


def free():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Clock:
    def __init__(self, t): self.t = t
    def __call__(self): return self.t


def base_cfg(tmp_path, dests):
    return config.validate({
        "station": dict(ST),
        "logger": {"outbox_dir": str(tmp_path / "out"), "db_path": str(tmp_path / "db.sqlite")},
        "devices": [{"name": "d", "host": "x"}],
        "tags": [{"param": "pH", "unit": "-", "device": "d", "register": 0}],
        "sinks": dests,
    })


def reader(dev, tags):
    return {t["param"]: {"value": 7.0, "ok": True, "calibrating": False} for t in tags}


# ---------- formats ----------
def test_formats_render():
    lg = {"decimals": 2}
    assert formats.render("tt10_txt", RECS, ST, lg).startswith("pH\t7.12\t-\t20261104100500\t00\r\n")
    csv = formats.render("csv", RECS, ST, lg).splitlines()
    assert csv[0] == "station,param,value,unit,time,status"
    assert csv[1] == "SITE01,pH,7.12,-,2026-11-04T10:05:00,ok" and csv[2].endswith(",fault")
    js = json.loads(formats.render("json", RECS, ST, lg))
    assert js["station"] == "SITE01" and js["values"][0] == {"param": "pH", "value": 7.12, "unit": "-", "status": "ok"}
    assert js["values"][1]["value"] is None
    lp = formats.render("influx", RECS, ST, lg).splitlines()
    assert len(lp) == 1 and lp[0].startswith("qtlink,station=SITE01,param=pH,unit=- value=7.123,status=\"ok\" ")
    assert formats.file_name("csv", ST, T) == "SITE01_20261104100500.csv"
    assert formats.file_name("tt10_txt", ST, T) == "BN_GULB_SITE01_20261104100500.txt"


# ---------- config ----------
def test_config_backward_compatible_and_defaults(tmp_path):
    c = config.load(os.path.join(os.path.dirname(__file__), "..", "config.example.tt10.yaml"))
    assert all(d["format"] == "tt10_txt" for d in c["destinations"])
    c = base_cfg(tmp_path, [{"name": "m", "type": "mqtt", "host": "h"}, {"name": "i", "protocol": "influxdb", "url": "u", "bucket": "b"}])
    assert [(d["protocol"], d["format"]) for d in c["destinations"]] == [("mqtt", "json"), ("influxdb", "influx")]


def test_config_tt10_fields_only_required_for_tt10(tmp_path):
    cfg = {"station": {"station": "S1"}, "devices": [{"name": "d", "host": "x"}],
           "tags": [{"param": "p", "unit": "u", "device": "d", "register": 0}],
           "sinks": [{"name": "h", "protocol": "http", "url": "http://x"}]}
    config.validate(json.loads(json.dumps(cfg)))
    cfg["sinks"].append({"name": "f", "protocol": "ftp", "host": "h"})
    with pytest.raises(ValueError, match="tt10_txt"):
        config.validate(cfg)


def test_config_rejects_bad_sinks(tmp_path):
    with pytest.raises(ValueError, match="protocol"):
        base_cfg(tmp_path, [{"name": "x", "protocol": "smtp", "host": "h"}])
    with pytest.raises(ValueError, match="url"):
        base_cfg(tmp_path, [{"name": "x", "protocol": "http"}])
    with pytest.raises(ValueError, match="Duplicate"):
        base_cfg(tmp_path, [{"name": "x", "protocol": "http", "url": "u"}, {"name": "x", "protocol": "http", "url": "u"}])


def test_device_templates_expand():
    c = config.validate({
        "station": {"station": "S1"},
        "devices": [{"name": "m", "template": "eastron_sdm120", "host": "x", "points": ["voltage", "total_active_energy"]},
                    {"name": "pv", "template": "sunspec_inverter_103", "host": "y"}],
        "tags": [{"param": "P", "device": "pv", "point": "ac_power"}],
        "sinks": [{"name": "h", "protocol": "http", "url": "http://x"}]})
    by = {t["param"]: t for t in c["tags"]}
    assert by["m.voltage"]["register"] == 0 and by["m.voltage"]["function"] == "input" and by["m.voltage"]["unit"] == "V"
    assert by["m.total_active_energy"]["register"] == 0x156
    assert by["P"]["register"] == 40083 and by["P"]["scale_register"] == 40084 and by["P"]["data_type"] == "int16"
    assert c["devices"][1]["port"] == 502


def test_all_device_templates_cite_a_source():
    tpls = config.list_templates()
    assert {"eastron_sdm120", "eastron_sdm630", "schneider_pm5xxx", "sunspec_inverter_103"} <= set(tpls)
    for name, t in tpls.items():
        assert t["source"].startswith("https://"), name
        for pn, p in t["points"].items():
            assert isinstance(p["register"], int) and p.get("unit"), (name, pn)


def test_scale_register_sunspec():
    class R:
        def __init__(self, regs): self.registers = regs
        def isError(self): return False
    mem = {40083: [1234], 40084: [0xFFFF]}  # W=1234, W_SF=-1
    class C:
        def read_holding_registers(self, a, count, device_id): return R(mem[a][:count])
    tag = {"register": 40083, "data_type": "int16", "scale_register": 40084, "function": "holding"}
    assert _read_tag(C(), {"unit_id": 1}, tag) == pytest.approx(123.4)


# ---------- HTTP / InfluxDB ----------
def test_http_webhook_sink(tmp_path):
    port = free()
    srv = testservers.start_http(str(tmp_path / "recv"), port=port, host="127.0.0.1")
    p = tmp_path / "SITE01_20261104100500.json"; p.write_text('{"a":1}')
    sinks.send({"name": "h", "protocol": "http", "format": "json", "url": f"http://127.0.0.1:{port}/ingest",
                "token": "abc", "headers": {"X-Site": "A"}}, str(p))
    r = srv.received[-1]
    assert r["path"] == "/ingest" and r["body"] == b'{"a":1}'
    assert r["headers"]["Authorization"] == "Bearer abc" and r["headers"]["Content-Type"] == "application/json"
    assert r["headers"]["X-Site"] == "A" and (tmp_path / "recv" / p.name).exists()
    srv.shutdown()


def test_http_error_raises(tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"])); self.send_response(500); self.end_headers()
        def log_message(self, *a): pass
    port = free(); srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p = tmp_path / "x.json"; p.write_text("{}")
    with pytest.raises(Exception):
        sinks.send({"protocol": "http", "url": f"http://127.0.0.1:{port}/"}, str(p))
    srv.shutdown()


def test_influxdb_sink_v2_and_v1(tmp_path, monkeypatch):
    port = free()
    srv = testservers.start_http(str(tmp_path / "recv"), port=port, host="127.0.0.1")
    p = tmp_path / "a.lp"; p.write_text("qtlink,station=S value=1 1\n")
    monkeypatch.setenv("TOK", "secret")
    sinks.send({"protocol": "influxdb", "url": f"http://127.0.0.1:{port}", "org": "o", "bucket": "b", "token_env": "TOK"}, str(p))
    r = srv.received[-1]
    assert r["path"] == "/api/v2/write?org=o&bucket=b&precision=s"
    assert r["headers"]["Authorization"] == "Token secret" and r["body"].startswith(b"qtlink,station=S")
    sinks.send({"protocol": "influxdb", "url": f"http://127.0.0.1:{port}/", "db": "mydb"}, str(p))
    assert srv.received[-1]["path"] == "/write?db=mydb&precision=s"
    srv.shutdown()


# ---------- MQTT (real local broker: amqtt) ----------
@pytest.fixture
def broker():
    amqtt = pytest.importorskip("amqtt.broker")
    port = free()
    loop = asyncio.new_event_loop()
    b = amqtt.Broker({"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
                      "plugins": {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}}}, loop=loop)
    threading.Thread(target=loop.run_forever, daemon=True).start()
    asyncio.run_coroutine_threadsafe(b.start(), loop).result(10)
    yield port
    asyncio.run_coroutine_threadsafe(b.shutdown(), loop).result(10)
    loop.call_soon_threadsafe(loop.stop)


def test_mqtt_sink_publishes_to_broker(tmp_path, broker):
    import paho.mqtt.client as mqtt
    got, ready = [], threading.Event()
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    sub.on_message = lambda c, u, m: got.append((m.topic, m.payload))
    sub.on_subscribe = lambda *a: ready.set()
    sub.connect("127.0.0.1", broker); sub.loop_start(); sub.subscribe("qtlink/#", qos=1)
    assert ready.wait(5)
    p = tmp_path / "SITE01_1.json"; p.write_text('{"v":1}')
    sinks.send({"protocol": "mqtt", "host": "127.0.0.1", "port": broker, "_station": "SITE01"}, str(p))
    for _ in range(50):
        if got: break
        time.sleep(0.1)
    sub.loop_stop(); sub.disconnect()
    assert got == [("qtlink/SITE01/data", b'{"v":1}')]


def test_mqtt_sink_unreachable_raises(tmp_path):
    p = tmp_path / "a.json"; p.write_text("{}")
    with pytest.raises(Exception):
        sinks.send({"protocol": "mqtt", "host": "127.0.0.1", "port": free(), "timeout": 2}, str(p))


# ---------- store-and-forward across sinks ----------
def test_one_file_per_format_and_independent_queues(tmp_path):
    clk = Clock(datetime(2026, 11, 4, 0, 0))
    down = {"mq"}
    sent = []
    def up(dest, path, rdir):
        if dest["name"] in down:
            raise ConnectionError("offline")
        sent.append((dest["name"], os.path.basename(path)))
    cfg = base_cfg(tmp_path, [{"name": "so", "protocol": "sftp", "host": "h"},
                              {"name": "mq", "protocol": "mqtt", "host": "h"},
                              {"name": "web", "protocol": "http", "url": "u"},
                              {"name": "off", "protocol": "http", "url": "u", "enabled": False}])
    e = Engine(cfg, reader=reader, upload=up, now=clk)
    for i in range(1, 4):
        e.poll_once(); e.build_file(datetime(2026, 11, 4, 0, 5 * i))
    assert e.db.q("SELECT COUNT(*) c FROM files")[0]["c"] == 6   # 3 slots x (txt + json)
    e.upload_pending()
    assert [s for s in sent if s[0] == "so"] == [("so", f"BN_GULB_SITE01_2026110400{m:02d}00.txt") for m in (5, 10, 15)]
    assert [s for s in sent if s[0] == "web"] == [("web", f"SITE01_2026110400{m:02d}00.json") for m in (5, 10, 15)]
    assert len(e.db.pending("mq")) == 3 and e.db.pending("off") == []
    down.clear()
    e.upload_pending(); e.upload_pending()
    assert [s[1] for s in sent if s[0] == "mq"] == [f"SITE01_2026110400{m:02d}00.json" for m in (5, 10, 15)]
    assert len(sent) == 9  # no duplicates


def test_queue_stops_at_first_failure_and_resumes_oldest_first(tmp_path):
    clk = Clock(datetime(2026, 11, 4, 0, 0))
    calls, fail_on = [], {"SITE01_20261104001000.json"}
    def up(dest, path, rdir):
        n = os.path.basename(path); calls.append(n)
        if n in fail_on:
            raise IOError("HTTP 503")
    e = Engine(base_cfg(tmp_path, [{"name": "web", "protocol": "http", "url": "u"}]), reader=reader, upload=up, now=clk)
    for i in range(1, 4):
        e.build_file(datetime(2026, 11, 4, 0, 5 * i))
    e.upload_pending()
    assert calls == ["SITE01_20261104000500.json", "SITE01_20261104001000.json"]   # 3rd not attempted out of order
    fail_on.clear(); calls.clear()
    e.upload_pending()
    assert calls == ["SITE01_20261104001000.json", "SITE01_20261104001500.json"]
    log = {r["name"]: r for r in e.db.upload_log()}
    assert log["SITE01_20261104001000.json"]["attempts"] == 2 and all(r["status"] == "sent" for r in log.values())


def test_rebuilding_same_slot_does_not_duplicate(tmp_path):
    clk = Clock(datetime(2026, 11, 4, 0, 0)); sent = []
    e = Engine(base_cfg(tmp_path, [{"name": "web", "protocol": "http", "url": "u"}]), reader=reader,
               upload=lambda d, p, r: sent.append(p), now=clk)
    e.build_file(T); e.build_file(T)
    e.upload_pending(); e.build_file(T); e.upload_pending()
    assert len(sent) == 1


def test_e2e_http_sink_with_local_server(tmp_path):
    port = free()
    srv = testservers.start_http(str(tmp_path / "recv"), port=port, host="127.0.0.1")
    clk = Clock(datetime(2026, 11, 4, 0, 1))
    e = Engine(base_cfg(tmp_path, [{"name": "web", "protocol": "http", "url": f"http://127.0.0.1:{port}/x"},
                                   {"name": "influx", "protocol": "influxdb", "url": f"http://127.0.0.1:{port}", "bucket": "b"}]),
               reader=reader, now=clk)
    e.poll_once(); e.build_file(datetime(2026, 11, 4, 0, 5)); e.upload_pending()
    bodies = {r["path"].split("?")[0]: r["body"] for r in srv.received}
    assert json.loads(bodies["/x"])["values"][0]["value"] == 7.0
    assert bodies["/api/v2/write"].startswith(b"qtlink,station=SITE01,param=pH")
    assert e.db.pending("web") == [] and e.db.pending("influx") == []
    srv.shutdown()
