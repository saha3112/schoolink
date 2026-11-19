"""Media library API + the pop-up's files (see services/media.py for the rules)."""
from flask import Blueprint, Response, abort, jsonify, render_template, request, url_for
from ..auth import current_user, login_required
from ..services import media as M
from ..utils import to_int

bp = Blueprint("media", __name__, url_prefix="/media")


def _staff():
    u = current_user()
    if not (u["is_admin"] or u["is_teacher"]):
        abort(403)
    return u


def _item(u, r, allow_staff):
    return {
        "id": r["id"], "name": r["name"], "ext": r["ext"], "kind": r["kind"], "size": r["size"], "size_h": M.human(r["size"]),
        "uploader": r.get("uploader") or "", "mine": r["uploaded_by"] == u["id"],
        "date": r["uploaded_at"].strftime("%d %b %Y, %H:%M") if r.get("uploaded_at") else "",
        "deleted": r["deleted_at"].strftime("%d %b %Y, %H:%M") if r.get("deleted_at") else None,
        "url": url_for("media.view", mid=r["id"]), "dl": url_for("media.view", mid=r["id"], dl=1),
        "thumb": url_for("media.thumb", mid=r["id"]) if r["kind"] == "image" else None,
        "can_purge": M.can_purge(u, {"uploaded_by": r["uploaded_by"]}, allow_staff),
    }


@bp.route("/")
@login_required
def library():
    _staff()
    return render_template("media_library.html")


@bp.route("/api/list")
@login_required
def api_list():
    u = _staff()
    ids = [i for i in (to_int(x) for x in (request.args.get("ids") or "").split(",")) if i]
    tab = "trash" if request.args.get("tab") == "trash" else "library"
    kind = request.args.get("kind") if request.args.get("kind") in ("image", "file") else "all"
    rows, total, page, pages = M.listing(u, tab, kind, (request.args.get("q") or "").strip()[:80], to_int(request.args.get("page"), 1) or 1,
                                         min(to_int(request.args.get("per"), 10) or 10, 50), ids or None)
    allow = M.staff_may_purge()
    lib, trash = M.counts(u)
    return jsonify(items=[_item(u, r, allow) for r in rows], total=total, page=page, pages=pages, library=lib, trash=trash,
                   admin=bool(u["is_admin"]), staff_purge=allow)


@bp.route("/api/upload", methods=["POST"])
@login_required
def api_upload():
    u = _staff()
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return jsonify(ok=False, error="Choose at least one file.", items=[], errors=[]), 400
    if len(files) > M.MAX_BATCH:
        return jsonify(ok=False, error=f"Upload at most {M.MAX_BATCH} files at a time.", items=[], errors=[]), 400
    allow = M.staff_may_purge()
    items, errors = [], []
    for f in files:
        row, err = M.add(u, f.filename, f.read(M.MAX_FILE + 1))
        if err:
            errors.append(err)
        else:
            items.append(_item(u, row, allow))
    return jsonify(ok=bool(items), items=items, errors=errors,
                   message=(f"{len(items)} file{'s' if len(items) != 1 else ''} uploaded." if items else "Nothing was uploaded."))


@bp.route("/api/action", methods=["POST"])
@login_required
def api_action():
    u = _staff()
    data = request.get_json(silent=True) or request.form
    ids = [i for i in (to_int(x) for x in (data.getlist("ids") if hasattr(data, "getlist") else data.get("ids", []))) if i]
    act = data.get("action")
    if not ids:
        return jsonify(ok=False, message="Select at least one file."), 400
    if act == "remove":
        n = M.remove(u, ids)
        return jsonify(ok=True, count=n, message=f"{n} file{'s' if n != 1 else ''} moved to Trash.")
    if act == "restore":
        n = M.restore(u, ids)
        return jsonify(ok=True, count=n, message=f"{n} file{'s' if n != 1 else ''} restored.")
    if act == "purge":
        n, refused = M.purge(u, ids)
        if refused and not n:
            return jsonify(ok=False, message="You do not have permission to delete files permanently. Ask an administrator."), 403
        if not n:
            return jsonify(ok=False, message="Nothing was deleted - the file is not in your Trash."), 404
        msg = f"{n} file{'s' if n != 1 else ''} deleted permanently."
        if refused:
            msg += f" {refused} could not be deleted (no permission)."
        return jsonify(ok=True, count=n, message=msg)
    return jsonify(ok=False, message="Unknown action."), 400


def _row_or_404(mid):
    u = current_user()
    r = M.get(mid)
    if not r or not M.can_see(u, r):
        abort(404)
    return r


@bp.route("/f/<int:mid>")
@login_required
def view(mid):
    r = _row_or_404(mid)
    f = M.file_bytes(r)
    if not f:
        abort(404)
    disp = "attachment" if request.args.get("dl") else "inline"
    return Response(f["data"], mimetype=f["mime"] or "application/octet-stream",
                    headers={"Content-Disposition": f'{disp}; filename="{r["name"]}"', "Cache-Control": "private, max-age=600"})


@bp.route("/t/<int:mid>")
@login_required
def thumb(mid):
    r = _row_or_404(mid)
    f = M.file_bytes(r, thumb=True)
    if not f:
        abort(404)
    return Response(f["data"], mimetype=f["mime"] or "image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
