"""In-app notifications (bell in the top bar)."""
from .. import db

_ready = False


def ensure():
    global _ready
    if _ready:
        return
    db.execute("""CREATE TABLE IF NOT EXISTS sl_notification (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, title VARCHAR(200) NOT NULL, body VARCHAR(500) NULL,
        link VARCHAR(255) NULL, is_read TINYINT NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, KEY (user_id, id))""")
    _ready = True


def notify(user_ids, title, body="", link=None, exclude=None):
    """Create one notification for every user id (duplicates and `exclude` skipped)."""
    ensure()
    ids = {int(u) for u in user_ids if u} - ({int(exclude)} if exclude else set())
    for uid in ids:
        db.execute("INSERT INTO sl_notification (user_id, title, body, link) VALUES (%s,%s,%s,%s)", (uid, title[:200], (body or "")[:500], link), commit=False)
    if ids:
        db.commit()
    return len(ids)


def staff_ids():
    """Every active admin / super admin / teacher."""
    return [r["id"] for r in db.query("SELECT id FROM new_users WHERE deleted_at IS NULL AND active='1' AND user_type IN ('0','1','2','9')")]


def admin_ids():
    return [r["id"] for r in db.query("SELECT id FROM new_users WHERE deleted_at IS NULL AND active='1' AND user_type IN ('0','1','9')")]


def section_staff(class_id, section_id=None):
    """Teachers (subject or class teacher) of a class / section plus all admins."""
    q = ("SELECT DISTINCT t_id AS u FROM assign_teacher WHERE isDelete='0' AND classId=%s" + (" AND sectionId=%s" if section_id else "") +
         " UNION SELECT DISTINCT teacherId FROM classTeacher WHERE isDelete='0' AND classId=%s" + (" AND sectionId=%s" if section_id else ""))
    args = [class_id] + ([section_id] if section_id else []) + [class_id] + ([section_id] if section_id else [])
    return [r["u"] for r in db.query(q, args)] + admin_ids()


def for_user(uid, limit=60):
    ensure()
    return db.query("SELECT id, title, body, link, is_read, DATE_FORMAT(created_at,'%%d %%b, %%H:%%i') AS at FROM sl_notification WHERE user_id=%s ORDER BY id DESC LIMIT %s", (uid, limit))


def unread(uid):
    ensure()
    return db.scalar("SELECT COUNT(*) FROM sl_notification WHERE user_id=%s AND is_read=0", (uid,)) or 0
