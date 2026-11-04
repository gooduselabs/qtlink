import os
from datetime import datetime, timedelta
from qtlink import config
from qtlink.engine import Engine, floor_time


class Clock:
    def __init__(self, t): self.t = t
    def __call__(self): return self.t


def make(tmp_path, clock, upload, reader=None):
    cfg = config.validate({
        "station": {"province": "BN", "facility": "GULB", "station": "NUOXA1"},
        "logger": {"outbox_dir": str(tmp_path / "out"), "db_path": str(tmp_path / "db.sqlite"), "disconnect_warn_hours": 12},
        "devices": [{"name": "d", "host": "x"}],
        "tags": [{"param": "pH", "unit": "-", "device": "d", "register": 0, "high": 9},
                 {"param": "COD", "unit": "mg/L", "device": "d", "register": 6}],
        "destinations": [{"name": "so", "protocol": "sftp", "host": "h", "station_folder": "NUOXA1"}],
    })
    vals = {"pH": 7.0, "COD": 50.0}
    reader = reader or (lambda dev, tags: {t["param"]: {"value": vals[t["param"]], "ok": True, "calibrating": False} for t in tags})
    return Engine(cfg, reader=reader, upload=upload, now=clock), vals


def test_floor_time():
    assert floor_time(datetime(2026, 1, 1, 10, 7, 33), 5) == datetime(2026, 1, 1, 10, 5)


def test_build_file_average(tmp_path):
    clk = Clock(datetime(2026, 11, 4, 10, 1))
    e, vals = make(tmp_path, clk, lambda *a: None)
    e.poll_once(); clk.t += timedelta(minutes=2); vals["pH"] = 8.0; e.poll_once()
    p = e.build_file(datetime(2026, 11, 4, 10, 5))
    assert os.path.basename(p) == "BN_GULB_NUOXA1_20261104100500.txt"
    txt = open(p, encoding="utf-8", newline="").read()
    assert "pH\t7.50\t-\t20261104100500\t00\r\n" in txt


def test_missing_data_marked_fault(tmp_path):
    clk = Clock(datetime(2026, 11, 4, 10, 1))
    e, _ = make(tmp_path, clk, lambda *a: None)
    txt = open(e.build_file(datetime(2026, 11, 4, 10, 5)), encoding="utf-8").read()
    assert txt.splitlines()[0].endswith("\t02")


def test_resend_queue_in_order_and_disconnect_warning(tmp_path):
    clk = Clock(datetime(2026, 11, 4, 0, 0))
    sent, online = [], {"up": False}
    def up(dest, path, rdir):
        if not online["up"]:
            raise ConnectionError("mất mạng")
        sent.append((os.path.basename(path), rdir))
    e, _ = make(tmp_path, clk, up)
    for i in range(1, 4):
        e.build_file(datetime(2026, 11, 4, 0, 5 * i))
    e.upload_pending()
    assert sent == [] and len(e.db.pending("so")) == 3
    assert not [a for a in e.db.alarms() if a["kind"] == "disconnect"]
    clk.t = datetime(2026, 11, 4, 13, 0)   # > 12h
    e.upload_pending()
    assert any(a["kind"] == "disconnect" and a["level"] == "warning" for a in e.db.alarms())
    online["up"] = True
    e.upload_pending()
    assert [s[0] for s in sent] == ["BN_GULB_NUOXA1_20261104000500.txt", "BN_GULB_NUOXA1_20261104001000.txt",
                                    "BN_GULB_NUOXA1_20261104001500.txt"]
    assert sent[0][1] == "/NUOXA1/2026/11/04"
    assert e.db.pending("so") == []
    e.upload_pending()
    assert len(sent) == 3  # không gửi trùng


def test_limit_alarm_edges(tmp_path):
    clk = Clock(datetime(2026, 11, 4, 10, 1))
    e, vals = make(tmp_path, clk, lambda *a: None)
    vals["pH"] = 9.5; e.poll_once(); e.poll_once()
    vals["pH"] = 7; e.poll_once()
    k = [a for a in e.db.alarms() if a["kind"] == "limit"]
    assert len(k) == 2 and k[1]["level"] == "alarm"


def test_cleanup_retention(tmp_path):
    clk = Clock(datetime(2026, 1, 1, 0, 0))
    e, _ = make(tmp_path, clk, lambda *a: None)
    p = e.build_file(datetime(2026, 1, 1, 0, 0))
    old = datetime(2025, 10, 1).timestamp(); os.utime(p, (old, old))
    e.poll_once()
    e.cleanup()
    assert not os.path.exists(p)
    assert e.db.q("SELECT COUNT(*) c FROM files")[0]["c"] == 1  # data_time 2026-01-01 vẫn trong 60 ngày
