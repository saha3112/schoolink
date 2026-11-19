"""Media library: every uploaded file / image lives here first, in the database (services/filestore), and forms only ever
*pick* items from it.

Visibility:  admin / super admin see every file;  everybody else sees only the files they uploaded themselves.
Removing   : a removed file goes to Trash (nothing is lost); it can be restored.
Permanent delete: admin / super admin always; other users only when an administrator switched
                  "Allow staff to delete their own files permanently" on (Settings)."""
import hashlib
import io
import re
import time

from .. import db
from . import filestore

_ready = False
ALLOWED = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "zip"}      # CSV files are data imports, never kept in the library
IMAGES = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE = 8 * 1024 * 1024
MAX_BATCH = 20
SETTING_PURGE = "media_staff_purge"


def ensure():
    global _ready
    if _ready:
        return
    db.execute("""CREATE TABLE IF NOT EXISTS sl_media (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(200) NOT NULL, ext VARCHAR(10) NOT NULL DEFAULT '', mime VARCHAR(80) NOT NULL DEFAULT '',
        size INT NOT NULL DEFAULT 0, kind VARCHAR(10) NOT NULL DEFAULT 'file', path VARCHAR(255) NULL, thumb_path VARCHAR(255) NULL, sha1 CHAR(40) NULL,
        uploaded_by INT NOT NULL, uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, deleted_at TIMESTAMP NULL, deleted_by INT NULL,
        KEY (uploaded_by), KEY (deleted_at), KEY (kind)) ENGINE=InnoDB""")
    _ready = True


# --------------------------------------------------------------------------- settings / permissions
def staff_may_purge():
    return (db.scalar("SELECT setting_value FROM system_settings WHERE setting_key=%s", (SETTING_PURGE,)) or "0") == "1"


def set_staff_purge(on):
    if db.one("SELECT 1 FROM system_settings WHERE setting_key=%s", (SETTING_PURGE,)):
        db.execute("UPDATE system_settings SET setting_value=%s WHERE setting_key=%s", ("1" if on else "0", SETTING_PURGE))
    else:
        db.execute("INSERT INTO system_settings (setting_key, setting_value) VALUES (%s,%s)", (SETTING_PURGE, "1" if on else "0"))


def can_see(user, row):
    return bool(user["is_admin"] or row["uploaded_by"] == user["id"])


def can_purge(user, row, allow_staff=None):
    if user["is_admin"]:
        return True
    return row["uploaded_by"] == user["id"] and (staff_may_purge() if allow_staff is None else allow_staff)


# --------------------------------------------------------------------------- helpers
def safe_name(name):
    name = re.sub(r"[^\w\.\- ]+", "_", (name or "file").strip().split("/")[-1].split("\\")[-1]) or "file"
    return name[-90:]


