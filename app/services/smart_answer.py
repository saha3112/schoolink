"""Question-style answers for the top bar search.

    "i need parents number of AFFAN HUSSAIN"      -> parent phone numbers of that student
    "afan husain father email"                    -> parent e-mail (spelling mistakes are forgiven)
    "address of aahil"                            -> parent address
    "admission number of rizwan ali"              -> the student's admission number
    "parent of aamir"                             -> everything we hold about the parent

Pure rules, no external service. A value is only shown when it is stored; otherwise the answer says it is not available.
Parent contact details are restricted to administrators."""
import difflib
import re
import time

from .. import db
from . import parent_identity as PI

PARENT_WORDS = {"parent", "parents", "father", "fathers", "mother", "mothers", "guardian", "guardians", "dad", "mom", "mum", "papa", "mummy", "abbu", "ammi"}
FIELD_WORDS = {
    "phone": {"number", "numbers", "phone", "phones", "mobile", "mobiles", "mob", "contact", "contacts", "whatsapp", "whatsap", "call", "cell", "telephone"},
    "email": {"email", "emails", "mail", "gmail", "e-mail"},
    "address": {"address", "addresses", "residence", "location", "lives", "live", "home"},
    "occupation": {"occupation", "job", "profession", "work", "works"},
    "religion": {"religion"},
    "admission": {"admission", "adm", "admno"},
    "code": {"code", "uid"},
    "second": {"second", "secondary"},
}
WORD_TO_FIELD = {w: f for f, ws in FIELD_WORDS.items() for w in ws}
FILLER = {"i", "need", "want", "needs", "give", "tell", "get", "find", "show", "me", "please", "plz", "pls", "can", "could", "would", "you", "what", "whats",
          "what's", "is", "are", "the", "of", "for", "to", "his", "her", "my", "about", "info", "information", "detail", "details", "student", "students", "name",
          "ph", "no", "nos", "n", "s", "and", "or", "with", "has", "have", "does", "do", "where", "who", "whose", "which", "a", "an", "kindly", "sir", "madam",
          "class", "section", "sec", "roll", "std", "standard", "marks", "mark", "result", "report", "card"}
STUDENT_FIELDS = {"admission", "code"}

_cache = {"t": 0, "rows": []}


def _students():
    if time.time() - _cache["t"] > 90:
        _cache["rows"] = db.query(
            "SELECT st.studentId, st.student_name, st.student_rollNumber, st.ADMNO, st.student_code, st.parent_id, st.class_id, st.section_id, "
            "c.class_name, s.section_name FROM students st JOIN classes c ON c.classId=st.class_id JOIN sections s ON s.sectionId=st.section_id "
            "WHERE st.isDelete='0'")
        for r in _cache["rows"]:
            r["_toks"] = [norm(t) for t in re.findall(r"[a-z]+", (r["student_name"] or "").lower())]
        _cache["t"] = time.time()
    return _cache["rows"]


_SUBS = [("ph", "f"), ("ck", "k"), ("q", "k"), ("x", "ks"), ("z", "j"), ("w", "v"), ("y", "i"), ("ee", "i"), ("oo", "u"), ("kh", "k"), ("sh", "s"), ("th", "t"), ("dh", "d")]


