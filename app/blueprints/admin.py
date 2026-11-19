"""Administration: masters, mappings, exams, settings."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from .. import db
from ..auth import admin_required, current_user
from ..utils import paginate, page_arg, to_int

bp = Blueprint("admin", __name__, url_prefix="/admin")
PER = 15


def _lookups():
    return dict(
        classes=db.query("SELECT classId, class_name FROM classes WHERE isDelete='0' ORDER BY classId"),
        exams=db.query("SELECT examId, exam_name FROM exams WHERE isDelete='0' ORDER BY examId"),
    )


# ------------------------------------------------------------------ JSON lookups (cascading selects)
@bp.route("/api/sections")
@admin_required
def api_sections():
    cid = to_int(request.args.get("class_id"))
    mapped = request.args.get("mapped") == "1"       # only sections that have subjects mapped
    if mapped:
        rows = db.query("SELECT DISTINCT s.sectionId, s.section_name FROM sections s "
                        "JOIN assign_subject a ON a.section_id=s.sectionId AND a.isDelete='0' "
                        "WHERE s.class_id=%s AND s.isDelete='0' ORDER BY s.section_name", (cid,))
    else:
        rows = db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0' "
                        "ORDER BY section_name", (cid,))
    return jsonify(rows)


@bp.route("/api/subjects")
@admin_required
def api_subjects():
    """Subjects mapped to the class and (any of) the given sections."""
    cid = to_int(request.args.get("class_id"))
    sids = [to_int(x) for x in request.args.getlist("section_id") if to_int(x)]
    if not sids:
        return jsonify([])
    ph = ",".join(["%s"] * len(sids))
    rows = db.query("SELECT DISTINCT sb.subjectId, sb.subject_name FROM assign_subject a "
                    "JOIN subjects sb ON sb.subjectId=a.subject_id "
                    f"WHERE a.class_id=%s AND a.section_id IN ({ph}) AND a.isDelete='0' AND sb.isDelete='0' "
                    "ORDER BY sb.subject_name", [cid] + sids)
    return jsonify(rows)


@bp.route("/api/section_subjects")
@admin_required
def api_section_subjects():
    """Every section of a class with its subjects. all=1 -> every subject (flagging the ones already mapped)."""
    cid, allsub = to_int(request.args.get("class_id")), request.args.get("all") == "1"
    secs = db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0' ORDER BY section_name", (cid,))
    mapped = {}
    for r in db.query("SELECT a.section_id, sb.subjectId, sb.subject_name FROM assign_subject a JOIN subjects sb ON sb.subjectId=a.subject_id "
                      "WHERE a.class_id=%s AND a.isDelete='0' AND sb.isDelete='0' ORDER BY sb.subject_name", (cid,)):
        mapped.setdefault(r["section_id"], []).append({"subjectId": r["subjectId"], "subject_name": r["subject_name"], "mapped": True})
    every = db.query("SELECT subjectId, subject_name FROM subjects WHERE isDelete='0' ORDER BY subject_name") if allsub else []
    out = []
    for s_ in secs:
        have = mapped.get(s_["sectionId"], [])
        if allsub:
            ids = {x["subjectId"] for x in have}
            subs = [{"subjectId": x["subjectId"], "subject_name": x["subject_name"], "mapped": x["subjectId"] in ids} for x in every]
        else:
            subs = have
        out.append({"sectionId": s_["sectionId"], "section_name": s_["section_name"], "subjects": subs})
    exam, st = to_int(request.args.get("exam_id")), to_int(request.args.get("subtype_id"))
    if exam and st:                       # full marks already set for this exam + sub-type, so they can be shown and edited
        cur = {(r["sectionId"], r["subjectId"]): r["fullmarsks"] for r in db.query(
            "SELECT sectionId, subjectId, fullmarsks FROM assign_exam_subtype WHERE classId=%s AND examId=%s AND exam_subtype_id=%s AND isDelete='0'", (cid, exam, st))}
        for o in out:
            for x in o["subjects"]:
                x["fullmarks"] = cur.get((o["sectionId"], x["subjectId"]))
    return jsonify(out)


def _pairs():
    """[(sectionId, subjectId)] from the section-wise checkboxes (value 'section:subject')."""
    out = []
    for v in request.form.getlist("pair"):
        a, _, b = v.partition(":")
        if to_int(a) and to_int(b):
            out.append((to_int(a), to_int(b)))
    return out



# ------------------------------------------------------------------ trash (soft-deleted rows): restore / delete permanently
_VARIANTS = {"classes": ("classId", "class_id"), "sections": ("sectionId", "section_id"), "subjects": ("subjectId", "subject_id"), "exams": ("examId", "exam_id")}


def _in_use(table, rid):
    """Where a master row is still referenced by live data -> list of 'table' names (blocks permanent delete)."""
    vs = _VARIANTS[table]
    cols = db.query("SELECT TABLE_NAME t, COLUMN_NAME c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND COLUMN_NAME IN (%s,%s) AND TABLE_NAME<>%s",
                    (vs[0], vs[1], table))
    has_del = {r["t"] for r in db.query("SELECT TABLE_NAME t FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='isDelete'")}
    used = []
    for c in cols:
        t, col = c["t"], c["c"]
        if t in ("pdf_track", "tabulation_sheet_track", "sl_live_event") or t == "system_settings":
            continue                                    # logs, not data that depends on the row
        if table == "subjects" and t == "exam_marks_development":
            continue                                    # its subjectId is a development-skill id
        w = f" AND isDelete='0'" if t in has_del else ""
        try:
            if db.scalar(f"SELECT COUNT(*) FROM `{t}` WHERE `{col}`=%s{w}", (rid,)):
                used.append(t)
        except Exception:
            pass
    return sorted(set(used))


def _trash_action(table, pk, singular, act, rid, restore_check=None):
    """Handle restore / purge for a soft-deleted row. Flashes the outcome."""
    row = db.one(f"SELECT * FROM `{table}` WHERE `{pk}`=%s AND isDelete='1'", (rid,))
    if not row:
        flash(f"That {singular.lower()} is not in the Trash.", "error"); return
    if act == "restore":
        msg = restore_check(row) if restore_check else None
        if msg:
            flash(msg, "error"); return
        db.execute(f"UPDATE `{table}` SET isDelete='0' WHERE `{pk}`=%s", (rid,))
        flash(f"{singular} restored.", "success")
    else:
        used = _in_use(table, rid)
        if used:
            flash(f"This {singular.lower()} cannot be deleted permanently - it is still used in: {', '.join(used[:4])}.", "error"); return
        try:
            db.execute(f"DELETE FROM `{table}` WHERE `{pk}`=%s AND isDelete='1'", (rid,))
        except Exception:
            flash(f"This {singular.lower()} cannot be deleted permanently because other records still refer to it.", "error"); return
        flash(f"{singular} deleted permanently.", "success")


_MAP = {   # mapping tables: key columns that must stay unique among active rows, and the master rows each column points at
    "assign_subject": ("assignSubjectId", "Mapping", ("class_id", "section_id", "subject_id")),
    "assign_exam": ("id", "Assignment", ("classId", "sectionId", "subjectId", "examId")),
    "assign_exam_subtype": ("id", "Sub-type setting", ("classId", "sectionId", "subjectId", "examId", "exam_subtype_id")),
    "classTeacher": ("id", "Class teacher", ("classId", "sectionId")),
    "assign_teacher": ("id", "Teacher mapping", ("t_id", "classId", "sectionId", "subjectId")),
}
_PARENT = {"class_id": ("classes", "classId"), "classId": ("classes", "classId"), "section_id": ("sections", "sectionId"), "sectionId": ("sections", "sectionId"),
           "subject_id": ("subjects", "subjectId"), "subjectId": ("subjects", "subjectId"), "examId": ("exams", "examId"), "exam_subtype_id": ("exam_subtype", "id")}


_PL = {"classes": "class", "sections": "section", "subjects": "subject", "exams": "exam", "exam_subtype": "exam sub-type"}


def _restore_block(table, row):
    """Why a soft-deleted mapping row cannot come back (message) - or None when it can."""
    pk, label, keys = _MAP[table]
    for k in keys:                                   # every class / section / subject / exam it points at must be active again
        if k in _PARENT:
            t, c = _PARENT[k]
            if not db.one(f"SELECT 1 FROM `{t}` WHERE `{c}`=%s AND isDelete='0'", (row[k],)):
                return f"Cannot restore - its {_PL[t]} is in the Trash. Restore that first."
    if db.one(f"SELECT 1 FROM `{table}` WHERE isDelete='0' AND `{pk}`<>%s AND " + " AND ".join(f"`{k}`=%s" for k in keys), [row[pk]] + [row[k] for k in keys]):
        return f"Cannot restore - an active {label.lower()} for the same combination already exists."
    return None


def _map_trash(table, act, rid):
    """Restore / permanently delete a soft-deleted mapping row. Returns the row (for follow-up notices) or None."""
    pk, label, keys = _MAP[table]
    row = db.one(f"SELECT * FROM `{table}` WHERE `{pk}`=%s AND isDelete='1'", (rid,))
    if not row:
        flash(f"That {label.lower()} is not in the Trash.", "error"); return None
    if act == "purge":
        db.execute(f"DELETE FROM `{table}` WHERE `{pk}`=%s AND isDelete='1'", (rid,))
        flash(f"{label} deleted permanently.", "success"); return row
    msg = _restore_block(table, row)
    if msg:
        flash(msg, "error"); return None
    db.execute(f"UPDATE `{table}` SET isDelete='0' WHERE `{pk}`=%s", (rid,))
    flash(f"{label} restored.", "success"); return row


def _teacher_bulk(t, act):
    """Move all of a teacher's mappings to the Trash, or restore / permanently delete everything in their Trash."""
    if act == "delete_all":
        n = db.execute("UPDATE assign_teacher SET isDelete='1' WHERE t_id=%s AND isDelete='0'", (t,))
        flash("All mappings of this teacher were moved to the Trash.", "success"); return
    n = bad = 0
    for row in db.query("SELECT * FROM assign_teacher WHERE t_id=%s AND isDelete='1'", (t,)):
        if act == "purge_all":
            db.execute("DELETE FROM assign_teacher WHERE id=%s AND isDelete='1'", (row["id"],), commit=False); n += 1
        elif _restore_block("assign_teacher", row):
            bad += 1
        else:
            db.execute("UPDATE assign_teacher SET isDelete='0' WHERE id=%s", (row["id"],), commit=False); n += 1
    db.commit()
    verb = "deleted permanently" if act == "purge_all" else "restored"
    flash(f"{n} mapping(s) {verb}." + (f" {bad} could not be restored (a class, section or subject is in the Trash, or it already exists)." if bad else ""), "success" if n or not bad else "error")


