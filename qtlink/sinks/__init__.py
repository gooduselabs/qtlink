"""Pluggable sinks (transports). Each sink takes (dest, local_path, remote_dir) and raises on failure.

All sinks are fed by the same SQLite store-and-forward queue (see db.py / engine.upload_pending):
items are sent oldest-first, marked 'sent' only after the sink returns, and a failing sink stops
for that round so ordering is preserved.
"""
from __future__ import annotations

from .files import upload_ftp, upload_sftp, password  # noqa: F401

FILE_PROTOCOLS = ("ftp", "ftps", "sftp")
PROTOCOLS = FILE_PROTOCOLS + ("mqtt", "http", "influxdb")
DEFAULT_FORMAT = {"ftp": "tt10_txt", "ftps": "tt10_txt", "sftp": "tt10_txt",
                  "mqtt": "json", "http": "json", "influxdb": "influx"}


def send(dest: dict, local_path: str, remote_dir: str = ""):
    p = dest["protocol"]
    if p in ("ftp", "ftps"):
        upload_ftp(dest, local_path, remote_dir)
    elif p == "sftp":
        upload_sftp(dest, local_path, remote_dir)
    elif p == "mqtt":
        from .mqtt import publish
        publish(dest, local_path)
    elif p == "http":
        from .http import post
        post(dest, local_path)
    elif p == "influxdb":
        from .http import influx_write
        influx_write(dest, local_path)
    else:
        raise ValueError(f"Unsupported protocol: {p}")


upload = send  # backward-compatible name
