from flask import Blueprint, Response, abort, render_template, request, redirect, url_for, session, flash, jsonify
from .. import db
from ..auth import verify_password, current_user, login_required, ADMIN_TYPES, TEACHER_TYPES, teacher_scope

bp = Blueprint("main", __name__)
auth_bp = Blueprint("auth", __name__)
notify_bp = Blueprint("notify", __name__, url_prefix="/notifications")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        pw = request.form.get("password", "")
        u = db.one("SELECT id, email, password, user_type, active FROM new_users "
                   "WHERE email=%s AND deleted_at IS NULL", (email,))
        if u and str(u["active"]) == "1" and verify_password(pw, u["password"]):
            session.clear()
            session.permanent = request.form.get("remember") == "1"
            session["uid"] = u["id"]
            from ..services import user_access as UA
            access = UA.record(u['id'])
            session['auth_version'] = access['session_version'] if access else 0
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("main.dashboard"))
        flash("Invalid email/mobile or password.", "error")
    from ..services import loginpage as LP
    return render_template("login.html", lp=LP.view())


@auth_bp.route("/brand/login/<slot>")
def brand_image(slot):
    """Pictures chosen for the sign-in page (logo, illustration, background). Public: the sign-in page needs them before anyone is logged in."""
    from ..services import filestore, loginpage as LP
    if slot not in LP.IMAGE_SLOTS:
        abort(404)
    f = filestore.get(f"login/{slot}")
    if not f:
        abort(404)
    resp = Response(f["data"], mimetype=f["mime"] if f["mime"] in ("image/png", "image/jpeg", "image/webp", "image/gif") else "image/png")
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable" if request.args.get("v") else "public, max-age=300"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/")
def index():
    return redirect(url_for("main.dashboard"))


@bp.route("/dashboard")
@login_required
def dashboard():
    u = current_user()
    if u.get("is_parent"):
        return redirect(url_for("parentpanel.dashboard"))
    from ..services import user_access as UA
    full_overview = u["is_admin"] and not UA.restricted(u)
    stats = {}
    if full_overview:
        stats = {
            "Classes": db.scalar("SELECT COUNT(*) FROM classes WHERE isDelete='0'"),
            "Sections": db.scalar("SELECT COUNT(*) FROM sections WHERE isDelete='0'"),
            "Students": db.scalar("SELECT COUNT(*) FROM students WHERE isDelete='0'"),
            "Subjects": db.scalar("SELECT COUNT(*) FROM subjects WHERE isDelete='0'"),
            "Teachers": db.scalar("SELECT COUNT(*) FROM teachers"),
        }
    dash = None
    if full_overview:
        from ..services import dashstats as D
        exs = D.exams()
        sel = request.args.get("exam", type=int)
        if sel not in [e["examId"] for e in exs]:
            sel = exs[0]["examId"] if exs else 0
        dash = D.all_for(sel)
        dash["exams"], dash["exam"] = exs, sel
    mine = None
    if u["is_teacher"]:
        mine = db.query("""
            SELECT c.class_name, s.section_name, GROUP_CONCAT(DISTINCT sb.subject_name ORDER BY sb.subject_name SEPARATOR ', ') subjects
            FROM assign_teacher a
            JOIN classes c ON c.classId=a.classId JOIN sections s ON s.sectionId=a.sectionId
            JOIN subjects sb ON sb.subjectId=a.subjectId
            WHERE a.t_id=%s AND a.isDelete='0' GROUP BY a.classId, a.sectionId, c.class_name, s.section_name
            ORDER BY a.classId, a.sectionId""", (u["id"],))
        ct = db.query("""SELECT c.class_name, s.section_name FROM classTeacher t
            JOIN classes c ON c.classId=t.classId JOIN sections s ON s.sectionId=t.sectionId
            WHERE t.teacherId=%s AND t.isDelete='0'""", (u["id"],))
    else:
        ct = []
    return render_template("dashboard.html", stats=stats, dash=dash, mine=mine, class_teacher_of=ct)


# ------------------------------------------------------------------------------ notification bell
@notify_bp.route("/")
@login_required
def nlist():
    from ..services import notifications as N
    uid = current_user()["id"]
    return jsonify(unread=N.unread(uid), items=N.for_user(uid))


@notify_bp.route("/count")
@login_required
def ncount():
    from ..services import notifications as N
    return jsonify(unread=N.unread(current_user()["id"]))


@notify_bp.route("/read", methods=["POST"])
@login_required
def nread():
    from ..services import notifications as N
    N.ensure()
    nid = request.form.get("id")
    if nid and nid.isdigit():
        db.execute("UPDATE sl_notification SET is_read=1 WHERE id=%s AND user_id=%s", (int(nid), current_user()["id"]))
    else:
        db.execute("UPDATE sl_notification SET is_read=1 WHERE user_id=%s", (current_user()["id"],))
    return jsonify(ok=True)


@notify_bp.route("/<int:nid>/delete", methods=["POST"])
@login_required
def ndelete(nid):
    from ..services import notifications as N
    N.ensure()
    db.execute("DELETE FROM sl_notification WHERE id=%s AND user_id=%s", (nid, current_user()["id"]))
    return jsonify(ok=True)


@notify_bp.route("/clear", methods=["POST"])
@login_required
def nclear():
    from ..services import notifications as N
    N.ensure()
    db.execute("DELETE FROM sl_notification WHERE user_id=%s", (current_user()["id"],))
    return jsonify(ok=True)
