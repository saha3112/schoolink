"""School-life modules brought over from the old Schoolink app: announcements, events & holidays, gallery,
classwork / homework, daily attendance and timetable. Uploaded files are stored in the database."""
import datetime as dt

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from .. import db
from ..auth import admin_required, current_user, login_required, roles_required
from ..services import access, features, filestore, notifications as N, schooldb
from ..utils import to_int

bp = Blueprint("school", __name__, url_prefix="/school")
staff = roles_required("teacher")                     # admin always passes, teachers pass
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _is_admin():
    return current_user()["is_admin"]


def my_pairs(user=None):
    """(classId, sectionId) pairs the user works with (subject or class teacher; admin: all)."""
    user = user or current_user()
    if user["is_admin"]:
        return [{"classId": r["classId"], "sectionId": r["sectionId"]} for r in db.query(
            "SELECT s.class_id AS classId, s.sectionId FROM sections s JOIN classes c ON c.classId=s.class_id WHERE s.isDelete='0' AND c.isDelete='0'")]
    seen, out = set(), []
    for p in list(access.subject_pairs(user)) + list(access.class_pairs(user)):
        k = (p["classId"], p["sectionId"])
        if k not in seen:
            seen.add(k); out.append({"classId": k[0], "sectionId": k[1]})
    return out


def _sel(pairs):
    cls, sec = to_int(request.values.get("class_id")), to_int(request.values.get("section_id"))
    classes = access.classes_for(pairs)
    cls, sec, _e, sections = access.autopick(pairs, classes, cls, sec, None)
    return cls, sec, classes, sections


def _allowed(cid, sid):
    return _is_admin() or (cid, sid) in {(p["classId"], p["sectionId"]) for p in my_pairs()}


def _label(cid, sid):
    if not cid:
        return "Whole school"
    c = db.scalar("SELECT class_name FROM classes WHERE classId=%s", (cid,)) or ""
    s = db.scalar("SELECT section_name FROM sections WHERE sectionId=%s", (sid,)) if sid else None
    return f"{c} {s}" if s else f"{c} (all sections)"


def _flash_errors(errs):
    for e in errs[:4]:
        flash(e, "warning")


@bp.route("/api/sections")
@staff
def api_sections():
    from flask import jsonify
    cid = to_int(request.args.get("class_id"))
    return jsonify(access.sections_for(my_pairs(), cid) if not _is_admin() else db.query(
        "SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0' ORDER BY section_name", (cid,)))


# ---------------------------------------------------------------------------------------------- files
@bp.route("/file/<path:p>")
@login_required
def file(p):
    f = filestore.get("uploads/" + p)
    if not f:
        abort(404)
    if current_user().get("is_parent"):
        a = db.one("SELECT owner_type, owner_id FROM sl_attachment WHERE path=%s", ("uploads/" + p,))
        if not a:
            abort(403)
        tbl = {"announcement": ("sl_announcement", "classId", "sectionId"), "album": ("sl_album", "classId", "sectionId"), "work": ("sl_work", "classId", "sectionId")}[a["owner_type"]]
        o = db.one(f"SELECT {tbl[1]} AS c, {tbl[2]} AS s FROM {tbl[0]} WHERE id=%s AND deleted=0", (a["owner_id"],))
        from ..auth import my_children
        mine = {(k["class_id"], k["section_id"]) for k in my_children()}
        if not o or not (o["c"] is None or any(c == o["c"] and (o["s"] is None or s_ == o["s"]) for c, s_ in mine)):
            abort(403)
    name = p.split("/")[-1].split("_", 1)[-1]
    inline = f["mime"].startswith("image/") or f["mime"] == "application/pdf"
    disp = "attachment" if (request.args.get("download") or not inline) else "inline"
    return Response(f["data"], mimetype=f["mime"], headers={"Content-Disposition": f'{disp}; filename="{name}"', "Cache-Control": "private, max-age=600"})


def furl(path, download=False):
    return url_for("school.file", p=path[len("uploads/"):]) + ("?download=1" if download else "")