def norm(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    for a, b in _SUBS:
        w = w.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", w)


def _skeleton(w):
    return w[:1] + re.sub(r"[aeiouh]", "", w[1:])


def _tok_score(q, t):
    """How well a typed word matches one word of a name (1.0 = same sound-alike spelling)."""
    if q == t:
        return 1.0
    if not q or not t:
        return 0.0
    if _skeleton(q) == _skeleton(t) and len(q) >= 3:
        return 0.92
    r = difflib.SequenceMatcher(None, q, t).ratio()
    if len(q) >= 3 and t.startswith(q):                   # first-name prefix ("aam" -> "aamir")
        r = max(r, 0.8)
    return r


def _score(qtoks, name_toks):
    if not name_toks:
        return 0.0
    total = 0.0
    for q in qtoks:
        best = max(_tok_score(q, t) for t in name_toks)
        if best < 0.72:
            return 0.0
        total += best
    s = total / len(qtoks)
    return s - 0.02 * max(0, len(name_toks) - len(qtoks))


def _candidates(qtoks, adm_tokens, cls_ids, sec_names):
    out = []
    for r in _students():
        if cls_ids and r["class_id"] not in cls_ids:
            continue
        if sec_names and (r["section_name"] or "").upper() not in sec_names:
            continue
        if adm_tokens and any(a in (str(r["ADMNO"] or ""), str(r["student_code"] or "")) for a in adm_tokens):
            out.append((1.0, r)); continue
        if qtoks:
            s = _score(qtoks, r["_toks"])
            if s >= 0.78:
                out.append((s, r))
    out.sort(key=lambda x: (-x[0], x[1]["class_id"], x[1]["section_id"], x[1]["student_name"]))
    return out


def _fact(label, value, tel=False):
    value = (str(value).strip() if value is not None else "")
    if value.lower() in ("", "none", "null", "n/a", "na", "-", "0", "not available"):
        return {"k": label, "v": None}
    return {"k": label, "v": value, "tel": tel}


def _digits(v):
    return re.sub(r"\D", "", str(v or ""))


def answer(user, q, p):
    """-> None (not a question we handle) | {"status": "none"|"ok", "say": str, "group": {...}, "chips": [...]}"""
    words = [w for w in re.findall(r"[a-z0-9'@.-]+", q.lower())]
    words = [w.replace("'s", "").strip("'.-") for w in words]
    parent_q = any(w in PARENT_WORDS for w in words)
    fields = {WORD_TO_FIELD[w] for w in words if w in WORD_TO_FIELD}
    if not parent_q and not fields:
        return None
    toks = [w for w in (t.replace("'s", "").strip("'.-") for t in p["tokens"]) if w and w not in FILLER and w not in PARENT_WORDS and w not in WORD_TO_FIELD]
    adm_tokens = [t for t in toks if t.isdigit() and len(t) >= 3]
    qtoks = [norm(t) for t in toks if not t.isdigit() and re.search(r"[a-z]", t) and len(norm(t)) >= 2]
    if not qtoks and not adm_tokens:
        return None
    cls_ids = []
    if p.get("cls"):
        from . import search as S
        cls_ids = [c["classId"] for c in S._class_matches(S._classes(), p["cls"])]
    sec_names = {p["sec"]} if p.get("sec") else set()
    cands = _candidates(qtoks, adm_tokens, cls_ids, sec_names)
    shown = " ".join(t.upper() for t in toks if not t.isdigit()) or " ".join(adm_tokens)
    if not cands:
        return {"status": "none", "say": f"I couldn't find a student matching “{shown}”. Please check the spelling or add the class, for example “parent number of {shown.lower()} class 5”."}

    top = cands[0][0]
    picks = [c for c in cands if c[0] >= top - 0.04][:4]
    student_only = bool(fields) and not parent_q and fields <= STUDENT_FIELDS
    if not user["is_admin"] and not student_only:
        return {"status": "ok", "say": "Parent contact details can only be viewed by an administrator.", "group": None, "chips": []}
    items, says = [], []
    for score, st in picks:
        cls_txt = f"{st['class_name']} · {st['section_name']} · Roll {st['student_rollNumber']}"
        par = db.one("SELECT p.*, u.fname AS account_name FROM parents p LEFT JOIN new_users u ON u.id=p.user_id AND u.deleted_at IS NULL "
                     "WHERE p.id=%s AND p.deleted_at IS NULL", (st["parent_id"],)) if st["parent_id"] else None
        wanted = fields or {"phone", "email", "address", "occupation", "religion", "second"}
        facts = []
        if not student_only:
            pname = PI.name(par) if par else ""
            facts.append(_fact("Parent", pname))
            if "second" in wanted and par:
                facts.append(_fact("Second parent", par.get("secondary_name")))
            if "phone" in wanted:
                p1, p2 = (par or {}).get("phone_1"), (par or {}).get("phone_2")
                facts.append(_fact("Phone", p1, tel=True))
                if _digits(p2) and _digits(p2) != _digits(p1):
                    facts.append(_fact("Alternate phone", p2, tel=True))
            if "email" in wanted:
                em = str((par or {}).get("email") or "").strip()
                facts.append(_fact("Email", em if "@" in em else None))   # some records keep the mobile number here
            if "address" in wanted:
                facts.append(_fact("Address", (par or {}).get("address")))
            if "occupation" in wanted:
                facts.append(_fact("Occupation", (par or {}).get("occupation")))
            if "religion" in wanted:
                facts.append(_fact("Religion", (par or {}).get("religion")))
        if "admission" in fields:
            facts.append(_fact("Admission no.", st["ADMNO"]))
        if "code" in fields:
            facts.append(_fact("Student code", st["student_code"]))
        if not student_only and not par:
            says.append(f"No parent record is linked to {st['student_name']}.")
        else:
            missing = [f["k"] for f in facts if f["v"] is None and f["k"] != "Parent"]
            have = [f for f in facts if f["v"] is not None and f["k"] != "Parent"]
            if len(picks) == 1:
                if have and not missing:
                    says.append(f"Here is what I have for {st['student_name']}.")
                elif have:
                    says.append(f"Found some details for {st['student_name']}. I don't have: {', '.join(m.lower() for m in missing)}.")
                else:
                    says.append(f"I don't have {', '.join(m.lower() for m in missing) or 'that information'} for {st['student_name']}.")
        note = "" if score >= 0.97 else "Closest spelling match"
        items.append({"title": st["student_name"], "sub": cls_txt, "icon": "users", "badge": note, "facts": facts, "url": None, "actions": [], "marks": None})
    if len(picks) > 1:
        says = [f"{len(picks)} students match that name. Showing each one with their class."]
    title = "Student details" if student_only else "Parent details"
    return {"status": "ok", "say": " ".join(says[:2]), "group": {"title": title, "items": items}, "chips": [title]}
