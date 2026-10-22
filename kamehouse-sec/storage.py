"""Preferencias, contraseña e historial locales en SQLite."""
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Santiago")


class Store:
    def __init__(self, path, initial_password):
        self.lock = threading.RLock()
        self.error = None
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    kind TEXT NOT NULL, message TEXT NOT NULL, mode TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_mode_time ON events(mode, created_at DESC);
            """)
            if not self.db.execute("SELECT 1 FROM settings WHERE key='password'").fetchone():
                self._set("password", self._hash(initial_password))
            if not self.db.execute("SELECT 1 FROM settings WHERE key='name'").fetchone():
                self._set("name", "Mi casa")
                self._set("sound_enabled", False)

    def _set(self, key, value):
        self.db.execute("INSERT INTO settings(key,value) VALUES (?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value, ensure_ascii=False)))

    def _get(self, key):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _hash(password):
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 250000)
        return dict(salt=base64.b64encode(salt).decode(), digest=base64.b64encode(digest).decode())

    def verify_password(self, password):
        with self.lock:
            item = self._get("password")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(item["salt"]), 250000)
        return hmac.compare_digest(digest, base64.b64decode(item["digest"]))

    def change_password(self, password):
        encoded = self._hash(password)
        with self.lock, self.db:
            self._set("password", encoded)

    def preferences(self):
        with self.lock:
            return dict(name=self._get("name"), sound_enabled=bool(self._get("sound_enabled")))

    def save_preferences(self, name, sound_enabled):
        with self.lock, self.db:
            self._set("name", name)
            self._set("sound_enabled", sound_enabled)

    def add_event(self, kind, message, mode, event_id=None, created_at=None):
        created_at = created_at or datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with self.lock, self.db:
            self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)",
                            (event_id or uuid.uuid4().hex, created_at, kind, message, mode))

    @staticmethod
    def day_bounds(day):
        start = datetime.combine(day, time.min, tzinfo=TZ)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=TZ)
        return (start.astimezone(timezone.utc).isoformat(timespec="microseconds"),
                end.astimezone(timezone.utc).isoformat(timespec="microseconds"))

    def history(self, mode, kind="all", day=None, limit=20, offset=0):
        conditions, values = ["mode=?"], [mode]
        if kind != "all":
            conditions.append("kind=?")
            values.append(kind)
        if day:
            conditions.append("created_at>=? AND created_at<?")
            values.extend(self.day_bounds(day))
        clause = " AND ".join(conditions)
        with self.lock:
            total = self.db.execute(f"SELECT COUNT(*) FROM events WHERE {clause}", values).fetchone()[0]
            rows = self.db.execute(f"SELECT * FROM events WHERE {clause} "
                                   "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                                   values + [limit, offset]).fetchall()
            return dict(events=[dict(row) for row in rows], total=total, offset=offset, limit=limit)

    def statistics(self, mode):
        start, end = self.day_bounds(datetime.now(TZ).date())
        with self.lock:
            rows = self.db.execute("SELECT kind,COUNT(*) AS n FROM events "
                                   "WHERE mode=? AND created_at>=? AND created_at<? GROUP BY kind",
                                   (mode, start, end)).fetchall()
            counts = {row["kind"]: row["n"] for row in rows}
            last = self.db.execute("SELECT created_at FROM events WHERE mode=? AND kind='opened' "
                                   "ORDER BY created_at DESC LIMIT 1", (mode,)).fetchone()
            revision = self.db.execute("SELECT COUNT(*) FROM events WHERE mode=?", (mode,)).fetchone()[0]
            return dict(openings_today=counts.get("opened", 0), denied_today=counts.get("denied", 0),
                        last_entry=last[0] if last else None, revision=revision)

    def close(self):
        with self.lock:
            self.db.close()
