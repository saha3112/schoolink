"""Live numbers for the admin / super-admin dashboard (all read from the database)."""
from .. import db


def _pct(done, total):
    return round(100.0 * done / total) if total else 0


def exams():
    return db.query("SELECT examId, exam_name FROM exams WHERE isDelete='0' ORDER BY examId")


def class_bars(exam_id):
    """Per class: student count + % of (section, subject) marks sheets that already have marks."""
    rows = db.query("""
        SELECT c.classId, c.class_name,
               (SELECT COUNT(*) FROM students s WHERE s.class_id=c.classId AND s.isDelete='0') students
        FROM classes c WHERE c.isDelete='0' ORDER BY c.classId""")
    prog = {r["classId"]: r for r in db.query("""
        SELECT a.classId, COUNT(*) total, SUM(m.classId IS NOT NULL) done
        FROM (SELECT DISTINCT classId, sectionId, subjectId FROM assign_exam WHERE isDelete='0' AND examId=%s) a
        LEFT JOIN (SELECT DISTINCT classId, sectionId, subjectId FROM exam_marks WHERE isDelete='0' AND examId=%s) m
               ON m.classId=a.classId AND m.sectionId=a.sectionId AND m.subjectId=a.subjectId
        GROUP BY a.classId""", (exam_id, exam_id))}
    out = []
    for r in rows:
        p = prog.get(r["classId"])
        out.append({"label": r["class_name"], "students": int(r["students"] or 0),
                    "entry": _pct(int(p["done"] or 0), int(p["total"])) if p else 0})
    return out


def progress(exam_id):
    me_total, me_done = db.one("""
        SELECT COUNT(*) t, COALESCE(SUM(m.classId IS NOT NULL),0) d
        FROM (SELECT DISTINCT classId, sectionId, subjectId FROM assign_exam WHERE isDelete='0' AND examId=%s) a
        LEFT JOIN (SELECT DISTINCT classId, sectionId, subjectId FROM exam_marks WHERE isDelete='0' AND examId=%s) m
               ON m.classId=a.classId AND m.sectionId=a.sectionId AND m.subjectId=a.subjectId""",
                               (exam_id, exam_id)).values()
    ta_total, ta_done = db.one("""
        SELECT COUNT(*) t, COALESCE(SUM(t.classId IS NOT NULL),0) d
        FROM (SELECT DISTINCT class_id, section_id, subject_id FROM assign_subject WHERE isDelete='0') s
        LEFT JOIN (SELECT DISTINCT classId, sectionId, subjectId FROM assign_teacher WHERE isDelete='0') t
               ON t.classId=s.class_id AND t.sectionId=s.section_id AND t.subjectId=s.subject_id""").values()
    ct_total, ct_done = db.one("""
        SELECT COUNT(*) t, COALESCE(SUM(t.classId IS NOT NULL),0) d
        FROM (SELECT DISTINCT class_id, section_id FROM students WHERE isDelete='0') x
        LEFT JOIN (SELECT DISTINCT classId, sectionId FROM classTeacher WHERE isDelete='0') t
               ON t.classId=x.class_id AND t.sectionId=x.section_id""").values()
    st_total = db.scalar("SELECT COUNT(*) FROM students WHERE isDelete='0'") or 0
    cm_done = db.scalar("""SELECT COUNT(DISTINCT studentId) FROM studentComment WHERE examId=%s AND isDelete='0'
                           AND comment IS NOT NULL AND TRIM(comment)<>''""", (exam_id,)) or 0
    pl = db.scalar("SELECT COUNT(*) FROM students WHERE isDelete='0' AND parent_id IS NOT NULL AND parent_id>0") or 0
    items = [
        ("Marks entry", _pct(int(me_done), int(me_total)), "#7366ed", f"{int(me_done)} of {int(me_total)} sheets"),
        ("Teacher assignments", _pct(int(ta_done), int(ta_total)), "#f4b15f", f"{int(ta_done)} of {int(ta_total)} subjects"),
        ("Class teachers set", _pct(int(ct_done), int(ct_total)), "#44bea5", f"{int(ct_done)} of {int(ct_total)} sections"),
        ("Report comments", _pct(cm_done, st_total), "#ed83a2", f"{cm_done} of {st_total} students"),
        ("Parents linked", _pct(pl, st_total), "#5aa9e6", f"{pl} of {st_total} students"),
    ]
    return [{"label": a, "pct": b, "color": c, "note": d} for a, b, c, d in items]


