"""Admin screens for report layouts (class/section -> card design, subject group, ranking) and subject groups."""
import json

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from .. import db
from ..auth import admin_required
from ..services import layouts as L
from ..utils import to_int

bp = Blueprint("layouts_admin", __name__, url_prefix="/admin/layouts")


def _classes():
    return db.query("SELECT classId, class_name FROM classes WHERE isDelete='0' ORDER BY classId")


def _sections():
    return db.query("SELECT sectionId, section_name, class_id FROM sections WHERE isDelete='0' ORDER BY class_id, sectionId")


def _names():
    cn = {r["classId"]: r["class_name"] for r in db.query("SELECT classId, class_name FROM classes")}
    sn = {r["sectionId"]: r["section_name"] for r in db.query("SELECT sectionId, section_name FROM sections")}
    return cn, sn


def _json_list(text):
    """Textarea (one name per line) -> JSON text or None."""
    items = [x.strip() for x in (text or "").splitlines() if x.strip()]
    return json.dumps(items, ensure_ascii=False) if items else None


# ------------------------------------------------------------------ layout rules
@bp.route("/", methods=["GET", "POST"])
@admin_required
def rules():
    L.ensure()
    f = request.form
    if request.method == "POST":
        action = f.get("action")
        if action == "delete":
            db.execute("DELETE FROM sl_layout_rule WHERE class_id=%s AND section_id=%s", (to_int(f.get("class_id")), to_int(f.get("section_id"), 0)))
            L.invalidate()
            flash("Rule deleted. That class/section now falls back to its class-wide rule (or has no report card design).", "success")
            return redirect(url_for("layouts_admin.rules"))
        cid, sid = to_int(f.get("class_id")), to_int(f.get("section_id"), 0)
        kind, slno, rank = f.get("kind"), f.get("slno_mode"), f.get("rank_mode")
        view = f.get("card_view") or None
        group = f.get("subject_group") or None
        if cid is None or kind not in L.KINDS or slno not in L.SLNO or rank not in L.formula_names():
            flash("Please fill the form completely.", "error")
            return redirect(url_for("layouts_admin.rules"))
        if view and view not in L.card_view_options():
            abort(400)
        if group and group not in L.group_keys(False):
            flash("Unknown subject group.", "error")
            return redirect(url_for("layouts_admin.rules"))
        if cid == 0 and sid:
            flash("The default rule applies to every section.", "error")
            return redirect(url_for("layouts_admin.rules"))
        if sid and not db.one("SELECT 1 FROM sections WHERE sectionId=%s AND class_id=%s", (sid, cid)):
            flash("That section does not belong to the selected class.", "error")
            return redirect(url_for("layouts_admin.rules"))
        move = _json_list(f.get("move_names"))
        vals = dict(class_id=cid, section_id=sid or 0, kind=kind, card_view=view, slno_mode=slno,
                    strength=1 if f.get("strength") else 0, wrank=1 if f.get("wrank") else 0, prune=1 if f.get("prune") else 0,
                    reorder_exact=_json_list(f.get("reorder_exact")), move_names=move,
                    move_after=(f.get("move_after") or "").strip() or None if move else None,
                    subject_group=group, rank_mode=rank)
        db.execute("REPLACE INTO sl_layout_rule (" + ",".join(L.FIELDS) + ") VALUES (" + ",".join(["%s"] * len(L.FIELDS)) + ")",
                   tuple(vals[k] for k in L.FIELDS))
        L.invalidate()
        flash("Layout rule saved.", "success")
        return redirect(url_for("layouts_admin.rules"))
    cn, sn = _names()
    rows = []
    for r in L.all_rules():
        r = dict(r)
        r["class_name"] = "All other classes (default)" if r["class_id"] == 0 else cn.get(r["class_id"], f"Class #{r['class_id']}")
        r["section_name"] = "—" if r["class_id"] == 0 else "All sections" if not r["section_id"] else sn.get(r["section_id"], f"#{r['section_id']}")
        r["reorder_list"] = "\n".join(json.loads(r["reorder_exact"])) if r.get("reorder_exact") else ""
        r["move_list"] = "\n".join(json.loads(r["move_names"])) if r.get("move_names") else ""
        rows.append(r)
    edit = None
    if request.args.get("edit"):
        edit = next((r for r in rows if str(r["class_id"]) + "-" + str(r["section_id"]) == request.args["edit"]), None)
    return render_template("layout_rules.html", rows=rows, edit=edit, classes=_classes(), sections=_sections(), L=L,
                           groups=L.group_keys(False), card_views=L.card_view_options(), formulas={n: L.get_formula(n).get("title") or n for n in L.formula_names()})


