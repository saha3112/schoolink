"""School profile printed on report cards / sheets (name, campus, address, phone, e-mail, website, board, session).

The bundled card designs contain these as plain text.  Values are kept in system_settings (key profile_<field>);
when printing, the original text of a design is replaced by the current value.  A field left at its original value
changes nothing, so existing output stays identical until an administrator edits the profile."""
import html as _html
import re

from .. import db

# field -> (label, original text inside the bundled designs)
FIELDS = {
    "campus": ("Campus / branch name", "Kidderpore"),
    "address": ("Address", "4, Diamond Harbour Rd, Khidirpur, Kolkata, West Bengal 700023"),
    "phone": ("Phone number(s)", "2479-3241/42"),
    "email": ("E-mail", "principal@stsboys.in"),
    "website": ("Website", "www.stthomasboysschoolkolkata.com"),
    "board": ("Board / council name", "CISCE"),
    "session": ("Academic session", "2026 to 2027"),
}
ORIGINAL_NAME = "St. Thomas' Boys' School"


def get():
    """{field: current value} (original text when nothing was saved) + 'name' from the school details."""
    out = {k: d for k, (_l, d) in FIELDS.items()}
    try:
        keys = ["profile_" + k for k in FIELDS]
        for r in db.query("SELECT setting_key, setting_value FROM system_settings WHERE setting_key IN (" + ",".join(["%s"] * len(keys)) + ")", keys):
            k = r["setting_key"][8:]
            if k in out and (r["setting_value"] or "").strip():
                out[k] = r["setting_value"].strip()
    except Exception:
        pass
    from ..branding import branding
    out["name"] = branding()["name"]
    return out


def save(values):
    for k, v in values.items():
        key = "profile_" + k
        if db.one("SELECT 1 FROM system_settings WHERE setting_key=%s", (key,)):
            db.execute("UPDATE system_settings SET setting_value=%s WHERE setting_key=%s", (v, key), commit=False)
        else:
            db.execute("INSERT INTO system_settings (setting_key, setting_value) VALUES (%s,%s)", (key, v), commit=False)
    db.commit()


def apply(doc):
    """Swap the original school text in a rendered design for the current profile."""
    cur = get()
    esc = lambda v: _html.escape(v, quote=False)
    if cur["name"] != ORIGINAL_NAME:
        doc = doc.replace(ORIGINAL_NAME, esc(cur["name"]))
    for k, (_l, orig) in FIELDS.items():
        v = cur[k]
        if v == orig:
            continue
        if k == "session":
            doc = re.sub(r"20\d\d to 20\d\d", lambda m: esc(v), doc)
        else:
            doc = doc.replace(orig, esc(v))
    return doc
