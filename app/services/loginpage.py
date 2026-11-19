"""Editable sign-in page: texts, colours, icons and images. Stored in the database, edited by administrators.

Every value has a default that reproduces the original design, every colour is checked as #RRGGBB, every icon comes from a fixed
set, and images are re-encoded by Pillow before they are stored - so nothing typed or uploaded here can inject markup."""
import io
import json
import re

from .. import cache, db
from . import filestore

TEXT_LIMITS = {
    "wordmark": 40, "wordmark_sub": 60, "pill": 60, "school_line": 80, "headline_1": 60, "headline_2": 60, "intro": 220,
    "kicker": 40, "welcome": 50, "welcome_sub": 160, "email_label": 40, "email_ph": 60, "password_label": 30, "password_ph": 60,
    "remember": 30, "button": 40, "help_title": 50, "help_text": 140,
}
DEFAULT_TEXTS = {
    "wordmark": "Schoolink", "wordmark_sub": "School Management Portal", "pill": "Your school. Connected.",
    "school_line": "Your learning community",
    "headline_1": "Learning together.", "headline_2": "Growing every day.",
    "intro": "A shared space for learning, progress and all the moments that make school life special.",
    "kicker": "Your school portal", "welcome": "Welcome back",
    "welcome_sub": "Your school day, beautifully connected.\nSign in to pick up where you left off.",
    "email_label": "Email or mobile number", "email_ph": "Enter your email or mobile",
    "password_label": "Password", "password_ph": "Enter your password",
    "remember": "Remember me", "button": "Sign in to your portal",
    "help_title": "Need help signing in?", "help_text": "Please contact your school administrator.",
}
DEFAULT_COLORS = {
    "brand": "#4525ef", "grad1": "#04a5f7", "grad2": "#2542e7", "grad3": "#6730f4", "grad4": "#b241ed",
    "bg1": "#fafcff", "bg2": "#e9efff", "bg3": "#ddebff", "glow1": "#d2b4ff", "glow2": "#cfddff",
    "text": "#0b1749", "sub": "#56648f",
}
DEFAULT_FEATURES = [
    {"icon": "calendar", "label": "Attendance", "color": "#6216f5"},
    {"icon": "chart", "label": "Report Cards", "color": "#008bfa"},
    {"icon": "megaphone", "label": "School Updates", "color": "#ff7614"},
]
DEFAULT_SHOW = {"pill": True, "school": True, "features": True, "art": True}
DEFAULT_SYMBOL = "graduation"
IMAGE_SLOTS = {"logo": "img/sts-logo.png", "art": "img/education-scene.png", "bg": None}

