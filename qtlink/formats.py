"""Output formats ("profiles"): turn one aggregated time slot into a file payload.

Every format receives the same list of tt10.Record objects (param, value, unit, time, status)
so adding a new profile never touches the polling or queue logic.

- tt10_txt : Vietnam Circular 10/2021/TT-BTNMT, Appendix XV (tab separated .txt)
- csv      : station,param,value,unit,time(ISO 8601),status
- json     : {"station":..., "time":..., "values":[{param,value,unit,status}, ...]}
- influx   : InfluxDB line protocol, one line per parameter
"""
from __future__ import annotations
import csv
import io
import json
from datetime import datetime

from . import tt10

FORMATS = ("tt10_txt", "csv", "json", "influx")
EXT = {"tt10_txt": "txt", "csv": "csv", "json": "json", "influx": "lp"}
CONTENT_TYPE = {"tt10_txt": "text/plain; charset=utf-8", "csv": "text/csv; charset=utf-8",
                "json": "application/json", "influx": "text/plain; charset=utf-8"}
STATUS_TEXT = {tt10.STATUS_MEASURING: "ok", tt10.STATUS_CALIBRATING: "calibrating", tt10.STATUS_FAULT: "fault"}


def station_id(station: dict) -> str:
    return str(station.get("id") or station.get("station"))


def file_name(fmt: str, station: dict, t: datetime) -> str:
    if fmt == "tt10_txt":
        return tt10.file_name(station["province"], station["facility"], station["station"], t)
    return f"{station_id(station)}_{t.strftime(tt10.TS_FMT)}.{EXT[fmt]}"


def render(fmt: str, records: list[tt10.Record], station: dict, logger: dict) -> str:
    dec = int(logger.get("decimals", 2))
    if fmt == "tt10_txt":
        return tt10.build_content(records, dec, "\r\n" if logger.get("newline", "crlf") == "crlf" else "\n")
    sid = station_id(station)
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["station", "param", "value", "unit", "time", "status"])
        for r in records:
            w.writerow([sid, r.parameter, "" if r.value is None else round(r.value, dec), r.unit,
                        r.time.isoformat(timespec="seconds"), STATUS_TEXT.get(r.status, r.status)])
        return buf.getvalue()
    if fmt == "json":
        t = records[0].time.isoformat(timespec="seconds") if records else None
        return json.dumps({"station": sid, "name": station.get("name"), "time": t,
                           "values": [{"param": r.parameter, "value": None if r.value is None else round(r.value, dec),
                                       "unit": r.unit, "status": STATUS_TEXT.get(r.status, r.status)} for r in records]},
                          ensure_ascii=False)
    if fmt == "influx":
        meas = _esc(logger.get("influx_measurement", "qtlink"))
        lines = []
        for r in records:
            if r.value is None:
                continue  # line protocol has no null; fault slots are still visible via status in other sinks
            ts = int(r.time.astimezone().timestamp())
            lines.append(f"{meas},station={_esc(sid)},param={_esc(r.parameter)},unit={_esc(r.unit)} "
                         f"value={float(r.value)!r},status=\"{STATUS_TEXT.get(r.status, r.status)}\" {ts}")
        return "\n".join(lines) + ("\n" if lines else "")
    raise ValueError(f"Unknown format: {fmt}")


def _esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace(",", "\\,").replace("=", "\\=").replace(" ", "\\ ")
