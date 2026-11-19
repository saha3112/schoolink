"""Parent panel: everything a parent sees about their own children (read only, plus leave requests)."""
import datetime as dt
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from .. import db
from ..auth import current_user, my_children, parent_required
from ..services import filestore, notifications as N, reportcard, schooldb
from ..utils import to_int

bp = Blueprint("parentpanel", __name__, url_prefix="/parent")
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _child():
    kids = my_children()
    cid = to_int(request.args.get("child"))
    pick = next((k for k in kids if k["studentId"] == cid), None) or (kids[0] if kids else None)
    return kids, pick


def _released(student_id):
    return bool(db.one("SELECT 1 AS x FROM releaseResult WHERE studentId=%s AND isOpen='1' AND documentName LIKE 'report_card%%'", (student_id,)))


def _ctx(**kw):
    kids, child = _child()
    return dict(kids=kids, child=child, **kw)


def _my_sections():
    return {(k["class_id"], k["section_id"]) for k in my_children()}


def _audience_ok(cid, sid):
    """classId NULL = whole school; sectionId NULL = whole class."""
    mine = _my_sections()
    return cid is None or any(c == cid and (sid is None or s == sid) for c, s in mine)


@bp.route("/")
@parent_required
def dashboard():
    schooldb.ensure()
    kids, child = _child()
    ann = [a for a in db.query("SELECT id, title, body, classId, sectionId, created_at FROM sl_announcement WHERE deleted=0 ORDER BY id DESC LIMIT 30") if _audience_ok(a["classId"], a["sectionId"])][:4]
    events = db.query("SELECT * FROM sl_event WHERE deleted=0 AND COALESCE(end_date, start_date)>=CURDATE() ORDER BY start_date LIMIT 4")
    stats = {}
    for k in kids:
        r = db.one("SELECT COUNT(*) t, SUM(status IN ('P','L')) p FROM sl_attendance WHERE studentId=%s AND att_date>=DATE_SUB(CURDATE(), INTERVAL 30 DAY)", (k["studentId"],))
        stats[k["studentId"]] = dict(att=(round(int(r["p"] or 0) * 100 / r["t"]) if r and r["t"] else None), released=_released(k["studentId"]))
    return render_template("pp_dashboard.html", kids=kids, child=child, ann=ann, events=events, stats=stats)


@bp.route("/card")
@parent_required
def card():
    kids, child = _child()
    if not child:
        abort(404)
    if not _released(child["studentId"]):
        return render_template("pp_card.html", kids=kids, child=child, released=False)
    return render_template("pp_card.html", kids=kids, child=child, released=True)


@bp.route("/card/view/<int:sid>")
@parent_required
def card_view(sid):
    if sid not in {k["studentId"] for k in my_children()} or not _released(sid):
        abort(403)
    from .reports import CARD_PAGE, pdf_response, render_view, with_page_css
    built = reportcard.build(sid)
    if not built:
        abort(404)
    html = render_view(built[0], built[1])
    if request.args.get("pdf"):
        return pdf_response(html, f"report_card_{sid}.pdf", CARD_PAGE, scale=0.7)
    return html


@bp.route("/attendance")
@parent_required
def attendance():
    schooldb.ensure()
    kids, child = _child()
    month = request.args.get("month") or dt.date.today().strftime("%Y-%m")
    try:
        first = dt.date.fromisoformat(month + "-01")
    except ValueError:
        first = dt.date.today().replace(day=1)
    nxt = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    days, summary = {}, None
    if child:
        for r in db.query("SELECT att_date, status FROM sl_attendance WHERE studentId=%s AND att_date>=%s AND att_date<%s", (child["studentId"], first, nxt)):
            days[r["att_date"].day] = r["status"]
        t = len(days); pr = sum(1 for v in days.values() if v in ("P", "L"))
        summary = dict(total=t, present=pr, absent=sum(1 for v in days.values() if v == "A"), pct=round(pr * 100 / t) if t else None)
    sessions = db.query("SELECT e.exam_name, sc.totalSession, sc.attendSession FROM studentComment sc JOIN exams e ON e.examId=sc.examId WHERE sc.studentId=%s AND sc.isDelete='0' AND sc.totalSession IS NOT NULL ORDER BY e.examId", (child["studentId"],)) if child else []
    return render_template("pp_attendance.html", kids=kids, child=child, first=first, days=days, summary=summary, sessions=sessions,
                           prev=(first - dt.timedelta(days=1)).strftime("%Y-%m"), nxt=nxt.strftime("%Y-%m"), last=(nxt - first).days)


@bp.route("/work")
@parent_required
def work():
    schooldb.ensure()
    kids, child = _child()
    rows = []
    if child:
        rows = db.query("SELECT w.*, sb.subject_name FROM sl_work w JOIN subjects sb ON sb.subjectId=w.subjectId WHERE w.deleted=0 AND w.classId=%s AND w.sectionId=%s ORDER BY w.work_date DESC, w.id DESC LIMIT 60",
                        (child["class_id"], child["section_id"]))
        att = schooldb.attachments("work", [r["id"] for r in rows])
        for r in rows: r["files"] = att.get(r["id"], [])
    return render_template("pp_work.html", kids=kids, child=child, rows=rows, kind=request.args.get("kind", ""))


