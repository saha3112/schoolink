"""All Parents (staff side): list, search, details, edit contact data, reset password, CSV export."""
import csv
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from .. import db
from ..auth import current_user, hash_password, roles_required, admin_required
from ..services import access, features, notifications as N
from ..services import parent_identity as PI
from ..utils import page_arg, paginate, to_int

bp = Blueprint("parents", __name__, url_prefix="/parents")
cap = roles_required("class_teacher")


def _scope():
    """None for admins, otherwise the set of (class, section) the class teacher looks after."""
    u = current_user()
    return None if u["is_admin"] else {(p["classId"], p["sectionId"]) for p in access.class_pairs(u)}


def _where(scope):
    cls, sec, q = to_int(request.args.get("class_id")), to_int(request.args.get("section_id")), request.args.get("q", "").strip()
    trash=request.args.get('trash')=='1'
    if trash and scope is not None:abort(403)
    state='p.deleted_at IS NOT NULL' if trash else 'p.deleted_at IS NULL'
    where, args = ["EXISTS (SELECT 1 FROM students st WHERE st.parent_id=p.id AND st.isDelete='0'" + (" AND st.class_id=%s" if cls else "") + (" AND st.section_id=%s" if sec else "") + ")"], []
    if scope is None and not cls and not sec:
        where = [state]
    else:
        where.append(state)
    if cls: args.append(cls)
    if sec: args.append(sec)
    if scope is not None:
        if not scope:
            where.append("1=0")
        else:
            conds = " OR ".join(["(st2.class_id=%s AND st2.section_id=%s)"] * len(scope))
            where.append(f"EXISTS (SELECT 1 FROM students st2 WHERE st2.parent_id=p.id AND st2.isDelete='0' AND ({conds}))")
            for c, s in scope: args += [c, s]
    if request.args.get('missing') == '1':
        where.append(PI.sql_name() + "='' ")
    if q:
        like = f"%{q}%"
        where.append("(" + PI.sql_name() + " LIKE %s OR p.phone_1 LIKE %s OR p.phone_2 LIKE %s OR p.email LIKE %s OR p.code LIKE %s OR p.address LIKE %s "
                     "OR p.id IN (SELECT st3.parent_id FROM students st3 WHERE st3.isDelete='0' AND st3.student_name LIKE %s))")
        args += [like] * 7
    return " AND ".join(where), args, cls, sec, q


def _children(ids):
    out = {}
    if ids:
        ph = ",".join(["%s"] * len(ids))
        for r in db.query(f"SELECT st.parent_id, st.studentId, st.student_name, st.student_code, st.ADMNO, st.student_rollNumber, c.class_name, s.section_name FROM students st "
                          f"JOIN classes c ON c.classId=st.class_id JOIN sections s ON s.sectionId=st.section_id WHERE st.isDelete='0' AND st.parent_id IN ({ph}) "
                          f"ORDER BY st.class_id, st.student_name", ids):
            out.setdefault(r["parent_id"], []).append(r)
    return out


def _name(p):
    return PI.name(p)


def _fill_parent_name(parent):
    return PI.fill(parent)


@bp.route("/", methods=["GET","POST"])
@cap
def all_parents():
    if request.method=='POST':
        if not current_user()['is_admin']:abort(403)
        from ..services import parent_lifecycle as lifecycle
        try:
            action=request.form.get('action','')
            count=lifecycle.apply(current_user(),action,request.form.getlist('ids'))
            message={'trash':'moved to Trash','restore':'restored','purge':'deleted permanently'}[action]
            flash(f'{count} parent(s) {message}. Student records were kept.','success')
        except lifecycle.ParentActionError as error:
            flash(str(error),'error')
        return redirect(url_for('parents.all_parents',**{key:request.args[key] for key in ('trash','class_id','section_id','missing','q') if key in request.args}))
    scope = _scope()
    where, args, cls, sec, q = _where(scope)
    total = db.scalar(f"SELECT COUNT(*) FROM parents p LEFT JOIN new_users u ON u.id=p.user_id WHERE {where}", args)
    pg = paginate(total, 25, page_arg())
    rows = db.query(f"SELECT p.*, u.fname AS account_name FROM parents p LEFT JOIN new_users u ON u.id=p.user_id WHERE {where} ORDER BY p.id LIMIT %s OFFSET %s", args + [pg["per_page"], pg["offset"]])
    kids = _children([r["id"] for r in rows])
    for r in rows:
        _fill_parent_name(r)
        r["name"] = _name(r); r["children"] = kids.get(r["id"], [])
    pairs = features.pairs("card", current_user()) if scope is not None else None
    classes = access.classes_for(pairs) if pairs is not None else db.query("SELECT classId, class_name FROM classes WHERE isDelete='0' ORDER BY classId")
    sections = (access.sections_for(pairs, cls) if pairs is not None else db.query("SELECT sectionId, section_name FROM sections WHERE class_id=%s AND isDelete='0' ORDER BY section_name", (cls,))) if cls else []
    return render_template("parents_list.html", rows=rows, p=pg, q=q, cls=cls, sec=sec, classes=classes, sections=sections, missing=request.args.get('missing') == '1', trash=request.args.get('trash')=='1',
                           n_trash=db.scalar('SELECT COUNT(*) FROM parents WHERE deleted_at IS NOT NULL') if current_user()['is_admin'] else 0)


