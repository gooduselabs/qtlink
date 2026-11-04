# Changelog
All notable changes to this project are documented here. Format: [Keep a Changelog](https://keepachangelog.com/), versioning: [SemVer](https://semver.org/).

## [0.2.0] - 2026-11-04
Repositioned as a general-purpose **lightweight Modbus edge datalogger with store-and-forward**; the Vietnam TT10/2021 format is now one output profile.

### Added
- Pluggable output formats: `csv`, `json`, `influx` (line protocol) next to `tt10_txt`.
- New sinks: `mqtt` (paho-mqtt, QoS 1, TLS, auth), `http` (webhook POST, Bearer/Basic, custom headers), `influxdb` (v2 write API or v1 `db`).
- All sinks share the SQLite store-and-forward queue (one entry per file × sink, oldest first, no duplicates, per-sink failure isolation).
- Device register-map library `devices/*.yaml` with cited sources: Eastron SDM120, Eastron SDM630, Schneider PM5xxx (basic), generic SunSpec inverter (model 103 int+SF). Devices can reference `template:`; tags can use `point:`; `points: [..] | all` auto-creates tags.
- SunSpec-style `scale_register` (value × 10^SF).
- English demo config (`config.demo.yaml`, "Demo Wastewater Plant") with sFTP/TT10 + FTP/CSV + HTTP/JSON sinks; local HTTP test receiver.
- `config.example.yaml` for energy meters → MQTT/InfluxDB/HTTP/sFTP.
- Tests for formats, config, device templates, HTTP/InfluxDB (local HTTP server), MQTT (local amqtt broker) and queue behaviour (35 tests).
- GitHub Actions CI, CONTRIBUTING.md, this changelog, AI-assistance note, architecture diagram.

### Changed
- Default dashboard language is English for new installs (`logger.language`, VI toggle kept and remembered).
- README is English first, Vietnamese second.
- `sinks:` accepted as an alias of `destinations:`; `type:` as alias of `protocol:`.
- `station.province` / `station.facility` are only required when a `tt10_txt` sink is configured.
- Default container timezone is UTC (set `TZ=Asia/Ho_Chi_Minh` for the TT10 profile).
- Vietnamese demo moved to `config.demo.vi.yaml`, TT10 production example to `config.example.tt10.yaml`.
- `qtlink.uploader` moved to `qtlink.sinks` (a compatibility shim remains).

### Compatibility
- v0.1 configs load unchanged: FTP/FTPS/sFTP destinations default to `format: tt10_txt`, file names and remote folders are identical.

## [0.1.0] - 2026-11-04
- First release: Modbus TCP/RTU → TT10/2021 Appendix XV `.txt` files → FTP/FTPS/sFTP with resend queue, alarms, 60-day retention, bilingual SCADA-style dashboard, simulator and test servers.