def human(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return (f"{int(n)} {u}" if u == "B" else f"{n:.1f} {u}")
        n /= 1024


def _thumb(data):
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(data)); im.load()
        im = ImageOps.exif_transpose(im)
        im.thumbnail((420, 420))
        if im.mode not in ("RGB", "L"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
            im = bg
        out = io.BytesIO(); im.convert("RGB").save(out, "JPEG", quality=82, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def add(user, filename, data):
    """-> (row dict | None, error | None)"""
    ensure()
    name = safe_name(filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext == "csv":
        return None, f"{name}: CSV files are not kept in the library. Use “Import CSV” on the page where the data belongs - the file is deleted after the import."
    if ext not in ALLOWED:
        return None, f"{name}: .{ext or '?'} files are not allowed."
    if not data:
        return None, f"{name}: the file is empty."
    if len(data) > MAX_FILE:
        return None, f"{name}: larger than {MAX_FILE // (1024 * 1024)} MB."
    kind = "image" if ext in IMAGES else "file"
    if kind == "image" and not _looks_like_image(data):
        return None, f"{name}: this is not a valid image."
    mid = db.execute("INSERT INTO sl_media (name, ext, mime, size, kind, sha1, uploaded_by) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                     (name, ext, filestore._mime(name, data), len(data), kind, hashlib.sha1(data).hexdigest(), user["id"]))
    path = f"media/{mid}/{name}"
    filestore.put(path, data, user["id"])
    tpath = None
    if kind == "image":
        t = _thumb(data)
        if t:
            tpath = f"media/{mid}/thumb.jpg"
            filestore.put(tpath, t, user["id"])
    db.execute("UPDATE sl_media SET path=%s, thumb_path=%s WHERE id=%s", (path, tpath, mid))
    return get(mid), None


def _looks_like_image(data):
    return data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or data[:6] in (b"GIF87a", b"GIF89a") or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")


def get(mid):
    ensure()
    return db.one("SELECT m.*, u.fname AS uploader FROM sl_media m LEFT JOIN new_users u ON u.id=m.uploaded_by WHERE m.id=%s", (mid,))


def file_bytes(row, thumb=False):
    p = (row.get("thumb_path") if thumb else row.get("path")) or row.get("path")
    f = filestore.get(p) if p else None
    return f


def listing(user, tab="library", kind="all", q="", page=1, per=10, ids=None):
    ensure()
    where, args = [("m.deleted_at IS NOT NULL" if tab == "trash" else "m.deleted_at IS NULL")], []
    if not user["is_admin"]:
        where.append("m.uploaded_by=%s"); args.append(user["id"])
    if kind in ("image", "file"):
        where.append("m.kind=%s"); args.append(kind)
    if q:
        where.append("m.name LIKE %s"); args.append(f"%{q}%")
    if ids:
        where.append("m.id IN (%s)" % ",".join(["%s"] * len(ids))); args += list(ids)
    w = " AND ".join(where)
    total = db.scalar(f"SELECT COUNT(*) FROM sl_media m WHERE {w}", args) or 0
    pages = max(1, -(-total // per))
    page = min(max(1, page), pages)
    rows = db.query(f"SELECT m.id, m.name, m.ext, m.size, m.kind, m.uploaded_by, m.uploaded_at, m.deleted_at, u.fname AS uploader FROM sl_media m "
                    f"LEFT JOIN new_users u ON u.id=m.uploaded_by WHERE {w} ORDER BY COALESCE(m.deleted_at, m.uploaded_at) DESC, m.id DESC LIMIT %s OFFSET %s",
                    args + [per, (page - 1) * per])
    return rows, total, page, pages


def counts(user):
    ensure()
    w, a = ("", [])
    if not user["is_admin"]:
        w, a = (" AND uploaded_by=%s", [user["id"]])
    return (db.scalar("SELECT COUNT(*) FROM sl_media WHERE deleted_at IS NULL" + w, a) or 0,
            db.scalar("SELECT COUNT(*) FROM sl_media WHERE deleted_at IS NOT NULL" + w, a) or 0)


def remove(user, ids):
    done = 0
    for i in ids:
        r = get(i)
        if r and r["deleted_at"] is None and can_see(user, r):
            db.execute("UPDATE sl_media SET deleted_at=NOW(), deleted_by=%s WHERE id=%s", (user["id"], i), commit=False); done += 1
    db.commit()
    return done


def restore(user, ids):
    done = 0
    for i in ids:
        r = get(i)
        if r and r["deleted_at"] is not None and can_see(user, r):
            db.execute("UPDATE sl_media SET deleted_at=NULL, deleted_by=NULL WHERE id=%s", (i,), commit=False); done += 1
    db.commit()
    return done


def purge(user, ids):
    """-> (deleted, refused)"""
    done = refused = 0
    allow = staff_may_purge()
    for i in ids:
        r = get(i)
        if not r or r["deleted_at"] is None or not can_see(user, r):
            continue
        if not can_purge(user, r, allow):
            refused += 1; continue
        for p in (r["path"], r["thumb_path"]):
            if p:
                try:
                    filestore.delete(p)
                except Exception:
                    pass
        db.execute("DELETE FROM sl_media WHERE id=%s", (i,), commit=False); done += 1
    db.commit()
    return done, refused


def take(user, ids):
    """Chosen library items for a form -> [(name, ext, bytes)] (only what the user may see, never trashed ones)."""
    out = []
    for i in ids:
        try:
            r = get(int(i))
        except (TypeError, ValueError):
            continue
        if not r or r["deleted_at"] is not None or not can_see(user, r):
            continue
        f = file_bytes(r)
        if f:
            out.append((r["name"], r["ext"], f["data"]))
    return out