def _trash_args():
    return {"trash": 1} if (request.form.get("trash") or request.args.get("trash")) else {}


def _n_trash(table):
    return db.scalar(f"SELECT COUNT(*) FROM `{table}` WHERE isDelete='1'")

# ------------------------------------------------------------------ generic master pages
MASTERS = {
    "classes": dict(table="classes", pk="classId", title="Classes", singular="Class",
                    fields=[("class_code", "Class code"), ("class_name", "Class name")]),
    "subjects": dict(table="subjects", pk="subjectId", title="Subjects", singular="Subject",
                     fields=[("subject_code", "Subject code"), ("subject_name", "Subject name")]),
    "exams": dict(table="exams", pk="examId", title="Exams", singular="Exam",
                  fields=[("exam_code", "Exam code"), ("exam_name", "Exam name")]),
}


def _master(key):
    m = MASTERS[key]
    t, pk, fields = m["table"], m["pk"], m["fields"]
    if request.method == "POST":
        act = request.form.get("action")
        if act == "delete":
            db.execute(f"UPDATE {t} SET isDelete='1' WHERE {pk}=%s", (to_int(request.form.get("id")),))
            flash(f"{m['singular']} deleted.", "success")
        elif act in ("restore", "purge"):
            def dup(row):
                if db.one(f"SELECT {pk} FROM {t} WHERE {fields[0][0]}=%s AND isDelete='0'", (row[fields[0][0]],)):
                    return f"Cannot restore - another active {m['singular'].lower()} already uses this {fields[0][1].lower()}."
            _trash_action(t, pk, m["singular"], act, to_int(request.form.get("id")), dup)
        else:
            vals = [request.form.get(f, "").strip() for f, _ in fields]
            if not all(vals):
                flash("All fields are required.", "error")
            else:
                rid = to_int(request.form.get("id"))
                dup = db.one(f"SELECT {pk} FROM {t} WHERE {fields[0][0]}=%s AND isDelete='0' AND {pk}<>%s",
                             (vals[0], rid or 0))
                if dup:
                    flash(f"{fields[0][1]} already exists.", "error")
                elif rid:
                    db.execute(f"UPDATE {t} SET " + ",".join(f"{f}=%s" for f, _ in fields) + f" WHERE {pk}=%s",
                               vals + [rid])
                    flash(f"{m['singular']} updated.", "success")
                else:
                    db.execute(f"INSERT INTO {t} (" + ",".join(f for f, _ in fields) + ") VALUES (" +
                               ",".join(["%s"] * len(fields)) + ")", vals)
                    flash(f"{m['singular']} created.", "success")
        return redirect(url_for(request.endpoint, **({"trash": 1} if request.form.get("trash") else {})))
    q = request.args.get("q", "").strip()
    trash = bool(request.args.get("trash"))
    n_trash = db.scalar(f"SELECT COUNT(*) FROM {t} WHERE isDelete='1'")
    where, args = ("WHERE isDelete='1'" if trash else "WHERE isDelete='0'"), []
    if q:
        where += " AND (" + " OR ".join(f"{f} LIKE %s" for f, _ in fields) + ")"
        args = [f"%{q}%"] * len(fields)
    total = db.scalar(f"SELECT COUNT(*) FROM {t} {where}", args)
    p = paginate(total, PER, page_arg())
    rows = db.query(f"SELECT * FROM {t} {where} ORDER BY {pk} DESC LIMIT %s OFFSET %s", args + [PER, p["offset"]])
    edit = db.one(f"SELECT * FROM {t} WHERE {pk}=%s", (to_int(request.args.get("edit")),)) if request.args.get("edit") else None
    return render_template("master.html", m=m, rows=rows, p=p, q=q, edit=edit, extra=None, trash=trash, n_trash=n_trash)


