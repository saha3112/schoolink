"""Subject teacher panel: marks entry, special subjects, marks list."""
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from .. import db
from ..auth import roles_required, current_user
from ..services import access, enrollment, features
from ..utils import to_int

bp = Blueprint("marks", __name__, url_prefix="/marks")
cap = roles_required("subject_teacher")

MARKERS = {"AB": "AB", "ABSENT": "AB", "NS": "NS", "NA": "NA"}
GRADE_RE = re.compile(r"^[A-E][+-]?$", re.I)


def parse_mark(raw, full):
    """-> (value_to_store, error). Accepts numbers within 0..full, AB/NS/NA markers and letter grades."""
    raw = raw.strip()
    if raw == "":
        return None, None
    if raw.upper() in MARKERS:
        return raw, None                        # stored as typed, exactly like the old application
    try:
        v = float(raw)
    except ValueError:
        if GRADE_RE.match(raw):
            return raw.upper(), None
        return None, f"'{raw}' is not valid (use a number, AB, NS, NA or a grade like A+)"
    if v < 0 or v > float(full or 0):
        return None, f"{raw} is outside 0–{full}"
    return (str(int(v)) if v == int(v) else str(v)), None


def upsert_mark(cid, sid, student, subject, exam, subtype, full, marks, teacher):
    db.execute("INSERT INTO exam_marks (classId, sectionId, studentId, subjectId, examId, exam_subtype_id, fullmarsks, marks, teacherId, isDelete) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'0') "
               "ON DUPLICATE KEY UPDATE marks=VALUES(marks), fullmarsks=VALUES(fullmarsks), teacherId=VALUES(teacherId)",
               (cid, sid, student, subject, exam, subtype, full, marks, teacher), commit=False)


def graded_ids(cls, sec, subjects):
    """Subjects entered as grades (A+, A, B …) rather than numbers: special subjects + every subject listed in a
    graded group of the section's subject-group set (Admin > Report setup > Subject groups)."""
    from ..services import layouts
    names = set()
    try:
        for gname, g in layouts.get_group(layouts.subject_group_key(cls, sec)).items():
            if layouts.group_role(gname) in ("graded", "misc_graded", "misc_lang"):
                names |= {x.strip().upper() for x in g.get("subjects", [])}
    except Exception:
        pass
    special = {r["subject_id"] for r in db.query("SELECT subject_id FROM assign_subject WHERE class_id=%s AND section_id=%s AND isSpecialSubject='1' AND isDelete='0'", (cls, sec))}
    return {s["subjectId"] for s in subjects if s["subjectId"] in special or s["subject_name"].strip().upper() in names}


def _ctx(user, feature="entry"):
    pairs=features.pairs(feature,user)
    cls,sec,exam=(to_int(request.values.get(k)) for k in ('class_id','section_id','exam_id'))
    classes=access.classes_for(pairs)
    if not user['is_admin']:
        if not pairs or not features.nav_allowed(user,request.endpoint):abort(403)
        if cls and cls not in {row['classId'] for row in pairs}:abort(403)
        if request.method=='POST' and (cls,sec) not in {(row['classId'],row['sectionId']) for row in pairs}:abort(403)
    # Class/section defaults must be resolved before choosing an eligible exam.
    cls,sec,_unused,sections=access.autopick(pairs,classes,cls,sec,None,[])
    exams=features.mark_exams(user,feature,cls,sec)
    if exam and exam not in {row['examId'] for row in exams}:
        if request.method=='POST':abort(403)
        exam=None
    if not exam and len(exams)==1:exam=exams[0]['examId']
    return pairs,cls,sec,exam,classes,sections,exams


