"""Background ZIP builders: all report cards / all sheets, organised as Class / Section folders."""
import os
import re
import tempfile
import threading
import time
import traceback
import uuid
import zipfile

from .. import db
from . import layouts, reportcard, reportdata
from .pdfgen import ChromePdf

JOBS = {}
LOCK = threading.Lock()
RUN_LOCK = threading.Lock()                      # one Chrome job at a time
OUT_DIR = os.path.join(tempfile.gettempdir(), "schoolink_bulk")
KEEP_SECONDS = 3600


def safe(name):
    return re.sub(r"[^\w\-\. ()&]+", "_", str(name or "").strip()).strip(" ._") or "x"


def _cleanup():
    os.makedirs(OUT_DIR, exist_ok=True)
    now = time.time()
    for f in os.listdir(OUT_DIR):
        p = os.path.join(OUT_DIR, f)
        try:
            if now - os.path.getmtime(p) > KEEP_SECONDS:
                os.remove(p)
        except OSError:
            pass
    with LOCK:
        for k in [k for k, j in JOBS.items() if now - j["created"] > KEEP_SECONDS]:
            JOBS.pop(k, None)


def sections_in_scope(allowed_pairs, class_id=None, section_id=None):
    """[(classId, class_name, sectionId, section_name)] limited to allowed pairs (None = everything) that have students."""
    rows = db.query("SELECT c.classId, c.class_name, s.sectionId, s.section_name FROM sections s JOIN classes c ON c.classId=s.class_id "
                    "WHERE s.isDelete='0' AND c.isDelete='0' AND EXISTS (SELECT 1 FROM students st WHERE st.class_id=c.classId "
                    "AND st.section_id=s.sectionId AND st.isDelete='0') ORDER BY c.classId, s.section_name")
    out = []
    for r in rows:
        if class_id and r["classId"] != class_id:
            continue
        if section_id and r["sectionId"] != section_id:
            continue
        if allowed_pairs is not None and (r["classId"], r["sectionId"]) not in allowed_pairs:
            continue
        out.append((r["classId"], r["class_name"], r["sectionId"], r["section_name"]))
    return out


def plan(kind, secs, exam_ids):
    """List of work items: (zip path, label, callable-spec)"""
    items = []
    if kind == "cardbook":      # one combined PDF per section
        for cid, cn, sid, sn in secs:
            items.append(dict(path=f"{safe(cn)}/Section {safe(sn)}/All Report Cards - {safe(cn)} {safe(sn)}.pdf", label=f"{cn} {sn} · all report cards (one PDF)", kind="cardbook", cid=cid, sid=sid))
    elif kind == "cards":
        for cid, cn, sid, sn in secs:
            for st in db.query("SELECT studentId, student_name, student_rollNumber FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0' "
                               "ORDER BY student_rollNumber, student_name", (cid, sid)):
                fn = f"{int(st['student_rollNumber'] or 0):02d} - {safe(st['student_name'])}.pdf"
                items.append(dict(path=f"{safe(cn)}/Section {safe(sn)}/{fn}", label=f"{cn} {sn} · {st['student_name']}", kind="card", student=st["studentId"]))
    else:
        exams = {e["examId"]: e["exam_name"] for e in db.query("SELECT examId, exam_name FROM exams WHERE isDelete='0' ORDER BY examId")}
        want_tab, want_wtd = kind in ("tab", "sheets"), kind in ("wtd", "sheets")
        for cid, cn, sid, sn in secs:
            base = f"{safe(cn)}/Section {safe(sn)}"
            for eid in exam_ids:
                if eid not in exams or not want_tab:
                    continue
                items.append(dict(path=f"{base}/Tabulation Sheet - {safe(exams[eid])}.pdf", label=f"{cn} {sn} · Tabulation · {exams[eid]}", kind="tab", cid=cid, sid=sid, eid=eid))
            if not want_wtd:
                continue
            if layouts.is_junior(cid, sid):
                for eid in exam_ids:
                    if eid in exams:
                        items.append(dict(path=f"{base}/Weighted Average - {safe(exams[eid])}.pdf", label=f"{cn} {sn} · Weighted · {exams[eid]}", kind="wtd", cid=cid, sid=sid, eid=eid))
            else:
                items.append(dict(path=f"{base}/Weighted Average.pdf", label=f"{cn} {sn} · Weighted average", kind="wtd", cid=cid, sid=sid, eid=None))
    return items


