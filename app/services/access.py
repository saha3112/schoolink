"""Which classes / sections / subjects may the logged in user work with."""
from .. import db


def subject_pairs(user):
    """(classId, sectionId) pairs where the user can enter subject marks."""
    if user["is_admin"]:
        return db.query("SELECT DISTINCT class_id AS classId, section_id AS sectionId FROM assign_subject WHERE isDelete='0'")
    return db.query("SELECT DISTINCT classId, sectionId FROM assign_teacher WHERE t_id=%s AND isDelete='0'", (user["id"],))


def class_pairs(user):
    """(classId, sectionId) pairs where the user is class teacher (admin: every section)."""
    if user["is_admin"]:
        return db.query("SELECT s.class_id AS classId, s.sectionId FROM sections s JOIN classes c ON c.classId=s.class_id "
                        "WHERE s.isDelete='0' AND c.isDelete='0'")
    return db.query("SELECT DISTINCT classId, sectionId FROM classTeacher WHERE teacherId=%s AND isDelete='0'", (user["id"],))


def classes_for(pairs):
    ids = sorted({p["classId"] for p in pairs})
    if not ids:
        return []
    return db.query(f"SELECT classId, class_name FROM classes WHERE isDelete='0' AND classId IN ({','.join(['%s'] * len(ids))}) ORDER BY classId", ids)


def sections_for(pairs, cid):
    ids = sorted({p["sectionId"] for p in pairs if p["classId"] == cid})
    if not ids or not cid:
        return []
    return db.query(f"SELECT sectionId, section_name FROM sections WHERE isDelete='0' AND class_id=%s AND sectionId IN ({','.join(['%s'] * len(ids))}) ORDER BY section_name", [cid] + ids)


def exams():
    return db.query("SELECT examId, exam_name FROM exams WHERE isDelete='0' ORDER BY examId")


def students(cid, sid):
    return db.query("SELECT studentId, student_name, student_rollNumber FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0' "
                    "ORDER BY student_rollNumber, student_name", (cid, sid))


def allowed_subjects(user, cid, sid, special=False):
    """Subjects of the section the user may mark. Ordered by the class serial number (classSubject_slNo)."""
    flag = "1" if special else "0"
    if user["is_admin"]:
        sql = ("SELECT DISTINCT sb.subjectId, sb.subject_name, CAST(sl.slNo AS UNSIGNED) AS sl FROM assign_subject a "
               "JOIN subjects sb ON sb.subjectId=a.subject_id "
               "LEFT JOIN classSubject_slNo sl ON sl.classId=a.class_id AND sl.sectionId=a.section_id AND sl.subjectId=sb.subjectId "
               "WHERE a.class_id=%s AND a.section_id=%s AND a.isDelete='0' AND a.isSpecialSubject=%s AND sb.isDelete='0' "
               "ORDER BY sl IS NULL, sl, sb.subject_name")
        return db.query(sql, (cid, sid, flag))
    sql = ("SELECT DISTINCT sb.subjectId, sb.subject_name, CAST(sl.slNo AS UNSIGNED) AS sl FROM assign_teacher t "
           "JOIN subjects sb ON sb.subjectId=t.subjectId "
           "JOIN assign_subject a ON a.subject_id=t.subjectId AND a.class_id=t.classId AND a.section_id=t.sectionId "
           "AND a.isDelete='0' AND a.isSpecialSubject=%s "
           "LEFT JOIN classSubject_slNo sl ON sl.classId=t.classId AND sl.sectionId=t.sectionId AND sl.subjectId=sb.subjectId "
           "WHERE t.classId=%s AND t.sectionId=%s AND t.t_id=%s AND t.isDelete='0' AND sb.isDelete='0' "
           "ORDER BY sl IS NULL, sl, sb.subject_name")
    return db.query(sql, (flag, cid, sid, user["id"]))


def subtypes(cid, sid, exam_id, subject_id):
    return db.query("SELECT x.id AS subtype_id, x.exam_type AS name, a.fullmarsks AS fullmarks FROM assign_exam_subtype a "
                    "JOIN exam_subtype x ON x.id=a.exam_subtype_id "
                    "WHERE a.classId=%s AND a.sectionId=%s AND a.examId=%s AND a.subjectId=%s AND a.isDelete='0' AND x.isDelete='0' "
                    "ORDER BY CAST(a.fullmarsks AS UNSIGNED), x.id", (cid, sid, exam_id, subject_id))


def editing_enabled():
    return db.scalar("SELECT setting_value FROM system_settings WHERE setting_key='marks_entry_editing_enabled'", None, "1") != "0"


def exams_for(cid, sid):
    """Exams that have at least one exam sub-type configured for the section."""
    if not (cid and sid):
        return exams()
    return db.query("SELECT DISTINCT e.examId, e.exam_name FROM exams e JOIN assign_exam_subtype a ON a.examId=e.examId "
                    "WHERE e.isDelete='0' AND a.isDelete='0' AND a.classId=%s AND a.sectionId=%s ORDER BY e.examId", (str(cid), str(sid)))


def autopick(pairs, classes, cls, sec, exam, exams_list=None):
    """Default the selection when there is only one choice (a teacher with a single class / section / exam).
    Returns (cls, sec, exam, sections)."""
    from flask import has_request_context,request,abort
    posting=has_request_context() and request.method=='POST'
    if cls and cls not in [row['classId'] for row in classes]:
        if posting:abort(403)
        cls=None
    if not cls and len(classes) == 1:
        cls = classes[0]["classId"]
    sections = sections_for(pairs, cls) if cls else []
    if sec and sec not in [x["sectionId"] for x in sections]:
        if posting:abort(403)
        sec = None
    if not sec and len(sections) == 1:
        sec = sections[0]["sectionId"]
    if exams_list is None and cls and sec:
        exams_list = exams_for(cls, sec)
    if exam and exams_list is not None and exam not in [row['examId'] for row in exams_list]:
        if posting:abort(403)
        exam=None
    if not exam and exams_list is not None and len(exams_list) == 1:
        exam = exams_list[0]["examId"]
    return cls, sec, exam, sections