@bp.route("/announcements")
@parent_required
def announcements():
    schooldb.ensure()
    rows = [a for a in db.query("SELECT a.*, u.fname AS author FROM sl_announcement a LEFT JOIN new_users u ON u.id=a.created_by WHERE a.deleted=0 ORDER BY a.id DESC LIMIT 100") if _audience_ok(a["classId"], a["sectionId"])]
    att = schooldb.attachments("announcement", [r["id"] for r in rows])
    for r in rows: r["files"] = att.get(r["id"], [])
    return render_template("pp_announcements.html", **_ctx(rows=rows))


@bp.route("/events")
@parent_required
def events():
    schooldb.ensure(); today = dt.date.today()
    rows = db.query("SELECT * FROM sl_event WHERE deleted=0 ORDER BY start_date")
    return render_template("pp_events.html", **_ctx(upcoming=[r for r in rows if (r["end_date"] or r["start_date"]) >= today], past=[r for r in rows if (r["end_date"] or r["start_date"]) < today][::-1][:20]))


@bp.route("/gallery")
@parent_required
def gallery():
    schooldb.ensure()
    albums = [a for a in db.query("SELECT * FROM sl_album WHERE deleted=0 ORDER BY id DESC LIMIT 60") if _audience_ok(a["classId"], a["sectionId"])]
    att = schooldb.attachments("album", [a["id"] for a in albums])
    for a in albums: a["files"] = [f for f in att.get(a["id"], []) if f["is_image"]]
    return render_template("pp_gallery.html", **_ctx(albums=albums))


@bp.route("/timetable")
@parent_required
def timetable():
    schooldb.ensure()
    kids, child = _child()
    cells, periods = {}, 8
    if child:
        for r in db.query("SELECT t.*, sb.subject_name, TRIM(CONCAT_WS(' ', th.fname, th.lname)) AS teacher FROM sl_timetable t LEFT JOIN subjects sb ON sb.subjectId=t.subjectId LEFT JOIN teachers th ON th.user_id=t.teacherId "
                          "WHERE t.classId=%s AND t.sectionId=%s", (child["class_id"], child["section_id"])):
            cells[(r["weekday"], r["period"])] = r; periods = max(periods, r["period"])
    return render_template("pp_timetable.html", kids=kids, child=child, cells=cells, periods=periods, days=WEEKDAYS)


@bp.route("/teachers")
@parent_required
def teachers():
    kids, child = _child()
    rows = []
    if child:
        rows = db.query("""SELECT TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) AS name, t.phone_1, GROUP_CONCAT(DISTINCT sb.subject_name ORDER BY sb.subject_name SEPARATOR ', ') AS subjects,
            MAX(ct.id IS NOT NULL) AS is_class_teacher FROM assign_teacher a JOIN teachers t ON t.user_id=a.t_id JOIN subjects sb ON sb.subjectId=a.subjectId
            LEFT JOIN classTeacher ct ON ct.teacherId=a.t_id AND ct.classId=a.classId AND ct.sectionId=a.sectionId AND ct.isDelete='0'
            WHERE a.isDelete='0' AND a.classId=%s AND a.sectionId=%s GROUP BY a.t_id, t.fname, t.mname, t.lname, t.phone_1 ORDER BY is_class_teacher DESC, name""", (child["class_id"], child["section_id"]))
    return render_template("pp_teachers.html", kids=kids, child=child, rows=rows)


@bp.route("/leave", methods=["GET", "POST"])
@parent_required
def leave():
    schooldb.ensure(); u = current_user()
    kids, child = _child()
    if request.method == "POST":
        sid = to_int(request.form.get("student_id"))
        if sid not in {k["studentId"] for k in kids}:
            abort(403)
        try:
            a, b = dt.date.fromisoformat(request.form.get("from_date", "")), dt.date.fromisoformat(request.form.get("to_date", ""))
            if b < a: raise ValueError
        except ValueError:
            flash("Choose valid dates (the last day cannot be before the first day).", "error"); return redirect(url_for("parentpanel.leave"))
        reason = request.form.get("reason", "").strip()
        if not reason:
            flash("Please write the reason.", "error"); return redirect(url_for("parentpanel.leave"))
        db.execute("INSERT INTO sl_leave (studentId, parent_user, from_date, to_date, reason) VALUES (%s,%s,%s,%s,%s)", (sid, u["id"], a, b, reason[:500]))
        st = next(k for k in kids if k["studentId"] == sid)
        from ..services import features
        ids = [r["teacherId"] for r in db.query("SELECT teacherId FROM classTeacher WHERE classId=%s AND sectionId=%s AND isDelete='0'", (st["class_id"], st["section_id"]))] + N.admin_ids()
        N.notify(ids, f"Leave request: {st['student_name']}", f"{a:%d %b} – {b:%d %b} · {reason[:80]}", url_for("leave.staff_list"))
        flash("Leave request sent to the class teacher.", "success")
        return redirect(url_for("parentpanel.leave"))
    rows = db.query("SELECT l.*, s.student_name FROM sl_leave l JOIN students s ON s.studentId=l.studentId WHERE l.parent_user=%s ORDER BY l.id DESC LIMIT 50", (u["id"],))
    return render_template("pp_leave.html", kids=kids, child=child, rows=rows, today=dt.date.today())