@bp.route("/classes", methods=["GET", "POST"])
@admin_required
def classes():
    return _master("classes")


@bp.route("/subjects", methods=["GET", "POST"])
@admin_required
def subjects():
    return _master("subjects")


@bp.route("/exams", methods=["GET", "POST"])
@admin_required
def exams():
    return _master("exams")


@bp.route("/sections", methods=["GET", "POST"])
@admin_required
def sections():
    if request.method == "POST":
        act = request.form.get("action")
        rid = to_int(request.form.get("id"))
        if act == "delete":
            db.execute("UPDATE sections SET isDelete='1' WHERE sectionId=%s", (rid,))
            flash("Section deleted.", "success")
        elif act in ("restore", "purge"):
            def parent(row):
                if not db.one("SELECT classId FROM classes WHERE classId=%s AND isDelete='0'", (row["class_id"],)):
                    return "Cannot restore - its class is deleted. Restore the class first."
                if db.one("SELECT sectionId FROM sections WHERE class_id=%s AND (section_name=%s OR section_code=%s) AND isDelete='0'", (row["class_id"], row["section_name"], row["section_code"])):
                    return "Cannot restore - an active section with this name or code already exists in the class."
            _trash_action("sections", "sectionId", "Section", act, rid, parent)
        else:
            cid, name, code = to_int(request.form.get("class_id")), request.form.get("section_name", "").strip(), request.form.get("section_code", "").strip()
            if not (cid and name and code):
                flash("All fields are required.", "error")
            elif db.one("SELECT sectionId FROM sections WHERE class_id=%s AND (section_name=%s OR section_code=%s) "
                        "AND isDelete='0' AND sectionId<>%s", (cid, name, code, rid or 0)):
                flash("Section already exists for this class.", "error")
            elif rid:
                db.execute("UPDATE sections SET class_id=%s, section_name=%s, section_code=%s WHERE sectionId=%s", (cid, name, code, rid))
                flash("Section updated.", "success")
            else:
                db.execute("INSERT INTO sections (class_id, section_name, section_code) VALUES (%s,%s,%s)", (cid, name, code))
                flash("Section created.", "success")
        return redirect(url_for("admin.sections", **({"trash": 1} if request.form.get("trash") else {})))
    q, cls = request.args.get("q", "").strip(), to_int(request.args.get("class_id"))
    trash = bool(request.args.get("trash"))
    n_trash = db.scalar("SELECT COUNT(*) FROM sections WHERE isDelete='1'")
    where, args = ("WHERE s.isDelete='1'" if trash else "WHERE s.isDelete='0' AND c.isDelete='0'"), []
    if q:
        where += " AND (s.section_name LIKE %s OR s.section_code LIKE %s OR c.class_name LIKE %s)"; args += [f"%{q}%"] * 3
    if cls:
        where += " AND s.class_id=%s"; args.append(cls)
    base = f"FROM sections s JOIN classes c ON c.classId=s.class_id {where}"
    total = db.scalar(f"SELECT COUNT(*) {base}", args)
    p = paginate(total, PER, page_arg())
    rows = db.query(f"SELECT s.*, c.class_name {base} ORDER BY s.class_id, s.section_name LIMIT %s OFFSET %s", args + [PER, p["offset"]])
    edit = db.one("SELECT * FROM sections WHERE sectionId=%s", (to_int(request.args.get("edit")),)) if request.args.get("edit") else None
    return render_template("sections.html", rows=rows, p=p, q=q, cls=cls, edit=edit, trash=trash, n_trash=n_trash, **_lookups())


