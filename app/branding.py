"""School name / tagline - editable in Settings, stored in system_settings, config values are only the fallback."""
from flask import current_app, g
from . import db

KEYS = {"name": "school_name", "tagline": "school_tagline"}


def branding():
    if "branding" not in g:
        out = {"name": current_app.config["SCHOOL_NAME"], "tagline": current_app.config["SCHOOL_TAGLINE"]}
        try:
            for r in db.query("SELECT setting_key, setting_value FROM system_settings WHERE setting_key IN ('school_name','school_tagline')"):
                for k, key in KEYS.items():
                    if r["setting_key"] == key and (r["setting_value"] or "").strip():
                        out[k] = r["setting_value"].strip()
        except Exception:
            pass
        g.branding = out
    return g.branding


def save(name, tagline):
    for key, val in (("school_name", name), ("school_tagline", tagline)):
        if db.one("SELECT 1 FROM system_settings WHERE setting_key=%s", (key,)):
            db.execute("UPDATE system_settings SET setting_value=%s WHERE setting_key=%s", (val, key))
        else:
            db.execute("INSERT INTO system_settings (setting_key, setting_value) VALUES (%s,%s)", (key, val))
