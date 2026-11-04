"""End-to-end: simulator -> tệp TT10 -> sFTP + FTP cục bộ."""
import asyncio, os, socket, threading, time
from datetime import datetime, timedelta
from qtlink import config, simulator, testservers, tt10
from qtlink.engine import Engine


def free():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def test_end_to_end(tmp_path):
    mp, sp, fp = free(), free(), free()
    threading.Thread(target=lambda: asyncio.run(simulator.serve("127.0.0.1", mp)), daemon=True).start()
    testservers.start_sftp(str(tmp_path / "sftp"), port=sp, host="127.0.0.1", key_path=str(tmp_path / "k"))
    testservers.start_ftp(str(tmp_path / "ftp"), port=fp, host="127.0.0.1")
    time.sleep(0.5)
    cfg = config.validate({
        "station": {"province": "BN", "facility": "GULB", "station": "NUOXA1"},
        "logger": {"outbox_dir": str(tmp_path / "out"), "db_path": str(tmp_path / "db")},
        "devices": [{"name": "a", "host": "127.0.0.1", "port": mp}],
        "tags": [{"param": "pH", "unit": "-", "device": "a", "register": 0},
                 {"param": "Flow out 1", "unit": "m3/h", "device": "a", "register": 10}],
        "destinations": [
            {"name": "s", "protocol": "sftp", "host": "127.0.0.1", "port": sp, "username": "demo", "password": "demo", "station_folder": "NUOXA1"},
            {"name": "f", "protocol": "ftp", "host": "127.0.0.1", "port": fp, "username": "demo", "password": "demo", "station_folder": "NUOXA1"}],
    })
    e = Engine(cfg)
    e.poll_once()
    slot = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
    e.build_file(slot)
    e.upload_pending()
    name = tt10.file_name("BN", "GULB", "NUOXA1", slot)
    for root in ("sftp", "ftp"):
        p = tmp_path / root / "NUOXA1" / f"{slot:%Y}" / f"{slot:%m}" / f"{slot:%d}" / name
        assert p.exists(), p
        recs = tt10.parse_content(p.read_text())
        assert [r.parameter for r in recs] == ["pH", "Flow out 1"] and recs[0].status == "00"
    assert e.db.pending("s") == [] and e.db.pending("f") == []
