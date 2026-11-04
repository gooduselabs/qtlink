# Contributing to QTLink
Thanks for helping! Issues and pull requests are welcome in English or Vietnamese.

## Dev setup
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q          # all tests must pass
python -m qtlink demo        # try it at http://localhost:8080
```

## Guidelines
- Keep it small: QTLink is an edge datalogger, not a SCADA. Prefer the standard library and few dependencies; it must run on a Raspberry Pi.
- Every change needs a test. Network sinks are tested against local servers (see `tests/test_sinks.py`).
- Never put secrets in configs or tests; use `password_env` / `token_env`.
- Update `CHANGELOG.md` under an "Unreleased" heading.

## Adding a sink (transport)
1. Add a module in `qtlink/sinks/` with a function `(dest: dict, local_path: str)` that **raises on failure** and returns only when the receiver has accepted the data.
2. Register the protocol in `qtlink/sinks/__init__.py` (`PROTOCOLS`, `DEFAULT_FORMAT`, `send`).
3. Add required-field checks in `qtlink/config.py` and tests. The store-and-forward queue is handled for you.

## Adding an output format
Add it to `qtlink/formats.py` (`FORMATS`, `EXT`, `CONTENT_TYPE`, `render`) with a test.

## Adding a device register map
Create `devices/<vendor>_<model>.yaml`:
```yaml
manufacturer: Vendor
model: Model
source: https://link-to-the-public-manual.pdf     # required
defaults: {function: input, data_type: float32, word_order: big}
points:
  voltage: {register: 0, unit: V, name: Voltage}   # 0-based PDU address; comment the manual's number
```
Rules: **only include registers you verified in a public manual, and cite it** (`source:` and comments). Use 0-based addresses and note the manual's numbering (e.g. `# 30001`). If you are not sure about an address, leave it out.

## AI-assisted contributions
AI-assisted code is fine; please say so in the PR and make sure you have read, run and tested it.
