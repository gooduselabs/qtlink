"""SQLite: số đo, tệp, hàng đợi gửi (mỗi tệp x mỗi đích), cảnh báo."""
from __future__ import annotations
import sqlite3
import threading
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings(ts TEXT, param TEXT, value REAL, status TEXT);
CREATE INDEX IF NOT EXISTS ix_readings ON readings(param, ts);
CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, name TEXT UNIQUE, path TEXT, data_time TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS uploads(id INTEGER PRIMARY KEY, file_id INTEGER, dest TEXT, status TEXT DEFAULT 'pending',
  attempts INTEGER DEFAULT 0, last_error TEXT, last_try TEXT, sent_at TEXT, UNIQUE(file_id, dest));
CREATE TABLE IF NOT EXISTS alarms(id INTEGER PRIMARY KEY, ts TEXT, level TEXT, kind TEXT, message TEXT);
"""


class DB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.executescript(SCHEMA)

    def q(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return [dict(r) for r in cur.fetchall()]

    # readings
    def add_reading(self, ts: datetime, param, value, status):
        self.q("INSERT INTO readings VALUES(?,?,?,?)", (ts.isoformat(timespec="seconds"), param, value, status))

    def readings_between(self, start: datetime, end: datetime):
        return self.q("SELECT * FROM readings WHERE ts>? AND ts<=? ORDER BY ts", (start.isoformat(), end.isoformat()))

    def trend(self, param, since: datetime):
        return self.q("SELECT ts,value,status FROM readings WHERE param=? AND ts>=? ORDER BY ts", (param, since.isoformat()))

    # files & queue
    def add_file(self, name, path, data_time: datetime, dests: list[str]) -> int:
        with self.lock:
            cur = self.conn.execute("INSERT OR IGNORE INTO files(name,path,data_time,created) VALUES(?,?,?,?)",
                                    (name, path, data_time.isoformat(), datetime.now().isoformat(timespec="seconds")))
            fid = cur.lastrowid or self.conn.execute("SELECT id FROM files WHERE name=?", (name,)).fetchone()[0]
            for d in dests:
                self.conn.execute("INSERT OR IGNORE INTO uploads(file_id,dest) VALUES(?,?)", (fid, d))
            self.conn.commit()
            return fid

    def pending(self, dest: str, limit=200):
        """Tệp chưa gửi, theo thứ tự thời gian dữ liệu (gửi bù cũ trước)."""
        return self.q("""SELECT u.id, u.attempts, f.name, f.path, f.data_time FROM uploads u JOIN files f ON f.id=u.file_id
                         WHERE u.dest=? AND u.status!='sent' ORDER BY f.data_time LIMIT ?""", (dest, limit))

    def mark(self, upload_id, ok: bool, err: str | None = None):
        now = datetime.now().isoformat(timespec="seconds")
        if ok:
            self.q("UPDATE uploads SET status='sent', attempts=attempts+1, sent_at=?, last_try=?, last_error=NULL WHERE id=?",
                   (now, now, upload_id))
        else:
            self.q("UPDATE uploads SET status='failed', attempts=attempts+1, last_try=?, last_error=? WHERE id=?",
                   (now, (err or "")[:300], upload_id))

    def last_success(self, dest: str):
        r = self.q("SELECT MAX(sent_at) m FROM uploads WHERE dest=? AND status='sent'", (dest,))
        return r[0]["m"]

    def upload_log(self, limit=100):
        return self.q("""SELECT f.name, u.dest, u.status, u.attempts, u.last_error, u.last_try, u.sent_at
                         FROM uploads u JOIN files f ON f.id=u.file_id ORDER BY f.data_time DESC, u.dest LIMIT ?""", (limit,))

    def queue_stats(self):
        return self.q("SELECT dest, SUM(status='sent') sent, SUM(status!='sent') pending FROM uploads GROUP BY dest")

    # alarms
    def alarm(self, level, kind, message):
        self.q("INSERT INTO alarms(ts,level,kind,message) VALUES(?,?,?,?)",
               (datetime.now().isoformat(timespec="seconds"), level, kind, message))

    def alarms(self, limit=50):
        return self.q("SELECT * FROM alarms ORDER BY id DESC LIMIT ?", (limit,))

    def cleanup(self, before: datetime):
        b = before.isoformat()
        self.q("DELETE FROM readings WHERE ts<?", (b,))
        self.q("DELETE FROM uploads WHERE file_id IN (SELECT id FROM files WHERE data_time<?)", (b,))
        self.q("DELETE FROM files WHERE data_time<?", (b,))
        self.q("DELETE FROM alarms WHERE ts<?", (b,))
