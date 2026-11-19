import os
from flask import Flask, render_template, session, g, request, redirect, url_for
from config import Config
from . import db as dbm
from .auth import current_user, teacher_scope
from .menu import MENU, PROFILE_MENU, ENDPOINT_FEATURE, PARENT_MENU


def allowed(cap, user, scope):
    if cap is None:
        return True
    if not user:
        return False
    if user["is_admin"]:
        return True
    if cap == "admin":
        return False
    if cap == "any_class":                       # needs at least one class / section of their own
        return bool(scope.get("subject_teacher") or scope.get("class_teacher"))
    return bool(scope.get(cap))


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)
    app.teardown_appcontext(dbm.close_db)

    from .blueprints import main, account, admin, students, marks, classteacher, leave, parentpanel, parents, reports, school, signatures, layouts_admin, search, live as live_bp, media, csvio, security
    for bp in (main.bp, account.bp, admin.bp, students.bp, marks.bp, classteacher.bp, reports.bp, signatures.admin_bp, signatures.bp, school.bp, parents.bp, leave.bp, parentpanel.bp, layouts_admin.bp, search.bp, live_bp.bp, media.bp, csvio.bp, security.bp):
        app.register_blueprint(bp)
    app.register_blueprint(main.auth_bp)
    app.register_blueprint(main.notify_bp)

    # report templates read signature files from the database instead of the disk
    from . import phpr
    from .services import filestore

    def _sig_reader(rel):
        try:
            f = filestore.get("signature/" + rel)
        except Exception:
            return None
        return f["data"] if f else None
    phpr.FILE_HOOK = _sig_reader

    import secrets
    from flask import abort

    @app.before_request
    def csrf_protect():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        if request.method == "POST" and request.endpoint != "auth.login":
            if request.form.get("csrf_token") != session.get("csrf") and request.headers.get("X-CSRF-Token") != session.get("csrf"):
                abort(400, "Invalid or missing CSRF token. Reload the page and try again.")

    @app.before_request
    def enforce_page_access():
        if request.endpoint == 'static' or not request.endpoint:
            return
        from .services import user_access as UA
        u = current_user()
        if u and u.get('is_teacher'):
            from .services import features
            feature=ENDPOINT_FEATURE.get(request.endpoint)
            if (feature and feature not in features.available(u)) or not features.nav_allowed(u,request.endpoint):
                from flask import abort
                abort(403)
        if u and not UA.endpoint_allowed(u, request.endpoint, request.view_args):
            from flask import abort
            abort(403)

    # ---- data version: any successful change invalidates every cached read at once (see app/cache.py)
    NO_BUMP = ("static", "notify.", "live.", "search.", "auth.")

    @app.after_request
    def keep_cache_fresh(resp):
        try:
            ep = request.endpoint or ""
            if request.method in ("POST", "PUT", "PATCH", "DELETE") and resp.status_code < 400 and not ep.startswith(NO_BUMP):
                from . import cache
                cache.bump(ep)
        except Exception:
            pass
        return resp

    @app.after_request
    def static_caching(resp):
        """Versioned assets (?v=...) never change under the same URL, so the browser may keep them for a year."""
        if request.endpoint == "static" and resp.status_code == 200:
            resp.headers["Cache-Control"] = "public, max-age=31536000, immutable" if request.args.get("v") else "public, max-age=3600"
        return resp

    from .branding import branding
    from .services import live as live_svc

    @app.after_request
    def publish_changes(resp):
        """Every successful change is announced to the other open panels (real-time sync)."""
        try:
            if request.method == "POST" and resp.status_code < 400 and request.blueprint in live_svc.PUBLISH_FROM and "uid" in session:
                from .utils import to_int
                live_svc.publish(request.blueprint, to_int(request.values.get("class_id")), to_int(request.values.get("section_id")),
                                 to_int(request.values.get("exam_id")), session.get("uid"))
        except Exception:
            pass
        return resp

    @app.context_processor
    def inject():
        u = current_user()
        from .services import user_access as UA
        from .services import features
        sc = teacher_scope(u) if u and u["is_teacher"] else {}
        menu = []
        feats = None
        if u and (u["is_admin"] or u["is_teacher"]):
            feats = features.available(u)
        for label, ep, icon, cap, children in MENU:
            if children is None:
                if allowed(cap, u, sc) and UA.endpoint_allowed(u, ep):
                    menu.append({"label": label, "endpoint": ep, "icon": icon, "children": None})
                continue
            kids = [{"label": cl, "endpoint": ce} for cl, ce, cc in children if allowed(cc, u, sc) and UA.endpoint_allowed(u, ce) and features.nav_allowed(u, ce)
                    and (feats is None or ENDPOINT_FEATURE.get(ce) is None or ENDPOINT_FEATURE[ce] in feats)]
            if kids:
                menu.append({"label": label, "endpoint": None, "icon": icon, "children": kids})
        pmenu = [{"label": l, "endpoint": e, "icon": i} for l, e, i, c in PROFILE_MENU if allowed(c, u, sc) and UA.endpoint_allowed(u, e)]
        if u and u['can_reset_passwords'] and not any(p['endpoint'] == 'account.users' for p in pmenu):
            pmenu.append({'label':'Users & password resets', 'endpoint':'account.users', 'icon':'shield'})
        if u and u['is_admin']:
            administration = [{'label':label, 'endpoint':ep} for label,ep in (
                ('Users & passwords','account.users'),('Create admin','security.admin_accounts'),
                ('User permissions','security.permissions'),('Mail / SMTP','security.smtp'),('School settings','admin.settings'),('Sign-in page','admin.login_page'))
                if UA.endpoint_allowed(u, ep)]
            if administration:
                menu.append({'label':'Administration','endpoint':None,'icon':'shield','children':administration})
        # users that are neither admin nor teacher only get the password page - parents get their own panel
        if u and not u["is_admin"] and not u["is_teacher"]:
            menu = list(PARENT_MENU) if u.get("is_parent") else []
        if u and not u['is_admin'] and u['can_reset_passwords']:
            menu.append({'label':'Password resets','endpoint':'account.users','icon':'shield','children':None})
        topics = live_svc.INTEREST.get(request.blueprint or "", []) if u else []
        try:
            lsince = live_svc.latest() if topics else 0
        except Exception:
            lsince, topics = 0, []
        from .services.csvio import ENDPOINT_KIND
        csv_kind = ENDPOINT_KIND.get(request.endpoint or "") if u and (u["is_admin"] or u["is_teacher"]) else None
        if request.endpoint in ('parents.all_parents','students.student_list') and request.args.get('trash') == '1':
            csv_kind = None
        if csv_kind in ("students", "parents") and not (u and u["is_admin"]):
            csv_kind = None                                 # these imports are administrator-only
        return dict(csv_kind=csv_kind, live_topics=",".join(topics), live_since=lsince, csrf_token=session.get('csrf', ''), me=u, menu=menu, profile_menu=pmenu, school_name=branding()["name"], school_tagline=branding()["tagline"],
                    current_ep=request.endpoint or "", can_access=lambda ep: UA.endpoint_allowed(u, ep))

    from .utils import page_url
    app.jinja_env.globals['page_url'] = page_url
    app.jinja_env.globals['furl'] = school.furl

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("error.html", code=403, msg="You do not have access to this page."), 403

    @app.errorhandler(404)
    def notfound(_e):
        return render_template("error.html", code=404, msg="Page not found."), 404

    return app
