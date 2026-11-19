"""Data builders for the tabulation sheet, weighted average sheet and report card.

This is a line by line port of the old CodeIgniter code (Marks::tabulationSheetV2, ::weightedAverageSheet,
::juniorWeightedSheet, ::showReportCardV2 and the MarksModel helpers) so that every figure matches the old output.
The structures are plain python dicts/lists here; the transpiled views receive them wrapped as PHP style arrays.
"""
import functools
import json
import os

from .. import db
from ..phpr import (_cmp, f_round, to_int, to_str, f_trim, is_numeric_str, f_is_numeric, wrap, f_strtoupper)

from . import layouts

SPECIAL_PERCENT_SUBJECTS = [
    "COMP.APPL/TECH.DRG.APPL./PHYSICAL EDU./ECO.APPL.", "ROBOTICS", "ROBOTICS / AI", "ROBOTICS AND AI",
]
_SPECIAL_UP = [s.upper() for s in SPECIAL_PERCENT_SUBJECTS]


# --------------------------------------------------------------------------------------------- model helpers
def subject_group(class_id, section_id, weighted=False):
    """MarksModel::getSubjectGroup - the group set is chosen by the class/section layout rule (Admin > Report layouts)."""
    return layouts.get_group(layouts.subject_group_key(class_id, section_id), weighted)


def students_v2(cid, sid):
    return db.query(
        "select students.studentId, students.student_name, students.student_id, students.ADMNO, students.student_rollNumber, "
        "students.studentUID, students.DOB, students.class_id, students.section_id, classes.class_name, sections.section_name "
        "FROM students, classes, sections WHERE students.class_id = classes.classId AND students.section_id = sections.sectionId "
        "AND students.class_id = %s AND section_id = %s AND students.isDelete = '0'  ORDER BY students.student_rollNumber", (cid, sid))


def class_teacher(cid, sid):
    return db.query("SELECT CONCAT(teachers.fname,' ',teachers.mname,' ',teachers.lname) as classTeacher, signature "
                    "FROM teachers , classTeacher WHERE teachers.user_id = classTeacher.teacherId AND classTeacher.classId = %s "
                    "AND classTeacher.sectionId = %s", (cid, sid))


def class_name(cid):
    r = db.query("SELECT class_name FROM classes WHERE classId = %s", (cid,))
    return r[0]["class_name"] if r else None


def section_name(cid, sid):
    r = db.query("SELECT section_name FROM sections WHERE class_id = %s AND sectionId = %s", (cid, sid))
    return r[0]["section_name"] if r else None


def exam_v2(exam_id):
    r = db.query("SELECT exam_name, examId FROM exams WHERE isDelete = '0' AND examId = %s", (exam_id,))
    return r[0]["exam_name"] if r else None


def class_strength(cid, sid):
    return db.scalar("SELECT COUNT(*) AS strength FROM students WHERE class_id = %s AND section_id = %s AND isDelete = '0'", (cid, sid))


def subjects_v2(cid, sid):
    return db.query("SELECT subjects.subject_name, subjects.subjectId FROM subjects , assign_subject WHERE subjects.subjectId = "
                    "assign_subject.subject_id AND assign_subject.class_id = %s AND assign_subject.section_id = %s "
                    "AND assign_subject.isDelete = '0' ", (cid, sid))


def subtypes_v2(cid, sid, exam_id, subject_id, memo=None):
    """MarksModel::getSubTypeDetailsV2 (fresh dict copies; optional per-request memo)."""
    key = (cid, sid, exam_id, subject_id)
    if memo is not None and key in memo:
        return [dict(r) for r in memo[key]]
    rows = db.query(
        "SELECT exam_subtype.exam_type, exam_subtype.id, MIN(assign_exam_subtype.fullmarsks) AS fullmarsks FROM exam_subtype "
        "JOIN assign_exam_subtype ON assign_exam_subtype.exam_subtype_id = exam_subtype.id WHERE assign_exam_subtype.classId = %s "
        "AND assign_exam_subtype.sectionId = %s AND assign_exam_subtype.examId = %s AND assign_exam_subtype.subjectId = %s "
        "AND assign_exam_subtype.isDelete = '0' AND exam_subtype.isDelete = '0' GROUP BY exam_subtype.id, exam_subtype.exam_type "
        "ORDER BY fullmarsks, exam_subtype.id", (cid, sid, exam_id, subject_id))
    if memo is not None:
        memo[key] = rows
    return [dict(r) for r in rows]


