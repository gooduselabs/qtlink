"""CLI: python -m qtlink [run|sim|testserver|demo]"""
from __future__ import annotations
import argparse
import logging
import threading
import time


def main():
    ap = argparse.ArgumentParser(prog="qtlink", description="QTLink - datalogger theo TT10/2021/TT-BTNMT")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Chạy datalogger + dashboard")
    r.add_argument("-c", "--config", default="config.yaml")
    r.add_argument("--host", default="0.0.0.0")
    r.add_argument("--port", type=int, default=8080)
    s = sub.add_parser("sim", help="Chạy bộ mô phỏng Modbus TCP")
    s.add_argument("--port", type=int, default=5020)
    t = sub.add_parser("testserver", help="Chạy máy chủ FTP+sFTP thử nghiệm")
    t.add_argument("--root", default="data/server")
    d = sub.add_parser("demo", help="Tất cả trong một: sim + FTP/sFTP test + logger + web")
    d.add_argument("-c", "--config", default="config.demo.yaml")
    d.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if a.cmd == "sim":
        from .simulator import run as sim_run
        sim_run(port=a.port)
    elif a.cmd == "testserver":
        from .testservers import start_ftp, start_sftp
        start_ftp(a.root + "/ftp")
        start_sftp(a.root + "/sftp")
        while True:
            time.sleep(3600)
    else:
        if a.cmd == "demo":
            from .simulator import run as sim_run
            from .testservers import start_ftp, start_sftp
            threading.Thread(target=sim_run, kwargs={"port": 5020}, daemon=True).start()
            start_ftp("data/server/ftp")
            start_sftp("data/server/sftp")
            time.sleep(1)
        import uvicorn
        from . import config
        from .engine import Engine
        from .web import create_app
        cfg = config.load(a.config)
        eng = Engine(cfg)
        eng.start()
        uvicorn.run(create_app(eng, a.config), host=getattr(a, "host", "0.0.0.0"), port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
