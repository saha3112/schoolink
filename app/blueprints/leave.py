"""Leave requests sent by parents; class teachers and admins approve or reject them."""
import datetime as dt

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import db
from ..auth import current_user, roles_required
from ..services import access, notifications as N, schooldb
from ..utils import to_int

bp = Blueprint("leave", __name__, url_prefix="/leave")
cap = roles_required("class_teacher")


@bp.route("/", methods=["GET", "POST"])
@cap
def staff_list():
    schooldb.ensure(); u = current_user()
    scope = None if u["is_admin"] else {(p["classId"], p["sectionId"]) for p in access.class_pairs(u)}
    if request.method == "POST":
        r = db.one("SELECT l.*, s.class_id, s.section_id, s.student_name FROM sl_leave l JOIN students s ON s.studentId=l.studentId WHERE l.id=%s", (to_int(request.form.get("id")),))
        if not r or (scope is not None and (r["class_id"], r["section_id"]) not in scope):
            abort(403)
        dec = "approved" if request.form.get("action") == "approve" else "rejected"
        db.execute("UPDATE sl_leave SET status=%s, decided_by=%s, decided_at=NOW(), note=%s WHERE id=%s", (dec, u["id"], request.form.get("note", "").strip()[:300] or None, r["id"]))
        N.notify([r["parent_user"]], f"Leave {dec}: {r['student_name']}", f"{r['from_date']:%d %b} – {r['to_date']:%d %b}", url_for("parentpanel.leave"))
        flash(f"Leave {dec}.", "success")
        return redirect(url_for("leave.staff_list", status=request.args.get("status", "")))
    status = request.args.get("status", "pending")
    where, args = "WHERE 1=1", []
    if status in ("pending", "approved", "rejected"):
        where += " AND l.status=%s"; args.append(status)
    rows = db.query(f"SELECT l.*, s.student_name, s.student_rollNumber, s.class_id, s.section_id, c.class_name, sc.section_name FROM sl_leave l JOIN students s ON s.studentId=l.studentId "
                    f"JOIN classes c ON c.classId=s.class_id JOIN sections sc ON sc.sectionId=s.section_id {where} ORDER BY l.id DESC LIMIT 200", args)
    if scope is not None:
        rows = [r for r in rows if (r["class_id"], r["section_id"]) in scope]
    return render_template("leave_staff.html", rows=rows, status=status)
