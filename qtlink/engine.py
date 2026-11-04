"""Vòng lặp chính: đọc Modbus -> lưu -> tạo tệp TT10 -> hàng đợi gửi -> cảnh báo -> dọn dẹp."""
from __future__ import annotations
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta

from . import modbus_reader, tt10, uploader
from .db import DB

log = logging.getLogger("qtlink")


def floor_time(t: datetime, minutes: int) -> datetime:
    t = t.replace(second=0, microsecond=0)
    return t - timedelta(minutes=t.minute % minutes)


class Engine:
    def __init__(self, cfg: dict, reader=modbus_reader.read_device, upload=uploader.upload, now=datetime.now):
        self.cfg = cfg
        self.reader = reader
        self.upload_fn = upload
        self.now = now
        lg = cfg["logger"]
        os.makedirs(lg["outbox_dir"], exist_ok=True)
        os.makedirs(os.path.dirname(lg["db_path"]) or ".", exist_ok=True)
        self.db = DB(lg["db_path"])
        self.live: dict[str, dict] = {}
        self._limit_state: dict[str, str] = {}
        self._disc_warned: set[str] = set()
        self._dev_down: set[str] = set()
        self._last_slot = floor_time(self.now(), lg["file_interval_minutes"])
        self._stop = threading.Event()
        for w in tt10.validate_ids(cfg["station"]["province"], cfg["station"]["facility"],
                                   cfg["station"]["station"], lg["strict_names"]):
            log.warning("Cấu hình tên trạm: %s", w)

    # ---------- polling ----------
    def poll_once(self):
        ts = self.now().replace(microsecond=0)
        tags_by_dev = defaultdict(list)
        for t in self.cfg["tags"]:
            tags_by_dev[t["device"]].append(t)
        for dev in self.cfg["devices"]:
            tags = tags_by_dev.get(dev["name"], [])
            if not tags:
                continue
            res = self.reader(dev, tags)
            all_bad = all(not r["ok"] for r in res.values())
            self._edge(dev["name"] in self._dev_down, all_bad,
                       lambda: self._dev_down.add(dev["name"]) or self.db.alarm("warning", "device", f"Mất kết nối thiết bị {dev['name']}"),
                       lambda: self._dev_down.discard(dev["name"]) or self.db.alarm("info", "device", f"Thiết bị {dev['name']} kết nối lại"))
            for tag in tags:
                r = res[tag["param"]]
                status = tt10.STATUS_FAULT if not r["ok"] else (tt10.STATUS_CALIBRATING if r["calibrating"] else tt10.STATUS_MEASURING)
                self.db.add_reading(ts, tag["param"], r["value"], status)
                self.live[tag["param"]] = {"value": r["value"], "unit": tag["unit"], "status": status, "ts": ts.isoformat(),
                                           "low": tag.get("low"), "high": tag.get("high"), "name": tag.get("name", tag["param"])}
                if r["ok"] and r["value"] is not None:
                    self.check_limits(tag, r["value"])

    @staticmethod
    def _edge(was, now, on_set, on_clear):
        if now and not was:
            on_set()
        elif was and not now:
            on_clear()

    def check_limits(self, tag: dict, v: float):
        p = tag["param"]
        state = "ok"
        if tag.get("high") is not None and v > float(tag["high"]):
            state = "high"
        elif tag.get("low") is not None and v < float(tag["low"]):
            state = "low"
        prev = self._limit_state.get(p, "ok")
        if state != prev:
            if state == "ok":
                self.db.alarm("info", "limit", f"{p} trở lại bình thường ({v:.2f} {tag['unit']})")
            else:
                lim = tag["high"] if state == "high" else tag["low"]
                self.db.alarm("alarm", "limit", f"{p} = {v:.2f} {tag['unit']} {'vượt ngưỡng trên' if state=='high' else 'dưới ngưỡng'} {lim}")
        self._limit_state[p] = state

    # ---------- file building ----------
    def build_file(self, slot_end: datetime) -> str:
        lg = self.cfg["logger"]
        st = self.cfg["station"]
        start = slot_end - timedelta(minutes=lg["file_interval_minutes"])
        rows = self.db.readings_between(start, slot_end)
        by = defaultdict(list)
        for r in rows:
            by[r["param"]].append(r)
        recs = []
        for tag in self.cfg["tags"]:
            rs = by.get(tag["param"], [])
            good = [r for r in rs if r["status"] != tt10.STATUS_FAULT and r["value"] is not None]
            if not good:
                recs.append(tt10.Record(tag["param"], None, tag["unit"], slot_end, tt10.STATUS_FAULT))
                continue
            val = good[-1]["value"] if lg["aggregate"] == "last" else sum(r["value"] for r in good) / len(good)
            status = tt10.STATUS_CALIBRATING if any(r["status"] == tt10.STATUS_CALIBRATING for r in rs) else \
                (tt10.STATUS_FAULT if len(good) < len(rs) and lg.get("partial_fault", False) else tt10.STATUS_MEASURING)
            recs.append(tt10.Record(tag["param"], val, tag["unit"], slot_end, status))
        name = tt10.file_name(st["province"], st["facility"], st["station"], slot_end)
        day_dir = os.path.join(lg["outbox_dir"], f"{slot_end:%Y}", f"{slot_end:%m}", f"{slot_end:%d}")
        os.makedirs(day_dir, exist_ok=True)
        path = os.path.join(day_dir, name)
        nl = "\r\n" if lg["newline"] == "crlf" else "\n"
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(tt10.build_content(recs, lg["decimals"], nl))
        self.db.add_file(name, path, slot_end, [d["name"] for d in self.cfg["destinations"] if d.get("enabled", True)])
        log.info("Tạo tệp %s", name)
        return path

    def maybe_build(self):
        slot = floor_time(self.now(), self.cfg["logger"]["file_interval_minutes"])
        if slot > self._last_slot:
            self.build_file(slot)
            self._last_slot = slot

    # ---------- upload queue ----------
    def upload_pending(self):
        st = self.cfg["station"]
        for dest in self.cfg["destinations"]:
            if not dest.get("enabled", True):
                continue
            for item in self.db.pending(dest["name"]):
                if not os.path.exists(item["path"]):
                    self.db.mark(item["id"], False, "Tệp cục bộ không còn")
                    continue
                t = datetime.fromisoformat(item["data_time"])
                rdir = tt10.remote_dir(dest.get("remote_root", ""), dest.get("station_folder", st["station"]), t)
                try:
                    self.upload_fn(dest, item["path"], rdir)
                    self.db.mark(item["id"], True)
                except Exception as e:  # noqa: BLE001
                    self.db.mark(item["id"], False, f"{type(e).__name__}: {e}")
                    log.warning("Gửi %s tới %s lỗi: %s", item["name"], dest["name"], e)
                    break  # đích lỗi: dừng, thử lại vòng sau (giữ thứ tự thời gian)
            self.check_disconnect(dest["name"])

    def check_disconnect(self, dest_name: str):
        hours = float(self.cfg["logger"]["disconnect_warn_hours"])
        pend = self.db.pending(dest_name, 1)
        if not pend:
            if dest_name in self._disc_warned:
                self._disc_warned.discard(dest_name)
                self.db.alarm("info", "disconnect", f"Đã gửi bù xong tới {dest_name}")
            return
        oldest = datetime.fromisoformat(pend[0]["data_time"])
        if self.now() - oldest > timedelta(hours=hours) and dest_name not in self._disc_warned:
            self._disc_warned.add(dest_name)
            self.db.alarm("warning", "disconnect",
                          f"Gián đoạn truyền tới {dest_name} quá {hours:g} giờ (từ {oldest:%d/%m/%Y %H:%M}). "
                          "Theo Điều 39 TT10: phải thông báo bằng văn bản và email cho cơ quan tiếp nhận.")

    def cleanup(self):
        lg = self.cfg["logger"]
        cutoff = self.now() - timedelta(days=int(lg["retention_days"]))
        self.db.cleanup(cutoff)
        for root, _, files in os.walk(lg["outbox_dir"], topdown=False):
            for fn in files:
                p = os.path.join(root, fn)
                if datetime.fromtimestamp(os.path.getmtime(p)) < cutoff:
                    os.remove(p)
            if root != lg["outbox_dir"] and not os.listdir(root):
                os.rmdir(root)

    # ---------- threads ----------
    def start(self):
        threading.Thread(target=self._loop_poll, daemon=True).start()
        threading.Thread(target=self._loop_upload, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop_poll(self):
        last_clean = 0.0
        while not self._stop.is_set():
            try:
                self.poll_once()
                self.maybe_build()
                if time.time() - last_clean > 3600:
                    self.cleanup()
                    last_clean = time.time()
            except Exception:  # noqa: BLE001
                log.exception("Lỗi vòng đọc")
            self._stop.wait(self.cfg["logger"]["poll_seconds"])

    def _loop_upload(self):
        while not self._stop.is_set():
            try:
                self.upload_pending()
            except Exception:  # noqa: BLE001
                log.exception("Lỗi vòng gửi")
            self._stop.wait(self.cfg["logger"]["upload_seconds"])