class MarksCache:
    """Preloads exam_marks of the given students so thousands of getStudentMarks_mod() calls cost one query."""

    def __init__(self, student_ids):
        self.m = {}
        if student_ids:
            ph = ",".join(["%s"] * len(student_ids))
            for r in db.query(f"SELECT studentId, subjectId, examId, exam_subtype_id, marks FROM exam_marks "
                              f"WHERE isDelete='0' AND studentId IN ({ph}) ORDER BY id", list(student_ids)):
                self.m.setdefault((r["studentId"], r["subjectId"], r["examId"], r["exam_subtype_id"]), r["marks"])

    def get(self, student, subject, exam, subtype):
        """MarksModel::getStudentMarks_mod  ('-' when nothing is stored)"""
        try:
            return self.m[(int(student), int(subject), int(exam), int(subtype))]
        except (KeyError, ValueError, TypeError):
            return "-"


def normalize_marker(raw):
    """Marks::normalizeMarksMarker"""
    s = to_str(raw).strip()
    if s.upper() in ("AB", "ABSENT"):
        return "AB"
    return s


def _num(v):
    v = to_str(v).strip()
    return v != "" and v != "N/A" and f_is_numeric(v)


def _special_percent(subtypes):
    """Full-marks weighted percentage used by the special subjects (see Marks::tabulationSheetV2)."""
    total_marks = total_full = 0
    any_entered = False
    for sub in subtypes:
        fm = sub.get("fullmarsks")
        total_full += to_int(fm) if fm is not None else 0
        val = to_str(sub.get("marks_obtained")).strip()
        if val != "" and val != "N/A" and f_is_numeric(val):
            total_marks += to_int(val)
            any_entered = True
    if any_entered and total_full > 0:
        return f_round((total_marks / total_full) * 100)
    return None


def _is_special(name):
    return to_str(name).strip().upper() in _SPECIAL_UP


