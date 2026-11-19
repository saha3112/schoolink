"""Which report layout / subject grouping / ranking rule applies to which class (and section).

Everything lives in the database (tables sl_layout_rule and sl_subject_group) and is edited from
Admin -> Report layouts / Subject groups.  The first start seeds both tables with the rules that used to be
hard-coded, and the same seed is the in-memory fallback if the database cannot be read, so behaviour never changes
until an administrator edits a rule.

A rule matches (class, section) exactly, otherwise the class-wide rule (section_id = 0).  No rule = the class has
no report-card design (same as the old behaviour for unknown classes)."""
import json
import os
import time

from .. import db

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GROUP = "getClass6ABCDto9ABSubjectGroup"

KINDS = {"junior": "Junior sheet (house points, per-exam weighted sheet)", "standard": "Standard sheet"}
SLNO = {"none": "Subject order as mapped", "class": "Order by class serial no.", "section": "Order by section serial no."}
RANK_MODES = {
    "sum": "Plain sum of all marks",
    "mid": "Classes 9-11 style (Eng/2 + Sci/3 + Soc/2 + other subjects)",
    "high": "Classes 12-13 style (adds Computer & Robotics, Science)",
    "high_alt": "Classes 12-13 style, Commercial Studies instead of Science",
    "senior": "Senior (English/2 + every other subject rounded)",
}
CARD_VIEWS = {
    "onetofive_mod": "Junior card (classes I-V)", "sixtoeight_mod": "Middle card", "ninetoten_mod": "Secondary card",
    "ninetoten2_mod": "Secondary card (alternate)", "eleven_science": "Class XI Science", "eleven_science_mod": "Class XI Science (alt)",
    "eleven_commerce": "Class XI Commerce", "eleven_humanities": "Class XI Humanities", "twelve_science": "Class XII Science",
    "twelve_science_mod": "Class XII Science (alt)", "twelve_commerce": "Class XII Commerce", "twelve_humanities": "Class XII Humanities",
}
# A group's *key* is what the sheet code relies on; a special role pins the key, the label is free text shown on the sheet.
GROUP_ROLES = {
    "normal": ("Ordinary subject group", None),
    "summary": ("Summary (Total / % / Rank)", "SUMMARY"),
    "attendance": ("Attendance", "ATTENDANCE"),
    "graded": ("Graded subjects", "GRADED"),
    "science": ("Science (averaged for the total)", "SCIENCE"),
    "social": ("Social studies (junior sheet)", "SOCIAL STUDIES"),
    "evs": ("EVS (junior sheet)", "EVS"),
    "misc_lang": ("Misc & 3rd language", "MISC & 3rd LANG"),
    "misc_graded": ("Misc & graded", "MISC & GRADED"),
}
RESERVED = {v[1]: k for k, v in GROUP_ROLES.items() if v[1]}


def group_role(key):
    return RESERVED.get(key, "normal")


def group_labels(groups):
    """{key: label} for groups whose label differs from the key (read by the sheets)."""
    return {k: (g.get("label") or k) for k, g in groups.items()}


FIELDS = ("class_id", "section_id", "kind", "card_view", "slno_mode", "strength", "wrank", "prune",
          "reorder_exact", "move_names", "move_after", "subject_group", "rank_mode")


def _r(c, s, kind, view, group=DEFAULT_GROUP, slno="none", strength=0, wrank=0, prune=0, reorder=None, move=None, after=None, rank="sum"):
    return dict(class_id=c, section_id=s, kind=kind, card_view=view, slno_mode=slno, strength=strength, wrank=wrank, prune=prune,
                reorder_exact=json.dumps(reorder) if reorder else None, move_names=json.dumps(move) if move else None,
                move_after=after, subject_group=group, rank_mode=rank)