def start(app, kind, items, host_url, owner):
    _cleanup()
    jid = uuid.uuid4().hex[:12]
    title = {"cards": "Report Cards", "cardbook": "Report Cards (one PDF per section)", "tab": "Tabulation Sheets", "wtd": "Weighted Average Sheets"}.get(kind, "Tabulation and Weighted Average Sheets")
    job = dict(id=jid, kind=kind, title=title, total=len(items), done=0, skipped=[], status="queued", current="", created=time.time(), owner=owner,
               zip=os.path.join(OUT_DIR, f"{jid}.zip"), name=f"{title.replace(' ', '_')}_{time.strftime('%Y%m%d_%H%M')}.zip", error="", cancel=False)
    with LOCK:
        JOBS[jid] = job
    threading.Thread(target=_run, args=(app, job, items, host_url), daemon=True).start()
    return job


def _html(it):
    from ..blueprints import reports as R
    if it["kind"] == "cardbook":
        html = R.combined_cards_html(it["cid"], it["sid"])
        return R.with_page_css(html, R.CARD_PAGE, scale=0.7) if html else None
    if it["kind"] == "card":
        built = reportcard.build(it["student"])
        if not built:
            return None
        return R.with_page_css(R.render_view(built[0], built[1]), R.CARD_PAGE, scale=0.7)
    if it["kind"] == "tab":
        v, ctx = reportdata.tabulation_sheet(it["cid"], it["sid"], it["eid"])
    elif it["cid"] and 4 <= it["cid"] <= 8:
        v, ctx = reportdata.junior_weighted_sheet(it["cid"], it["sid"], it["eid"])
    else:
        v, ctx = reportdata.weighted_sheet(it["cid"], it["sid"])
    return R.with_page_css(R.render_view(v, ctx), R.SHEET_PAGE, margin="0.4in")


def _run(app, job, items, host_url):
    with RUN_LOCK:
        job["status"] = "running"
        chrome = None
        try:
            with app.app_context():
                chrome = ChromePdf(app.config["CHROME_BIN"])
                with zipfile.ZipFile(job["zip"], "w", zipfile.ZIP_DEFLATED) as z:
                    for it in items:
                        if job["cancel"]:
                            job["status"] = "cancelled"; break
                        job["current"] = it["label"]
                        try:
                            html = _html(it)
                            if html is None:
                                job["skipped"].append(f"{it['label']} (no report card design for this class)")
                            else:
                                html = re.sub(r"(?i)<head>", f"<head><base href='{host_url}'>", html, count=1)
                                z.writestr(it["path"], chrome.to_pdf(html))
                        except Exception as e:           # one bad file must not stop the whole zip
                            job["skipped"].append(f"{it['label']} ({e})")
                            traceback.print_exc()
                        job["done"] += 1
                    if job["skipped"]:
                        z.writestr("_not_generated.txt", "These files could not be generated:\n\n" + "\n".join(job["skipped"]))
            if job["status"] != "cancelled":
                job["status"] = "done"
                try:
                    with app.app_context():
                        from . import notifications as N
                        N.notify([job["owner"]], f"{job['title']} ZIP is ready", f"{job['done']} file(s) prepared.", f"/reports/bulk/{job['id']}/download")
                except Exception:
                    traceback.print_exc()
        except Exception as e:
            traceback.print_exc()
            job["status"], job["error"] = "error", str(e)
        finally:
            if chrome:
                chrome.close()