# ---------------------------------------------------------------------------------------------- announcements
@bp.route("/announcements", methods=["GET", "POST"])
@staff
def announcements():
    schooldb.ensure(); u = current_user()
    pairs = my_pairs()
    if request.method == "POST":
        act = request.form.get("action")
        if act == "delete":
            r = db.one("SELECT id, created_by FROM sl_announcement WHERE id=%s AND deleted=0", (to_int(request.form.get("id")),))
            if r and (_is_admin() or r["created_by"] == u["id"]):
                db.execute("UPDATE sl_announcement SET deleted=1 WHERE id=%s", (r["id"],)); schooldb.delete_attachments("announcement", r["id"])
                flash("Announcement deleted.", "success")
        else:
            title, body = request.form.get("title", "").strip(), request.form.get("body", "").strip()
            aud, cid, sid = request.form.get("audience"), to_int(request.form.get("class_id")), to_int(request.form.get("section_id"))
            if not title or not body:
                flash("Title and message are required.", "error")
            elif aud == "school" and not _is_admin():
                flash("Only an administrator can post to the whole school.", "error")
            elif aud != "school" and not (cid and (_is_admin() and not sid or _allowed(cid, sid))):
                flash("Choose the class / section this is for.", "error")
            else:
                if aud == "school": cid = sid = None
                new = db.execute("INSERT INTO sl_announcement (title, body, classId, sectionId, created_by) VALUES (%s,%s,%s,%s,%s)", (title[:200], body, cid, sid, u["id"]))
                n, errs = schooldb.save_attachments("announcement", new, request.files.getlist("files"), u["id"], request.form.getlist("media_ids")); _flash_errors(errs)
                N.notify(N.staff_ids() if aud == "school" else N.section_staff(cid, sid), "New announcement: " + title[:80], f"{_label(cid, sid)} · {u['fname']}",
                         url_for("school.announcements"), exclude=u["id"])
                flash("Announcement posted.", "success")
        return redirect(url_for("school.announcements"))
    mine = {(p["classId"], p["sectionId"]) for p in pairs}
    rows = [r for r in db.query("SELECT a.*, u.fname AS author FROM sl_announcement a LEFT JOIN new_users u ON u.id=a.created_by WHERE a.deleted=0 ORDER BY a.id DESC LIMIT 200")
            if _is_admin() or r["classId"] is None or (r["classId"], r["sectionId"]) in mine or (r["sectionId"] is None and any(c == r["classId"] for c, _ in mine))]
    att = schooldb.attachments("announcement", [r["id"] for r in rows])
    for r in rows:
        r["label"] = _label(r["classId"], r["sectionId"]); r["files"] = att.get(r["id"], []); r["can_edit"] = _is_admin() or r["created_by"] == u["id"]
    return render_template("school_announcements.html", rows=rows, classes=access.classes_for(pairs), furl=furl)


# ---------------------------------------------------------------------------------------------- events & holidays
@bp.route("/events", methods=["GET", "POST"])
@staff
def events():
    schooldb.ensure()
    if request.method == "POST":
        if not _is_admin():
            abort(403)
        if request.form.get("action") == "delete":
            db.execute("UPDATE sl_event SET deleted=1 WHERE id=%s", (to_int(request.form.get("id")),)); flash("Removed.", "success")
        else:
            try:
                s = dt.date.fromisoformat(request.form.get("start_date", "")); e = request.form.get("end_date")
                e = dt.date.fromisoformat(e) if e else None
                if e and e < s: raise ValueError
                t = request.form.get("title", "").strip()
                if not t: raise ValueError
                kind = "holiday" if request.form.get("kind") == "holiday" else "event"
                db.execute("INSERT INTO sl_event (kind, title, description, start_date, end_date, created_by) VALUES (%s,%s,%s,%s,%s,%s)",
                           (kind, t[:200], request.form.get("description", "").strip(), s, e, current_user()["id"]))
                N.notify(N.staff_ids(), ("Holiday: " if kind == "holiday" else "Event: ") + t[:80], s.strftime("%A, %d %B %Y"), url_for("school.events"), exclude=current_user()["id"])
                flash("Saved.", "success")
            except ValueError:
                flash("Enter a title and valid dates (end date cannot be before the start date).", "error")
        return redirect(url_for("school.events"))
    today = dt.date.today()
    rows = db.query("SELECT * FROM sl_event WHERE deleted=0 ORDER BY start_date")
    upcoming = [r for r in rows if (r["end_date"] or r["start_date"]) >= today]
    past = [r for r in rows if (r["end_date"] or r["start_date"]) < today][::-1][:30]
    return render_template("school_events.html", upcoming=upcoming, past=past, today=today)