def _seed_rules():
    out = []
    for c in (4, 5):
        out.append(_r(c, 0, "junior", "onetofive_mod", "junior4"))
    for c in (6, 7, 8):
        out.append(_r(c, 0, "junior", "onetofive_mod", "junior6"))
    for c in (9, 10, 11):
        out.append(_r(c, 0, "standard", "sixtoeight_mod", slno="class", strength=1, rank="mid"))
    out.append(_r(12, 0, "standard", "ninetoten_mod", slno="section", strength=1, wrank=1, rank="high"))
    for s in (49, 50):
        out.append(_r(12, s, "standard", "ninetoten2_mod", "getClass9CDSubjectGroup", slno="section", strength=1, wrank=1, rank="high_alt"))
    out.append(_r(13, 0, "standard", "ninetoten_mod", slno="section", strength=1, wrank=1, rank="high"))
    for s in (22, 30):
        out.append(_r(13, s, "standard", "ninetoten_mod", "getClass10ABSubjectGroup", slno="section", strength=1, wrank=1, rank="high"))
    for s in (52, 53):
        out.append(_r(13, s, "standard", "ninetoten2_mod", "getClass10CDSubjectGroup", slno="section", strength=1, wrank=1, rank="high_alt"))
    eleven = {55: ("eleven_science", "getClass11ASubjectGroup"), 56: ("eleven_science_mod", "getClass11BSubjectGroup"),
              57: ("eleven_commerce", "getClass11CSubjectGroup"), 58: ("eleven_commerce", "getClass11DSubjectGroup"),
              63: ("eleven_humanities", "getClass11ESubjectGroup")}
    for s, (v, g) in eleven.items():
        reorder = (["ENGLISH LANGUAGE", "ENGLISH LITERATURE", "HINDI / BENGALI", "MATHEMATICS", "MATHEMATICS / APPLIED MATHEMATICS",
                    "BUSINESS STUDIES", "ECONOMICS", "ACCOUNTS", "PHYSICAL EDUCATION", "ROBOTICS", "ROBOTICS / AI"] if s == 57 else None)
        out.append(_r(14, s, "standard", v, g, strength=1, prune=1, reorder=reorder, rank="senior"))
    twelve = {59: ("twelve_science", "getClass12ASubjectGroup"), 60: ("twelve_science_mod", "getClass12BSubjectGroup"),
              61: ("twelve_commerce", "getClass12CSubjectGroup"), 62: ("twelve_commerce", "getClass12DSubjectGroup"),
              64: ("twelve_humanities", "getClass12ESubjectGroup")}
    for s, (v, g) in twelve.items():
        mv, af = ((["MATHEMATICS / APPLIED MATHEMATICS"], "HISTORY") if s == 64 else (None, None))
        out.append(_r(15, s, "standard", v, g, strength=1, wrank=1, prune=1, move=mv, after=af, rank="senior"))
    return out


_ENG = ["ENGLISH LANGUAGE", "ENGLISH LITERATURE"]
_SCI = ["PHYSICS", "CHEMISTRY", "BIOLOGY"]
_SOC = ["HISTORY & CIVICS", "GEOGRAPHY"]
_COMP9 = ["COMP.APPL/TECH.DRG.APPL./PHYSICAL EDU./ECO.APPL.", "COMPUTER APPLICATIONS", "TECHNICAL DRAWING APPLICATION"]
_ROBO = ["ROBOTICS", "ROBOTICS / AI", "ROBOTICS AND AI"]


def _c(subjects, divisor=1, rnd=False):
    return {"subjects": subjects, "divisor": divisor, "round": rnd}


# Rank total = sum of components (marks of the listed subjects / divisor, optionally rounded) + what is left over ("rest").
SEED_FORMULAS = {
    "sum": {"title": RANK_MODES["sum"], "components": [], "rest": "sum"},
    "mid": {"title": RANK_MODES["mid"], "rest": "ignore", "components": [
        _c(_ENG, 2, True), _c(_SCI, 3, True), _c(_SOC, 2, True), _c(["HINDI / BENGALI"], 1, True), _c(["MATHEMATICS"], 1, True),
        _c(["COMPUTER STUDIES", "COMPUTER"], 1, True), _c(_ROBO, 1, True)]},
    "high": {"title": RANK_MODES["high"], "rest": "ignore", "components": [
        _c(_ENG, 2, True), _c(_SCI, 3, True), _c(_SOC, 2, True), _c(["HINDI / BENGALI"]), _c(["MATHEMATICS"]),
        _c(_COMP9, 2, True), _c(_ROBO, 2, True)]},
    "high_alt": {"title": RANK_MODES["high_alt"], "rest": "ignore", "components": [
        _c(_ENG, 2, True), _c(_SOC, 2, True), _c(["HINDI / BENGALI"]), _c(["MATHEMATICS"]), _c(_COMP9, 2, True), _c(_ROBO, 2, True),
        _c(["COMMERCIAL STUDIES", "COMMMERCIAL STUDIES"])]},
    "senior": {"title": RANK_MODES["senior"], "rest": "sum_rounded", "components": [_c(_ENG, 2, True)]},
}
REST_MODES = {"ignore": "Ignore other subjects", "sum": "Add other subjects' marks as they are", "sum_rounded": "Add other subjects' marks, each rounded"}


