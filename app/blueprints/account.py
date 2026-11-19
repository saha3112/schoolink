from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from .. import db
from ..auth import login_required, admin_required, current_user, hash_password
from ..services import notifications as N
from ..utils import paginate, page_arg

bp = Blueprint("account", __name__, url_prefix="/account")


@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    """Any signed in user may change their own password. No old password is asked."""
    if request.method == "POST":
        new = request.form.get("new_password", "")
        conf = request.form.get("confirm_password", "")
        if len(new) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif new != conf:
            flash("The two passwords do not match.", "error")
        else:
            db.execute("UPDATE new_users SET password=%s WHERE id=%s", (hash_password(new), current_user()["id"]))
            flash("Password changed successfully.", "success")
            return redirect(url_for("account.change_password"))
    return render_template("change_password.html")


@bp.route("/users")
@admin_required
def users():
    q = request.args.get("q", "").strip()
    where, args = "WHERE deleted_at IS NULL AND user_type IN ('0','1','2','9')", []
    if q:
        where += " AND (fname LIKE %s OR email LIKE %s)"
        args += [f"%{q}%"] * 2
    total = db.scalar(f"SELECT COUNT(*) FROM new_users {where}", args)
    p = paginate(total, 20, page_arg())
    rows = db.query(f"SELECT id, fname, email, user_type, active FROM new_users {where} "
                    f"ORDER BY user_type, fname LIMIT %s OFFSET %s", args + [p["per_page"], p["offset"]])
    return render_template("users.html", rows=rows, p=p, q=q)


@bp.route("/users/<int:uid>/reset", methods=["POST"])
@admin_required
def reset_password(uid):
    new = request.form.get("new_password", "")
    if len(new) < 6:
        flash("Password must be at least 6 characters.", "error")
    else:
        db.execute("UPDATE new_users SET password=%s WHERE id=%s", (hash_password(new), uid))
        N.notify([uid], "Your password was changed by an administrator", "Use the new password the next time you sign in.", url_for("account.change_password"))
        flash("Password updated.", "success")
    return redirect(request.referrer or url_for("account.users"))