# ------------------------------------------------------------------ subject groups
@bp.route("/groups", methods=["GET", "POST"])
@admin_required
def groups():
    L.ensure()
    weighted = request.values.get("w") == "1"
    key = (request.values.get("key") or "").strip()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            used = [r for r in L.all_rules() if r["subject_group"] == key]
            if used:
                flash("This group is used by a layout rule - point the rule to another group first.", "error")
            else:
                L.delete_group(key, weighted)
                flash("Group set deleted.", "success")
            return redirect(url_for("layouts_admin.groups", w=int(weighted)))
        names, roles = request.form.getlist("g_name"), request.form.getlist("g_role")
        cfg = {}
        for i, label in enumerate(names):
            label = label.strip()
            if not label:
                continue
            role = roles[i] if i < len(roles) and roles[i] in L.GROUP_ROLES else L.group_role(label)
            gkey = L.GROUP_ROLES[role][1] or label
            if gkey in L.RESERVED and L.RESERVED[gkey] != role:      # a plain group may not take a reserved name
                flash(f"“{gkey}” is a reserved name - choose its role in the Role list instead.", "error")
                return redirect(url_for("layouts_admin.groups", w=int(weighted), key=key))
            if gkey in cfg:
                flash(f"Two groups would use the same name/role: {gkey}", "error")
                return redirect(url_for("layouts_admin.groups", w=int(weighted), key=key))
            subs = [x.strip() for x in request.form.getlist("g_subjects")[i].splitlines() if x.strip()]
            cfg[gkey] = {"subjects": subs, "calculateAvg": request.form.get(f"g_avg_{i}") == "1",
                         "color": (request.form.getlist("g_color")[i] or "th-other-main").strip(),
                         "partition": request.form.get(f"g_part_{i}") == "1"}
            if label != gkey:
                cfg[gkey]["label"] = label
        new_key = (request.form.get("new_key") or "").strip() or key
        if not new_key or not cfg:
            flash("A group set needs a name and at least one group.", "error")
            return redirect(url_for("layouts_admin.groups", w=int(weighted), key=key))
        L.save_group(new_key, weighted, cfg)
        flash("Subject groups saved.", "success")
        return redirect(url_for("layouts_admin.groups", w=int(weighted), key=new_key))
    keys = L.group_keys(weighted)
    cfg = L.get_group(key, weighted) if key in keys else None
    used = {k: [] for k in keys}
    cn, sn = _names()
    for r in L.all_rules():
        if r["subject_group"] in used:
            used[r["subject_group"]].append(f"{cn.get(r['class_id'], r['class_id'])} {('· ' + sn.get(r['section_id'], '')) if r['section_id'] else ''}".strip())
    subjects = [r["subject_name"] for r in db.query("SELECT DISTINCT subject_name FROM subjects WHERE isDelete='0' ORDER BY subject_name")]
    return render_template("layout_groups.html", keys=keys, key=key, cfg=cfg, weighted=weighted, used=used, subjects=subjects, L=L)