# ---------------------------------------------------------------------------------------------- gallery
@bp.route("/gallery", methods=["GET", "POST"])
@staff
def gallery():
    schooldb.ensure(); u = current_user(); pairs = my_pairs()
    if request.method == "POST":
        act = request.form.get("action")
        if act == "delete":
            a = db.one("SELECT id, created_by FROM sl_album WHERE id=%s AND deleted=0", (to_int(request.form.get("id")),))
            if a and (_is_admin() or a["created_by"] == u["id"]):
                db.execute("UPDATE sl_album SET deleted=1 WHERE id=%s", (a["id"],)); schooldb.delete_attachments("album", a["id"]); flash("Album deleted.", "success")
        else:
            title, cid, sid = request.form.get("title", "").strip(), to_int(request.form.get("class_id")), to_int(request.form.get("section_id"))
            if not title:
                flash("Album title is required.", "error")
            elif (cid or sid) and not (_allowed(cid, sid) or (_is_admin() and cid)):
                flash("You cannot add photos for that class.", "error")
            elif not (cid or _is_admin()):
                flash("Choose a class / section.", "error")
            else:
                try: d = dt.date.fromisoformat(request.form.get("album_date", "")) 
                except ValueError: d = dt.date.today()
                new = db.execute("INSERT INTO sl_album (title, album_date, classId, sectionId, created_by) VALUES (%s,%s,%s,%s,%s)", (title[:200], d, cid, sid, u["id"]))
                n, errs = schooldb.save_attachments("album", new, [f for f in request.files.getlist("files")], u["id"], request.form.getlist("media_ids"))
                if n == 0:
                    db.execute("DELETE FROM sl_album WHERE id=%s", (new,)); flash("Add at least one valid image.", "error")
                else:
                    N.notify(N.section_staff(cid, sid) if cid else N.staff_ids(), "New photo album: " + title[:80], f"{n} photo(s) · {_label(cid, sid)}", url_for("school.gallery"), exclude=u["id"])
                    flash(f"Album created with {n} photo(s).", "success")
                _flash_errors(errs)
        return redirect(url_for("school.gallery"))
    mine = {(p["classId"], p["sectionId"]) for p in pairs}
    albums = [a for a in db.query("SELECT a.*, u.fname AS author FROM sl_album a LEFT JOIN new_users u ON u.id=a.created_by WHERE a.deleted=0 ORDER BY a.id DESC LIMIT 100")
              if _is_admin() or a["classId"] is None or (a["classId"], a["sectionId"]) in mine or (a["sectionId"] is None and any(c == a["classId"] for c, _ in mine))]
    att = schooldb.attachments("album", [a["id"] for a in albums])
    for a in albums:
        a["files"] = [f for f in att.get(a["id"], []) if f["is_image"]]; a["label"] = _label(a["classId"], a["sectionId"]); a["can_edit"] = _is_admin() or a["created_by"] == u["id"]
    return render_template("school_gallery.html", albums=albums, classes=access.classes_for(pairs), furl=furl)


