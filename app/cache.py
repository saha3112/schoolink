"""Shared read cache that can never serve data older than the last change.

How it stays correct
  * every cached value is stamped with the "data version" it was read under;
  * the version is bumped whenever anything is written (every successful POST / PUT / PATCH / DELETE - saving marks, adding or
    editing records, moving something to Trash, restoring, deleting permanently, changing permissions ...);
  * the bump is also written to the database (table sl_data_version), so a second server process or any other writer is noticed
    within CHECK_EVERY seconds;
  * every entry also expires on its own (TTL), so even a change made directly in the database shows up after at most a minute.
Values are handed out as copies, so a caller can edit what it receives without damaging the cache."""
import copy
import threading
import time

from flask import has_app_context

from . import db

CHECK_EVERY = 1.0          # seconds between looks at the database version
MAX_ENTRIES = 4000

_lock = threading.RLock()
_store = {}                # key -> (stamp, expires_at, value)
_local = [0]               # bumps done by this process
_dbv = {"v": 0, "t": 0.0, "ready": False}
stats = {"hits": 0, "misses": 0, "bumps": 0}


def _ensure():
    if _dbv["ready"]:
        return
    db.execute("CREATE TABLE IF NOT EXISTS sl_data_version (id TINYINT PRIMARY KEY, v BIGINT NOT NULL DEFAULT 0, "
               "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB")
    db.execute("INSERT IGNORE INTO sl_data_version (id, v) VALUES (1, 0)")
    _dbv["ready"] = True


def _db_version(force=False):
    """Version number kept in the database (shared by every process). Looked at most once per CHECK_EVERY seconds."""
    now = time.time()
    if not force and now - _dbv["t"] < CHECK_EVERY:
        return _dbv["v"]
    if not has_app_context():
        return _dbv["v"]
    try:
        _ensure()
        v = db.scalar("SELECT v FROM sl_data_version WHERE id=1")
        _dbv["v"], _dbv["t"] = int(v or 0), now
    except Exception:
        _dbv["t"] = now                      # database hiccup: keep the last known value, try again shortly
    return _dbv["v"]


def stamp():
    return (_local[0], _db_version())


def bump(reason=""):
    """Something was written: every cached value is now out of date."""
    with _lock:
        _local[0] += 1
        _store.clear()
        stats["bumps"] += 1
    if has_app_context():
        try:
            _ensure()
            db.execute("UPDATE sl_data_version SET v=v+1 WHERE id=1")
            _db_version(force=True)
        except Exception:
            pass


def get(key, loader, ttl=60, copy_result=True):
    """Cached value for key; loader() runs only when it is missing, expired or the data version moved on."""
    st, now = stamp(), time.time()
    with _lock:
        hit = _store.get(key)
    if hit and hit[0] == st and hit[1] > now:
        stats["hits"] += 1
        return copy.deepcopy(hit[2]) if copy_result else hit[2]
    stats["misses"] += 1
    value = loader()
    with _lock:
        if len(_store) >= MAX_ENTRIES:
            for k in sorted(_store, key=lambda x: _store[x][1])[: MAX_ENTRIES // 4]:
                _store.pop(k, None)
        _store[key] = (st, now + ttl, value)
    return copy.deepcopy(value) if copy_result else value


def clear():
    with _lock:
        _store.clear()
