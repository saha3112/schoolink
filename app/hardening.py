"""Security hardening for the public deployment (call init_app(app) once, right after create_app()).

  * trusts the tunnel / proxy for the client address and scheme only, and answers only for the configured host names
  * HTTPS: Secure session cookie whenever the request is HTTPS, HSTS, plain-http requests from outside are sent to https
  * security headers (CSP, anti-clickjacking, nosniff, referrer, permissions, COOP/CORP) and no-store for private pages
  * generic error pages: a failure never shows code, paths or a traceback"""
from flask import abort, redirect, render_template, request
from flask.sessions import SecureCookieSessionInterface
from werkzeug.middleware.proxy_fix import ProxyFix

LOCAL = {"127.0.0.1", "localhost", "[::1]", "::1"}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; "
       "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self' https://cloudflareinsights.com; "
       "frame-src 'self' blob: data:; object-src 'self'; worker-src 'self' blob:; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
_dummy = [None]


def client_ip():
    """Address of the visitor. The app listens on 127.0.0.1 only, so the only caller is the tunnel, which sets CF-Connecting-IP."""
    return ((request.headers.get("CF-Connecting-IP") or request.remote_addr or "?").strip())[:64]


def dummy_hash():
    """A real bcrypt hash used to spend the same time when a login does not exist (no user enumeration by timing)."""
    if _dummy[0] is None:
        from .auth import hash_password
        _dummy[0] = hash_password("not-a-real-password-" + __import__("secrets").token_hex(8))
    return _dummy[0]


class _CloudflareScheme:
    """Cloudflare tells the origin how the visitor connected in CF-Visitor ({"scheme":"https"}). Trusted because only the tunnel (loopback) can reach the app."""

    def __init__(self, wsgi):
        self.wsgi = wsgi

    def __call__(self, environ, start_response):
        if environ.get("REMOTE_ADDR") in ("127.0.0.1", "::1") and '"scheme":"https"' in (environ.get("HTTP_CF_VISITOR") or "").replace(" ", ""):
            environ["wsgi.url_scheme"] = "https"
        return self.wsgi(environ, start_response)


class _Sessions(SecureCookieSessionInterface):
    def get_cookie_secure(self, app):            # Secure over HTTPS (the public tunnel); http://127.0.0.1 keeps working locally
        try:
            return request.is_secure
        except RuntimeError:
            return False


def init_app(app):
    allowed = {h for h in app.config.get("ALLOWED_HOSTS", []) if h} | LOCAL
    app.wsgi_app = _CloudflareScheme(ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0))
    app.session_interface = _Sessions()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_REFRESH_EACH_REQUEST=True)

    @app.before_request
    def guard_host_and_scheme():
        host = (request.host or "").split(":")[0].lower() if not request.host.startswith("[") else "[::1]"
        if len(allowed) > len(LOCAL) and host not in allowed:
            abort(400)                                           # unknown Host header (cache poisoning / spoofed links)
        if not request.is_secure and host not in LOCAL and request.headers.get("X-Forwarded-Proto") == "http":
            return redirect(request.url.replace("http://", "https://", 1), 301)

    @app.after_request
    def security_headers(resp):
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "SAMEORIGIN")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        h.setdefault("Content-Security-Policy", CSP)
        if request.is_secure:
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        ctype = h.get("Content-Type", "")
        if request.endpoint not in ("static", "auth.brand_image") and ctype.startswith(("text/html", "application/json")) and "Cache-Control" not in h:
            h["Cache-Control"] = "no-store"                      # private pages are never kept by the browser or a proxy
            h["Pragma"] = "no-cache"
        return resp

    @app.errorhandler(400)
    def bad_request(_e):
        return render_template("error.html", code=400, msg="That request could not be processed. Reload the page and try again."), 400

    @app.errorhandler(429)
    def too_many(_e):
        return render_template("error.html", code=429, msg="Too many requests. Please wait a moment."), 429

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("error.html", code=500, msg="Something went wrong on our side. Please try again."), 500
    return app
