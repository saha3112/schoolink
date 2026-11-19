"""Tabulation sheet, weighted average sheet and report cards (HTML view + PDF export)."""
import importlib
import os
import re
import subprocess
import tempfile

from flask import (Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for)
from .. import db
from ..auth import current_user, login_required, roles_required, admin_required
from ..services import access, bulk, features, layouts, reportcard, reportdata
from ..utils import to_int

bp = Blueprint("reports", __name__, url_prefix="/reports")
cap = roles_required("class_teacher")

# Paper formats used for PDF export / printing
SHEET_PAGE = "35in 23in"      # tabulation + weighted average sheets: 23 x 35 inch (landscape)
CARD_PAGE = "A4"              # report cards


def render_view(name, ctx):
    from ..services import profile
    if name.startswith("custom:"):
        from ..services import carddesign
        return carddesign.render(int(name[7:]), ctx)
    mod = importlib.import_module(f"app.views_py.{name}")
    return profile.apply(mod.render(ctx))


def relabel(html):
    """The old sheets said 12x35 / 18x12 in a few labels - the export size is now 23 x 35 inch."""
    html = re.sub(r"\(\s*\d+\s*x\s*\d+\s*Size\s*\)", "(23x35 in)", html)
    return re.sub(r"\b(12|18)x35\b", "23x35", html)


def with_page_css(html, size, scale=None, margin="0.3in"):
    html = relabel(html) if size == SHEET_PAGE else html
    """Force the print page size (the old templates hard-code their own @page rules)."""
    css = f"<style id='page-override'>@page {{ size: {size}; margin: {margin}; }}"
    if scale:
        css += f" html {{ zoom: {scale}; }}"
    css += " @media print { .no-print, .print-btn, .toolbar { display:none !important; } }</style>"
    if "</head>" in html:
        return html.replace("</head>", css + "</head>", 1)
    return css + html


def pdf_response(html, filename, size, scale=None):
    """Render html to PDF with headless Chrome. Relative urls resolve against this server."""
    chrome = current_app.config["CHROME_BIN"]
    if not os.path.exists(chrome):
        abort(501, "PDF export needs Google Chrome (set CHROME_BIN).")
    base = request.host_url
    html = with_page_css(html, size, scale)
    html = re.sub(r"(?i)<head>", f"<head><base href='{base}'>", html, count=1)
    with tempfile.TemporaryDirectory() as d:
        src, out = os.path.join(d, "in.html"), os.path.join(d, "out.pdf")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(html)
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer", "--print-to-pdf-no-header",
                        f"--print-to-pdf={out}", "--virtual-time-budget=4000", "file://" + src],
                       check=True, timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(out, "rb") as fh:
            data = fh.read()
    return Response(data, mimetype="application/pdf", headers={"Content-Disposition": f'{"attachment" if request.args.get("dl") else "inline"}; filename="{filename}"'})


def _check_access(cid, sid):
    u = current_user()
    if u["is_admin"]:
        return
    if (cid, sid) not in {(p["classId"], p["sectionId"]) for p in access.class_pairs(u)}:
        abort(403)


def _picker(need_exam, feature="sheet"):
    u = current_user()
    pairs = features.pairs(feature, u)
    cls, sec, exam = (to_int(request.args.get(k)) for k in ("class_id", "section_id", "exam_id"))
    classes = access.classes_for(pairs)
    cls, sec, exam, sections = access.autopick(pairs, classes, cls, sec, exam, access.exams() if need_exam else None)
    return dict(cls=cls, sec=sec, exam=exam, classes=classes, sections=sections, exams=access.exams())


