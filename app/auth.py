"""Authentication, roles and menu visibility.

Roles (new_users.user_type):
    1 -> admin, 0/9 -> super admin (both full access)
    2 -> teacher (menu depends on what is assigned to the teacher)
Anything else cannot use this panel.
"""
from functools import wraps

import bcrypt
from flask import session, redirect, url_for, request, flash, abort, g

from . import db

ADMIN_TYPES = {"0", "1", "9"}
TEACHER_TYPES = {"2"}


def verify_password(plain, stored):
    try:
        return bcrypt.checkpw(plain.encode()[:72], stored.encode())
    except Exception:
        return False


def hash_password(plain):
    # PHP compatible ($2y$) so the old application can still read the hash.
    h = bcrypt.hashpw(plain.encode()[:72], bcrypt.gensalt(10))
    return h.replace(b"$2b$", b"$2y$").decode()


def current_user():
    if "user" in g:
        return g.user
    uid = session.get("uid")
    g.user = None
    if uid:
        from . import cache
        u = cache.get(("auth.user", str(uid)), lambda: db.one("SELECT id, fname, email, user_type, active FROM new_users "
                                                              "WHERE id=%s AND deleted_at IS NULL", (uid,)), 20)
        if u and str(u["active"]) in ("1", "true"):
            from .services import user_access as UA
            u['_access'] = cache.get(("auth.access", u['id']), lambda: UA.record(u['id']), 20)
            version = u['_access']['session_version'] if u['_access'] else 0
            if session.get('auth_version', 0) != version:
                session.clear()
                return None
            u["user_type"] = str(u["user_type"])
            u["is_super_admin"] = UA.is_super(u)
            u["is_admin"] = u["user_type"] in ADMIN_TYPES
            u["is_teacher"] = u["user_type"] in TEACHER_TYPES
            u["is_parent"] = u["user_type"] == "3"
            if u['is_parent']:
                from .services import parent_identity as PI
                u['fname'] = PI.for_users([u['id']]).get(u['id']) or 'Parent'
            u["initials"] = "".join(w[0] for w in (u["fname"] or "U").split()[:2]).upper()
            u["role_label"] = ("Super Admin" if u["user_type"] in ("0", "9")
                               else "Admin" if u["user_type"] == "1"
                               else "Teacher" if u["user_type"] == "2" else "Parent" if u["user_type"] == "3" else "User")
            from .services import filestore
            u['profile_version'] = filestore.version(f"profile/{u['id']}.png")
            u['can_reset_passwords'] = UA.has(u, 'reset_passwords')
            u['sidebar_label'] = ('Super Admin Workspace' if u['is_super_admin'] else 'Administration Workspace' if u['is_admin'] else 'Teacher Workspace' if u['is_teacher'] else 'Parent & Family Portal' if u['is_parent'] else 'My Workspace')
            g.user = u
    return g.user


def teacher_scope(user=None):
    """What the logged in teacher is allowed to do -> drives the menu and the data filters."""
    user = user or current_user()
    if not user:
        return {}
    if "scope" in g:
        return g.scope
    tid = user["id"]
    subj = db.query(
        "SELECT DISTINCT classId, sectionId, subjectId FROM assign_teacher "
        "WHERE t_id=%s AND isDelete='0'", (tid,))
    cls = db.query("SELECT DISTINCT classId, sectionId FROM classTeacher "
                   "WHERE teacherId=%s AND isDelete='0'", (tid,))
    g.scope = {
        "subject_teacher": bool(subj),
        "class_teacher": bool(cls),
        "subject_rows": subj,
        "class_rows": cls,
    }
    return g.scope


def login_required(f):
    @wraps(f)
    def w(*a, **kw):
        if not current_user():
            session.clear()
            return redirect(url_for("auth.login", next=request.path))
        return f(*a, **kw)
    return w


def roles_required(*caps):
    """caps: 'admin', 'subject_teacher', 'class_teacher'. Any one match is enough.
    Admin always passes."""
    def deco(f):
        @wraps(f)
        @login_required
        def w(*a, **kw):
            u = current_user()
            if u["is_admin"]:
                return f(*a, **kw)
            if u["is_teacher"]:
                sc = teacher_scope(u)
                if "teacher" in caps or any(sc.get(c) for c in caps):
                    return f(*a, **kw)
            abort(403)
        return w
    return deco


admin_required = roles_required("admin")


def parent_required(f):
    """Parent panel: signed in parent (admins may look too, handled per page)."""
    @wraps(f)
    @login_required
    def w(*a, **kw):
        if not current_user().get("is_parent"):
            abort(403)
        return f(*a, **kw)
    return w


def my_children(user=None):
    """Active students linked to the logged in parent (parents.user_id -> students.parent_id)."""
    user = user or current_user()
    if "children" in g:
        return g.children
    g.children = db.query("""SELECT st.studentId, st.student_name, st.student_rollNumber, st.class_id, st.section_id, st.student_code, st.ADMNO, st.DOB,
        c.class_name, s.section_name FROM parents p JOIN students st ON st.parent_id=p.id AND st.isDelete='0'
        JOIN classes c ON c.classId=st.class_id JOIN sections s ON s.sectionId=st.section_id
        WHERE p.user_id=%s ORDER BY st.class_id, st.student_name""", (str(user["id"]),))
    return g.children
