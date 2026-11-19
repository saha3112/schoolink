"""Principal / HOD / class teacher signatures: upload, replace, remove, history & restore (admin only).

Files are stored in the database (services/filestore.py) - nothing is written to disk. They are served from
/static/assets/signature/<path> so the report card templates keep working unchanged."""
import io
import time

from flask import Blueprint, Response, abort, render_template, request, redirect, url_for, flash
from PIL import Image, ImageOps

from .. import db
from ..auth import admin_required, current_user
from ..services import filestore, notifications as N
from ..utils import to_int

bp = Blueprint("signatures", __name__)           # file serving route lives at the site root
admin_bp = Blueprint("signatures_admin", __name__, url_prefix="/signatures")

FIXED = {
    "principal": dict(label="Principal", note="Printed on every report card", path="PRINCIPAL_SIGNATURE_new.png"),
    "hod": dict(label="HOD (classes I – V)", note="Printed on the junior (I – V) report cards", path="HOD_SIGNATURE/Adobe_Scan.png"),
}
MAX_BYTES = 3 * 1024 * 1024
PREFIX = "signature/"


def _chosen_image():
    """The signature image chosen in the media library pop-up (media_id), or a classic file upload."""
    from ..services import media
    mid = to_int(request.form.get("media_id"))
    if mid:
        got = media.take(current_user(), [mid])
        if got and got[0][1] in media.IMAGES:
            return got[0][2]
        raise ValueError("Choose an image from the library first.")
    f = request.files.get("file")
    return f.read(MAX_BYTES + 1) if f else b""


def _convert(source):
    raw = source if isinstance(source, (bytes, bytearray)) else (source.read(MAX_BYTES + 1) if source else b"")
    if not raw:
        raise ValueError("Choose an image file first.")
    if len(raw) > MAX_BYTES:
        raise ValueError("Image is larger than 3 MB.")
    try:
        im = Image.open(io.BytesIO(raw)); im.load()
    except Exception:
        raise ValueError("That file is not a valid image (use PNG or JPG).")
    im = ImageOps.exif_transpose(im).convert("RGBA")
    if im.width > 700:
        im = im.resize((700, int(im.height * 700 / im.width)), Image.LANCZOS)
    out = io.BytesIO(); im.save(out, "PNG", optimize=True)
    return out.getvalue()


def _url(rel):
    v = filestore.version(PREFIX + rel)
    return url_for("signatures.serve", name=rel) + f"?v={v}" if v else None


@bp.route("/static/assets/signature/<path:name>")
def serve(name):
    """Signature files for the report cards (and the admin page). ?download=1 forces a download."""
    f = filestore.get(PREFIX + name)
    if not f:
        abort(404)
    h = {"Cache-Control": "public, max-age=3600", "ETag": f['sha1']}
    if request.args.get("download"):
        h["Content-Disposition"] = f'attachment; filename="{name.split("/")[-1]}"'
    return Response(f["data"], mimetype=f["mime"], headers=h)


@admin_bp.route("/history/<int:hid>")
@admin_required
def history_file(hid):
    r = db.one("SELECT mime, data FROM app_file_history WHERE id=%s", (hid,))
    if not r:
        abort(404)
    return Response(r["data"], mimetype=r["mime"], headers={"Cache-Control": "private, max-age=600"})


def _hist(tag):
    return [dict(id=h["id"], when=h["when"], url=url_for("signatures_admin.history_file", hid=h["id"])) for h in filestore.history(tag)]


def _teacher_rel(sig):
    return "teacher/" + sig.split("/")[-1] if sig else None