# ------------------------------------------------------------------ rank formulas
@bp.route("/rank", methods=["GET", "POST"])
@admin_required
def rank():
    L.ensure()
    name = (request.values.get("name") or "").strip()
    if request.method == "POST":
        if request.form.get("action") == "delete":
            if any(r["rank_mode"] == name for r in L.all_rules()):
                flash("A layout rule still uses this formula.", "error")
            elif name in ("sum",):
                flash("The basic 'sum' formula cannot be deleted.", "error")
            else:
                L.delete_formula(name)
                flash("Formula deleted.", "success")
            return redirect(url_for("layouts_admin.rank"))
        new_name = "".join(ch for ch in (request.form.get("new_name") or name).strip().lower().replace(" ", "_") if ch.isalnum() or ch == "_")[:40]
        if not new_name:
            flash("Give the formula a name.", "error")
            return redirect(url_for("layouts_admin.rank", name=name))
        comps = []
        subs, divs = request.form.getlist("c_subjects"), request.form.getlist("c_divisor")
        for i, text in enumerate(subs):
            names = [x.strip() for x in text.splitlines() if x.strip()]
            if not names:
                continue
            try:
                d = float(divs[i]) if divs[i] else 1.0
            except ValueError:
                d = 0
            if d <= 0:
                flash("Divisor must be a number greater than 0.", "error")
                return redirect(url_for("layouts_admin.rank", name=name))
            comps.append({"subjects": names, "divisor": int(d) if d == int(d) else d, "round": request.form.get(f"c_round_{i}") == "1"})
        rest = request.form.get("rest") if request.form.get("rest") in L.REST_MODES else "ignore"
        L.save_formula(new_name, {"title": (request.form.get("title") or new_name).strip()[:120], "components": comps, "rest": rest})
        flash("Rank formula saved.", "success")
        return redirect(url_for("layouts_admin.rank", name=new_name))
    names = L.formula_names()
    cfg = L.get_formula(name) if name in names else None
    used = {n: [] for n in names}
    cn, sn = _names()
    for r in L.all_rules():
        if r["rank_mode"] in used:
            used[r["rank_mode"]].append(f"{cn.get(r['class_id'], r['class_id'])}{(' · ' + sn.get(r['section_id'], '')) if r['section_id'] else ''}")
    subjects = [r["subject_name"] for r in db.query("SELECT DISTINCT subject_name FROM subjects WHERE isDelete='0' ORDER BY subject_name")]
    return render_template("layout_rank.html", names=names, name=name, cfg=cfg, used=used, subjects=subjects, L=L)


# ------------------------------------------------------------------ card designs (created in the browser)
@bp.route("/designs", methods=["GET", "POST"])
@admin_required
def designs():
    from ..services import carddesign as D
    D.ensure()
    did = to_int(request.values.get("id"))
    if request.method == "POST":
        if request.form.get("action") == "delete":
            if any(r["card_view"] == f"custom:{did}" for r in L.all_rules()):
                flash("A layout rule still uses this design.", "error")
                return redirect(url_for("layouts_admin.designs", id=did))
            D.delete(did)
            flash("Design deleted.", "success")
            return redirect(url_for("layouts_admin.designs"))
        if request.form.get("action") == "preset":
            key = request.form.get("preset")
            if key not in D.PRESETS:
                abort(400)
            pname, _desc, phtml = D.PRESETS[key]
            n = D.save(None, f"{pname} (copy)", phtml)
            flash(f"“{pname}” template added to your designs - edit it freely.", "success")
            return redirect(url_for("layouts_admin.designs", id=n))
        name, html = (request.form.get("name") or "").strip()[:120], request.form.get("html") or ""
        if not name or not html.strip():
            flash("Name and design are required.", "error")
            return redirect(url_for("layouts_admin.designs", id=did))
        try:
            D.check(html)
        except Exception as e:
            flash(f"Design has an error: {e}", "error")
            return render_template("layout_designs.html", designs=D.all_designs(), cur=dict(id=did, name=name, html=html), D=D,
                                   classes=_classes(), sections=_sections(), preview=None), 200
        did = D.save(did, name, html)
        flash("Design saved.", "success")
        return redirect(url_for("layouts_admin.designs", id=did, student=request.form.get("student") or ""))
    cur = None
    if request.args.get("new"):
        cur = dict(id=None, name="My report card", html=D.STARTER)
    elif did:
        cur = D.get(did)
    student = to_int(request.args.get("student"))
    presets = builtins = None
    if not cur:
        presets = [dict(key=k, name=v[0], desc=v[1]) for k, v in D.PRESETS.items()]
        builtins = _builtin_designs()
    return render_template("layout_designs.html", presets=presets, builtins=builtins, designs=D.all_designs(), cur=cur, D=D, classes=_classes(), sections=_sections(),
                           preview=(url_for("layouts_admin.design_preview", did=did, student=student) if cur and cur["id"] and student else None),
                           student=student)


