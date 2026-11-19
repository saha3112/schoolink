import csv, io, random
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from .. import db
from ..auth import admin_required, current_user
from ..services import enrollment, notifications as N, rolls
from ..utils import paginate, page_arg, to_int

bp = Blueprint("students", __name__, url_prefix="/students")


def _classes():
    return db.query("SELECT classId, class_name FROM classes WHERE isDelete='0' ORDER BY classId")


def _sections(cid):
    return db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0' ORDER BY section_name", (cid,)) if cid else []


@bp.route("/")
@admin_required
def student_list():
    cls, sec, q = to_int(request.args.get("class_id")), to_int(request.args.get("section_id")), request.args.get("q", "").strip()
    where, args = "WHERE st.isDelete='0'", []
    if cls: where += " AND st.class_id=%s"; args.append(cls)
    if sec: where += " AND st.section_id=%s"; args.append(sec)
    if q:
        where += " AND (st.student_name LIKE %s OR st.student_code LIKE %s OR st.ADMNO LIKE %s OR st.studentUID LIKE %s)"; args += [f"%{q}%"] * 4
    base = f"FROM students st LEFT JOIN classes c ON c.classId=st.class_id LEFT JOIN sections s ON s.sectionId=st.section_id {where}"
    total = db.scalar(f"SELECT COUNT(*) {base}", args)
    p = paginate(total, 25, page_arg())
    rows = db.query(f"SELECT st.*, c.class_name, s.section_name {base} ORDER BY st.class_id, st.section_id, st.student_rollNumber LIMIT %s OFFSET %s", args + [25, p["offset"]])
    return render_template("student_list.html", rows=rows, p=p, cls=cls, sec=sec, q=q, classes=_classes(), sections=_sections(cls))


@bp.route("/<int:sid>/edit", methods=["GET", "POST"])
@admin_required
def edit(sid):
    st = db.one("SELECT st.*, c.class_name, s.section_name FROM students st LEFT JOIN classes c ON c.classId=st.class_id LEFT JOIN sections s ON s.sectionId=st.section_id WHERE st.studentId=%s", (sid,))
    if not st:
        flash("Student not found.", "error"); return redirect(url_for("students.student_list"))
    if request.method == "POST":
        f = request.form
        name = f.get("student_name", "").strip()
        if not name:
            flash("Name is required.", "error")
        else:
            db.execute("UPDATE students SET student_name=%s, studentUID=%s, DOB=%s, ADMNO=%s, student_code=%s WHERE studentId=%s",
                       (name, f.get("studentUID", "").strip(), f.get("DOB", "").strip(), f.get("ADMNO", "").strip(), f.get("student_code", "").strip(), sid))
            flash("Student updated. (Use Move / Leave to change class or section.)", "success")
            return redirect(url_for("students.edit", sid=sid))
    return render_template("student_edit.html", st=st)


# --------------------------------------------------------------------- roll numbers
@bp.route("/rolls", methods=["GET", "POST"])
@admin_required
def rolls_page():
    cls, sec = to_int(request.values.get("class_id")), to_int(request.values.get("section_id"))
    if request.method == "POST" and cls and sec:
        mode = "name" if request.form.get("mode") == "name" else "keep"
        n = rolls.renumber(cls, sec, mode, commit=True)
        flash(f"Roll numbers rewritten ({n} changed).", "success")
        return redirect(url_for("students.rolls_page", class_id=cls, section_id=sec))
    rows = rolls._ordered(cls, sec) if cls and sec else []
    nums = [r["student_rollNumber"] for r in rows]
    problems = bool(rows) and sorted(nums) != list(range(1, len(nums) + 1))
    return render_template("rolls.html", rows=rows, cls=cls, sec=sec, classes=_classes(), sections=_sections(cls), problems=problems)


@bp.route("/api/students")
@admin_required
def api_students():
    cls, sec = to_int(request.args.get("class_id")), to_int(request.args.get("section_id"))
    return jsonify(db.query("SELECT studentId, CONCAT(student_rollNumber, '. ', student_name) AS label FROM students "
                            "WHERE class_id=%s AND section_id=%s AND isDelete='0' ORDER BY student_rollNumber", (cls, sec)))


