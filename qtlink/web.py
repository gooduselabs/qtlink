"""Dashboard web (FastAPI)."""
from __future__ import annotations
import os
from datetime import datetime, timedelta

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from . import config as cfgmod

STATIC = os.path.join(os.path.dirname(__file__), "static")


def create_app(engine, config_path: str | None = None) -> FastAPI:
    app = FastAPI(title="QTLink")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC, "index.html"))

    @app.get("/api/status")
    def status():
        st = engine.cfg["station"]
        q = {r["dest"]: r for r in engine.db.queue_stats()}
        dests = []
        for d in engine.cfg["destinations"]:
            r = q.get(d["name"], {})
            dests.append({"name": d["name"], "protocol": d["protocol"], "host": d.get("host") or d.get("url", ""), "format": d.get("format"), "enabled": d.get("enabled", True),
                          "sent": r.get("sent") or 0, "pending": r.get("pending") or 0,
                          "last_success": engine.db.last_success(d["name"])})
        return {"station": st, "now": datetime.now().isoformat(timespec="seconds"),
                "interval": engine.cfg["logger"]["file_interval_minutes"],
                "language": engine.cfg["logger"].get("language", "en"), "destinations": dests}

    @app.get("/api/live")
    def live():
        return engine.live

    @app.get("/api/trend")
    def trend(param: str, hours: float = 6):
        return engine.db.trend(param, datetime.now() - timedelta(hours=hours))

    @app.get("/api/uploads")
    def uploads(limit: int = 100):
        return engine.db.upload_log(limit)

    @app.get("/api/alarms")
    def alarms(limit: int = 50):
        return engine.db.alarms(limit)

    @app.get("/api/config", response_class=PlainTextResponse)
    def get_config():
        return yaml.safe_dump(engine.cfg, allow_unicode=True, sort_keys=False)

    @app.post("/api/config")
    async def set_config(req: Request):
        text = (await req.body()).decode("utf-8")
        try:
            new = cfgmod.validate(yaml.safe_load(text))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(400, f"Invalid config: {e}")
        engine.cfg = new
        if config_path:
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(text)
        return {"ok": True}

    @app.post("/api/build-now")
    def build_now():
        slot = datetime.now().replace(microsecond=0)
        return {"path": engine.build_file(slot)}

    return app
