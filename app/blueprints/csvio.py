"""CSV import (marks, attendance, comments, ranks, house points, development skills, average, students) + sample files."""
from flask import Blueprint, Response, jsonify, request
from ..auth import current_user, login_required
from ..services import csvio as C

bp = Blueprint("csvio", __name__, url_prefix="/csv")


def _ctx(kind):
    u = current_user()
    if not (u["is_admin"] or u["is_teacher"]):
        raise PermissionError("Not allowed.")
    return C.context(u, kind, request.values)


@bp.route("/sample/<kind>")
@login_required
def sample(kind):
    try:
        ctx = _ctx(kind)
        h, rows = C.sample(ctx, blank=bool(request.args.get("blank")))
    except PermissionError as e:
        return jsonify(ok=False, message=str(e)), 403
    except C.CsvError as e:
        return jsonify(ok=False, message=str(e)), 400
    name = C.file_name(ctx).replace(".csv", "") + ("_template" if request.args.get("blank") else "_sample") + ".csv"
    return Response(C.to_csv_bytes(h, rows), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@bp.route("/import/<kind>", methods=["POST"])
@login_required
def do_import(kind):
    f = request.files.get("file")
    try:
        ctx = _ctx(kind)
        if not f or not f.filename:
            raise C.CsvError("Choose a CSV file first.")
        if not f.filename.lower().endswith((".csv", ".txt")):
            raise C.CsvError("Please choose a .csv file.")
        res = C.run_import(ctx, f.read(C.MAX_BYTES + 1))          # read into memory only - the upload is never written anywhere
        return jsonify(res), (200 if res["ok"] else 422)
    except PermissionError as e:
        return jsonify(ok=False, message=str(e), errors=[], warnings=[]), 403
    except C.CsvError as e:
        return jsonify(ok=False, message=str(e), errors=[], warnings=[]), 400
    except Exception:                                              # never leak internals; nothing half-written
        from .. import db
        db.rollback()
        return jsonify(ok=False, message="Something went wrong while reading the file. Nothing was imported.", errors=[], warnings=[]), 500