# --------------------------------------------------------------------- move / leave
@bp.route("/move", methods=["GET", "POST"])
@admin_required
def move():
    if request.method == "POST":
        sid, action = to_int(request.form.get("student_id")), request.form.get("action")
        note = request.form.get("note", "").strip()[:250]
        try:
            if action == "leave":
                st = rolls.leave_student(sid, note, current_user()["id"])
                N.notify(N.section_staff(st["class_id"], st["section_id"]), f"{st['student_name']} left school", "Roll numbers of the section were renumbered.", url_for("students.rolls_page", class_id=st["class_id"], section_id=st["section_id"]), exclude=current_user()["id"])
                flash(f"{st['student_name']} marked as left. Roll numbers of the section were updated automatically.", "success")
            else:
                r = rolls.move_student(sid, to_int(request.form.get("to_class")), to_int(request.form.get("to_section")),
                                       request.form.get("place", "name"), note, current_user()["id"])
                nm = db.scalar("SELECT student_name FROM students WHERE studentId=%s", (sid,))
                ids = set(N.section_staff(r["from"][0], r["from"][1])) | set(N.section_staff(r["to"][0], r["to"][1]))
                N.notify(ids, f"{nm} moved to another section", f"Old roll {r['from'][2]} → new roll {r['to'][2]}", url_for("students.rolls_page", class_id=r["to"][0], section_id=r["to"][1]), exclude=current_user()["id"])
                flash(f"Student moved. Old roll {r['from'][2]} → new roll {r['to'][2]}; the old section was renumbered.", "success")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(url_for("students.move"))
    log = db.query("""SELECT l.*, st.student_name, c1.class_name fc, s1.section_name fs, c2.class_name tc, s2.section_name ts
        FROM student_transfer_log l JOIN students st ON st.studentId=l.studentId
        LEFT JOIN classes c1 ON c1.classId=l.from_class LEFT JOIN sections s1 ON s1.sectionId=l.from_section
        LEFT JOIN classes c2 ON c2.classId=l.to_class LEFT JOIN sections s2 ON s2.sectionId=l.to_section
        ORDER BY l.id DESC LIMIT 15""") if db.scalar("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='student_transfer_log'") else []
    return render_template("move.html", classes=_classes(), log=log)


# --------------------------------------------------------------------- CSV upload
@bp.route("/upload", methods=["GET", "POST"])
@admin_required
def upload():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename.lower().endswith(".csv"):
            flash("Please choose a .csv file.", "error"); return redirect(url_for("students.upload"))
        rows = list(csv.reader(io.StringIO(f.read().decode("utf-8-sig"))))
        added = skipped = 0
        errors = []
        touched = set()
        for n, r in enumerate(rows, 1):
            if len(r) < 7 or not r[1].strip():
                continue
            if n == 1 and not r[1].strip().upper().startswith("STS"):
                pass
            c = db.one("SELECT classId FROM classes WHERE class_name=%s AND isDelete='0'", (r[5].strip(),))
            s = db.one("SELECT sectionId FROM sections WHERE class_id=%s AND section_name=%s AND isDelete='0'", (c["classId"], r[6].strip())) if c else None
            if not (c and s):
                errors.append(f"Row {n}: class/section '{r[5]} {r[6]}' not found"); continue
            if db.one("SELECT 1 FROM students WHERE student_code=%s AND isDelete='0'", (r[1].strip(),)):
                skipped += 1; continue
            name = (r[2].strip() + " " + r[3].strip()).strip()
            roll = to_int(r[4]) or rolls.next_roll(c["classId"], s["sectionId"])
            db.execute("INSERT INTO students (student_id, student_code, student_name, class_id, section_id, student_rollNumber) VALUES (%s,%s,%s,%s,%s,%s)",
                       (r[0].strip() or "N/A", r[1].strip(), name, c["classId"], s["sectionId"], roll), commit=False)
            touched.add((c["classId"], s["sectionId"])); added += 1
        db.commit()
        flash(f"{added} student(s) added, {skipped} already existed.", "success")
        for e in errors[:8]:
            flash(e, "warning")
        return redirect(url_for("students.upload"))
    return render_template("student_upload.html")


# --------------------------------------------------------------------- which subjects does each student take
@bp.route("/subjects", methods=["GET", "POST"])
@admin_required
def subjects():
    cls, sec = to_int(request.values.get("class_id")), to_int(request.values.get("section_id"))
    studs, subs = [], []
    if cls and sec:
        studs = db.query("SELECT studentId, student_name, student_rollNumber FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0' ORDER BY student_rollNumber, student_name", (cls, sec))
        subs = db.query("SELECT DISTINCT sb.subjectId, sb.subject_name, a.isSpecialSubject FROM assign_subject a JOIN subjects sb ON sb.subjectId=a.subject_id "
                        "WHERE a.class_id=%s AND a.section_id=%s AND a.isDelete='0' ORDER BY a.isSpecialSubject, sb.subject_name", (cls, sec))
    if request.method == "POST" and studs:
        enrolled = {(to_int(k.split("_")[1]), to_int(k.split("_")[2])) for k in request.form if k.startswith("e_")}
        n = enrollment.save(cls, sec, enrolled)
        flash(f"Saved. {n} student-subject combination(s) are marked as 'not taken'.", "success")
        return redirect(url_for("students.subjects", class_id=cls, section_id=sec))
    excl = enrollment.excluded(cls, sec) if studs else set()
    suggested = set()
    if studs and request.args.get("detect"):
        suggested = enrollment.detect(cls, sec) - excl
        flash(f"{len(suggested)} suggestion(s) found from the entered marks (highlighted). Review and press Save.", "info" if suggested else "warning")
        excl = excl | suggested
    return render_template("student_subjects.html", cls=cls, sec=sec, classes=_classes(), sections=_sections(cls), students=studs, subjects=subs,
                           excl=excl, suggested=suggested)