# --------------------------------------------------------------------------------------------- tabulation sheet
def tabulation_sheet(class_id, section_id, exam_id):
    """Marks::tabulationSheetV2  -> (view name, {'finalData': ...})"""
    cid, sid, eid = int(class_id), int(section_id), int(exam_id)
    junior = layouts.is_junior(cid, sid)
    final = {}
    students = students_v2(cid, sid)
    final["classTeacher"] = (class_teacher(cid, sid) or [{}])[0].get("classTeacher")
    final["className"] = class_name(cid)
    final["sectionName"] = section_name(cid, sid)
    final["examDetails"] = exam_v2(eid)
    st = class_strength(cid, sid)
    final["classStrenth"] = st if st is not None else "N/A"

    groups = subject_group(cid, sid)
    final["groupLabels"] = layouts.group_labels(groups)
    cache = MarksCache([s["studentId"] for s in students])
    subj_cache, memo = {}, {}

    for student in students:
        cd = db.query("SELECT totalSession, attendSession, `rank`, comment FROM studentComment WHERE classId = %s AND sectionId = %s "
                      "AND examId = %s AND studentId = %s AND isDelete = '0'", (cid, sid, eid, student["studentId"]))
        if cd:
            student["totalSession"], student["attendSession"] = cd[0]["totalSession"], cd[0]["attendSession"]
            student["rank"], student["comment"] = cd[0]["rank"], cd[0]["comment"]
        else:
            student["totalSession"] = student["attendSession"] = student["rank"] = student["comment"] = ""

        key = (student["class_id"], student["section_id"])
        if key not in subj_cache:
            subj_cache[key] = subjects_v2(*key)
        subjects = subj_cache[key]

        grouped = {}
        for gname, gcfg in groups.items():
            slist = gcfg["subjects"]
            grouped[gname] = {"subjects": [], "avgPercent": 0, "color": gcfg["color"], "partition": gcfg["partition"]}
            subj_sum, subj_count, matched = 0, 0, False
            for subject in subjects:
                if subject["subject_name"] not in slist:
                    continue
                matched = True
                subject = dict(subject)
                if gname != "MISC & 3rd LANG":
                    stp = subtypes_v2(student["class_id"], student["section_id"], eid, subject["subjectId"], memo)
                    subject["examSubType"] = stp if stp else [{"exam_type": "", "id": "", "fullmarsks": "", "marks_obtained": ""}]
                else:
                    subject["examSubType"] = [{"exam_type": "WRITTEN", "id": "2", "fullmarsks": "80", "marks_obtained": ""}]
                subject_total, has_valid = 0, False
                for idx, sub in enumerate(subject["examSubType"]):
                    sub = dict(sub)
                    subject["examSubType"][idx] = sub
                    raw = to_str(cache.get(student["studentId"], subject["subjectId"], eid, sub["id"])).strip()
                    if gname in ("MISC & 3rd LANG", "GRADED"):
                        sub["marks_obtained"] = "N/A" if raw in ("", "-") else normalize_marker(raw)
                    else:
                        if raw in ("", "-"):
                            sub["marks_obtained"] = "N/A"
                        elif not f_is_numeric(raw):
                            sub["marks_obtained"] = normalize_marker(raw)
                        else:
                            n = to_int(raw)
                            sub["marks_obtained"] = n
                            subject_total += n
                            has_valid = True
                if _is_special(subject["subject_name"]):
                    p = _special_percent(subject["examSubType"])
                    if p is not None:
                        subject_total, has_valid = p, True
                if has_valid:
                    subj_sum += subject_total
                    subj_count += 1
                grouped[gname]["subjects"].append(subject)
            if not matched:
                for name in slist:
                    grouped[gname]["subjects"].append({"subject_name": name, "examSubType": [{"marks_obtained": "N/A"}]})
            if gcfg["calculateAvg"] and subj_count > 0:
                grouped[gname]["avgPercent"] = f_round(subj_sum / subj_count)

        # ---- SUMMARY
        total_summary, total_subjects = 0, 0
        for gname, gcfg in groups.items():
            if gname in ("SUMMARY", "MISC & 3rd LANG", "MISC & GRADED", "ATTENDANCE", "GRADED"):
                continue
            if (gcfg["calculateAvg"] or gname == "SCIENCE") and (not junior):
                value = grouped[gname]["avgPercent"]
                if value > 0:
                    total_summary += value
                    total_subjects += 1
                else:
                    for subj in grouped[gname]["subjects"]:
                        subject_total, has_valid = 0, False
                        if _is_special(subj["subject_name"]):
                            p = _special_percent(subj["examSubType"])
                            if p is not None:
                                subject_total, has_valid = p, True
                        else:
                            for stp in subj["examSubType"]:
                                if _num(stp.get("marks_obtained")):
                                    subject_total += _intval(stp["marks_obtained"])
                                    has_valid = True
                        if has_valid:
                            total_summary += subject_total
                            total_subjects += 1
            else:
                if junior:
                    for subj in grouped[gname]["subjects"]:
                        subject_total, has_valid = 0, False
                        for stp in subj["examSubType"]:
                            if _num(stp.get("marks_obtained")):
                                subject_total += _intval(stp["marks_obtained"])
                                has_valid = True
                        if has_valid:
                            total_summary += subject_total
                            total_subjects += 1
                else:
                    group_total, has_valid = 0, False
                    for subj in grouped[gname]["subjects"]:
                        if _is_special(subj["subject_name"]):
                            p = _special_percent(subj["examSubType"])
                            if p is not None:
                                group_total += p
                                has_valid = True
                        else:
                            for stp in subj["examSubType"]:
                                if _num(stp.get("marks_obtained")):
                                    group_total += _intval(stp["marks_obtained"])
                                    has_valid = True
                    if has_valid:
                        total_summary += group_total
                        total_subjects += 1

        percent_summary = f_round(total_summary / total_subjects) if total_subjects > 0 else 0
        summ = grouped["SUMMARY"]["subjects"]
        summ[0]["examSubType"][0]["marks_obtained"] = total_summary
        summ[1]["examSubType"][0]["marks_obtained"] = percent_summary
        summ[2]["examSubType"][0]["marks_obtained"] = ""
        student["calculated_total"] = total_summary
        student["calculated_percentage"] = percent_summary
        student["groupedSubjects"] = grouped

    if junior:
        for student in students:
            h = db.one("SELECT houseName, housePoints FROM student_house WHERE studentId=%s AND examId=%s AND isDelete='0' ORDER BY id DESC LIMIT 1",
                       (student["studentId"], eid))
            student["houseName"] = h["houseName"] if h else ""
            student["housePoints"] = h["housePoints"] if h else ""
        copy = sorted(students, key=functools.cmp_to_key(
            lambda a, b: (_cmp(b["calculated_total"], a["calculated_total"]) if a["calculated_percentage"] == b["calculated_percentage"]
                          else _cmp(b["calculated_percentage"], a["calculated_percentage"]))))
        ranks = {sc["studentId"]: i for i, sc in enumerate(copy, 1)}
        for student in students:
            r = ranks.get(student["studentId"], "")
            student["rank"] = r
            student["groupedSubjects"]["SUMMARY"]["subjects"][2]["examSubType"][0]["marks_obtained"] = r

    final["studentDetails"] = students
    # processStudentGrades: sort each subject's sub-types by full marks (stable, loose comparison)
    for student in students:
        for gname, grp in student["groupedSubjects"].items():
            for subject in grp["subjects"]:
                subject["examSubType"] = sorted(subject["examSubType"], key=functools.cmp_to_key(
                    lambda a, b: _cmp(a.get("fullmarsks", 0), b.get("fullmarsks", 0))))
    view = "junior_sheet" if junior else "sheet"
    return view, {"finalData": wrap(final)}


