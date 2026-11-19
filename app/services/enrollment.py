"""Which students do NOT take a subject of their section (optional / stream subjects).

Stored in `student_subject_exclusion` (additive table, created on first use). A student is enrolled in every subject of
the section unless a row says otherwise, so existing data keeps working unchanged."""
from .. import db

_ready = False


def ensure():
    global _ready
    if _ready:
        return
    db.execute("""CREATE TABLE IF NOT EXISTS student_subject_exclusion (
        id INT AUTO_INCREMENT PRIMARY KEY, studentId INT NOT NULL, subjectId INT NOT NULL, classId INT NOT NULL, sectionId INT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE KEY uq_student_subject (studentId, subjectId), KEY idx_section (classId, sectionId))""")
    _ready = True


def excluded(cid, sid):
    ensure()
    return {(r["studentId"], r["subjectId"]) for r in db.query(
        "SELECT studentId, subjectId FROM student_subject_exclusion WHERE classId=%s AND sectionId=%s", (cid, sid))}


def save(cid, sid, enrolled):
    """enrolled: set of (studentId, subjectId) that ARE taken. Everything else of the section becomes an exclusion."""
    ensure()
    studs = [r["studentId"] for r in db.query("SELECT studentId FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (cid, sid))]
    subs = [r["subject_id"] for r in db.query("SELECT DISTINCT subject_id FROM assign_subject WHERE class_id=%s AND section_id=%s AND isDelete='0'", (cid, sid))]
    db.execute("DELETE FROM student_subject_exclusion WHERE classId=%s AND sectionId=%s", (cid, sid), commit=False)
    n = 0
    for st in studs:
        for sb in subs:
            if (st, sb) not in enrolled:
                db.execute("INSERT INTO student_subject_exclusion (studentId, subjectId, classId, sectionId) VALUES (%s,%s,%s,%s)", (st, sb, cid, sid), commit=False)
                n += 1
    db.commit()
    return n


def detect(cid, sid):
    """Suggest exclusions: a subject that some students have marks for while other students have none at all."""
    studs = [r["studentId"] for r in db.query("SELECT studentId FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (cid, sid))]
    if not studs:
        return set()
    ph = ",".join(["%s"] * len(studs))
    have = {}
    for r in db.query(f"SELECT DISTINCT subjectId, studentId FROM exam_marks WHERE isDelete='0' AND studentId IN ({ph})", studs):
        have.setdefault(r["subjectId"], set()).add(r["studentId"])
    out = set()
    for sb in [r["subject_id"] for r in db.query("SELECT DISTINCT subject_id FROM assign_subject WHERE class_id=%s AND section_id=%s AND isDelete='0'", (cid, sid))]:
        h = have.get(sb, set())
        if h and len(h) < len(studs) and len(h) >= max(2, int(0.25 * len(studs))):   # clearly an optional subject, not just unfinished entry
            out |= {(st, sb) for st in studs if st not in h}
    return out


def forget_student(student_id):
    ensure()
    db.execute("DELETE FROM student_subject_exclusion WHERE studentId=%s", (student_id,), commit=False)