# ------------------------------------------------------------------------------------------- storage
_ready = False
_cache = {"t": 0, "rules": None, "groups": {}}
TTL = 15


def ensure():
    """Create the tables and seed them once (never overwrites anything an admin has saved)."""
    global _ready
    if _ready:
        return
    db.execute("""CREATE TABLE IF NOT EXISTS sl_layout_rule (
        id INT AUTO_INCREMENT PRIMARY KEY, class_id INT NOT NULL, section_id INT NOT NULL DEFAULT 0,
        kind VARCHAR(20) NOT NULL DEFAULT 'standard', card_view VARCHAR(60) NULL, slno_mode VARCHAR(20) NOT NULL DEFAULT 'none',
        strength TINYINT NOT NULL DEFAULT 0, wrank TINYINT NOT NULL DEFAULT 0, prune TINYINT NOT NULL DEFAULT 0,
        reorder_exact TEXT NULL, move_names TEXT NULL, move_after VARCHAR(150) NULL,
        subject_group VARCHAR(100) NULL, rank_mode VARCHAR(20) NOT NULL DEFAULT 'sum',
        UNIQUE KEY uq_rule (class_id, section_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS sl_subject_group (
        group_key VARCHAR(100) NOT NULL, weighted TINYINT NOT NULL DEFAULT 0, config LONGTEXT NOT NULL,
        PRIMARY KEY (group_key, weighted))""")
    db.execute("""CREATE TABLE IF NOT EXISTS sl_rank_formula (name VARCHAR(40) NOT NULL PRIMARY KEY, config LONGTEXT NOT NULL)""")
    if not db.scalar("SELECT COUNT(*) FROM sl_rank_formula"):
        for n, cfg in SEED_FORMULAS.items():
            db.execute("INSERT IGNORE INTO sl_rank_formula (name, config) VALUES (%s,%s)", (n, json.dumps(cfg, ensure_ascii=False)), commit=False)
        db.commit()
    if not db.scalar("SELECT COUNT(*) FROM sl_layout_rule"):
        for r in _seed_rules():
            db.execute("INSERT IGNORE INTO sl_layout_rule (" + ",".join(FIELDS) + ") VALUES (" + ",".join(["%s"] * len(FIELDS)) + ")",
                       tuple(r[f] for f in FIELDS), commit=False)
        db.commit()
    if not db.scalar("SELECT COUNT(*) FROM sl_subject_group"):
        with open(os.path.join(_HERE, "..", "subject_groups.json")) as fh:
            data = json.load(fh)
        for kind, w in (("normal", 0), ("weighted", 1)):
            for key, cfg in data[kind].items():
                db.execute("INSERT IGNORE INTO sl_subject_group (group_key, weighted, config) VALUES (%s,%s,%s)",
                           (key, w, json.dumps(cfg, ensure_ascii=False)), commit=False)
        db.commit()
    if not db.scalar("SELECT 1 FROM system_settings WHERE setting_key='layout_default_seeded'"):
        # one-time: the editable "all other classes" rule. No card design = same behaviour as before.
        d = _r(0, 0, "standard", None)
        db.execute("INSERT IGNORE INTO sl_layout_rule (" + ",".join(FIELDS) + ") VALUES (" + ",".join(["%s"] * len(FIELDS)) + ")",
                   tuple(d[f] for f in FIELDS), commit=False)
        db.execute("INSERT INTO system_settings (setting_key, setting_value) VALUES ('layout_default_seeded','1')", commit=False)
        db.commit()
    _ready = True


def invalidate():
    _cache["t"] = 0
    _cache["groups"] = {}


def _load():
    if _cache["rules"] is not None and time.time() - _cache["t"] < TTL:
        return _cache["rules"]
    try:
        ensure()
        rows = db.query("SELECT " + ",".join(FIELDS) + " FROM sl_layout_rule")
        rules = {(int(r["class_id"]), int(r["section_id"])): r for r in rows}
    except Exception:                       # database unreadable -> the built-in defaults
        rules = {(r["class_id"], r["section_id"]): r for r in _seed_rules()}
    _cache["rules"], _cache["t"] = rules, time.time()
    return rules