@bp.route("/entry", methods=["GET", "POST"])
@cap
def entry():
    user = current_user()
    pairs, cls, sec, exam, classes, sections, exams = _ctx(user)
    subjects, students, existing, excl = [], [], {}, set()
    if cls and sec and exam:
        students = access.students(cls, sec)
        subjects = access.allowed_subjects(user, cls, sec)
        for s in subjects:
            s["subtypes"] = access.subtypes(cls, sec, exam, s["subjectId"])
        subjects = [s for s in subjects if s["subtypes"]]
        excl = enrollment.excluded(cls, sec)
        subjects = [s for s in subjects if any((stu["studentId"], s["subjectId"]) not in excl for stu in students)]
        if request.method == "POST":
            if not access.editing_enabled() and not user["is_admin"]:
                flash("Marks entry is currently switched off by the administrator.", "error")
                return redirect(request.url)
            errors, rows = [], []
            for s in subjects:
                for st in s["subtypes"]:
                    for stu in students:
                        if (stu["studentId"], s["subjectId"]) in excl:
                            continue
                        key = f"m_{s['subjectId']}_{st['subtype_id']}_{stu['studentId']}"
                        val, err = parse_mark(request.form.get(key, ""), st["fullmarks"])
                        if err:
                            errors.append(f"{stu['student_name']} · {s['subject_name']} ({st['name']}): {err}")
                        elif val is not None:
                            rows.append((stu["studentId"], s["subjectId"], st["subtype_id"], st["fullmarks"], val))
            if errors:
                for e in errors[:6]:
                    flash(e, "error")
                if len(errors) > 6:
                    flash(f"…and {len(errors) - 6} more problem(s). Nothing was saved.", "error")
                # re-show the typed values
                existing = {(stu["studentId"], s["subjectId"], st["subtype_id"]): request.form.get(f"m_{s['subjectId']}_{st['subtype_id']}_{stu['studentId']}", "")
                            for s in subjects for st in s["subtypes"] for stu in students}
                return render_template("marks_entry.html", pairs=pairs, cls=cls, sec=sec, exam=exam, classes=classes, sections=sections,
                                       exams=exams, subjects=subjects, students=students, existing=existing, excl=excl, graded=graded_ids(cls, sec, subjects))
            for r in rows:
                upsert_mark(cls, sec, r[0], r[1], exam, r[2], r[3], r[4], user["id"])
            db.commit()
            flash(f"Marks saved ({len(rows)} entries).", "success")
            return redirect(url_for("marks.entry", class_id=cls, section_id=sec, exam_id=exam))
        for r in db.query("SELECT studentId, subjectId, exam_subtype_id, marks FROM exam_marks WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam)):
            existing[(r["studentId"], r["subjectId"], r["exam_subtype_id"])] = r["marks"]
    return render_template("marks_entry.html", pairs=pairs, cls=cls, sec=sec, exam=exam, classes=classes, sections=sections,
                           exams=exams, subjects=subjects, students=students, existing=existing, excl=excl, graded=graded_ids(cls, sec, subjects))


@bp.route("/special", methods=["GET", "POST"])
@cap
def special():
    """Special subjects have a single (WRITTEN, id 2) mark column, usually a grade."""
    user = current_user()
    pairs, cls, sec, exam, classes, sections, exams = _ctx(user, "special")
    subjects, students, existing, excl = [], [], {}, set()
    if cls and sec and exam:
        students = access.students(cls, sec)
        allowed={row['subjectId'] for row in features.mark_contexts(user,'special') if (row['classId'],row['sectionId'],row['examId'])==(cls,sec,exam)}
        subjects = [subject for subject in access.allowed_subjects(user, cls, sec, special=True) if subject['subjectId'] in allowed]
        excl = enrollment.excluded(cls, sec)
        subjects = [s for s in subjects if any((stu["studentId"], s["subjectId"]) not in excl for stu in students)]
        if request.method == "POST":
            if not access.editing_enabled() and not user["is_admin"]:
                flash("Marks entry is currently switched off by the administrator.", "error")
                return redirect(request.url)
            n = 0
            for s in subjects:
                full = db.scalar("SELECT fullmarsks FROM assign_exam_subtype WHERE classId=%s AND sectionId=%s AND subjectId=%s AND examId=%s AND exam_subtype_id=2 AND isDelete='0' LIMIT 1",
                                 (cls, sec, s["subjectId"], exam), 0) or 0
                for stu in students:
                    if (stu["studentId"], s["subjectId"]) in excl:
                        continue
                    raw = request.form.get(f"m_{s['subjectId']}_{stu['studentId']}", "").strip()
                    if raw:
                        upsert_mark(cls, sec, stu["studentId"], s["subjectId"], exam, 2, full, raw[:40], user["id"]); n += 1
            db.commit()
            flash(f"Saved {n} entries.", "success")
            return redirect(url_for("marks.special", class_id=cls, section_id=sec, exam_id=exam))
        for r in db.query("SELECT studentId, subjectId, marks FROM exam_marks WHERE classId=%s AND sectionId=%s AND examId=%s AND exam_subtype_id=2 AND isDelete='0'", (cls, sec, exam)):
            existing[(r["studentId"], r["subjectId"])] = r["marks"]
    return render_template("marks_special.html", cls=cls, sec=sec, exam=exam, classes=classes, sections=sections,
                           exams=exams, subjects=subjects, students=students, existing=existing, excl=excl)


@bp.route("/list")
@cap
def marks_list():
    user = current_user()
    pairs, cls, sec, exam, classes, sections, exams = _ctx(user)
    subjects, students, grid, excl = [], [], {}, set()
    if cls and sec and exam:
        students = access.students(cls, sec)
        subjects = access.allowed_subjects(user, cls, sec)
        for s in subjects:
            s["subtypes"] = access.subtypes(cls, sec, exam, s["subjectId"])
        subjects = [s for s in subjects if s["subtypes"]]
        excl = enrollment.excluded(cls, sec)
        subjects = [s for s in subjects if any((stu["studentId"], s["subjectId"]) not in excl for stu in students)]
        for r in db.query("SELECT studentId, subjectId, exam_subtype_id, marks FROM exam_marks WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam)):
            grid[(r["studentId"], r["subjectId"], r["exam_subtype_id"])] = r["marks"]
    fmt = request.args.get('download')
    if fmt:
        if fmt not in ('pdf', 'xlsx', 'csv') or not (cls and sec and exam and subjects):
            abort(400, 'Choose an available class, section and exam before downloading.')
        from ..services.marks_export import download
        cname = next((r['class_name'] for r in classes if r['classId'] == cls), '')
        sname = next((r['section_name'] for r in sections if r['sectionId'] == sec), '')
        ename = next((r['exam_name'] for r in exams if r['examId'] == exam), '')
        title = f"{cname} · Section {sname} · {ename}"
        return download(fmt, title, f'marks-class-{cls}-section-{sec}-exam-{exam}', subjects, students, grid, excl)
    return render_template("marks_list.html", cls=cls, sec=sec, exam=exam, classes=classes, sections=sections,
                           exams=exams, subjects=subjects, students=students, grid=grid, excl=excl, can_edit=features.nav_allowed(user, "marks.entry"))