@bp.route("/gallery/<int:aid>/add", methods=["POST"])
@staff
def gallery_add(aid):
    a = db.one("SELECT id, created_by FROM sl_album WHERE id=%s AND deleted=0", (aid,))
    if not a or not (_is_admin() or a["created_by"] == current_user()["id"]):
        abort(403)
    n, errs = schooldb.save_attachments("album", aid, request.files.getlist("files"), current_user()["id"], request.form.getlist("media_ids"))
    flash(f"{n} photo(s) added.", "success" if n else "warning"); _flash_errors(errs)
    return redirect(url_for("school.gallery"))


@bp.route("/attachment/<int:fid>/delete", methods=["POST"])
@staff
def attachment_delete(fid):
    r = db.one("SELECT * FROM sl_attachment WHERE id=%s", (fid,))
    if not r:
        abort(404)
    owner = {"album": "sl_album", "announcement": "sl_announcement", "work": "sl_work"}[r["owner_type"]]
    o = db.one(f"SELECT created_by FROM {owner} WHERE id=%s", (r["owner_id"],))
    if not o or not (_is_admin() or o["created_by"] == current_user()["id"]):
        abort(403)
    filestore.delete(r["path"]); db.execute("DELETE FROM sl_attachment WHERE id=%s", (fid,)); flash("File removed.", "success")
    return redirect(request.referrer or url_for("school.gallery"))


