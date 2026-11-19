"""Uploaded files / images live in the database (no upload folders on disk).

Tables (additive, created on first use):
  app_files          current files, addressed by a logical path such as  signature/teacher/NAME.png
  app_file_history   earlier versions (tag = which signature) so a replace / remove can always be undone
"""
import hashlib
import mimetypes
import os

from .. import db

_ready = False


def ensure():
    global _ready
    if _ready:
        return
    db.execute("""CREATE TABLE IF NOT EXISTS app_files (
        id INT AUTO_INCREMENT PRIMARY KEY, path VARCHAR(255) NOT NULL, mime VARCHAR(80) NOT NULL, size INT NOT NULL, sha1 CHAR(40) NOT NULL,
        data LONGBLOB NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, updated_by INT NULL,
        UNIQUE KEY uq_path (path)) ENGINE=InnoDB""")
    db.execute("""CREATE TABLE IF NOT EXISTS app_file_history (
        id INT AUTO_INCREMENT PRIMARY KEY, tag VARCHAR(80) NOT NULL, path VARCHAR(255) NOT NULL, mime VARCHAR(80) NOT NULL, size INT NOT NULL,
        data LONGBLOB NOT NULL, archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, archived_by INT NULL, KEY idx_tag (tag)) ENGINE=InnoDB""")
    _ready = True


def _mime(path, data=None):
    if data and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def put(path, data, user_id=None):
    ensure()
    db.execute("INSERT INTO app_files (path, mime, size, sha1, data, updated_by) VALUES (%s,%s,%s,%s,%s,%s) "
               "ON DUPLICATE KEY UPDATE mime=VALUES(mime), size=VALUES(size), sha1=VALUES(sha1), data=VALUES(data), updated_by=VALUES(updated_by)",
               (path, _mime(path, data), len(data), hashlib.sha1(data).hexdigest(), data, user_id))


def get(path):
    """-> dict(path, mime, data, updated_at, sha1) or None"""
    ensure()
    return db.one("SELECT path, mime, data, size, sha1, updated_at FROM app_files WHERE path=%s", (path,))


def exists(path):
    ensure()
    return db.one("SELECT 1 AS x FROM app_files WHERE path=%s", (path,)) is not None


def version(path):
    """Version stamp of a stored file (used to refresh browser copies). Cached; any upload / removal clears it."""
    from .. import cache

    def load():
        ensure()
        r = db.one("SELECT UNIX_TIMESTAMP(updated_at) AS v FROM app_files WHERE path=%s", (path,))
        return int(r["v"]) if r else None
    return cache.get(("filestore.version", path), load, 300)


def delete(path):
    ensure()
    db.execute("DELETE FROM app_files WHERE path=%s", (path,))


def archive(tag, path, user_id=None):
    """Copy the current file of `path` into history (keeps the live row)."""
    ensure()
    f = get(path)
    if f:
        db.execute("INSERT INTO app_file_history (tag, path, mime, size, data, archived_by) VALUES (%s,%s,%s,%s,%s,%s)",
                   (tag, path, f["mime"], f["size"], f["data"], user_id))
        return True
    return False


def history(tag, limit=6):
    ensure()
    return db.query("SELECT id, DATE_FORMAT(archived_at,'%%Y-%%m-%%d %%H:%%i') AS `when` FROM app_file_history WHERE tag=%s ORDER BY id DESC LIMIT %s", (tag, limit))


def history_get(hid, tag):
    ensure()
    return db.one("SELECT id, tag, path, mime, size, data FROM app_file_history WHERE id=%s AND tag=%s", (hid, tag))


def import_folder(folder, prefix):
    """One-off migration: copy every file below `folder` into the database under `prefix/...` (skips existing)."""
    ensure()
    n = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        for fn in files:
            full = os.path.join(root, fn)
            rel = prefix + "/" + os.path.relpath(full, folder).replace(os.sep, "/")
            if not exists(rel):
                with open(full, "rb") as fh:
                    put(rel, fh.read())
                n += 1
    return n