@bp.route("/designs/<int:did>/preview")
@admin_required
def design_preview(did):
    from ..services import carddesign as D, reportcard
    sid = to_int(request.args.get("student"))
    if not D.exists(did) or not sid:
        abort(404)
    sd = reportcard.student_details(sid)
    if not sd:
        abort(404)
    built = reportcard.build(sid, force_view=f"custom:{did}")        # same data as a real card
    if not built:
        abort(404)
    return D.render(did, built[1])


@bp.route("/students")
@admin_required
def students_json():
    from flask import jsonify
    cid, sid = to_int(request.args.get("class_id")), to_int(request.args.get("section_id"))
    rows = db.query("SELECT studentId, student_rollNumber, student_name FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0' ORDER BY student_rollNumber", (cid, sid))
    return jsonify([dict(id=r["studentId"], name=f"{r['student_rollNumber']}. {r['student_name']}") for r in rows])


def _builtin_designs():
    """The report card designs that ship with the application, with the classes that use each one and a sample student for the preview."""
    cn, sn = _names()
    rules = L.all_rules()
    out = []
    for view, label in L.CARD_VIEWS.items():
        users, sample = [], None
        for r in rules:
            if r["card_view"] != view:
                continue
            users.append(("All other classes" if r["class_id"] == 0 else cn.get(r["class_id"], f"Class #{r['class_id']}")) + (f" {sn.get(r['section_id'], '')}" if r["section_id"] else ""))
            if sample is None and r["class_id"]:
                q, a = "SELECT studentId FROM students WHERE class_id=%s AND isDelete='0'", [r["class_id"]]
                if r["section_id"]:
                    q += " AND section_id=%s"; a.append(r["section_id"])
                sample = db.scalar(q + " ORDER BY student_rollNumber LIMIT 1", a)
        out.append(dict(view=view, label=label, used=users, sample=sample))
    return out


@bp.route("/designs/builtin/<view>/preview")
@admin_required
def builtin_preview(view):
    """Preview of a built-in design with a real student (read only - nothing is changed)."""
    from ..services import reportcard
    from .reports import render_view
    if view not in L.CARD_VIEWS:
        abort(404)
    sid = to_int(request.args.get("student"))
    if not sid:
        abort(404)
    try:
        built = reportcard.build(sid, force_view=view)
        if not built:
            abort(404)
        return render_view(view, built[1])
    except Exception:
        return ("<p style='font:14px Arial;padding:30px'>This design needs the settings of the class it is meant for, so it cannot be previewed "
                "with this student. Pick a class that uses it in <b>Report layouts</b>.</p>")


# ------------------------------------------------------------------ "Use in a class" pop-up for the built-in designs
@bp.route("/designs/targets")
@admin_required
def designs_targets():
    """Every class with its sections and the design each currently uses (fresh data for the pop-up)."""
    labels = L.card_view_options()
    view = request.args.get("view")
    meant = {r["class_id"] for r in L.all_rules() if view and r["card_view"] == view}          # classes this design was made for
    tree = []
    for c in _classes():
        secs = []
        for s in _sections():
            if s["class_id"] != c["classId"]:
                continue
            r = L.rule(c["classId"], s["sectionId"])
            secs.append(dict(id=s["sectionId"], name=s["section_name"], current=labels.get(r["card_view"]) if r and r["card_view"] else None))
        whole = L.rule(c["classId"], 0)
        tree.append(dict(id=c["classId"], name=c["class_name"], sections=secs, fit=(not view) or c["classId"] in meant, current=labels.get(whole["card_view"]) if whole and whole["card_view"] else None))
    return jsonify(classes=tree)


_PREP = ("kind", "slno_mode", "strength", "wrank", "prune")


def _row(cid, sid):
    r = db.one("SELECT " + ",".join(L.FIELDS) + " FROM sl_layout_rule WHERE class_id=%s AND section_id=%s", (cid, sid))
    return dict(r) if r else None


