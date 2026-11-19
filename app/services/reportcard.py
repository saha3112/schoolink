"""Report card data (port of Marks::showReportCardV2 and its MarksModel / helper functions)."""
import functools

from .. import db
from . import layouts
from ..phpr import _cmp, f_round, f_is_numeric, to_str, wrap, add


def _first(rows, key, default=None):
    return rows[0][key] if rows else default


def _sorted(items, cmpfn):
    return sorted(items, key=functools.cmp_to_key(cmpfn))


def student_details(student_id):
    return db.query("select students.student_name, students.student_id, students.ADMNO, students.student_rollNumber, students.studentUID, "
                    "students.DOB, students.class_id, students.section_id, classes.class_name, sections.section_name FROM students, classes, "
                    "sections WHERE students.class_id = classes.classId AND students.section_id = sections.sectionId AND studentId = %s", (student_id,))


def parent_details(student_id):
    return db.query("SELECT CONCAT_WS(' ', parents.fname, parents.mname, parents.lname) AS parentName, parents.address, parents.phone_1 "
                    "FROM parents, students WHERE parents.id = students.parent_id AND students.studentId = %s", (student_id,))


def build(student_id, force_view=None):
    """-> (view_name, context dict) or None when the student does not exist."""
    sd = student_details(student_id)
    if not sd:
        return None
    s0 = sd[0]
    cid, sid = s0["class_id"], s0["section_id"]
    data = {"studentData": sd, "parentData": parent_details(student_id)}
    ct = db.query("SELECT CONCAT(teachers.fname,' ',teachers.mname,' ',teachers.lname) as classTeacher, signature FROM teachers , classTeacher "
                  "WHERE teachers.user_id = classTeacher.teacherId AND classTeacher.classId = %s AND classTeacher.sectionId = %s", (cid, sid))
    data["teacher"] = {"classTeachString": _first(ct, "classTeacher", ""), "signature": _first(ct, "signature", "")}

    exams = db.query("SELECT exam_name, examId FROM exams WHERE isDelete = '0' ")
    normal = db.query("SELECT subjects.subject_name, subjects.subjectId FROM subjects , assign_subject WHERE subjects.subjectId = assign_subject.subject_id "
                      "AND assign_subject.class_id = %s AND assign_subject.section_id = %s AND assign_subject.isSpecialSubject = '0' "
                      "AND assign_subject.isDelete = '0' ", (cid, sid))
    special = db.query("SELECT subjects.subject_name, subjects.subjectId FROM subjects , assign_subject WHERE subjects.subjectId = assign_subject.subject_id "
                       "AND assign_subject.class_id = %s AND assign_subject.section_id = %s AND assign_subject.isSpecialSubject = '1' "
                       "AND assign_subject.isDelete = '0'", (cid, sid))
    skills = db.query("SELECT id, skillName FROM developmentSkill WHERE classId = %s AND sectionId = %s AND isDelete = '0' ", (cid, sid))

    for ex in exams:
        ex["examSubtype"] = db.query(
            " SELECT exam_subtype.exam_type, exam_subtype.id, MIN(assign_exam_subtype.fullmarsks) AS fullmarsks FROM exam_subtype JOIN "
            "assign_exam_subtype ON assign_exam_subtype.exam_subtype_id = exam_subtype.id WHERE assign_exam_subtype.classId = %s AND "
            "assign_exam_subtype.sectionId = %s AND assign_exam_subtype.examId = %s AND assign_exam_subtype.isDelete = '0' AND "
            "exam_subtype.isDelete = '0' GROUP BY exam_subtype.id, exam_subtype.exam_type ORDER BY fullmarsks, exam_subtype.id",
            (cid, sid, ex["examId"]))

    # preload marks / grades
    marks = {}
    for r in db.query("SELECT subjectId, examId, exam_subtype_id, marks FROM exam_marks WHERE studentId=%s AND isDelete='0' ORDER BY id", (student_id,)):
        marks.setdefault((r["subjectId"], r["examId"], r["exam_subtype_id"]), r["marks"])
    grades = {}
    for r in db.query("SELECT subjectId, examId, marks FROM exam_marks_development WHERE studentId=%s AND isDelete='0' ORDER BY id", (student_id,)):
        grades.setdefault((r["subjectId"], r["examId"]), r["marks"])
    fullmarks = {}
    for r in db.query("SELECT subjectId, examId, exam_subtype_id, fullmarsks FROM assign_exam_subtype WHERE classId=%s AND sectionId=%s ORDER BY id", (str(cid), str(sid))):
        fullmarks.setdefault((int(r["subjectId"]), int(r["examId"]), int(r["exam_subtype_id"])), r["fullmarsks"])

    def structure(subjects, with_fullmarks):
        out = []
        for sub in subjects:
            exs = []
            for ex in exams:
                stps = []
                for stp in ex["examSubtype"]:
                    d = {"subtype_id": stp["id"], "subtype_name": stp["exam_type"], "full_marks": stp["fullmarsks"]}
                    if with_fullmarks:
                        d["full_marks"] = fullmarks.get((sub["subjectId"], ex["examId"], stp["id"]), 0)
                    d["marks_obtained"] = marks.get((sub["subjectId"], ex["examId"], stp["id"]), "-")
                    stps.append(d)
                exs.append({"exam_id": ex["examId"], "exam_name": ex["exam_name"], "subtypes": stps})
            out.append({"subject_id": sub["subjectId"], "subject_name": sub["subject_name"], "exams": exs})
        return out

    data["examDetails"] = exams
    data["normalSubject"] = structure(normal, True)
    data["specialSubject"] = structure(special, False)
    data["developmentSkill"] = [
        {"skill_id": k["id"], "skill_name": k["skillName"],
         "exams": [{"exam_id": ex["examId"], "exam_name": ex["exam_name"], "grade": grades.get((k["id"], ex["examId"]), "-")} for ex in exams]}
        for k in skills]
    data["rankAvarage"] = db.query("SELECT rankAvarage, award, promotion FROM rankAvarageOther WHERE studentId = %s ORDER BY id DESC LIMIT 1", (student_id,))

    attend = []
    for ex in exams:
        r = db.query("SELECT totalSession, attendSession, comment, `rank` FROM studentComment WHERE classId = %s AND sectionId = %s AND examId = %s "
                     "AND studentId = %s AND isDelete = '0' ORDER BY id DESC LIMIT 1", (cid, sid, ex["examId"], student_id))
        attend.append(r[0] if r else {"totalSession": 0, "attendSession": 0, "comment": "", "rank": "N/A"})
    data["AttendentData"] = attend

    for ex in data["examDetails"]:
        ex["totaMarks"], ex["subjectCount"] = 0, 0
    for sub in data["normalSubject"]:
        for key, ex in enumerate(sub["exams"]):
            has = False
            for stp in ex["subtypes"]:
                if f_is_numeric(stp["marks_obtained"]):
                    data["examDetails"][key]["totaMarks"] = add(data["examDetails"][key]["totaMarks"], stp["marks_obtained"])
                    has = True
            if has:
                data["examDetails"][key]["subjectCount"] += 1
    for ex in data["examDetails"]:
        avg = ex["totaMarks"] / ex["subjectCount"] if ex["subjectCount"] > 0 else None
        ex["avarage"] = "-" if avg is None else to_str(f_round(avg)) + "%"

    def slno(cls, sec, subject_id):
        r = db.query("SELECT slNo FROM classSubject_slNo WHERE classId = %s AND sectionId = %s AND subjectId = %s ", (cls, sec, subject_id))
        return r[0]["slNo"] if r else None

    def strength():
        n = db.scalar("SELECT COUNT(*) AS strength FROM students WHERE class_id = %s AND section_id = %s AND isDelete = '0' ", (cid, sid))
        return n if n is not None else "N/A"

    def w_rank():
        return db.query("SELECT w_rank FROM weighted_rank where classId = %s AND sectionId = %s AND studentId = %s ", (cid, sid, student_id))

    def sort_slno():
        data["normalSubject"] = _sorted(data["normalSubject"], lambda a, b: _cmp(a["slno"], b["slno"]))

    def prune_and_sort():
        for key in ("normalSubject", "specialSubject"):
            for sub in data[key]:
                for ex in sub["exams"]:
                    ex["subtypes"] = [s for s in ex["subtypes"] if not (s["marks_obtained"] == "-" and isinstance(s["marks_obtained"], str))]
        for sub in data["normalSubject"]:
            for ex in sub["exams"]:
                ex["subtypes"] = _sorted(ex["subtypes"], lambda a, b: _cmp(a["full_marks"], b["full_marks"]))

    def reorder_exact(order):
        remaining = list(data["normalSubject"])
        out = []
        for name in order:
            for i, sub in enumerate(remaining):
                if sub["subject_name"].strip() == name:
                    out.append(sub)
                    del remaining[i]
                    break
        data["normalSubject"] = out + remaining

    def move_after(names, after):
        to_move = [s for s in data["normalSubject"] if s["subject_name"].strip() in names]
        rest = [s for s in data["normalSubject"] if s["subject_name"].strip() not in names]
        if not to_move:
            return
        out, inserted = [], False
        for sub in rest:
            out.append(sub)
            if not inserted and sub["subject_name"].strip() == after:
                out.extend(to_move)
                inserted = True
        if not inserted:
            out.extend(to_move)
        data["normalSubject"] = out

    plan = layouts.card_plan(cid, sid)          # Admin > Report layouts
    if force_view:                              # design preview: use this design with the section's other settings
        plan = dict(plan or layouts.default_plan(), card_view=force_view)
    if plan is None:
        return None
    if plan["prune"]:
        prune_and_sort()
    if plan["slno_mode"] in ("class", "section"):
        slno_section = 0 if plan["slno_mode"] == "class" else sid
        for key in ("normalSubject", "specialSubject"):
            for sub in data[key]:
                sub["slno"] = slno(cid, slno_section, sub["subject_id"])
    if plan["reorder_exact"]:
        reorder_exact(plan["reorder_exact"])
    if plan["move_names"]:
        move_after(plan["move_names"], plan["move_after"])
    if plan["strength"]:
        data["classStrenth"] = strength()
    if plan["slno_mode"] in ("class", "section"):
        sort_slno()
    if plan["wrank"]:
        data["w_rank"] = w_rank()
    view = plan["card_view"]
    if view.startswith("custom:"):
        return view, data                       # custom designs are rendered from the plain dict (see services/carddesign.py)
    return view, wrap(data)