_S = 'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"'
ICONS = {          # name -> (label, inner svg). Trusted constants: they are the only markup ever rendered for an icon.
    "calendar": ("Calendar", '<rect x="4" y="5" width="16" height="16" rx="3"/><path d="M8 3v4m8-4v4M4 11h16m-11 5 2 2 4-4"/>'),
    "chart": ("Chart", '<path d="M6 19v-6m6 6V8m6 11V3"/>'),
    "megaphone": ("Megaphone", '<path d="m4 10 15-6v15L4 14v-4Zm5 6 2 5H7l-2-7m14-6c4 0 4 8 0 8"/>'),
    "book": ("Book", '<path d="M4 19V5a2 2 0 0 1 2-2h14v14H6a2 2 0 0 0-2 2Zm0 0a2 2 0 0 0 2 2h14M8 7h8"/>'),
    "users": ("People", '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>'),
    "award": ("Award", '<circle cx="12" cy="9" r="6"/><path d="m8.5 14-1.5 8 5-3 5 3-1.5-8"/>'),
    "bell": ("Bell", '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9m4.3 13a2 2 0 0 0 3.4 0"/>'),
    "clock": ("Clock", '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    "message": ("Message", '<path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"/>'),
    "shield": ("Shield", '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6Z"/><path d="m9 12 2 2 4-4"/>'),
    "star": ("Star", '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9Z"/>'),
    "home": ("Home", '<path d="m3 11 9-8 9 8M5 10v10h14V10M10 20v-6h4v6"/>'),
    "camera": ("Gallery", '<path d="M3 7h4l2-3h6l2 3h4v13H3Z"/><circle cx="12" cy="13" r="4"/>'),
    "file": ("Document", '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Zm0 0v5h5M9 13h6M9 17h6"/>'),
    "heart": ("Heart", '<path d="M12 20s-8-4.6-8-10.2A4.3 4.3 0 0 1 12 7a4.3 4.3 0 0 1 8 2.8C20 15.4 12 20 12 20Z"/>'),
    "trophy": ("Trophy", '<path d="M8 4h8v6a4 4 0 0 1-8 0Zm-3 1h3v3a3 3 0 0 1-3-3Zm14 0h-3v3a3 3 0 0 0 3-3ZM12 14v4m-4 3h8"/>'),
    "bus": ("Transport", '<rect x="4" y="3" width="16" height="15" rx="3"/><path d="M4 12h16M7 18v3m10-3v3"/><circle cx="8" cy="15" r=".6"/><circle cx="16" cy="15" r=".6"/>'),
    "pencil": ("Pencil", '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>'),
    "graduation": ("Graduation cap", '<path d="m2 9 10-5 10 5-10 5L2 9Z"/><path d="M6 11v6c4 3 8 3 12 0v-6M22 9v7"/>'),
}
SYMBOLS = ["graduation", "book", "star", "home", "award", "heart", "trophy", "users"]
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ready = [False]


def icon_svg(name, size=24, extra=""):
    inner = ICONS.get(name, ICONS["star"])[1]
    return f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" {extra or _S} aria-hidden="true">{inner}</svg>'


def _ensure():
    if _ready[0]:
        return
    db.execute("CREATE TABLE IF NOT EXISTS sl_login_page (id TINYINT PRIMARY KEY, config LONGTEXT NULL, updated_by INT NULL, "
               "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB")
    _ready[0] = True


def _tint(hex_color, amount):
    """Mix a colour with white (amount 0..1 = how much white)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    mix = lambda v: round(v + (255 - v) * amount)
    return "#%02x%02x%02x" % (mix(r), mix(g), mix(b))


def defaults():
    return {"texts": dict(DEFAULT_TEXTS), "colors": dict(DEFAULT_COLORS), "features": [dict(f) for f in DEFAULT_FEATURES],
            "show": dict(DEFAULT_SHOW), "symbol": DEFAULT_SYMBOL, "bg_strength": 55}


def _merge(stored):
    cfg = defaults()
    if not isinstance(stored, dict):
        return cfg
    for k, lim in TEXT_LIMITS.items():
        v = (stored.get("texts") or {}).get(k)
        if isinstance(v, str) and v.strip():
            cfg["texts"][k] = v.strip()[:lim]
    for k in DEFAULT_COLORS:
        v = (stored.get("colors") or {}).get(k)
        if isinstance(v, str) and HEX.match(v):
            cfg["colors"][k] = v.lower()
    feats = stored.get("features")
    if isinstance(feats, list):
        for i, f in enumerate(feats[:3]):
            if isinstance(f, dict):
                if f.get("icon") in ICONS:
                    cfg["features"][i]["icon"] = f["icon"]
                if isinstance(f.get("label"), str) and f["label"].strip():
                    cfg["features"][i]["label"] = f["label"].strip()[:30]
                if isinstance(f.get("color"), str) and HEX.match(f["color"]):
                    cfg["features"][i]["color"] = f["color"].lower()
    for k in DEFAULT_SHOW:
        if isinstance((stored.get("show") or {}).get(k), bool):
            cfg["show"][k] = stored["show"][k]
    if stored.get("symbol") in SYMBOLS:
        cfg["symbol"] = stored["symbol"]
    try:
        cfg["bg_strength"] = max(0, min(100, int(stored.get("bg_strength", 55))))
    except (TypeError, ValueError):
        pass
    return cfg


def config():
    """Saved configuration merged over the defaults."""
    def load():
        _ensure()
        row = db.one("SELECT config FROM sl_login_page WHERE id=1")
        try:
            return _merge(json.loads(row["config"])) if row and row["config"] else defaults()
        except ValueError:
            return defaults()
    return cache.get(("loginpage.config",), load, 300)


def from_form(form):
    """Configuration from a submitted form (used by Save and by the live preview). Anything invalid falls back to the saved value."""
    base, out = config(), defaults()
    out["texts"] = {k: ((form.get("t_" + k) if form.get("t_" + k) is not None else base["texts"][k]).replace("\r", "").strip()[:lim] or DEFAULT_TEXTS[k])
                    for k, lim in TEXT_LIMITS.items()}
    for k in DEFAULT_COLORS:
        v = (form.get("c_" + k) or "").strip()
        out["colors"][k] = v.lower() if HEX.match(v) else base["colors"][k]
    for i in range(3):
        icon, label, color = form.get(f"f{i}_icon"), (form.get(f"f{i}_label") or "").strip()[:30], (form.get(f"f{i}_color") or "").strip()
        out["features"][i] = {"icon": icon if icon in ICONS else base["features"][i]["icon"], "label": label or DEFAULT_FEATURES[i]["label"],
                              "color": color.lower() if HEX.match(color) else base["features"][i]["color"]}
    out["show"] = {k: bool(form.get("s_" + k)) for k in DEFAULT_SHOW}
    out["symbol"] = form.get("symbol") if form.get("symbol") in SYMBOLS else base["symbol"]
    try:
        out["bg_strength"] = max(0, min(100, int(form.get("bg_strength", base["bg_strength"]))))
    except (TypeError, ValueError):
        out["bg_strength"] = base["bg_strength"]
    return out


def save(cfg, user_id):
    _ensure()
    db.execute("INSERT INTO sl_login_page (id, config, updated_by) VALUES (1, %s, %s) ON DUPLICATE KEY UPDATE config=VALUES(config), updated_by=VALUES(updated_by)",
               (json.dumps(cfg, ensure_ascii=False), user_id))


def reset(user_id):
    _ensure()
    db.execute("DELETE FROM sl_login_page WHERE id=1")
    for slot in IMAGE_SLOTS:
        filestore.delete(f"login/{slot}")


# ------------------------------------------------------------------ images
def store_image(slot, file_storage, user_id):
    """Store an uploaded picture. Returns an error text or None."""
    if slot not in IMAGE_SLOTS or not file_storage or not file_storage.filename:
        return None
    return store_bytes(slot, file_storage.read(4 * 1024 * 1024 + 1), user_id)


def store_bytes(slot, raw, user_id):
    """Validate, shrink and store a picture (from an upload or the media library). Returns an error text or None."""
    from PIL import Image
    if slot not in IMAGE_SLOTS or not raw:
        return None
    if len(raw) > 4 * 1024 * 1024:
        return "The picture is larger than 4 MB."
    try:
        im = Image.open(io.BytesIO(raw)); im.verify()
        im = Image.open(io.BytesIO(raw))
        fmt = (im.format or "").upper()
        if fmt not in ("PNG", "JPEG", "WEBP", "GIF"):
            return "Use a PNG, JPG or WebP picture."
        limit = 2000 if slot == "bg" else 1200
        im.thumbnail((limit, limit))
        buf = io.BytesIO()
        if slot == "bg" or fmt == "JPEG":
            im.convert("RGB").save(buf, "JPEG", quality=88, optimize=True)
        else:
            im.convert("RGBA").save(buf, "PNG", optimize=True)
    except Exception:
        return "That file is not a valid picture."
    filestore.put(f"login/{slot}", buf.getvalue(), user_id)
    return None


def image_url(slot, version=None):
    from flask import url_for
    path = f"login/{slot}"
    v = filestore.version(path)
    if v:
        return url_for("auth.brand_image", slot=slot, v=v)
    default = IMAGE_SLOTS.get(slot)
    return url_for("static", filename=default) if default else None


def has_custom(slot):
    return bool(filestore.version(f"login/{slot}"))


# ------------------------------------------------------------------ rendering helpers
def view(cfg=None):
    """Everything the sign-in template needs, including the generated style block."""
    cfg = cfg or config()
    c = cfg["colors"]
    feats = []
    for f in cfg["features"]:
        feats.append({**f, "svg": icon_svg(f["icon"], 24), "bg": f"linear-gradient({_tint(f['color'], .92)},{_tint(f['color'], .80)})"})
    bg = image_url("bg")
    alpha = "%02x" % round(255 * cfg["bg_strength"] / 100)
    bg_css = (f"body.login-body{{background:linear-gradient(125deg,{c['bg1']}{alpha},{c['bg2']}{alpha} 55%,{c['bg3']}{alpha}),url('{bg}') center/cover fixed}}" if bg and has_custom("bg") else "")
    css = (f":root{{--bg:{c['bg2']};--text:{c['text']};--sub:{c['sub']};--brand:{c['brand']};--lp-g1:{c['grad1']};--lp-g2:{c['grad2']};--lp-g3:{c['grad3']};--lp-g4:{c['grad4']}}}"
           f"body.login-body{{background:radial-gradient(ellipse at 100% 0,{c['glow1']}88,transparent 46%),radial-gradient(ellipse at 8% 64%,{c['glow2']}88,transparent 42%),"
           f"linear-gradient(125deg,{c['bg1']},{c['bg2']} 55%,{c['bg3']})}}"
           f"{bg_css}"
           f".login-submit{{background-image:linear-gradient(110deg,{c['grad1']},{c['grad2']} 46%,{c['grad3']} 77%,{c['grad4']})}}"
           f".login-card:before{{background:linear-gradient(90deg,{c['grad1']}66,{c['grad4']}88,{c['grad2']},{c['grad1']})}}"
           f".login-intro h2 em{{background-image:linear-gradient(95deg,{c['grad2']},{c['grad3']} 65%,{c['grad4']});background-clip:text;-webkit-background-clip:text}}"
           f".login-kicker{{color:{c['brand']}}}.login-symbol{{background:linear-gradient(150deg,{c['grad2']},{c['grad3']})}}"
           f".login-kicker:before{{background-image:linear-gradient(90deg,transparent 10%,{c['grad4']}66 35%,{c['grad4']} 50%,{c['grad4']}66 65%,transparent 90%)}}"
           f".login-kicker:after{{background-image:linear-gradient(90deg,transparent 10%,{c['grad1']}66 35%,{c['grad1']} 50%,{c['grad1']}66 65%,transparent 90%)}}"
           f".ribbon{{background:linear-gradient(120deg,#ffffff15,{c['grad4']}5c 55%,{c['grad3']}9c);box-shadow:0 22px 0 {c['grad1']}55,0 47px 0 {c['grad2']}55}}"
           f".ribbon-bottom{{background:linear-gradient(120deg,{c['grad3']},{c['grad1']} 60%,#b3ddff);box-shadow:0 -24px 0 {c['grad1']}70,0 -50px 0 #ffffff80}}"
           f".scroll-progress{{background:linear-gradient(90deg,{c['grad1']},{c['grad4']})}}"
           f".login-card input:focus{{border-color:{c['brand']};box-shadow:0 0 0 3px {c['brand']}22}}"
           f".login-help .help-title{{color:{c['sub']}}}"
           ".feature-icon.fi1{animation-delay:-2s}.feature-icon.fi2{animation-delay:-4s}"
           + "".join(f".feature-icon.fi{i}{{color:{f['color']};background:{f['bg']}}}" for i, f in enumerate(feats)))
    return {"cfg": cfg, "t": cfg["texts"], "show": cfg["show"], "features": feats, "css": css,
            "symbol_svg": icon_svg(cfg["symbol"], 34, 'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"'),
            "logo": image_url("logo"), "art": image_url("art"), "welcome_lines": cfg["texts"]["welcome_sub"].split("\n")[:3]}