def _sheet_list(kind):
    """Every section the user may print, grouped by class, for one exam - like the report card list."""
    p = _picker(True)
    exams = access.exams()
    exam = p["exam"] or (exams[0]["examId"] if exams else None)
    secs = bulk.sections_in_scope({(x["classId"], x["sectionId"]) for x in features.pairs("sheet", current_user())}, p["cls"], p["sec"])
    groups = {}
    for cid, cn, sid, sn in secs:
        n = db.scalar("SELECT COUNT(*) FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (cid, sid))
        groups.setdefault((cid, cn), []).append(dict(sid=sid, name=sn, students=n, junior=layouts.is_junior(cid, sid)))
    return render_template("report_index.html", kind=kind, exam=exam, groups=groups, **{k: v for k, v in p.items() if k != "exam"})


# ------------------------------------------------------------------------------ tabulation
@bp.route("/tabulation")
@cap
def tabulation_index():
    return _sheet_list("tabulation")


@bp.route("/tabulation/<int:cid>/<int:sid>/<int:eid>")
@cap
def tabulation(cid, sid, eid):
    _check_access(cid, sid)
    view, ctx = reportdata.tabulation_sheet(cid, sid, eid)
    html = render_view(view, ctx)
    if request.args.get("pdf"):
        return pdf_response(html, f"tabulation_{cid}_{sid}_{eid}.pdf", SHEET_PAGE)
    return with_page_css(html, SHEET_PAGE, margin="0.4in")


# ------------------------------------------------------------------------------ weighted average
@bp.route("/weighted")
@cap
def weighted_index():
    return _sheet_list("weighted")


@bp.route("/weighted/<int:cid>/<int:sid>")
@bp.route("/weighted/<int:cid>/<int:sid>/<int:eid>")
@cap
def weighted(cid, sid, eid=None):
    _check_access(cid, sid)
    if layouts.is_junior(cid, sid):
        if not eid:
            abort(400, "Select an exam for the junior weighted sheet.")
        view, ctx = reportdata.junior_weighted_sheet(cid, sid, eid)
    else:
        view, ctx = reportdata.weighted_sheet(cid, sid)
    html = render_view(view, ctx)
    if request.args.get("pdf"):
        return pdf_response(html, f"weighted_{cid}_{sid}.pdf", SHEET_PAGE)
    return with_page_css(html, SHEET_PAGE, margin="0.4in")


# ------------------------------------------------------------------------------ report cards
def _top_level_divs(body):
    """Split a card body into its top-level <div>...</div> blocks (None if the markup is not just divs)."""
    import re as _re
    parts, depth, start = [], 0, None
    last_end = 0
    for m in _re.finditer(r"(?is)<(/?)div\b[^>]*>", body):
        if m.group(1) == "":
            if depth == 0:
                if body[last_end:m.start()].strip():
                    return None
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                parts.append(body[start:m.end()]); last_end = m.end()
            elif depth < 0:
                return None
    if depth != 0 or body[last_end:].strip():
        return None
    return parts


def combined_cards_html(cid, sid):
    """All report cards of a section in ONE document: the cover page once at the very beginning, then only the
    student report page of every student (each on its own page). None if the section has no card design."""
    import re as _re
    students = db.query("SELECT studentId FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0' ORDER BY student_rollNumber, student_name", (cid, sid))
    head, cover, pages = None, None, []
    for st in students:
        built = reportcard.build(st["studentId"])
        if not built:
            continue
        doc = render_view(built[0], built[1])
        m = _re.search(r"(?is)<body[^>]*>(.*)</body>", doc)
        body = m.group(1) if m else doc
        if head is None:
            h = _re.search(r"(?is)<head>(.*?)</head>", doc)
            head = h.group(1) if h else ""
        blocks = _top_level_divs(body)
        if blocks and len(blocks) == 2:                 # [cover, student report]
            if cover is None:
                cover = blocks[0]
            pages.append(blocks[1])
        else:                                           # unexpected layout: keep the whole card, nothing is lost
            pages.append(body)
    if not pages:
        return None
    out = []
    if cover:
        out.append(f"<div>{cover}</div>")
    for i, pg in enumerate(pages):
        brk = "break-before:page;page-break-before:always;" if (i or cover) else ""
        out.append(f'<div style="{brk}">{pg}</div>')
    return ("<!DOCTYPE html><html lang='en'><head>" + (head or "") + "</head><body style='padding:0;margin:0'>" + "".join(out) + "</body></html>")


@bp.route("/report-cards")
@cap
def report_cards():
    p = _picker(False, "card")
    secs = bulk.sections_in_scope({(x["classId"], x["sectionId"]) for x in features.pairs("card", current_user())}, p["cls"], p["sec"])
    groups = {}
    for cid, cn, sid, sn in secs:
        n = db.scalar("SELECT COUNT(*) FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (cid, sid))
        groups.setdefault((cid, cn), []).append(dict(sid=sid, name=sn, students=n))
    return render_template("report_cards.html", groups=groups, classes=p["classes"], cls=p["cls"])


@bp.route("/section-students")
@cap
def section_students():
    cid, sid = to_int(request.args.get("class_id")), to_int(request.args.get("section_id"))
    _check_access(cid, sid)
    return jsonify([dict(id=r["studentId"], roll=r["student_rollNumber"], name=r["student_name"]) for r in access.students(cid, sid)])


@bp.route("/section-cards/<int:cid>/<int:sid>")
@cap
def section_cards(cid, sid):
    """All report cards of a section as one document / one PDF."""
    _check_access(cid, sid)
    html = combined_cards_html(cid, sid)
    if html is None:
        abort(404)
    if request.args.get("pdf"):
        cn, sn = bulk.safe(class_name_of(cid)), bulk.safe(section_name_of(cid, sid))
        return pdf_response(with_page_css(html, CARD_PAGE, scale=0.7), f"Report Cards - {cn} {sn}.pdf", CARD_PAGE, scale=0.7)
    return with_page_css(html, CARD_PAGE, scale=0.7)


def class_name_of(cid):
    return reportdata.class_name(cid) or f"Class {cid}"


def section_name_of(cid, sid):
    return reportdata.section_name(cid, sid) or str(sid)


@bp.route("/card/<int:student_id>")
@cap
def card(student_id):
    st = db.one("SELECT class_id, section_id FROM students WHERE studentId=%s", (student_id,))
    if not st:
        abort(404)
    _check_access(st["class_id"], st["section_id"])
    built = reportcard.build(student_id)
    if not built:
        abort(404)
    view, ctx = built
    html = render_view(view, ctx)
    if request.args.get("pdf"):
        return pdf_response(html, f"report_card_{student_id}.pdf", CARD_PAGE, scale=0.7)
    return html


# ------------------------------------------------------------------------------ bulk ZIP downloads
def _allowed_pairs():
    u = current_user()
    return None if u["is_admin"] else {(p["classId"], p["sectionId"]) for p in access.class_pairs(u)}


@bp.route("/bulk/start", methods=["POST"])
@cap
def bulk_start():
    kind = request.form.get("kind")
    if kind not in ("cards", "cardbook", "tab", "wtd", "sheets"):
        abort(400)
    cls, sec = to_int(request.form.get("class_id")), to_int(request.form.get("section_id"))
    feat = "card" if kind in ("cards", "cardbook") else "sheet"
    secs = bulk.sections_in_scope({(x["classId"], x["sectionId"]) for x in features.pairs(feat, current_user())}, cls, sec)
    exam_ids = [to_int(x) for x in request.form.getlist("exam_id") if to_int(x)]
    if kind not in ("cards", "cardbook") and not exam_ids:
        exam_ids = [e["examId"] for e in access.exams()]
    items = bulk.plan(kind, secs, exam_ids)
    if not items:
        return jsonify(error="Nothing to download for this selection."), 400
    job = bulk.start(current_app._get_current_object(), kind, items, request.host_url, current_user()["id"])
    return jsonify(id=job["id"], total=job["total"])


def _job_or_404(jid):
    j = bulk.JOBS.get(jid)
    if not j or j["owner"] != current_user()["id"]:
        abort(404)
    return j


@bp.route("/bulk/<jid>/status")
@cap
def bulk_status(jid):
    j = _job_or_404(jid)
    return jsonify(status=j["status"], total=j["total"], done=j["done"], current=j["current"], error=j["error"],
                   skipped=len(j["skipped"]), title=j["title"])


@bp.route("/bulk/<jid>/cancel", methods=["POST"])
@cap
def bulk_cancel(jid):
    _job_or_404(jid)["cancel"] = True
    return jsonify(ok=True)


@bp.route("/bulk/<jid>/download")
@cap
def bulk_download(jid):
    j = _job_or_404(jid)
    if j["status"] not in ("done", "cancelled") or not os.path.exists(j["zip"]):
        abort(409)
    return send_file(j["zip"], as_attachment=True, download_name=j["name"], mimetype="application/zip")


@bp.route("/release", methods=["GET", "POST"])
@admin_required
def release():
    """Release report cards to parents (parents see a card only when it is released)."""
    from ..services import notifications as N
    cls, sec = to_int(request.values.get("class_id")), to_int(request.values.get("section_id"))
    if request.method == "POST" and cls and sec:
        mode = request.form.get("mode")
        ids = [to_int(request.form.get("student_id"))] if request.form.get("student_id") else [r["studentId"] for r in access.students(cls, sec)]
        on = "1" if mode in ("release", "release_one") else "0"
        n = 0
        for sid in ids:
            st = db.one("SELECT studentId, student_id, student_code, parent_id FROM students WHERE studentId=%s AND class_id=%s AND section_id=%s", (sid, cls, sec))
            if not st:
                continue
            ex = db.one("SELECT id, isOpen FROM releaseResult WHERE studentId=%s AND documentName='report_card'", (sid,))
            if ex:
                if ex["isOpen"] != on:
                    db.execute("UPDATE releaseResult SET isOpen=%s, openAt=IF(%s='1', NOW(), openAt) WHERE id=%s", (on, on, ex["id"]), commit=False); changed = True
                else:
                    changed = False
            else:
                db.execute("INSERT INTO releaseResult (studentId, syncStudentId, student_code, documentName, isOpen, openAt) VALUES (%s,%s,%s,'report_card',%s,IF(%s='1', NOW(), NULL))",
                           (sid, st["student_id"], st["student_code"], on, on), commit=False); changed = on == "1"
            if changed:
                n += 1
                if on == "1" and st["parent_id"]:
                    pu = db.scalar("SELECT user_id FROM parents WHERE id=%s", (st["parent_id"],))
                    nm = db.scalar("SELECT student_name FROM students WHERE studentId=%s", (sid,))
                    if pu:
                        N.notify([int(pu)], f"Report card ready: {nm}", "You can view and download it now.", url_for("parentpanel.card", child=sid))
        db.commit()
        flash(f"{n} report card(s) {'released' if on == '1' else 'hidden'}.", "success")
        return redirect(url_for("reports.release", class_id=cls, section_id=sec))
    pairs = features.pairs("card", current_user())
    classes = access.classes_for(pairs)
    cls, sec, _e, sections = access.autopick(pairs, classes, cls, sec, None)
    rows = []
    if cls and sec:
        rel = {r["studentId"]: r for r in db.query("SELECT studentId, isOpen, openAt FROM releaseResult WHERE documentName='report_card'")}
        for s_ in access.students(cls, sec):
            r = rel.get(s_["studentId"]); s_["released"] = bool(r and r["isOpen"] == "1"); s_["openAt"] = r["openAt"] if r else None; rows.append(s_)
    return render_template("release.html", cls=cls, sec=sec, classes=classes, sections=sections, rows=rows)
