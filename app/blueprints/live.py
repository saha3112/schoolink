"""Polling endpoint used by static/js/live.js."""
from flask import Blueprint, jsonify, request
from ..auth import login_required
from ..services import live
from ..utils import to_int

bp = Blueprint("live", __name__, url_prefix="/live")


@bp.route("/poll")
@login_required
def poll():
    last = to_int(request.args.get("since"), 0)
    if last < 0:                                   # "what is the newest event right now?"
        return jsonify(last=live.latest(), events=[])
    topics = {t for t in (request.args.get("topics") or "").split(",") if t}          # optional filter
    ev = live.since(last)
    new_last = max([e["id"] for e in ev], default=last)
    return jsonify(last=new_last, events=[dict(id=e["id"], t=e["topic"], c=e["class_id"], s=e["section_id"], e=e["exam_id"], a=e["actor"])
                                          for e in ev if not topics or e["topic"] in topics])
