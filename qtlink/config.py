from __future__ import annotations
import yaml

REQUIRED = ["station", "devices", "tags", "destinations"]


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return validate(yaml.safe_load(f))


def validate(cfg: dict) -> dict:
    if not isinstance(cfg, dict):
        raise ValueError("Config phải là YAML dạng mapping")
    for k in REQUIRED:
        if k not in cfg:
            raise ValueError(f"Thiếu mục '{k}' trong config")
    st = cfg["station"]
    for k in ("province", "facility", "station"):
        if not st.get(k):
            raise ValueError(f"Thiếu station.{k}")
    devs = {d["name"] for d in cfg["devices"]}
    for t in cfg["tags"]:
        for k in ("param", "unit", "device", "register"):
            if k not in t:
                raise ValueError(f"Tag thiếu '{k}': {t}")
        if t["device"] not in devs:
            raise ValueError(f"Tag {t['param']} trỏ tới thiết bị không tồn tại: {t['device']}")
    cfg.setdefault("logger", {})
    lg = cfg["logger"]
    lg.setdefault("poll_seconds", 10)
    lg.setdefault("file_interval_minutes", 5)
    lg.setdefault("aggregate", "avg")
    lg.setdefault("decimals", 2)
    lg.setdefault("newline", "crlf")
    lg.setdefault("retention_days", 60)
    lg.setdefault("outbox_dir", "data/outbox")
    lg.setdefault("db_path", "data/qtlink.db")
    lg.setdefault("upload_seconds", 30)
    lg.setdefault("disconnect_warn_hours", 12)
    lg.setdefault("strict_names", True)
    return cfg
