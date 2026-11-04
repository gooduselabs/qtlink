"""Config loading/validation. Backward compatible with v0.1 (TT10-only) configs.

New in v0.2:
- `sinks:` is accepted as an alias of `destinations:` (both may be used; they are merged).
- each destination has `protocol` (or `type`): ftp | ftps | sftp | mqtt | http | influxdb
  and an optional `format`: tt10_txt | csv | json | influx (defaults depend on protocol).
- devices may reference a register-map template from devices/*.yaml (`template: eastron_sdm120`);
  tags may then use `point: voltage` instead of register/data_type/function, and
  `points: [voltage, current]` (or `all`) on the device auto-creates tags.
- `station.province/facility` are only required when a tt10_txt sink is configured.
"""
from __future__ import annotations
import os

import yaml

from . import formats
from .sinks import DEFAULT_FORMAT, PROTOCOLS

REQUIRED = ["station", "devices", "tags"]
DEVICES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devices")
POINT_KEYS = ("register", "data_type", "function", "word_order", "scale", "offset", "scale_register", "unit")


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return validate(yaml.safe_load(f))


def list_templates(devices_dir: str = DEVICES_DIR) -> dict[str, dict]:
    out = {}
    if os.path.isdir(devices_dir):
        for fn in sorted(os.listdir(devices_dir)):
            if fn.endswith((".yaml", ".yml")):
                with open(os.path.join(devices_dir, fn), encoding="utf-8") as f:
                    out[os.path.splitext(fn)[0]] = yaml.safe_load(f)
    return out


def load_template(name: str, devices_dir: str = DEVICES_DIR) -> dict:
    for ext in (".yaml", ".yml"):
        p = os.path.join(devices_dir, name + ext)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return yaml.safe_load(f)
    raise ValueError(f"Device template not found: {name} (looked in {devices_dir})")


def _expand_templates(cfg: dict, devices_dir: str):
    tpl_by_dev = {}
    for d in cfg["devices"]:
        if d.get("template"):
            tpl = load_template(d["template"], devices_dir)
            tpl_by_dev[d["name"]] = tpl
            for k, v in (tpl.get("connection") or {}).items():
                d.setdefault(k, v)
    existing = {(t.get("device"), t.get("point")) for t in cfg["tags"]}
    for d in cfg["devices"]:
        tpl = tpl_by_dev.get(d["name"])
        want = d.get("points")
        if not tpl or not want:
            continue
        names = list(tpl["points"]) if want == "all" else list(want)
        for pn in names:
            if (d["name"], pn) not in existing:
                cfg["tags"].append({"param": f"{d['name']}.{pn}", "device": d["name"], "point": pn})
    for t in cfg["tags"]:
        if "point" not in t:
            continue
        tpl = tpl_by_dev.get(t.get("device"))
        if not tpl:
            raise ValueError(f"Tag {t.get('param')} uses point '{t['point']}' but device {t.get('device')} has no template")
        if t["point"] not in tpl["points"]:
            raise ValueError(f"Point '{t['point']}' not in template of device {t['device']}")
        merged = dict(tpl.get("defaults") or {})
        merged.update(tpl["points"][t["point"]])
        for k in POINT_KEYS:
            if k in merged:
                t.setdefault(k, merged[k])
        t.setdefault("name", merged.get("name", t["point"]))


def validate(cfg: dict) -> dict:
    if not isinstance(cfg, dict):
        raise ValueError("Config must be a YAML mapping")
    for k in REQUIRED:
        if k not in cfg:
            raise ValueError(f"Missing section '{k}' in config")
    dests = list(cfg.get("destinations") or []) + list(cfg.pop("sinks", None) or [])
    if not dests:
        raise ValueError("Missing section 'destinations' (or 'sinks') in config")
    cfg["destinations"] = dests
    cfg.setdefault("logger", {})
    lg = cfg["logger"]
    _expand_templates(cfg, lg.get("devices_dir", DEVICES_DIR))

    names = set()
    for d in dests:
        if "protocol" not in d and "type" in d:
            d["protocol"] = d.pop("type")
        p = d.get("protocol")
        if p not in PROTOCOLS:
            raise ValueError(f"Destination {d.get('name')}: protocol must be one of {', '.join(PROTOCOLS)} (got {p!r})")
        if not d.get("name"):
            raise ValueError(f"Destination without name: {d}")
        if d["name"] in names:
            raise ValueError(f"Duplicate destination name: {d['name']}")
        names.add(d["name"])
        d.setdefault("format", DEFAULT_FORMAT[p])
        if d["format"] not in formats.FORMATS:
            raise ValueError(f"Destination {d['name']}: format must be one of {', '.join(formats.FORMATS)}")
        need = {"http": ["url"], "influxdb": ["url"], "mqtt": ["host"]}.get(p, ["host"])
        for k in need:
            if not d.get(k):
                raise ValueError(f"Destination {d['name']}: missing '{k}'")
        if p == "influxdb" and not (d.get("bucket") or d.get("db")):
            raise ValueError(f"Destination {d['name']}: influxdb needs 'bucket' (v2) or 'db' (v1)")

    st = cfg["station"]
    if not (st.get("station") or st.get("id")):
        raise ValueError("Missing station.station (station id)")
    st.setdefault("station", st.get("id"))
    if any(d["format"] == "tt10_txt" for d in dests):
        for k in ("province", "facility", "station"):
            if not st.get(k):
                raise ValueError(f"Missing station.{k} (required by the tt10_txt output profile)")
    devs = {d["name"] for d in cfg["devices"]}
    for t in cfg["tags"]:
        for k in ("param", "unit", "device", "register"):
            if k not in t:
                raise ValueError(f"Tag missing '{k}': {t}")
        if t["device"] not in devs:
            raise ValueError(f"Tag {t['param']} refers to unknown device: {t['device']}")
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
    lg.setdefault("language", "en")
    return cfg