@bp.route("/export.csv")
@cap
def export():
    scope = _scope()
    where, args, *_ = _where(scope)
    rows = db.query(f"SELECT p.*, u.fname AS account_name FROM parents p LEFT JOIN new_users u ON u.id=p.user_id WHERE {where} ORDER BY p.id", args)
    kids = _children([r["id"] for r in rows])
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["mobile", "first_name", "middle_name", "last_name", "alternate_phone", "secondary_name", "address", "student_codes", "admission_numbers", "student_names", "class_names", "section_names", "roll_numbers", "parent_code", "email", "occupation"])
    for r in rows:
        _fill_parent_name(r)
        children = kids.get(r["id"], [])
        values = ["; ".join(str(k.get(key) or "") for k in children) for key in ("student_code", "ADMNO", "student_name", "class_name", "section_name", "student_rollNumber")]
        w.writerow([r["phone_1"], r["fname"] or "", r["mname"] or "", r["lname"] or "", r["phone_2"] if r["phone_2"] != r["phone_1"] else "", r["secondary_name"] or "", r["address"] or "", *values, r["code"], r["email"] or "", r["occupation"] or ""])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": 'attachment; filename="all_parents.csv"'})


def _student_options():
    return db.query("SELECT st.studentId, st.student_name, st.student_code, st.ADMNO, st.parent_id, c.class_name, s.section_name FROM students st LEFT JOIN classes c ON c.classId=st.class_id LEFT JOIN sections s ON s.sectionId=st.section_id WHERE st.isDelete='0' ORDER BY st.student_name, st.studentId")


def _chosen_children(form, students):
    chosen = {to_int(value) for value in form.getlist("child_ids") if value}
    if None in chosen or not chosen.issubset({s["studentId"] for s in students}):
        raise ValueError("Please select valid students from the child lists.")
    return chosen


@bp.route("/create", methods=["GET", "POST"])
@admin_required
def create():
    from ..services.parent_links import create_parent, valid_email
    import re
    students = _student_options()
    if request.method == "POST":
        f = request.form
        mobile = re.sub(r"\D", "", f.get("mobile", ""))
        try:
            if not 10 <= len(mobile) <= 15:
                raise ValueError("Enter a valid mobile number (10–15 digits).")
            if not f.get("fname", "").strip():
                raise ValueError("First name is required.")
            if len(f.get("initial_password", "")) < 6:
                raise ValueError("Initial password must have at least 6 characters.")
            if db.one("SELECT id FROM parents WHERE REPLACE(REPLACE(phone_1,' ',''),'+','')=%s AND deleted_at IS NULL", (mobile,)) or db.one("SELECT id FROM new_users WHERE email=%s AND deleted_at IS NULL", (mobile,)):
                raise ValueError("This mobile already exists. Open the existing parent to link children.")
            selected = _chosen_children(f, students)
            details = {key: f.get(key, "").strip() for key in ("fname", "mname", "lname", "phone_2", "secondary_name", "address", "email", "occupation")}
            if any(len(value) > (500 if key == "address" else 150) for key, value in details.items()):
                raise ValueError("A parent detail is too long.")
            if not valid_email(details["email"]):
                raise ValueError("Enter a valid email address or leave Email ID blank.")
            pid = create_parent(mobile, details, f["initial_password"])
            for sid in selected:
                db.execute("UPDATE students SET parent_id=%s WHERE studentId=%s", (pid, sid), commit=False)
            db.commit()
            flash("Parent created and selected children linked.", "success")
            return redirect(url_for("parents.all_parents"))
        except ValueError as error:
            db.rollback()
            flash(str(error), "error")
        except Exception:
            db.rollback()
            raise
    return render_template("parent_create.html", student_options=students, selected_children=request.form.getlist("child_ids") if request.method == "POST" else [])


