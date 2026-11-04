"""CLI: python -m qtlink [run|sim|testserver|demo]"""
from __future__ import annotations
import argparse
import logging
import threading
import time


def main():
    ap = argparse.ArgumentParser(prog="qtlink", description="QTLink - lightweight Modbus edge datalogger with store-and-forward")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Run datalogger + dashboard")
    r.add_argument("-c", "--config", default="config.yaml")
    r.add_argument("--host", default="0.0.0.0")
    r.add_argument("--port", type=int, default=8080)
    s = sub.add_parser("sim", help="Run the Modbus TCP simulator")
    s.add_argument("--port", type=int, default=5020)
    t = sub.add_parser("testserver", help="Run local FTP + sFTP + HTTP test servers")
    t.add_argument("--root", default="data/server")
    d = sub.add_parser("demo", help="All-in-one: simulator + test servers + logger + web (English demo; -c config.demo.vi.yaml for Vietnamese)")
    d.add_argument("-c", "--config", default="config.demo.yaml")
    d.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if a.cmd == "sim":
        from .simulator import run as sim_run
        sim_run(port=a.port)
    elif a.cmd == "testserver":
        from .testservers import start_ftp, start_http, start_sftp
        start_ftp(a.root + "/ftp")
        start_sftp(a.root + "/sftp")
        start_http(a.root + "/http")
        while True:
            time.sleep(3600)
    else:
        if a.cmd == "demo":
            from .simulator import run as sim_run
            from .testservers import start_ftp, start_http, start_sftp
            threading.Thread(target=sim_run, kwargs={"port": 5020}, daemon=True).start()
            start_ftp("data/server/ftp")
            start_sftp("data/server/sftp")
            start_http("data/server/http")
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