# ------------------------------------------------------------------ class · section · subject mapping
@bp.route("/class-subjects", methods=["GET", "POST"])
@admin_required
def class_subjects():
    if request.method == "POST":
        act = request.form.get("action")
        if act == "delete":
            db.execute("UPDATE assign_subject SET isDelete='1' WHERE assignSubjectId=%s", (to_int(request.form.get("id")),))
            flash("Mapping removed.", "success")
        elif act in ("restore", "purge"):
            _map_trash("assign_subject", act, to_int(request.form.get("id")))
            return redirect(url_for("admin.class_subjects", **_trash_args()))
        elif act == "special":
            db.execute("UPDATE assign_subject SET isSpecialSubject=%s WHERE assignSubjectId=%s",
                       ("1" if request.form.get("value") == "1" else "0", to_int(request.form.get("id"))))
            flash("Updated.", "success")
        else:
            cid = to_int(request.form.get("class_id"))
            special = "1" if request.form.get("special") else "0"
            if not (cid and _pairs()):
                flash("Select a class and tick the subjects under the sections.", "error")
            else:
                added = 0
                for s, sb in _pairs():
                    if True:
                        if not db.one("SELECT 1 FROM assign_subject WHERE class_id=%s AND section_id=%s AND subject_id=%s AND isDelete='0'", (cid, s, sb)):
                            db.execute("INSERT INTO assign_subject (class_id, section_id, subject_id, isSpecialSubject) VALUES (%s,%s,%s,%s)",
                                       (cid, s, sb, special), commit=False)
                            added += 1
                db.commit()
                flash(f"{added} mapping(s) created.", "success")
        return redirect(url_for("admin.class_subjects", class_id=request.form.get("class_id") or ""))
    cls, sec = to_int(request.args.get("class_id")), to_int(request.args.get("section_id"))
    trash = bool(request.args.get("trash"))
    where, args = ("WHERE a.isDelete='1'" if trash else "WHERE a.isDelete='0' AND c.isDelete='0' AND s.isDelete='0' AND sb.isDelete='0'"), []
    if cls:
        where += " AND a.class_id=%s"; args.append(cls)
    if sec:
        where += " AND a.section_id=%s"; args.append(sec)
    base = ("FROM assign_subject a JOIN classes c ON c.classId=a.class_id JOIN sections s ON s.sectionId=a.section_id "
            f"JOIN subjects sb ON sb.subjectId=a.subject_id {where}")
    total = db.scalar(f"SELECT COUNT(*) {base}", args)
    p = paginate(total, 20, page_arg())
    rows = db.query(f"SELECT a.assignSubjectId, a.isSpecialSubject, c.class_name, s.section_name, sb.subject_name {base} "
                    "ORDER BY a.class_id, a.section_id, sb.subject_name LIMIT %s OFFSET %s", args + [20, p["offset"]])
    all_subjects = db.query("SELECT subjectId, subject_name FROM subjects WHERE isDelete='0' ORDER BY subject_name")
    secs_for_filter = db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0'", (cls,)) if cls else []
    return render_template("class_subjects.html", rows=rows, p=p, cls=cls, sec=sec, all_subjects=all_subjects, trash=trash, n_trash=_n_trash("assign_subject"),
                           secs_for_filter=secs_for_filter, **_lookups())


# ------------------------------------------------------------------ teacher mapping (ONE row per teacher)
def _teachers():
    return db.query("SELECT t.user_id, TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) AS full_name "
                    "FROM teachers t WHERE t.deleted_at IS NULL ORDER BY t.fname, t.lname")


