"""One-off: copy parent names / addresses from the old Schoolink database snapshots into `parents` (only fills empty fields).
usage: .venv/bin/python tools/import_parents.py"""
import html, re, sys
sys.path.insert(0, ".")
from app import create_app

OLD = "schoollink-ST-thomas"
SNAPSHOTS = ["parents_300825", "parents_270825", "parents_260624", "parents_080823", "parents_310723", "parents_050723", "parents"]   # newest first


def clean(v):
    if v is None:
        return ""
    v = re.sub(r"(?i)<br\s*/?>|</p>", ", ", str(v))
    v = re.sub(r"<[^>]+>", "", v)
    v = html.unescape(v).replace("\xa0", " ")
    return re.sub(r"\s+", " ", v).strip(" ,")


app = create_app()
with app.app_context():
    from app import db
    best = {}
    for t in SNAPSHOTS:
        for r in db.query(f"SELECT TRIM(phone_1) ph, fname, mname, lname, address, secondary_name, phone_2 FROM `{OLD}`.`{t}` WHERE phone_1<>''"):
            if r["ph"] not in best and (clean(r["fname"]) or clean(r["lname"])):
                best[r["ph"]] = r
    n = 0
    for p in db.query("SELECT id, TRIM(phone_1) ph, fname, mname, lname, address, secondary_name FROM parents"):
        r = best.get(p["ph"])
        if not r:
            continue
        have_name = (p["fname"] or p["lname"])
        vals = {}
        if not have_name:
            vals.update(fname=clean(r["fname"]), mname=clean(r["mname"]) or None, lname=clean(r["lname"]))
        if not p["address"] and clean(r["address"]):
            vals["address"] = clean(r["address"])
        if not p["secondary_name"] and clean(r["secondary_name"]) not in ("", "0"):
            vals["secondary_name"] = clean(r["secondary_name"])
        if vals:
            db.execute("UPDATE parents SET " + ",".join(f"{k}=%s" for k in vals) + " WHERE id=%s", list(vals.values()) + [p["id"]], commit=False)
            n += 1
    db.commit()
    print("parents enriched:", n, "of", db.scalar("SELECT COUNT(*) FROM parents"))
    print(db.query("SELECT fname, mname, lname, phone_1, LEFT(address,50) a FROM parents WHERE fname<>'' LIMIT 3"))