@admin_bp.route("/", methods=["GET", "POST"])
@admin_required
def manage():
    uid = current_user()["id"]
    if request.method == "POST":
        act, kind = request.form.get("action"), request.form.get("kind")
        try:
            if kind in FIXED:
                rel = PREFIX + FIXED[kind]["path"]; tag = kind
                if act in ("upload", "replace"):
                    png = _convert(_chosen_image())
                    filestore.archive(tag, rel, uid); filestore.put(rel, png, uid)
                    flash(f"{FIXED[kind]['label']} signature {'replaced' if act == 'replace' else 'uploaded'}.", "success")
                elif act == "remove":
                    if filestore.archive(tag, rel, uid):
                        filestore.delete(rel)
                        flash(f"{FIXED[kind]['label']} signature removed (kept in history, you can restore it).", "success")
                elif act == "restore":
                    h = filestore.history_get(to_int(request.form.get("hid")), tag)
                    if h:
                        filestore.archive(tag, rel, uid); filestore.put(rel, h["data"], uid)
                        flash("Previous signature restored.", "success")
            elif kind == "teacher":
                tid = to_int(request.form.get("teacher_id"))
                t = db.one("SELECT user_id, signature FROM teachers WHERE user_id=%s", (tid,))
                if not t:
                    raise ValueError("Teacher not found.")
                tag = f"teacher{tid}"
                cur = PREFIX + _teacher_rel(t["signature"]) if t["signature"] else None
                if act in ("upload", "replace"):
                    png = _convert(_chosen_image())
                    name = f"teacher_{tid}_{int(time.time())}.png"
                    if cur:
                        filestore.archive(tag, cur, uid)
                    filestore.put(PREFIX + "teacher/" + name, png, uid)
                    db.execute("UPDATE teachers SET signature=%s WHERE user_id=%s", (name, tid))
                    N.notify([tid], "Your signature was updated", "It will appear on your class report cards.", exclude=uid)
                    flash("Signature saved.", "success")
                elif act == "remove":
                    if cur:
                        filestore.archive(tag, cur, uid)
                    db.execute("UPDATE teachers SET signature='' WHERE user_id=%s", (tid,))
                    flash("Signature removed (kept in history, you can restore it).", "success")
                elif act == "restore":
                    h = filestore.history_get(to_int(request.form.get("hid")), tag)
                    if h:
                        name = f"teacher_{tid}_{int(time.time())}.png"
                        filestore.put(PREFIX + "teacher/" + name, h["data"], uid)
                        db.execute("UPDATE teachers SET signature=%s WHERE user_id=%s", (name, tid))
                        flash("Previous signature restored.", "success")
        except ValueError as e:
            flash(str(e), "error")
        return redirect(request.referrer or url_for("signatures_admin.manage"))

    fixed = [dict(kind=k, label=v["label"], note=v["note"], url=_url(v["path"]), history=_hist(k)) for k, v in FIXED.items()]
    q, cls, status = request.args.get("q", "").strip(), to_int(request.args.get("class_id")), request.args.get("status", "")
    rows = db.query("""
        SELECT t.user_id, TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) AS name, t.signature,
               GROUP_CONCAT(DISTINCT CONCAT(c.class_name, ' ', s.section_name) ORDER BY c.classId, s.section_name SEPARATOR ', ') AS sections,
               MIN(ct.classId) AS first_class
        FROM teachers t JOIN classTeacher ct ON ct.teacherId=t.user_id AND ct.isDelete='0'
        JOIN classes c ON c.classId=ct.classId JOIN sections s ON s.sectionId=ct.sectionId
        GROUP BY t.user_id, t.fname, t.mname, t.lname, t.signature ORDER BY first_class, name""")
    teachers, done = [], 0
    for r in rows:
        rel = _teacher_rel(r["signature"])
        has = bool(rel and filestore.exists(PREFIX + rel))
        done += has
        r.update(has=has, url=_url(rel) if has else None, missing_file=bool(rel and not has), history=_hist(f"teacher{r['user_id']}"))
        if q and q.lower() not in (r["name"] + " " + (r["sections"] or "")).lower():
            continue
        if cls and not db.one("SELECT 1 FROM classTeacher WHERE teacherId=%s AND classId=%s AND isDelete='0'", (r["user_id"], cls)):
            continue
        if (status == "uploaded" and not has) or (status == "missing" and has):
            continue
        teachers.append(r)
    classes = db.query("SELECT classId, class_name FROM classes WHERE isDelete='0' ORDER BY classId")
    return render_template("signatures.html", fixed=fixed, teachers=teachers, stats=dict(total=len(rows), done=done), q=q, cls=cls, status=status, classes=classes)