@bp.route("/teacher-mapping", methods=["GET", "POST"])
@admin_required
def teacher_mapping():
    if request.method == "POST":
        act, t = request.form.get("action"), to_int(request.form.get("teacher_id"))
        if act in ("restore", "purge"):
            _map_trash("assign_teacher", act, to_int(request.form.get("id")))
        elif act in ("delete_all", "restore_all", "purge_all") and t:
            _teacher_bulk(t, act)
        return redirect(url_for("admin.teacher_mapping", **_trash_args()))
    """One row per teacher: subjects, classes and sections are folded into comma separated values."""
    q = request.args.get("q", "").strip()
    tid = to_int(request.args.get("teacher_id"))
    cls, sec, sub = (to_int(request.args.get(k)) for k in ("class_id", "section_id", "subject_id"))
    trash = bool(request.args.get("trash"))
    where, args = ("WHERE a.isDelete='1'" if trash else "WHERE a.isDelete='0'"), []
    if q:
        where += " AND (t.fname LIKE %s OR t.lname LIKE %s OR u.email LIKE %s)"; args += [f"%{q}%"] * 3
    for col, val in (("a.t_id", tid), ("a.classId", cls), ("a.sectionId", sec), ("a.subjectId", sub)):
        if val:
            where += f" AND {col}=%s"; args.append(val)
    base = ("FROM assign_teacher a JOIN teachers t ON t.user_id=a.t_id LEFT JOIN new_users u ON u.id=a.t_id "
            "JOIN classes c ON c.classId=a.classId JOIN sections s ON s.sectionId=a.sectionId "
            f"JOIN subjects sb ON sb.subjectId=a.subjectId {where}")
    if trash:                                    # one line per removed mapping, each can be restored / deleted for good
        total = db.scalar(f"SELECT COUNT(*) {base}", args)
        p = paginate(total, 20, page_arg())
        rows = db.query(f"SELECT a.id, TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) AS teacher, c.class_name, s.section_name, sb.subject_name {base} "
                        "ORDER BY t.fname, c.classId, s.section_name, sb.subject_name LIMIT %s OFFSET %s", args + [20, p["offset"]])
        return render_template("teacher_mapping.html", rows=rows, p=p, q=q, tid=tid, cls=cls, sec=sec, sub=sub, trash=True, n_trash=_n_trash("assign_teacher"),
                               teachers=_teachers(), all_subjects=db.query("SELECT subjectId, subject_name FROM subjects WHERE isDelete='0' ORDER BY subject_name"),
                               secs_for_filter=db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0'", (cls,)) if cls else [], **_lookups())
    total = db.scalar(f"SELECT COUNT(DISTINCT a.t_id) {base}", args)
    p = paginate(total, 12, page_arg())
    rows = db.query(f"""
        SELECT a.t_id, TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) AS teacher, u.email,
               GROUP_CONCAT(DISTINCT sb.subject_name ORDER BY sb.subject_name SEPARATOR ', ') AS subjects,
               GROUP_CONCAT(DISTINCT c.class_name ORDER BY c.classId SEPARATOR ', ') AS classes,
               COUNT(*) AS total
        {base} GROUP BY a.t_id, t.fname, t.mname, t.lname, u.email
        ORDER BY t.fname, t.lname LIMIT %s OFFSET %s""", args + [12, p["offset"]])
    ids = [r["t_id"] for r in rows]
    by_teacher = {}
    if ids:
        ph = ",".join(["%s"] * len(ids))
        for r in db.query(f"SELECT DISTINCT a.t_id, c.classId, c.class_name, s.section_name FROM assign_teacher a JOIN classes c ON c.classId=a.classId "
                          f"JOIN sections s ON s.sectionId=a.sectionId WHERE a.isDelete='0' AND a.t_id IN ({ph}) ORDER BY c.classId, s.section_name", ids):
            by_teacher.setdefault(r["t_id"], {}).setdefault(r["class_name"], []).append(r["section_name"])
    for r in rows:      # "Class 6: A, B, D" - the class name is written once, not for every section
        r["sections"] = [(cn, ", ".join(secs)) for cn, secs in by_teacher.get(r["t_id"], {}).items()]
    return render_template("teacher_mapping.html", rows=rows, p=p, q=q, tid=tid, cls=cls, sec=sec, sub=sub, trash=False, n_trash=_n_trash("assign_teacher"),
                           teachers=_teachers(), all_subjects=db.query("SELECT subjectId, subject_name FROM subjects WHERE isDelete='0' ORDER BY subject_name"),
                           secs_for_filter=db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0'", (cls,)) if cls else [],
                           **_lookups())


@bp.route("/teacher-mapping/new", methods=["GET", "POST"])
@bp.route("/teacher-mapping/<int:teacher_id>", methods=["GET", "POST"])
@admin_required
def teacher_mapping_edit(teacher_id=None):
    if request.method == "POST":
        act = request.form.get("action")
        t = to_int(request.form.get("teacher_id")) or teacher_id
        if act == "delete":
            db.execute("UPDATE assign_teacher SET isDelete='1' WHERE id=%s AND t_id=%s", (to_int(request.form.get("id")), t))
            flash("Removed.", "success")
        elif act in ("restore", "purge"):
            _map_trash("assign_teacher", act, to_int(request.form.get("id")))
            return redirect(url_for("admin.teacher_mapping_edit", teacher_id=t))
        else:
            cid = to_int(request.form.get("class_id"))
            if not (t and cid and _pairs()):
                flash("Select the teacher, the class and tick the subjects under the sections.", "error")
            else:
                added = 0
                for s, sb in _pairs():
                    if True:
                        if not db.one("SELECT 1 FROM assign_teacher WHERE classId=%s AND sectionId=%s AND subjectId=%s AND t_id=%s AND isDelete='0'", (cid, s, sb, t)):
                            db.execute("INSERT INTO assign_teacher (classId, sectionId, subjectId, t_id) VALUES (%s,%s,%s,%s)", (cid, s, sb, t), commit=False)
                            added += 1
                db.commit()
                flash(f"{added} assignment(s) added.", "success")
        return redirect(url_for("admin.teacher_mapping_edit", teacher_id=t))
    rows = []
    trash, n_trash = False, 0
    if teacher_id:
        raw = db.query("""SELECT a.id, a.classId, a.sectionId, c.class_name, s.section_name, sb.subject_name FROM assign_teacher a
            JOIN classes c ON c.classId=a.classId JOIN sections s ON s.sectionId=a.sectionId JOIN subjects sb ON sb.subjectId=a.subjectId
            WHERE a.t_id=%s AND a.isDelete=%s ORDER BY a.classId, s.section_name, sb.subject_name""", (teacher_id, "1" if trash else "0"))
        groups = {}
        for r in raw:       # class -> section -> subjects (each with the id needed to remove it)
            groups.setdefault(r["class_name"], {}).setdefault(r["section_name"], []).append({"id": r["id"], "name": r["subject_name"]})
        rows = groups
    me = next((t for t in _teachers() if t["user_id"] == teacher_id), None)
    return render_template("teacher_mapping_edit.html", rows=rows, teacher_id=teacher_id, teacher=me, trash=trash, n_trash=n_trash, teachers=_teachers(), **_lookups())


# ------------------------------------------------------------------ class teacher
@bp.route("/class-teachers", methods=["GET", "POST"])
@admin_required
def class_teachers():
    from ..services import notifications as N
    me = current_user()["id"]
    if request.method == "POST":
        act = request.form.get("action")
        rid = to_int(request.form.get("id"))
        if act == "delete":
            old = db.one("SELECT teacherId FROM classTeacher WHERE id=%s", (rid,))
            db.execute("UPDATE classTeacher SET isDelete='1' WHERE id=%s", (rid,))
            if old:
                N.notify([old["teacherId"]], "You are no longer a class teacher", "Removed by the administrator.", exclude=me)
            flash("Class teacher removed.", "success")
        elif act in ("restore", "purge"):
            row = _map_trash("classTeacher", act, rid)
            if row and act == "restore":
                N.notify([row["teacherId"]], "You are now a class teacher", _ct_label(row["classId"], row["sectionId"]), exclude=me)
            return redirect(url_for("admin.class_teachers", **_trash_args()))
        else:
            cid, sid, tid = (to_int(request.form.get(k)) for k in ("class_id", "section_id", "teacher_id"))
            if not (cid and sid and tid):
                flash("Select class, section and teacher.", "error")
            elif not db.one("SELECT 1 FROM sections WHERE sectionId=%s AND class_id=%s AND isDelete='0'", (sid, cid)):
                flash("That section does not belong to the class.", "error")
            elif act == "update":
                cur = db.one("SELECT * FROM classTeacher WHERE id=%s AND isDelete='0'", (rid,))
                clash = db.one("SELECT id FROM classTeacher WHERE classId=%s AND sectionId=%s AND isDelete='0' AND id<>%s", (cid, sid, rid))
                if not cur:
                    flash("Record not found.", "error")
                elif clash:
                    flash("That section already has a class teacher. Edit or remove that one first.", "error")
                else:
                    db.execute("UPDATE classTeacher SET classId=%s, sectionId=%s, teacherId=%s WHERE id=%s", (cid, sid, tid, rid))
                    if cur["teacherId"] != tid:
                        N.notify([tid], "You are now a class teacher", _ct_label(cid, sid), exclude=me)
                        N.notify([cur["teacherId"]], "You are no longer a class teacher", _ct_label(cur["classId"], cur["sectionId"]), exclude=me)
                    flash("Class teacher updated.", "success")
                    return redirect(url_for("admin.class_teachers"))
                return redirect(url_for("admin.class_teachers", edit=rid))
            else:
                ex = db.one("SELECT id, teacherId FROM classTeacher WHERE classId=%s AND sectionId=%s AND isDelete='0'", (cid, sid))
                if ex:   # one class teacher per section: replace
                    db.execute("UPDATE classTeacher SET teacherId=%s WHERE id=%s", (tid, ex["id"]))
                    flash("Class teacher replaced.", "success")
                else:
                    db.execute("INSERT INTO classTeacher (classId, sectionId, teacherId) VALUES (%s,%s,%s)", (cid, sid, tid))
                    flash("Class teacher assigned.", "success")
                N.notify([tid], "You are now a class teacher", _ct_label(cid, sid), exclude=me)
        return redirect(url_for("admin.class_teachers"))
    trash = bool(request.args.get("trash"))
    rows = db.query("""SELECT ct.id, ct.classId, ct.sectionId, ct.teacherId, c.class_name, s.section_name, TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) AS teacher
        FROM classTeacher ct JOIN classes c ON c.classId=ct.classId JOIN sections s ON s.sectionId=ct.sectionId
        LEFT JOIN teachers t ON t.user_id=ct.teacherId WHERE ct.isDelete=%s ORDER BY ct.classId, s.section_name""", ("1" if trash else "0",))
    edit = next((r for r in rows if str(r["id"]) == request.args.get("edit", "")), None)
    sections = db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0' ORDER BY section_name", (edit["classId"],)) if edit else []
    return render_template("class_teachers.html", rows=rows, edit=edit, trash=trash, n_trash=_n_trash("classTeacher"), sections=sections, teachers=_teachers(), **_lookups())


def _ct_label(cid, sid):
    c = db.scalar("SELECT class_name FROM classes WHERE classId=%s", (cid,)) or ""
    s = db.scalar("SELECT section_name FROM sections WHERE sectionId=%s", (sid,)) or ""
    return f"{c} {s}"


# ------------------------------------------------------------------ assign exam / sub type
@bp.route("/assign-exam", methods=["GET", "POST"])
@admin_required
def assign_exam():
    if request.method == "POST":
        act = request.form.get("action")
        if act == "delete":
            db.execute("UPDATE assign_exam SET isDelete='1' WHERE id=%s", (to_int(request.form.get("id")),))
            flash("Removed.", "success")
        elif act in ("restore", "purge"):
            _map_trash("assign_exam", act, to_int(request.form.get("id")))
            return redirect(url_for("admin.assign_exam", **_trash_args()))
        else:
            cid, exam = to_int(request.form.get("class_id")), to_int(request.form.get("exam_id"))
            if not (cid and exam and _pairs()):
                flash("Select the class, the exam and tick the subjects under the sections.", "error")
            else:
                n = 0
                for s, sb in _pairs():
                    if True:
                        if not db.one("SELECT 1 FROM assign_exam WHERE classId=%s AND sectionId=%s AND subjectId=%s AND examId=%s AND isDelete='0'", (cid, s, sb, exam)):
                            db.execute("INSERT INTO assign_exam (classId, sectionId, subjectId, examId) VALUES (%s,%s,%s,%s)", (cid, s, sb, exam), commit=False); n += 1
                db.commit(); flash(f"{n} assignment(s) created.", "success")
        return redirect(url_for("admin.assign_exam"))
    cls, sec, exam = (to_int(request.args.get(k)) for k in ("class_id", "section_id", "exam_id"))
    trash = bool(request.args.get("trash"))
    where, args = ("WHERE a.isDelete='1'" if trash else "WHERE a.isDelete='0'"), []
    for col, v in (("a.classId", cls), ("a.sectionId", sec), ("a.examId", exam)):
        if v:
            where += f" AND {col}=%s"; args.append(v)
    base = ("FROM assign_exam a JOIN classes c ON c.classId=a.classId JOIN sections s ON s.sectionId=a.sectionId "
            f"JOIN subjects sb ON sb.subjectId=a.subjectId JOIN exams e ON e.examId=a.examId {where}")
    total = db.scalar(f"SELECT COUNT(*) {base}", args)
    p = paginate(total, 20, page_arg())
    rows = db.query(f"SELECT a.id, c.class_name, s.section_name, sb.subject_name, e.exam_name {base} ORDER BY a.classId, a.sectionId, sb.subject_name LIMIT %s OFFSET %s", args + [20, p["offset"]])
    return render_template("assign_exam.html", rows=rows, p=p, cls=cls, sec=sec, exam=exam, trash=trash, n_trash=_n_trash("assign_exam"),
                           secs_for_filter=db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0'", (cls,)) if cls else [], **_lookups())


@bp.route("/assign-subtype", methods=["GET", "POST"])
@admin_required
def assign_subtype():
    if request.method == "POST":
        act = request.form.get("action")
        if act == "delete":
            db.execute("UPDATE assign_exam_subtype SET isDelete='1' WHERE id=%s", (to_int(request.form.get("id")),))
            flash("Removed.", "success")
        elif act in ("restore", "purge"):
            _map_trash("assign_exam_subtype", act, to_int(request.form.get("id")))
            return redirect(url_for("admin.assign_subtype", **_trash_args()))
        elif act == "update":
            db.execute("UPDATE assign_exam_subtype SET fullmarsks=%s WHERE id=%s", (str(to_int(request.form.get("fullmarks"), 0)), to_int(request.form.get("id"))))
            flash("Full marks updated.", "success")
        elif act == "subtype_add":
            n = request.form.get("exam_type", "").strip()
            if n and not db.one("SELECT 1 FROM exam_subtype WHERE exam_type=%s AND isDelete='0'", (n,)):
                db.execute("INSERT INTO exam_subtype (exam_type) VALUES (%s)", (n,)); flash("Sub-type added.", "success")
            else:
                flash("Enter a new sub-type name.", "error")
        else:
            cid, exam, st = (to_int(request.form.get(k)) for k in ("class_id", "exam_id", "subtype_id"))
            default = to_int(request.form.get("fullmarks"))              # used for every ticked subject that has no mark of its own
            pairs = _pairs()
            if not (cid and exam and st and pairs):
                flash("Choose class, exam and sub-type, and tick the subjects under the sections.", "error")
            else:
                plan, bad = [], []
                for s_, sb in pairs:
                    raw = (request.form.get(f"fm_{s_}_{sb}") or "").strip()
                    fm = to_int(raw) if raw else default
                    if fm is None or fm < 0:
                        bad.append(db.scalar("SELECT subject_name FROM subjects WHERE subjectId=%s", (sb,)) or str(sb))
                    else:
                        plan.append((s_, sb, fm))
                if bad:
                    flash("Enter full marks for: " + ", ".join(sorted(set(bad))[:6]) + ("…" if len(set(bad)) > 6 else "") + ". Nothing was saved.", "error")
                else:
                    made = changed = same = 0
                    for s_, sb, fm in plan:
                        row = db.one("SELECT id, fullmarsks FROM assign_exam_subtype WHERE classId=%s AND sectionId=%s AND subjectId=%s AND examId=%s AND exam_subtype_id=%s AND isDelete='0'", (cid, s_, sb, exam, st))
                        if not row:
                            db.execute("INSERT INTO assign_exam_subtype (classId, sectionId, subjectId, examId, exam_subtype_id, fullmarsks) VALUES (%s,%s,%s,%s,%s,%s)",
                                       (cid, s_, sb, exam, st, str(fm)), commit=False); made += 1
                        elif str(row["fullmarsks"]) != str(fm):
                            db.execute("UPDATE assign_exam_subtype SET fullmarsks=%s WHERE id=%s", (str(fm), row["id"]), commit=False); changed += 1
                        else:
                            same += 1
                    db.commit()
                    parts = ([f"{made} created"] if made else []) + ([f"{changed} updated"] if changed else []) + ([f"{same} already set"] if same and not (made or changed) else [])
                    flash("Full marks saved: " + (", ".join(parts) or "nothing to change") + ".", "success")
        return redirect(url_for("admin.assign_subtype", class_id=request.form.get("class_id") or ""))
    cls, sec, exam = (to_int(request.args.get(k)) for k in ("class_id", "section_id", "exam_id"))
    trash = bool(request.args.get("trash"))
    where, args = ("WHERE a.isDelete='1'" if trash else "WHERE a.isDelete='0'"), []
    for col, v in (("a.classId", cls), ("a.sectionId", sec), ("a.examId", exam)):
        if v:
            where += f" AND {col}=%s"; args.append(v)
    base = ("FROM assign_exam_subtype a JOIN classes c ON c.classId=a.classId JOIN sections s ON s.sectionId=a.sectionId "
            "JOIN subjects sb ON sb.subjectId=a.subjectId JOIN exams e ON e.examId=a.examId "
            f"JOIN exam_subtype x ON x.id=a.exam_subtype_id {where}")
    total = db.scalar(f"SELECT COUNT(*) {base}", args)
    p = paginate(total, 20, page_arg())
    rows = db.query(f"SELECT a.id, a.fullmarsks, c.class_name, s.section_name, sb.subject_name, e.exam_name, x.exam_type {base} ORDER BY a.classId, a.sectionId, sb.subject_name, e.examId LIMIT %s OFFSET %s", args + [20, p["offset"]])
    return render_template("assign_subtype.html", rows=rows, p=p, cls=cls, sec=sec, exam=exam, trash=trash, n_trash=_n_trash("assign_exam_subtype"),
                           subtypes=db.query("SELECT id, exam_type FROM exam_subtype WHERE isDelete='0' ORDER BY id"),
                           secs_for_filter=db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0'", (cls,)) if cls else [], **_lookups())


# ------------------------------------------------------------------ sign-in page editor
@bp.route("/login-page", methods=["GET", "POST"])
@admin_required
def login_page():
    from ..services import filestore, loginpage as LP, user_access as UA
    u = current_user()
    if request.method == "POST":
        if request.form.get("form") == "reset":
            LP.reset(u["id"]); UA.audit(u["id"], "login_page.reset", None, "Sign-in page reset to the default design")
            flash("The sign-in page is back to the default design.", "success")
            return redirect(url_for("admin.login_page"))
        LP.save(LP.from_form(request.form), u["id"])
        problems = []
        for slot in LP.IMAGE_SLOTS:
            if request.form.get("reset_" + slot):
                filestore.delete(f"login/{slot}")
                continue
            picked = request.form.getlist("pick_" + slot)
            err = None
            if picked:                                              # chosen in the media library popup
                from ..services import media as MD
                got = MD.take(u, picked[:1])
                err = LP.store_bytes(slot, got[0][2], u["id"]) if got else "That library item is not available."
            else:                                                   # classic upload (kept as a fallback)
                err = LP.store_image(slot, request.files.get(slot), u["id"])
            if err:
                problems.append(f"{slot.title()}: {err}")
        UA.audit(u["id"], "login_page.save", None, "Sign-in page design saved")
        for msg in problems:
            flash(msg, "error")
        flash("Sign-in page saved. It is live now." if not problems else "Saved, but some pictures were not changed.", "success" if not problems else "warning")
        return redirect(url_for("admin.login_page"))
    images = {slot: {"url": LP.image_url(slot), "custom": LP.has_custom(slot)} for slot in LP.IMAGE_SLOTS}
    return render_template("login_page.html", cfg=LP.config(), defaults=LP.defaults(), icons=LP.ICONS, symbols=LP.SYMBOLS, limits=LP.TEXT_LIMITS, images=images,
                           preview_url=url_for("admin.login_page_preview"))


@bp.route("/login-page/preview", methods=["POST"])
@admin_required
def login_page_preview():
    """Renders the sign-in page with the unsaved form values (nothing is stored)."""
    from ..services import loginpage as LP
    return render_template("login.html", lp=LP.view(LP.from_form(request.form)))


# ------------------------------------------------------------------ settings
@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    key = "marks_entry_editing_enabled"
    from .. import branding as B
    if request.method == "POST" and request.form.get("form") == "media":
        from ..services import media as MD
        MD.set_staff_purge(bool(request.form.get("staff_purge")))
        flash("Files & gallery settings saved." if request.form.get("staff_purge") else "Teachers can no longer delete files permanently.", "success")
        return redirect(url_for("admin.settings"))
    if request.method == "POST" and request.form.get("form") == "profile":
        from ..services import profile as P
        P.save({k: (request.form.get(k) or "").strip()[:200] for k in P.FIELDS if (request.form.get(k) or "").strip()})
        flash("Report profile saved.", "success")
        return redirect(url_for("admin.settings"))
    if request.method == "POST" and request.form.get("form") == "brand":
        name = (request.form.get("school_name") or "").strip()
        if not name:
            flash("School name is required.", "error")
        else:
            B.save(name[:120], (request.form.get("school_tagline") or "").strip()[:80])
            flash("School details saved.", "success")
        return redirect(url_for("admin.settings"))
    if request.method == "POST":
        val = "1" if request.form.get("enabled") else "0"
        if db.one("SELECT 1 FROM system_settings WHERE setting_key=%s", (key,)):
            db.execute("UPDATE system_settings SET setting_value=%s WHERE setting_key=%s", (val, key))
        else:
            db.execute("INSERT INTO system_settings (setting_key, setting_value) VALUES (%s,%s)", (key, val))
        from ..services import notifications as N
        N.notify([r["id"] for r in db.query("SELECT id FROM new_users WHERE deleted_at IS NULL AND active='1' AND user_type='2'")],
                 "Marks entry is now " + ("open" if val == "1" else "closed"), "Set by the administrator.", exclude=current_user()["id"])
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))
    enabled = db.scalar("SELECT setting_value FROM system_settings WHERE setting_key=%s", (key,), "1") != "0"
    return render_template("settings.html", enabled=enabled, brand=B.branding(), staff_purge=__import__("app.services.media", fromlist=["x"]).staff_may_purge(), profile=__import__("app.services.profile", fromlist=["x"]).get(), pfields=__import__("app.services.profile", fromlist=["x"]).FIELDS)