@bp.route("/<int:pid>", methods=["GET", "POST"])
@cap
def detail(pid):
    p = db.one("SELECT p.*, u.fname AS account_name FROM parents p LEFT JOIN new_users u ON u.id=p.user_id AND u.deleted_at IS NULL WHERE p.id=%s AND p.deleted_at IS NULL", (pid,))
    if not p:
        abort(404)
    _fill_parent_name(p)
    scope = _scope()
    kids = _children([pid]).get(pid, [])
    if scope is not None:
        mine = {(k["class_name"], k["section_name"]) for k in kids}
        ok = db.one("SELECT 1 AS x FROM students WHERE parent_id=%s AND isDelete='0' AND (" + " OR ".join(["(class_id=%s AND section_id=%s)"] * max(len(scope), 1)) + ")",
                    [pid] + [v for pair in (scope or {(0, 0)}) for v in pair])
        if not ok:
            abort(403)
    u = current_user()
    if request.method == "POST":
        act = request.form.get("action")
        if act == "reset":
            from .account import reset_password
            return reset_password(int(p['user_id']))
        elif act == "link" and u["is_admin"]:
            try:
                selected = _chosen_children(request.form, _student_options())
                for sid in selected:
                    db.execute("UPDATE students SET parent_id=%s WHERE studentId=%s", (pid, sid), commit=False)
                db.commit()
                flash("Selected children linked. Existing children remain linked.", "success")
            except ValueError as error:
                db.rollback()
                flash(str(error), "error")
            except Exception:
                db.rollback()
                raise
        elif act == "save" and u["is_admin"]:
            from ..services.parent_links import valid_email
            f = request.form
            if not f.get("fname", "").strip():
                flash("First name is required.", "error")
                return redirect(url_for("parents.detail", pid=pid))
            if not valid_email(f.get("email", "").strip()):
                flash("Enter a valid email address or leave Email ID blank.", "error")
                return redirect(url_for("parents.detail", pid=pid))
            import re
            mobile = re.sub(r"\D", "", f.get("mobile", p["phone_1"]))
            if not 10 <= len(mobile) <= 15:
                flash("Enter a valid login mobile number (10–15 digits).", "error")
                return redirect(url_for("parents.detail", pid=pid))
            if mobile != re.sub(r"\D", "", p["phone_1"] or ""):
                conflict = db.one("SELECT id FROM parents WHERE REGEXP_REPLACE(phone_1,'[^0-9]','')=%s AND id<>%s AND deleted_at IS NULL", (mobile, pid))
                login_conflict = db.one("SELECT id FROM new_users WHERE email=%s AND id<>%s AND deleted_at IS NULL", (mobile, p["user_id"]))
                if conflict or login_conflict:
                    flash("This login mobile number is already used by another account.", "error")
                    return redirect(url_for("parents.detail", pid=pid))
            try:
                db.execute("UPDATE parents SET fname=%s, mname=%s, lname=%s, phone_2=%s, address=%s, secondary_name=%s, occupation=%s, email=%s, phone_1=%s WHERE id=%s",
                           (f.get("fname", "").strip() or None, f.get("mname", "").strip() or None, f.get("lname", "").strip() or None, f.get("phone_2", "").strip(),
                            f.get("address", "").strip() or None, f.get("secondary_name", "").strip() or None, f.get("occupation", "").strip() or "", f.get("email", "").strip(), mobile, pid), commit=False)
                db.execute("UPDATE new_users SET email=%s, fname=%s WHERE id=%s", (mobile, " ".join(f.get(key, "").strip() for key in ("fname", "mname", "lname")).strip(), p["user_id"]), commit=False)
                db.commit()
            except Exception:
                db.rollback()
                raise
            flash("Parent details saved.", "success")
        return redirect(url_for("parents.detail", pid=pid))
    p["name"] = _name(p)
    return render_template("parent_detail.html", p=p, kids=kids, student_options=_student_options() if u["is_admin"] else [], selected_children=[k["studentId"] for k in kids])