def all_rules():
    return sorted(_load().values(), key=lambda r: (r["class_id"], r["section_id"]))


def rule(cid, sid):
    rules = _load()
    return rules.get((int(cid), int(sid))) or rules.get((int(cid), 0)) or rules.get((0, 0))     # (0, 0) = default for any other class


# ------------------------------------------------------------------------------------------- questions the report code asks
def is_junior(cid, sid=0):
    r = rule(cid, sid)
    return bool(r and r["kind"] == "junior")


def card_supported(cid, sid):
    r = rule(cid, sid)
    return bool(r and r["card_view"])


def subject_group_key(cid, sid):
    r = rule(cid, sid)
    return (r and r["subject_group"]) or DEFAULT_GROUP


def rank_mode(cid, sid):
    r = rule(cid, sid)
    return (r and r["rank_mode"]) or "sum"


def card_plan(cid, sid):
    """Rule with the JSON columns decoded, or None when the section has no report-card design."""
    r = rule(cid, sid)
    if not r or not r["card_view"]:
        return None
    p = dict(r)
    p["reorder_exact"] = json.loads(r["reorder_exact"]) if r.get("reorder_exact") else None
    p["move_names"] = json.loads(r["move_names"]) if r.get("move_names") else None
    return p


# ------------------------------------------------------------------------------------------- subject groups
def _file_groups():
    with open(os.path.join(_HERE, "..", "subject_groups.json")) as fh:
        return json.load(fh)


def group_keys(weighted=False):
    try:
        ensure()
        return [r["group_key"] for r in db.query("SELECT group_key FROM sl_subject_group WHERE weighted=%s ORDER BY group_key", (1 if weighted else 0,))]
    except Exception:
        return sorted(_file_groups()["weighted" if weighted else "normal"])


def get_group(key, weighted=False):
    """Fresh copy (order preserved) of one subject group set, DB first and the bundled JSON as a fallback."""
    ck = (key, bool(weighted))
    hit = _cache["groups"].get(ck)
    if hit is not None and time.time() - hit[0] < TTL:
        return json.loads(hit[1])
    text = None
    try:
        ensure()
        text = db.scalar("SELECT config FROM sl_subject_group WHERE group_key=%s AND weighted=%s", (key, 1 if weighted else 0))
    except Exception:
        text = None
    if text is None:
        text = json.dumps(_file_groups()["weighted" if weighted else "normal"].get(key) or _file_groups()["normal"][DEFAULT_GROUP])
    _cache["groups"][ck] = (time.time(), text)
    return json.loads(text)


def save_group(key, weighted, cfg):
    db.execute("REPLACE INTO sl_subject_group (group_key, weighted, config) VALUES (%s,%s,%s)",
               (key, 1 if weighted else 0, json.dumps(cfg, ensure_ascii=False)))
    invalidate()


def delete_group(key, weighted):
    db.execute("DELETE FROM sl_subject_group WHERE group_key=%s AND weighted=%s", (key, 1 if weighted else 0))
    invalidate()


# ------------------------------------------------------------------------------------------- rank formulas
def formula_names():
    try:
        ensure()
        return [r["name"] for r in db.query("SELECT name FROM sl_rank_formula ORDER BY name")]
    except Exception:
        return sorted(SEED_FORMULAS)


def get_formula(name):
    try:
        ensure()
        text = db.scalar("SELECT config FROM sl_rank_formula WHERE name=%s", (name,))
    except Exception:
        text = None
    if text is None:
        return json.loads(json.dumps(SEED_FORMULAS.get(name) or SEED_FORMULAS["sum"]))
    return json.loads(text)


def save_formula(name, cfg):
    db.execute("REPLACE INTO sl_rank_formula (name, config) VALUES (%s,%s)", (name, json.dumps(cfg, ensure_ascii=False)))


def delete_formula(name):
    db.execute("DELETE FROM sl_rank_formula WHERE name=%s", (name,))


def card_view_options():
    """{view: label} - the built-in designs plus every design created in Admin > Card designs."""
    out = dict(CARD_VIEWS)
    try:
        from . import carddesign
        for d in carddesign.all_designs():
            out["custom:%d" % d["id"]] = "Custom: " + d["name"]
    except Exception:
        pass
    return out


def default_plan():
    """Neutral card settings (used when previewing a design for a section that has no rule)."""
    p = _r(0, 0, "standard", "x")
    p["reorder_exact"], p["move_names"] = None, None
    return p