def _intval(v):
    """(int)$value for a mark that is either int or a numeric string"""
    return to_int(v)


# --------------------------------------------------------------------------------------------- weighted average
def weighted_sheet(class_id, section_id):
    """Marks::weightedAverageSheet"""
    cid, sid = int(class_id), int(section_id)
    final = {}
    students = students_v2(cid, sid)
    final["classTeacher"] = (class_teacher(cid, sid) or [{}])[0].get("classTeacher")
    final["className"] = class_name(cid)
    final["sectionName"] = section_name(cid, sid)
    exams = db.query("SELECT examId, exam_name FROM exams WHERE isDelete = '0'")
    final["examDetails"] = exams
    groups = subject_group(cid, sid, weighted=True)
    final["groupLabels"] = layouts.group_labels(groups)
    cache = MarksCache([s["studentId"] for s in students])
    subj_cache, memo = {}, {}
    for student in students:
        key = (student["class_id"], student["section_id"])
        if key not in subj_cache:
            subj_cache[key] = subjects_v2(*key)
        subjects = subj_cache[key]
        grouped = {}
        for gname, gcfg in groups.items():
            slist = gcfg["subjects"]
            grouped[gname] = {"subjects": [], "avgPercent": 0, "color": gcfg["color"], "partition": gcfg["partition"]}
            subj_sum, subj_count, matched = 0, 0, False
            for subject in subjects:
                if subject["subject_name"] not in slist:
                    continue
                matched = True
                subject = dict(subject)
                subject["exams"] = {}
                for exam in exams:
                    exam_id = exam["examId"]
                    if gname != "MISC & 3rd LANG":
                        stp = subtypes_v2(student["class_id"], student["section_id"], exam_id, subject["subjectId"], memo)
                        est = stp if stp else [{"exam_type": "", "id": "", "fullmarsks": "", "marks_obtained": ""}]
                    else:
                        est = [{"exam_type": "WRITTEN", "id": "2", "fullmarsks": "80", "marks_obtained": ""}]
                    est = [dict(x) for x in est]
                    subject_total, has_valid = 0, False
                    for sub in est:
                        raw = to_str(cache.get(student["studentId"], subject["subjectId"], exam_id, sub["id"])).strip()
                        if gname == "MISC & 3rd LANG":
                            sub["marks_obtained"] = "N/A" if raw == "" else raw
                        else:
                            if raw == "" or not f_is_numeric(raw):
                                sub["marks_obtained"] = "N/A"
                            else:
                                n = to_int(raw)
                                sub["marks_obtained"] = n
                                subject_total += n
                                has_valid = True
                    if _is_special(subject["subject_name"]):
                        p = _special_percent(est)
                        if p is not None:
                            subject_total, has_valid = p, True
                    subject["exams"][exam_id] = {"exam_name": exam["exam_name"], "examSubType": est, "total": subject_total}
                    if has_valid:
                        subj_sum += subject_total
                        subj_count += 1
                grouped[gname]["subjects"].append(subject)
            if not matched:
                for name in slist:
                    grouped[gname]["subjects"].append({"subject_name": name, "exams": {}})
            if subj_count > 0:
                grouped[gname]["avgPercent"] = f_round(subj_sum / subj_count)
        student["groupedSubjects"] = grouped
    final["studentDetails"] = students
    return "weighted_sheet", {"finalData": wrap(final)}


