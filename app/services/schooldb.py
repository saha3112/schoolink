"""Tables for the school-life modules (announcements, events, gallery, classwork/homework, daily attendance, timetable).
New, additive tables - the report card tables are untouched. Files are kept in the database (services/filestore)."""
import mimetypes
import re
import time

from .. import db
from . import filestore

_ready = False
ALLOWED = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "zip"}
IMAGES = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE = 8 * 1024 * 1024
MAX_FILES = 6


def ensure():
    global _ready
    if _ready:
        return
    stmts = [
        """CREATE TABLE IF NOT EXISTS sl_announcement (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(200) NOT NULL, body TEXT NOT NULL,
            classId INT NULL, sectionId INT NULL, created_by INT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, deleted TINYINT NOT NULL DEFAULT 0, KEY(classId, sectionId))""",
        """CREATE TABLE IF NOT EXISTS sl_event (id INT AUTO_INCREMENT PRIMARY KEY, kind ENUM('event','holiday') NOT NULL DEFAULT 'event', title VARCHAR(200) NOT NULL,
            description TEXT NULL, start_date DATE NOT NULL, end_date DATE NULL, created_by INT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, deleted TINYINT NOT NULL DEFAULT 0, KEY(start_date))""",
        """CREATE TABLE IF NOT EXISTS sl_album (id INT AUTO_INCREMENT PRIMARY KEY, title VARCHAR(200) NOT NULL, album_date DATE NULL, classId INT NULL, sectionId INT NULL,
            created_by INT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, deleted TINYINT NOT NULL DEFAULT 0)""",
        """CREATE TABLE IF NOT EXISTS sl_work (id INT AUTO_INCREMENT PRIMARY KEY, kind ENUM('classwork','homework') NOT NULL, classId INT NOT NULL, sectionId INT NOT NULL, subjectId INT NOT NULL,
            title VARCHAR(200) NOT NULL, body TEXT NULL, work_date DATE NOT NULL, due_date DATE NULL, created_by INT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted TINYINT NOT NULL DEFAULT 0, KEY(classId, sectionId, work_date))""",
        """CREATE TABLE IF NOT EXISTS sl_attachment (id INT AUTO_INCREMENT PRIMARY KEY, owner_type VARCHAR(20) NOT NULL, owner_id INT NOT NULL, path VARCHAR(255) NOT NULL,
            name VARCHAR(200) NOT NULL, is_image TINYINT NOT NULL DEFAULT 0, KEY(owner_type, owner_id))""",
        """CREATE TABLE IF NOT EXISTS sl_attendance (id INT AUTO_INCREMENT PRIMARY KEY, classId INT NOT NULL, sectionId INT NOT NULL, studentId INT NOT NULL, att_date DATE NOT NULL,
            status CHAR(1) NOT NULL, marked_by INT NOT NULL, UNIQUE KEY uq (studentId, att_date), KEY sec (classId, sectionId, att_date))""",
        """CREATE TABLE IF NOT EXISTS sl_timetable (id INT AUTO_INCREMENT PRIMARY KEY, classId INT NOT NULL, sectionId INT NOT NULL, weekday TINYINT NOT NULL, period TINYINT NOT NULL,
            subjectId INT NULL, teacherId INT NULL, start_time VARCHAR(5) NULL, end_time VARCHAR(5) NULL, UNIQUE KEY uq (classId, sectionId, weekday, period))""",
        """CREATE TABLE IF NOT EXISTS sl_leave (id INT AUTO_INCREMENT PRIMARY KEY, studentId INT NOT NULL, parent_user INT NOT NULL, from_date DATE NOT NULL, to_date DATE NOT NULL,
            reason VARCHAR(500) NOT NULL, status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending', decided_by INT NULL, decided_at TIMESTAMP NULL, note VARCHAR(300) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, KEY(studentId), KEY(status))""",
    ]
    for s in stmts:
        db.execute(s, commit=False)
    db.commit()
    _ready = True


def safe_name(name):
    name = re.sub(r"[^\w\.\- ]+", "_", (name or "file").strip().split("/")[-1].split("\\")[-1]) or "file"
    return name[-90:]


class _Picked:
    """A media-library item shaped like an uploaded file."""
    def __init__(self, name, data):
        self.filename, self._d = name, data

    def read(self, n=-1):
        return self._d


def save_attachments(owner_type, owner_id, files, user_id, media_ids=None):
    """Store attachments in the database. `files` = classic uploads, `media_ids` = items chosen in the media library
    (only ones the current user may see). Returns (saved, errors)."""
    ensure()
    saved, errors = 0, []
    if media_ids:
        from flask import session
        from . import media
        from ..auth import current_user
        u = current_user()
        files = list(files or []) + [_Picked(n, d) for n, _e, d in media.take(u, media_ids)] if u else list(files or [])
    have = db.scalar("SELECT COUNT(*) FROM sl_attachment WHERE owner_type=%s AND owner_id=%s", (owner_type, owner_id)) or 0
    for f in files:
        if not f or not f.filename:
            continue
        name = safe_name(f.filename)
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ALLOWED:
            errors.append(f"{name}: file type .{ext} is not allowed"); continue
        if have + saved >= MAX_FILES:
            errors.append(f"{name}: at most {MAX_FILES} files per post"); continue
        data = f.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            errors.append(f"{name}: larger than 8 MB"); continue
        if not data:
            continue
        path = f"uploads/{owner_type}/{owner_id}/{int(time.time() * 1000)}_{name}"
        filestore.put(path, data, user_id)
        db.execute("INSERT INTO sl_attachment (owner_type, owner_id, path, name, is_image) VALUES (%s,%s,%s,%s,%s)",
                   (owner_type, owner_id, path, name, 1 if ext in IMAGES else 0), commit=False)
        saved += 1
    db.commit()
    return saved, errors


def attachments(owner_type, ids):
    """{owner_id: [rows]}"""
    ensure()
    if not ids:
        return {}
    ph = ",".join(["%s"] * len(ids))
    out = {}
    for r in db.query(f"SELECT id, owner_id, path, name, is_image FROM sl_attachment WHERE owner_type=%s AND owner_id IN ({ph}) ORDER BY id", [owner_type] + list(ids)):
        out.setdefault(r["owner_id"], []).append(r)
    return out


def delete_attachments(owner_type, owner_id):
    ensure()
    for r in db.query("SELECT path FROM sl_attachment WHERE owner_type=%s AND owner_id=%s", (owner_type, owner_id)):
        filestore.delete(r["path"])
    db.execute("DELETE FROM sl_attachment WHERE owner_type=%s AND owner_id=%s", (owner_type, owner_id))