# ---------------------------------------------------------------------------------------------- classwork / homework
@bp.route("/work", methods=["GET", "POST"])
@roles_required("subject_teacher")
def work():
    schooldb.ensure(); u = current_user(); pairs = features.pairs("entry", u)
    if request.method == "POST":
        act = request.form.get("action")
        if act == "delete":
            r = db.one("SELECT id, created_by FROM sl_work WHERE id=%s AND deleted=0", (to_int(request.form.get("id")),))
            if r and (_is_admin() or r["created_by"] == u["id"]):
                db.execute("UPDATE sl_work SET deleted=1 WHERE id=%s", (r["id"],)); schooldb.delete_attachments("work", r["id"]); flash("Deleted.", "success")
        else:
            cid, sid, sub = (to_int(request.form.get(k)) for k in ("class_id", "section_id", "subject_id"))
            title = request.form.get("title", "").strip()
            allowed_sub = {s["subjectId"] for s in access.allowed_subjects(u, cid, sid)} | {s["subjectId"] for s in access.allowed_subjects(u, cid, sid, special=True)} if cid and sid else set()
            if not (title and cid and sid and sub in allowed_sub):
                flash("Choose one of your class / section / subject combinations and enter a title.", "error")
            else:
                try: wd = dt.date.fromisoformat(request.form.get("work_date", ""))
                except ValueError: wd = dt.date.today()
                try: due = dt.date.fromisoformat(request.form.get("due_date", "")) if request.form.get("due_date") else None
                except ValueError: due = None
                new = db.execute("INSERT INTO sl_work (kind, classId, sectionId, subjectId, title, body, work_date, due_date, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                                 ("homework" if request.form.get("kind") == "homework" else "classwork", cid, sid, sub, title[:200], request.form.get("body", "").strip(), wd, due, u["id"]))
                n, errs = schooldb.save_attachments("work", new, request.files.getlist("files"), u["id"], request.form.getlist("media_ids")); _flash_errors(errs)
                N.notify(N.section_staff(cid, sid), ("Homework: " if request.form.get("kind") == "homework" else "Classwork: ") + title[:80], f"{_label(cid, sid)} · {u['fname']}",
                         url_for("school.work", class_id=cid, section_id=sid), exclude=u["id"])
                flash("Posted.", "success")
        return redirect(url_for("school.work", class_id=request.form.get("class_id") or "", section_id=request.form.get("section_id") or ""))
    cls, sec, classes, sections = _sel(pairs)
    subjects = access.allowed_subjects(u, cls, sec) + access.allowed_subjects(u, cls, sec, special=True) if cls and sec else []
    kind = request.args.get("kind", "")
    where, args = "WHERE w.deleted=0", []
    ok = {(p["classId"], p["sectionId"]) for p in pairs}
    if cls: where += " AND w.classId=%s"; args.append(cls)
    if sec: where += " AND w.sectionId=%s"; args.append(sec)
    if kind in ("classwork", "homework"): where += " AND w.kind=%s"; args.append(kind)
    rows = [r for r in db.query(f"SELECT w.*, c.class_name, s.section_name, sb.subject_name, u.fname AS author FROM sl_work w JOIN classes c ON c.classId=w.classId "
                                f"JOIN sections s ON s.sectionId=w.sectionId JOIN subjects sb ON sb.subjectId=w.subjectId LEFT JOIN new_users u ON u.id=w.created_by {where} "
                                "ORDER BY w.work_date DESC, w.id DESC LIMIT 100", args) if _is_admin() or (r["classId"], r["sectionId"]) in ok]
    att = schooldb.attachments("work", [r["id"] for r in rows])
    for r in rows:
        r["files"] = att.get(r["id"], []); r["can_edit"] = _is_admin() or r["created_by"] == u["id"]
    return render_template("school_work.html", rows=rows, cls=cls, sec=sec, classes=classes, sections=sections, subjects=subjects, kind=kind, today=dt.date.today(), furl=furl)


# ---------------------------------------------------------------------------------------------- daily attendance
@bp.route("/attendance", methods=["GET", "POST"])
@roles_required("class_teacher")
def daily_attendance():
    schooldb.ensure(); u = current_user(); pairs = features.pairs("attendance", u)
    cls, sec, classes, sections = _sel(pairs)
    try: day = dt.date.fromisoformat(request.values.get("date", "")) if request.values.get("date") else dt.date.today()
    except ValueError: day = dt.date.today()
    students = access.students(cls, sec) if cls and sec else []
    if request.method == "POST" and students and request.form.get("action") == "save":
        if day > dt.date.today():
            flash("Attendance cannot be marked for a future date.", "error")
        else:
            for s in students:
                st = request.form.get(f"s_{s['studentId']}", "P")
                st = st if st in ("P", "A", "L") else "P"
                db.execute("INSERT INTO sl_attendance (classId, sectionId, studentId, att_date, status, marked_by) VALUES (%s,%s,%s,%s,%s,%s) "
                           "ON DUPLICATE KEY UPDATE status=VALUES(status), classId=VALUES(classId), sectionId=VALUES(sectionId), marked_by=VALUES(marked_by)",
                           (cls, sec, s["studentId"], day, st, u["id"]), commit=False)
            db.commit(); flash(f"Attendance saved for {day:%d %b %Y}.", "success")
        return redirect(url_for("school.daily_attendance", class_id=cls, section_id=sec, date=day.isoformat()))
    if request.method == "POST" and students and request.form.get("action") == "apply":
        # copy the daily records into the report card sessions (studentComment) for an exam
        exam, d1, d2 = to_int(request.form.get("exam_id")), request.form.get("from"), request.form.get("to")
        try:
            a, b = dt.date.fromisoformat(d1), dt.date.fromisoformat(d2)
        except (TypeError, ValueError):
            flash("Choose a valid date range.", "error"); return redirect(request.url)
        n = 0
        for s in students:
            r = db.one("SELECT COUNT(*) t, SUM(status IN ('P','L')) p FROM sl_attendance WHERE studentId=%s AND att_date BETWEEN %s AND %s", (s["studentId"], a, b))
            if r and r["t"]:
                db.execute("INSERT INTO studentComment (classId, sectionId, examId, studentId, totalSession, attendSession, teacherId, isDelete) VALUES (%s,%s,%s,%s,%s,%s,%s,'0') "
                           "ON DUPLICATE KEY UPDATE totalSession=VALUES(totalSession), attendSession=VALUES(attendSession), teacherId=VALUES(teacherId)",
                           (cls, sec, exam, s["studentId"], int(r["t"]), int(r["p"] or 0), u["id"]), commit=False); n += 1
        db.commit(); flash(f"Report card attendance updated for {n} student(s).", "success")
        return redirect(url_for("school.daily_attendance", class_id=cls, section_id=sec, date=day.isoformat()))
    marks = {r["studentId"]: r["status"] for r in db.query("SELECT studentId, status FROM sl_attendance WHERE classId=%s AND sectionId=%s AND att_date=%s", (cls, sec, day))} if students else {}
    month = {}
    if students:
        for r in db.query("SELECT studentId, COUNT(*) t, SUM(status IN ('P','L')) p FROM sl_attendance WHERE classId=%s AND sectionId=%s AND att_date BETWEEN %s AND %s GROUP BY studentId",
                          (cls, sec, day.replace(day=1), day)):
            month[r["studentId"]] = (int(r["t"]), int(r["p"] or 0))
    return render_template("school_attendance.html", cls=cls, sec=sec, classes=classes, sections=sections, students=students, day=day, marks=marks, month=month,
                           exams=access.exams(), today=dt.date.today())


# ---------------------------------------------------------------------------------------------- timetable
@bp.route("/timetable", methods=["GET", "POST"])
@staff
def timetable():
    schooldb.ensure(); u = current_user()
    pairs = my_pairs()
    cls, sec, classes, sections = _sel(pairs)
    if request.method == "POST":
        if not u["is_admin"]:
            abort(403)
        periods = to_int(request.form.get("periods"), 8)
        db.execute("DELETE FROM sl_timetable WHERE classId=%s AND sectionId=%s", (cls, sec), commit=False)
        for d in range(len(WEEKDAYS)):
            for p in range(1, periods + 1):
                sb, tc = to_int(request.form.get(f"sub_{d}_{p}")), to_int(request.form.get(f"tch_{d}_{p}"))
                if sb:
                    db.execute("INSERT INTO sl_timetable (classId, sectionId, weekday, period, subjectId, teacherId, start_time, end_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                               (cls, sec, d, p, sb, tc, request.form.get(f"st_{p}") or None, request.form.get(f"et_{p}") or None), commit=False)
        db.commit(); flash("Timetable saved.", "success")
        return redirect(url_for("school.timetable", class_id=cls, section_id=sec))
    cells, times, periods = {}, {}, 8
    subs, teachers = [], []
    if cls and sec:
        for r in db.query("SELECT t.*, sb.subject_name, TRIM(CONCAT_WS(' ', th.fname, th.lname)) AS teacher FROM sl_timetable t LEFT JOIN subjects sb ON sb.subjectId=t.subjectId "
                          "LEFT JOIN teachers th ON th.user_id=t.teacherId WHERE t.classId=%s AND t.sectionId=%s", (cls, sec)):
            cells[(r["weekday"], r["period"])] = r; times[r["period"]] = (r["start_time"] or "", r["end_time"] or ""); periods = max(periods, r["period"])
        subs = db.query("SELECT DISTINCT sb.subjectId, sb.subject_name FROM assign_subject a JOIN subjects sb ON sb.subjectId=a.subject_id WHERE a.class_id=%s AND a.section_id=%s AND a.isDelete='0' ORDER BY sb.subject_name", (cls, sec))
        teachers = db.query("SELECT user_id, TRIM(CONCAT_WS(' ', fname, NULLIF(mname,''), lname)) AS name FROM teachers ORDER BY fname")
    mine = []
    if u["is_teacher"]:
        mine = db.query("SELECT t.*, c.class_name, s.section_name, sb.subject_name FROM sl_timetable t JOIN classes c ON c.classId=t.classId JOIN sections s ON s.sectionId=t.sectionId "
                        "JOIN subjects sb ON sb.subjectId=t.subjectId WHERE t.teacherId=%s ORDER BY t.weekday, t.period", (u["id"],))
    return render_template("school_timetable.html", cls=cls, sec=sec, classes=classes, sections=sections, cells=cells, times=times, periods=periods, days=WEEKDAYS,
                           subs=subs, teachers=teachers, mine=mine)