def junior_weighted_sheet(class_id, section_id, exam_id):
    """Marks::juniorWeightedSheet"""
    cid, sid, eid = int(class_id), int(section_id), int(exam_id)
    students = db.query("SELECT studentId, student_name, student_id, student_rollNumber FROM students WHERE class_id=%s AND section_id=%s "
                        "AND isDelete='0' ORDER BY student_rollNumber, student_name", (cid, sid))
    subjects = db.query("SELECT DISTINCT subjects.subjectId, subjects.subject_name FROM assign_subject JOIN subjects ON "
                        "assign_subject.subject_id = subjects.subjectId WHERE assign_subject.class_id=%s AND assign_subject.section_id=%s "
                        "AND assign_subject.isDelete='0' ORDER BY subjects.subject_name", (cid, sid))
    for s in subjects:
        s["subtypes"] = db.query("SELECT exam_subtype.id, exam_subtype.exam_type, assign_exam_subtype.fullmarsks FROM assign_exam_subtype "
                                 "JOIN exam_subtype ON assign_exam_subtype.exam_subtype_id = exam_subtype.id WHERE assign_exam_subtype.classId=%s "
                                 "AND assign_exam_subtype.sectionId=%s AND assign_exam_subtype.examId=%s AND assign_exam_subtype.subjectId=%s "
                                 "AND assign_exam_subtype.isDelete='0' ORDER BY exam_subtype.id", (cid, sid, eid, s["subjectId"]))
    cache = MarksCache([s["studentId"] for s in students])
    for st in students:
        st["totalMarks"], st["totalFullMarks"], st["weightedMarks"] = 0, 0, {}
        for sub in subjects:
            total = full = 0
            for stp in sub["subtypes"]:
                mark = cache.get(st["studentId"], sub["subjectId"], eid, stp["id"])
                if f_is_numeric(mark):
                    total += float(mark)
                    full += float(stp["fullmarsks"])
            st["weightedMarks"][sub["subjectId"]] = {"marks": total, "fullmarks": full, "percent": f_round((total / full) * 100, 2) if full > 0 else 0}
            st["totalMarks"] += total
            st["totalFullMarks"] += full
        st["percentage"] = f_round((st["totalMarks"] / st["totalFullMarks"]) * 100, 2) if st["totalFullMarks"] > 0 else 0
        h = db.one("SELECT houseName, housePoints FROM student_house WHERE studentId=%s AND examId=%s AND isDelete='0' ORDER BY id DESC LIMIT 1", (st["studentId"], eid))
        st["houseName"] = h["houseName"] if h else ""
        st["housePoints"] = h["housePoints"] if h else ""
    students.sort(key=functools.cmp_to_key(lambda a, b: 0 if a["percentage"] == b["percentage"] else (-1 if a["percentage"] > b["percentage"] else 1)))
    for i, st in enumerate(students, 1):
        st["rank"] = i
    final = {
        "className": class_name(cid) or "", "sectionName": section_name(cid, sid) or "", "examDetails": exam_v2(eid) or "",
        "classTeacher": (class_teacher(cid, sid) or [{}])[0].get("classTeacher") or "", "students": students, "subjects": subjects,
    }
    return "junior_weighted_sheet", {"finalData": wrap(final)}