def _put(r):
    db.execute("REPLACE INTO sl_layout_rule (" + ",".join(L.FIELDS) + ") VALUES (" + ",".join(["%s"] * len(L.FIELDS)) + ")", tuple(r[k] for k in L.FIELDS))
    L.invalidate()


def _trial(cid, sid, view):
    """Render a real card of the section with the new setting; True when it works."""
    from ..services import reportcard
    from .reports import render_view
    q, a = "SELECT studentId FROM students WHERE class_id=%s AND isDelete='0'", [cid]
    if sid:
        q += " AND section_id=%s"; a.append(sid)
    stu = db.scalar(q + " ORDER BY student_rollNumber LIMIT 1", a)
    if not stu:
        return True, "no students yet"
    try:
        built = reportcard.build(stu)
        if not built or built[0] != view:
            return False, "the class settings do not allow this design"
        html = render_view(built[0], built[1])
        return (len(html) > 1500), "ok"
    except Exception as e:
        return False, "it needs data this class does not have"


@bp.route("/designs/builtin/<view>/apply", methods=["POST"])
@admin_required
def builtin_apply(view):
    """Use a built-in design for the chosen classes / sections. Each change is test-rendered with a real student and
    undone on the spot if the card cannot be produced, so a class never ends up without a working card."""
    if view not in L.CARD_VIEWS:
        abort(404)
    data = request.get_json(silent=True) or {}
    targets = [(to_int(t.get("class_id")), to_int(t.get("section_id"), 0) or 0) for t in (data.get("targets") or [])]
    targets = [t for t in dict.fromkeys(targets) if t[0]]
    if not targets:
        return jsonify(ok=False, message="Select at least one class or section."), 400
    L.ensure()
    tmpl = next((r for r in L.all_rules() if r["card_view"] == view), None)
    if not tmpl:
        return jsonify(ok=False, message="No class uses this design yet, so its settings are unknown."), 400
    cn, sn = _names()
    labels = L.card_view_options()
    applied, failed = [], []
    for cid, sid in targets:
        if not db.one("SELECT 1 FROM classes WHERE classId=%s AND isDelete='0'", (cid,)) or (sid and not db.one("SELECT 1 FROM sections WHERE sectionId=%s AND class_id=%s", (sid, cid))):
            failed.append(dict(label=f"Class #{cid}", reason="not found")); continue
        label = cn.get(cid, f"Class {cid}") + (f" {sn.get(sid, '')}" if sid else " (all sections)")
        rows = [(cid, sid)] if sid else [(cid, 0)] + [(r["class_id"], r["section_id"]) for r in L.all_rules() if r["class_id"] == cid and r["section_id"]]
        snapshot = {key: _row(*key) for key in rows}
        before = labels.get((L.rule(cid, sid) or {}).get("card_view")) or "none"
        try:
            for key in rows:
                old = snapshot[key] or ({**dict(L.rule(cid, key[1]) or {}), "class_id": key[0], "section_id": key[1]} if L.rule(cid, key[1]) else None)
                new = dict(old) if old else dict(class_id=key[0], section_id=key[1], subject_group=L.DEFAULT_GROUP, rank_mode="sum", reorder_exact=None, move_names=None, move_after=None)
                new.update(class_id=key[0], section_id=key[1], card_view=view, **{k: tmpl[k] for k in _PREP})
                new["reorder_exact"] = new["move_names"] = new["move_after"] = None
                _put(new)
            ok, why = _trial(cid, sid, view)
            if not ok:
                raise RuntimeError(why)
            applied.append(dict(label=label, before=before, after=labels.get(view)))
        except Exception as e:
            for key, old in snapshot.items():
                if old:
                    _put(old)
                else:
                    db.execute("DELETE FROM sl_layout_rule WHERE class_id=%s AND section_id=%s", key); L.invalidate()
            failed.append(dict(label=label, reason=str(e) if isinstance(e, RuntimeError) else "it could not be applied"))
    msg = f"{len(applied)} applied" + (f", {len(failed)} could not be changed (left exactly as they were)" if failed else "")
    return jsonify(ok=bool(applied), applied=applied, failed=failed, message=msg + ("." if not failed else "."))