def counts():
    q = lambda sql: db.scalar(sql) or 0
    return [
        ("Classes", q("SELECT COUNT(*) FROM classes WHERE isDelete='0'"), "layers", "Across all grades"),
        ("Students", q("SELECT COUNT(*) FROM students WHERE isDelete='0'"), "users", "Active enrolments"),
        ("Teachers", q("SELECT COUNT(*) FROM teachers WHERE deleted_at IS NULL"), "file-text", "Faculty members"),
        ("Subjects", q("SELECT COUNT(*) FROM subjects WHERE isDelete='0'"), "clipboard", "Academic curriculum"),
    ]


def activity(limit=6):
    ev = []
    for r in db.query("""SELECT t.action, t.created_at, s.student_name, c.class_name cf, sf.section_name sf_, c2.class_name ct, st.section_name st_
        FROM student_transfer_log t LEFT JOIN students s ON s.studentId=t.studentId
        LEFT JOIN classes c ON c.classId=t.from_class LEFT JOIN sections sf ON sf.sectionId=t.from_section
        LEFT JOIN classes c2 ON c2.classId=t.to_class LEFT JOIN sections st ON st.sectionId=t.to_section
        ORDER BY t.created_at DESC LIMIT 5"""):
        ev.append((r["created_at"], "users", f"{r['student_name'] or 'Student'} {('moved' if r['action']=='move' else r['action'] or 'updated')}",
                   f"{r['cf'] or ''}-{r['sf_'] or ''} → {r['ct'] or ''}-{r['st_'] or ''}"))
    for r in db.query("""SELECT l.status, l.created_at, s.student_name FROM sl_leave l LEFT JOIN students s ON s.studentId=l.studentId
                         ORDER BY l.created_at DESC LIMIT 5"""):
        ev.append((r["created_at"], "calendar", f"Leave request ({r['status']})", r["student_name"] or ""))
    for r in db.query("SELECT title, created_at FROM sl_announcement WHERE deleted=0 ORDER BY created_at DESC LIMIT 5"):
        ev.append((r["created_at"], "bell", "Announcement posted", r["title"]))
    for r in db.query("SELECT documentName, createdAt FROM releaseResult ORDER BY createdAt DESC LIMIT 5"):
        ev.append((r["createdAt"], "file-text", "Report card generated", r["documentName"]))
    ev = [e for e in ev if e[0]]
    ev.sort(key=lambda e: e[0], reverse=True)
    return [{"when": e[0], "icon": e[1], "title": e[2], "desc": e[3]} for e in ev[:limit]]


def highlights(exam_id):
    ex = db.scalar("SELECT COUNT(*) FROM exams WHERE isDelete='0'") or 0
    sec = db.scalar("SELECT COUNT(DISTINCT class_id, section_id) FROM students WHERE isDelete='0'") or 0
    rel = db.scalar("SELECT COUNT(*) FROM releaseResult WHERE isOpen='1'") or 0
    gen = db.scalar("SELECT COUNT(*) FROM releaseResult") or 0
    pending = db.scalar("SELECT COUNT(*) FROM sl_leave WHERE status='pending'") or 0
    return {"sections": sec, "exams": ex, "released": rel, "generated": gen, "leave_pending": pending}


def all_for(exam_id):
    from .. import cache
    return cache.get(("dash.all_for", exam_id), lambda: {"counts": counts(), "bars": class_bars(exam_id), "progress": progress(exam_id),
                                                         "activity": activity(), "hl": highlights(exam_id)}, 30)
