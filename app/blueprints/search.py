"""Top bar live search (admin / super admin / teacher)."""
from flask import Blueprint, abort, jsonify, request
from ..auth import current_user, login_required
from ..services import search as S

bp = Blueprint("search", __name__, url_prefix="/search")


@bp.route("/api")
@login_required
def api():
    u = current_user()
    if not (u["is_admin"] or u["is_teacher"]):
        abort(403)
    return jsonify(S.run(u, request.args.get("q", "")))
