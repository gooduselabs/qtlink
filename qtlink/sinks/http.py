"""HTTP sinks: generic webhook POST and InfluxDB line-protocol write (v2 API, or v1 when `db` is set)."""
from __future__ import annotations
import os
import urllib.parse
import urllib.request

from .. import formats
from .files import password


def _do(url: str, body: bytes, headers: dict, timeout: float, verify: bool = True):
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    ctx = None
    if url.startswith("https") and not verify:
        import ssl
        ctx = ssl._create_unverified_context()  # noqa: S323 - explicit opt-out by config
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:  # raises HTTPError on 4xx/5xx
        if not 200 <= r.status < 300:
            raise IOError(f"HTTP {r.status}")


def post(dest: dict, local_path: str):
    with open(local_path, "rb") as f:
        body = f.read()
    headers = {"Content-Type": formats.CONTENT_TYPE.get(dest.get("format", "json"), "application/octet-stream"),
               "User-Agent": "QTLink", "X-QTLink-File": os.path.basename(local_path)}
    headers.update({str(k): str(v) for k, v in (dest.get("headers") or {}).items()})
    tok = os.environ.get(dest["token_env"], "") if dest.get("token_env") else dest.get("token")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    elif dest.get("username"):
        import base64
        headers["Authorization"] = "Basic " + base64.b64encode(f"{dest['username']}:{password(dest)}".encode()).decode()
    _do(dest["url"], body, headers, float(dest.get("timeout", 15)), dest.get("verify_tls", True))


def influx_write(dest: dict, local_path: str):
    with open(local_path, "rb") as f:
        body = f.read()
    if not body.strip():
        return
    base = dest["url"].rstrip("/")
    tok = os.environ.get(dest["token_env"], "") if dest.get("token_env") else dest.get("token", "")
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    if dest.get("db"):  # InfluxDB 1.x
        q = {"db": dest["db"], "precision": "s"}
        if dest.get("username"):
            q.update(u=dest["username"], p=password(dest))
        url = f"{base}/write?{urllib.parse.urlencode(q)}"
    else:  # InfluxDB 2.x / 3.x compatible v2 write API
        url = f"{base}/api/v2/write?{urllib.parse.urlencode({'org': dest.get('org', ''), 'bucket': dest['bucket'], 'precision': 's'})}"
        if tok:
            headers["Authorization"] = f"Token {tok}"
    _do(url, body, headers, float(dest.get("timeout", 15)), dest.get("verify_tls", True))
