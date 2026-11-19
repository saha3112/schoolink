"""Class teacher panel: attendance, comments, development skills, rank, house points, average/award."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from .. import db
from ..auth import roles_required, current_user
from ..services import access, features, ranking
from ..utils import to_int

bp = Blueprint("classteacher", __name__, url_prefix="/class-teacher")
cap = roles_required("class_teacher")

DEV_GRADES = ["EXCELLENT", "GOOD", "NEEDS IMPROVEMENT", "UNSATISFACTORY", "ABSENT"]


FEATURE_OF = {"attendance": "attendance", "comments": "comments", "development": "development", "rank": "rank", "house": "house", "average": "average"}


def _ctx(need_exam=True):
    user = current_user()
    pairs = features.pairs(FEATURE_OF.get(request.endpoint.split(".")[-1], "card"), user)
    cls, sec, exam = (to_int(request.values.get(k)) for k in ("class_id", "section_id", "exam_id"))
    if not user['is_admin']:
        if not pairs or not features.nav_allowed(user,request.endpoint):abort(403)
        if cls and cls not in {p['classId'] for p in pairs}:abort(403)
        if request.method=='POST' and (cls,sec) not in {(p['classId'],p['sectionId']) for p in pairs}:abort(403)
    classes = access.classes_for(pairs)
    cls, sec, exam, sections = access.autopick(pairs, classes, cls, sec, exam, None if need_exam else [])
    ready = bool(cls and sec and (exam or not need_exam))
    return user, dict(cls=cls, sec=sec, exam=exam, classes=classes, sections=sections, exams=access.exams_for(cls,sec) if need_exam else [],
                      students=access.students(cls, sec) if ready else []), ready


def _guard(user):
    if not access.editing_enabled() and not user["is_admin"]:
        flash("Entry is currently switched off by the administrator.", "error")
        return False
    return True


def _upsert_comment_row(cls, sec, exam, stu, user, **cols):
    """studentComment has one active row per (class, section, exam, student)."""
    names = list(cols)
    sql = (f"INSERT INTO studentComment (classId, sectionId, examId, studentId, {','.join('`'+c+'`' for c in names)}, teacherId, isDelete) "
           f"VALUES (%s,%s,%s,%s,{','.join(['%s'] * len(names))},%s,'0') ON DUPLICATE KEY UPDATE "
           + ",".join(f"`{c}`=VALUES(`{c}`)" for c in names) + ", teacherId=VALUES(teacherId)")
    db.execute(sql, [cls, sec, exam, stu] + [cols[c] for c in names] + [user["id"]], commit=False)


def _comment_map(cls, sec, exam):
    return {r["studentId"]: r for r in db.query(
        "SELECT studentId, totalSession, attendSession, comment, `rank` FROM studentComment "
        "WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam))}


# ---------------------------------------------------------------- attendance
@bp.route("/attendance", methods=["GET", "POST"])
@cap
def attendance():
    user, c, ready = _ctx()
    if ready and request.method == "POST" and _guard(user):
        total = request.form.get("total_all", "").strip()
        for s in c["students"]:
            t = request.form.get(f"total_{s['studentId']}", total).strip()
            a = request.form.get(f"att_{s['studentId']}", "").strip()
            if t.isdigit() and a.isdigit():
                if int(a) > int(t):
                    flash(f"{s['student_name']}: attended ({a}) is more than total sessions ({t}).", "error")
                    db.rollback()
                    return redirect(request.url)
                _upsert_comment_row(c["cls"], c["sec"], c["exam"], s["studentId"], user, totalSession=int(t), attendSession=int(a))
        db.commit()
        flash("Attendance saved.", "success")
        return redirect(url_for("classteacher.attendance", class_id=c["cls"], section_id=c["sec"], exam_id=c["exam"]))
    return render_template("ct_attendance.html", data=_comment_map(c["cls"], c["sec"], c["exam"]) if ready else {}, ready=ready, **c)


# ---------------------------------------------------------------- comments
@bp.route("/comments", methods=["GET", "POST"])
@cap
def comments():
    user, c, ready = _ctx()
    if ready and request.method == "POST" and _guard(user):
        for s in c["students"]:
            txt = request.form.get(f"comment_{s['studentId']}", "").strip()
            if txt:
                _upsert_comment_row(c["cls"], c["sec"], c["exam"], s["studentId"], user, comment=txt[:2000])
                db.execute("INSERT IGNORE INTO comment_templates (comment_text) VALUES (%s)", (txt[:500],), commit=False)
        db.commit()
        flash("Comments saved.", "success")
        return redirect(url_for("classteacher.comments", class_id=c["cls"], section_id=c["sec"], exam_id=c["exam"]))
    templates = [r["comment_text"] for r in db.query("SELECT comment_text FROM comment_templates ORDER BY comment_text")] if ready else []
    return render_template("ct_comments.html", data=_comment_map(c["cls"], c["sec"], c["exam"]) if ready else {}, templates=templates, ready=ready, **c)


# ---------------------------------------------------------------- development skills (graded)
@bp.route("/development", methods=["GET", "POST"])
@cap
def development():
    user, c, ready = _ctx()
    skills = db.query("SELECT id, skillName FROM developmentSkill WHERE classId=%s AND sectionId=%s AND isDelete='0' ORDER BY id", (c["cls"], c["sec"])) if ready else []
    if ready and request.method == "POST" and _guard(user):
        n = 0
        for s in c["students"]:
            for k in skills:
                v = request.form.get(f"g_{k['id']}_{s['studentId']}", "").strip()
                if v:
                    ex = db.one("SELECT id FROM exam_marks_development WHERE classId=%s AND sectionId=%s AND studentId=%s AND subjectId=%s AND examId=%s AND isDelete='0' LIMIT 1",
                                (c["cls"], c["sec"], s["studentId"], k["id"], c["exam"]))
                    if ex:
                        db.execute("UPDATE exam_marks_development SET marks=%s, teacherId=%s WHERE id=%s", (v, user["id"], ex["id"]), commit=False)
                    else:
                        db.execute("INSERT INTO exam_marks_development (classId, sectionId, subjectId, examId, studentId, exam_subtype_id, fullmarsks, teacherId, marks) VALUES (%s,%s,%s,%s,%s,2,0,%s,%s)",
                                   (c["cls"], c["sec"], k["id"], c["exam"], s["studentId"], user["id"], v), commit=False)
                    n += 1
        db.commit()
        flash(f"Saved {n} grade(s).", "success")
        return redirect(url_for("classteacher.development", class_id=c["cls"], section_id=c["sec"], exam_id=c["exam"]))
    existing = {(r["studentId"], r["subjectId"]): r["marks"] for r in db.query(
        "SELECT studentId, subjectId, marks FROM exam_marks_development WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'",
        (c["cls"], c["sec"], c["exam"]))} if ready else {}
    return render_template("ct_development.html", skills=skills, existing=existing, grades=DEV_GRADES, ready=ready, **c)


# ---------------------------------------------------------------- rank (manual + auto)
@bp.route("/rank", methods=["GET", "POST"])
@cap
def rank():
    user, c, ready = _ctx()
    if ready and request.method == "POST" and _guard(user):
        for s in c["students"]:
            v = request.form.get(f"rank_{s['studentId']}", "").strip()
            if v:
                _upsert_comment_row(c["cls"], c["sec"], c["exam"], s["studentId"], user, **{"rank": v[:20]})
        db.commit()
        flash("Ranks saved.", "success")
        return redirect(url_for("classteacher.rank", class_id=c["cls"], section_id=c["sec"], exam_id=c["exam"]))
    auto = {}
    if ready and request.args.get("auto"):
        auto = ranking.auto_ranks(c["cls"], c["sec"], c["exam"])
        flash("Ranks were calculated from the marks. Review them and press Save.", "info")
    return render_template("ct_rank.html", data=_comment_map(c["cls"], c["sec"], c["exam"]) if ready else {}, auto=auto, ready=ready, **c)


# ---------------------------------------------------------------- house points
@bp.route("/house", methods=["GET", "POST"])
@cap
def house():
    user, c, ready = _ctx()
    if ready and request.method == "POST" and _guard(user):
        for s in c["students"]:
            hn = request.form.get(f"house_{s['studentId']}", "").strip()
            hp = request.form.get(f"points_{s['studentId']}", "").strip()
            if hn or hp:
                ex = db.one("SELECT id FROM student_house WHERE classId=%s AND sectionId=%s AND examId=%s AND studentId=%s AND isDelete='0' LIMIT 1",
                            (c["cls"], c["sec"], c["exam"], s["studentId"]))
                if ex:
                    db.execute("UPDATE student_house SET houseName=%s, housePoints=%s WHERE id=%s", (hn, to_int(hp, 0), ex["id"]), commit=False)
                else:
                    nid = (db.scalar("SELECT COALESCE(MAX(id),0)+1 FROM student_house") or 1)
                    db.execute("INSERT INTO student_house (id, classId, sectionId, examId, studentId, houseName, housePoints, teacherId) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                               (nid, c["cls"], c["sec"], c["exam"], s["studentId"], hn, to_int(hp, 0), user["id"]), commit=False)
        db.commit()
        flash("House points saved.", "success")
        return redirect(url_for("classteacher.house", class_id=c["cls"], section_id=c["sec"], exam_id=c["exam"]))
    data = {r["studentId"]: r for r in db.query("SELECT studentId, houseName, housePoints FROM student_house WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'",
                                                (c["cls"], c["sec"], c["exam"]))} if ready else {}
    houses = [r["houseName"] for r in db.query("SELECT DISTINCT houseName FROM student_house WHERE houseName<>'' ORDER BY houseName")]
    return render_template("ct_house.html", data=data, houses=houses, ready=ready, **c)


# ---------------------------------------------------------------- average / award / promotion
@bp.route("/average", methods=["GET", "POST"])
@cap
def average():
    user, c, ready = _ctx(need_exam=False)
    if ready and request.method == "POST" and _guard(user):
        for s in c["students"]:
            sid = s["studentId"]
            avg, award, promo = (request.form.get(f"{k}_{sid}", "").strip() for k in ("avg", "award", "promo"))
            if avg or award or promo:
                ex = db.one("SELECT id FROM rankAvarageOther WHERE studentId=%s AND isDelete='0' ORDER BY id DESC LIMIT 1", (sid,))
                if ex:
                    db.execute("UPDATE rankAvarageOther SET classId=%s, sectionId=%s, rankAvarage=%s, award=%s, promotion=%s, teacherId=%s WHERE id=%s",
                               (c["cls"], c["sec"], avg, award, promo, user["id"], ex["id"]), commit=False)
                else:
                    db.execute("INSERT INTO rankAvarageOther (classId, sectionId, studentId, teacherId, rankAvarage, award, promotion) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                               (c["cls"], c["sec"], sid, user["id"], avg, award, promo), commit=False)
        db.commit()
        flash("Saved.", "success")
        return redirect(url_for("classteacher.average", class_id=c["cls"], section_id=c["sec"]))
    data = {}
    if ready:
        for s in c["students"]:
            r = db.one("SELECT rankAvarage, award, promotion FROM rankAvarageOther WHERE studentId=%s AND isDelete='0' ORDER BY id DESC LIMIT 1", (s["studentId"],))
            if r:
                data[s["studentId"]] = r
    return render_template("ct_average.html", data=data, ready=ready, **c)
