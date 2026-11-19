"""Question answering for the top bar search (rule based, no external service).

It understands free sentences such as
    "i need parents number of AFFAN HUSSAIN"       parent contact of a student (spelling mistakes are forgiven)
    "which class is aahil in" / "roll no of aahil"  basic student facts
    "who is the class teacher of 5 b"               class teacher / subject teachers of a section
    "who teaches maths in class 6 a"
    "phone of akreeti kaur" / "what does arif teach" teacher facts
    "how many students in class 3"                  counts
    "attendance of rizwan"                          attendance summary
    "my child's class teacher" (parent login)       the signed in parent's own children

What a person gets back always follows what that account is allowed to see:
    super admin / admin   everything their permissions allow
    teacher               students of their own sections, colleagues' names and teaching load (never parent or teacher phone numbers)
    parent                only their own children and the people who teach them
A value is shown only when it is stored; otherwise the answer says it is not available."""
import difflib
import re
import time

from .. import db
from . import parent_identity as PI

# ------------------------------------------------------------------ vocabulary
PARENT_WORDS = {"parent", "parents", "father", "fathers", "mother", "mothers", "guardian", "guardians", "dad", "mom", "mum", "papa", "mummy", "abbu", "ammi", "baba"}
TEACHER_HINT = {"teacher", "teachers", "sir", "madam", "mam", "maam", "miss", "mr", "mrs", "faculty", "staff", "coordinator", "teach", "teaches", "teaching", "taught"}
ME_WORDS = {"my", "mine", "me", "our", "myself"}
CHILD_WORDS = {"child", "children", "son", "daughter", "kid", "kids", "ward", "wards", "boy", "girl"}
FIELD_WORDS = {
    "phone": {"number", "numbers", "phone", "phones", "mobile", "mobiles", "mob", "contact", "contacts", "whatsapp", "whatsap", "call", "cell", "telephone", "no"},
    "email": {"email", "emails", "mail", "gmail", "e-mail"},
    "address": {"address", "addresses", "residence", "location", "lives", "live", "home", "stay", "stays"},
    "occupation": {"occupation", "job", "profession", "work", "works"},
    "religion": {"religion"},
    "second": {"second", "secondary", "other"},
}
ATTR_WORDS = {
    "admission": {"admission", "adm", "admno"},
    "code": {"code", "uid"},
    "dob": {"dob", "birthday", "birth", "born", "age", "old", "birthdate"},
    "house": {"house"},
    "attendance": {"attendance", "present", "absent", "absence", "attended"},
    "timetable": {"timetable", "routine", "schedule", "period", "periods", "timing", "timings"},
    "events": {"event", "events", "holiday", "holidays", "program", "programs"},
    "announcements": {"announcement", "announcements", "notice", "notices", "circular", "circulars"},
    "leave": {"leave", "leaves"},
    "report_card": {"reportcard", "marksheet", "marksheets"},
    "comment": {"remark", "remarks", "comment", "comments", "feedback"},
    "teaches": {"teach", "teaches", "teaching", "taught", "subject", "subjects"},
    "profile": {"details", "detail", "info", "information", "profile", "everything", "all"},
    "section": {"section", "class", "std", "standard", "studying", "study", "studies", "reads", "grade"},
}
WORD_FIELD = {w: f for f, ws in FIELD_WORDS.items() for w in ws}
WORD_ATTR = {w: a for a, ws in ATTR_WORDS.items() for w in ws}
FILLER = {"i", "need", "want", "needs", "give", "tell", "get", "find", "show", "me", "please", "plz", "pls", "can", "could", "would", "you", "what", "whats", "what's",
          "is", "are", "the", "of", "for", "to", "his", "her", "my", "about", "student", "students", "name", "and", "or", "with", "has", "have", "does", "do", "where",
          "who", "whose", "which", "a", "an", "kindly", "ph", "nos", "n", "s", "in", "on", "at", "this", "that", "it", "be", "by", "from", "how", "many", "much",
          "total", "count", "strength", "list", "any", "there", "tomorrow", "today", "now", "his", "hers", "their", "them", "he", "she", "they", "was", "will", "when",
          "marks", "mark", "result", "results", "score", "scores", "report", "card", "exam", "term", "teacher", "teachers", "sir", "madam", "mam", "maam", "miss", "mr",
          "mrs", "mak", "amak", "amake", "dao", "dau", "den", "dite", "dis", "koro", "korun", "er", "der", "ke", "ta", "gulo", "gula", "sob", "sobar", "shob", "sokol", "tader",
          "tar", "ja", "je", "ki", "kon", "koto", "ekta", "na", "hole", "bolo", "bol", "dekhao", "dekha", "dekhan", "chai", "chaye", "lagbe", "each", "every", "all", "with",
          "published", "publish", "released", "release", "available", "upcoming", "next", "coming", "latest", "new", "hello", "hi", "hey", "status", "update", "updates", "class", "section", "sec", "roll", "std", "standard", "get", "got", "obtained", "date", "birthdate", "details"} | ME_WORDS | CHILD_WORDS
SUBJECT_ALIAS = {"maths": "math", "mathematics": "math", "eng": "english", "sci": "science", "comp": "computer", "gk": "general", "bangla": "bengali",
                 "hist": "history", "geo": "geography", "phy": "physics", "chem": "chemistry", "bio": "biology"}

_cache = {"t": 0, "stu": [], "tea": []}
_STEMS = {"student", "parent", "teacher", "father", "mother", "class", "section", "guardian", "child", "children", "number", "phone", "mobile", "contact", "address", "email"}


def _stem(w):
    """'studenter' -> 'student', 'parenter' -> 'parent' (Bengali style possessive endings)."""
    for suf in ("er", "der", "r", "s'", "'s"):
        if w.endswith(suf) and w[: -len(suf)] in _STEMS:
            return w[: -len(suf)]
    return w


# ------------------------------------------------------------------ name matching
_SUBS = [("ph", "f"), ("ck", "k"), ("q", "k"), ("x", "ks"), ("z", "j"), ("w", "v"), ("y", "i"), ("ee", "i"), ("oo", "u"), ("kh", "k"), ("sh", "s"), ("th", "t"), ("dh", "d")]


def norm(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    for a, b in _SUBS:
        w = w.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", w)


def _skeleton(w):
    return w[:1] + re.sub(r"[aeiouh]", "", w[1:])


def _tok_score(q, t):
    if q == t:
        return 1.0
    if not q or not t:
        return 0.0
    if len(q) >= 3 and _skeleton(q) == _skeleton(t):
        return 0.92
    r = difflib.SequenceMatcher(None, q, t).ratio()
    if len(q) >= 3 and t.startswith(q):
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
    return total / len(qtoks) - 0.02 * max(0, len(name_toks) - len(qtoks))


def _load():
    if time.time() - _cache["t"] > 90:
        _cache["stu"] = db.query(
            "SELECT st.studentId, st.student_name, st.student_rollNumber, st.ADMNO, st.student_code, st.studentUID, st.DOB, st.parent_id, st.class_id, st.section_id, "
            "c.class_name, s.section_name FROM students st JOIN classes c ON c.classId=st.class_id JOIN sections s ON s.sectionId=st.section_id WHERE st.isDelete='0'")
        for r in _cache["stu"]:
            r["_toks"] = [norm(t) for t in re.findall(r"[a-z]+", (r["student_name"] or "").lower())]
        _cache["tea"] = db.query(
            "SELECT t.user_id, t.fname, t.mname, t.lname, t.phone_1, t.phone_2, t.address, t.coordinator_type, u.email AS login FROM teachers t "
            "LEFT JOIN new_users u ON u.id=t.user_id WHERE t.deleted_at IS NULL")
        for r in _cache["tea"]:
            r["nm"] = " ".join(x.strip() for x in (r["fname"], r["mname"], r["lname"]) if x and x.strip())
            r["_toks"] = [norm(t) for t in re.findall(r"[a-z]+", r["nm"].lower())]
        _cache["t"] = time.time()
    return _cache["stu"], _cache["tea"]


def _rank(rows, qtoks, floor=0.78):
    qtoks = [norm(q) for q in qtoks]
    out = []
    for r in rows:
        s = _score(qtoks, r["_toks"])
        if s >= floor:
            out.append((s, r))
    out.sort(key=lambda x: -x[0])
    return out


# ------------------------------------------------------------------ access
class Access:
    """What the signed in account may see. Built once per question."""

    def __init__(self, user):
        from . import user_access as UA
        from .. import auth
        self.user = user
        self.admin = bool(user.get("is_admin"))
        self.teacher = bool(user.get("is_teacher"))
        self.parent = bool(user.get("is_parent"))
        self.UA = UA
        self.kids = []
        if self.parent:
            self.kids = auth.my_children()
        self._scope = None
        self._ct = None

    def can(self, domain):
        keys = {"student": "students.student_list", "parent": "parents.all_parents", "teacher": "admin.teacher_mapping", "marks": "marks.list"}
        if self.admin:
            return True if not self.UA.restricted(self.user) else self.UA.has(self.user, keys.get(domain, domain))
        if self.teacher:
            return domain in ("student", "teacher_names", "marks")
        if self.parent:
            return domain in ("student", "teacher_names")
        return False

    def scope(self):
        """None = every student; else set of (class_id, section_id)."""
        if self.admin:
            return None
        if self._scope is None:
            from . import access
            if self.teacher:
                self._scope = {(p["classId"], p["sectionId"]) for p in list(access.class_pairs(self.user)) + list(access.subject_pairs(self.user))}
            else:
                self._scope = {(k["class_id"], k["section_id"]) for k in self.kids}
        return self._scope

    def class_teacher_pairs(self):
        if self._ct is None:
            from . import access
            self._ct = {(p["classId"], p["sectionId"]) for p in access.class_pairs(self.user)} if self.teacher else set()
        return self._ct

    def student_ok(self, st):
        if self.admin:
            return True
        if self.parent:
            return st["studentId"] in {k["studentId"] for k in self.kids}
        sc = self.scope()
        return sc is not None and (st["class_id"], st["section_id"]) in sc

    def parent_contact_ok(self, st):
        if self.admin:
            return self.can("parent")
        return self.teacher and (st["class_id"], st["section_id"]) in self.class_teacher_pairs()   # a class teacher sees their own section's parents


# ------------------------------------------------------------------ small helpers
def _clean(v):
    import html as _html
    v = _html.unescape(re.sub(r"<[^>]*>", " ", str(v))) if v is not None else ""      # some stored addresses contain <p> tags
    v = " ".join(v.split())
    return "" if v.lower() in ("", "none", "null", "n/a", "na", "-", "0", "not available", "0000-00-00") else v


def fact(label, value, tel=False):
    v = _clean(value)
    return {"k": label, "v": v or None, "tel": bool(tel and v)}


def _digits(v):
    return re.sub(r"\D", "", str(v or ""))


def _item(title, sub, facts, badge="", actions=None):
    return {"title": title, "sub": sub, "icon": "users", "badge": badge, "facts": facts, "url": None, "actions": actions or [], "marks": None}


def _ok(say, groups, chips=()):
    return {"status": "ok", "say": say, "groups": [g for g in groups if g], "chips": list(chips)}


def _none(say):
    return {"status": "none", "say": say}


def _classes():
    return db.query("SELECT classId, class_name FROM classes WHERE isDelete='0' ORDER BY classId")


def _sec_letter(ql, names):
    pats = [r"\b(?:section|sec|sect)\s*[-:]?\s*([a-z0-9]{1,2})\b", r"\b([a-z0-9]{1,2})\s+(?:section|sec)\b",
            r"\b(?:class|std|standard)\s*[-:]?\s*(?:\d{1,2}|[ivx]{1,4})\s*(?:st|nd|rd|th)?\s*(?:er|r)?\s*[-/]?\s*([a-e])\b", r"\b\d{1,2}\s*[-/]?\s*([a-e])\b"]
    for pat in pats:
        for m in re.finditer(pat, ql):
            if m.group(1).upper() in names:
                return m.group(1).upper()
    return None


def _find_sections(p):
    """Sections named by the sentence ('class 5', 'class 5 b', 'class 6 er c section')."""
    if not p.get("cls"):
        return []
    from . import search as S
    cl = S._class_matches(_classes(), p["cls"])
    if not cl:
        return []
    ids = [c["classId"] for c in cl]
    rows = db.query("SELECT s.sectionId, s.section_name, s.class_id, c.class_name FROM sections s JOIN classes c ON c.classId=s.class_id WHERE s.isDelete='0' AND s.class_id IN (%s) "
                    "ORDER BY s.class_id, s.section_name" % ",".join(["%s"] * len(ids)), ids)
    names = {(r["section_name"] or "").upper() for r in rows}
    sec = p.get("sec") if (p.get("sec") or "") in names else None
    sec = sec or _sec_letter(p.get("_ql", ""), names)
    p["sec"] = sec
    if sec:
        rows = [r for r in rows if (r["section_name"] or "").upper() == sec]
    return rows


def _class_teacher(cid, sid):
    return db.query("SELECT TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) nm, t.phone_1, t.user_id FROM classTeacher k JOIN teachers t ON t.user_id=k.teacherId "
                    "WHERE k.classId=%s AND k.sectionId=%s AND k.isDelete='0'", (cid, sid))


def _subject_teachers(cid, sid, subject_like=None):
    sql = ("SELECT sb.subject_name, TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) nm, t.user_id FROM assign_teacher a JOIN subjects sb ON sb.subjectId=a.subjectId "
           "JOIN teachers t ON t.user_id=a.t_id WHERE a.classId=%s AND a.sectionId=%s AND a.isDelete='0' AND t.deleted_at IS NULL")
    args = [cid, sid]
    rows = db.query(sql + " ORDER BY sb.subject_name", args)
    if subject_like:
        rows = [r for r in rows if all(re.search(re.escape(w), r["subject_name"].lower()) for w in subject_like)]
    return rows


def _subject_words(tokens):
    out = []
    for t in tokens:
        t2 = SUBJECT_ALIAS.get(t, t)
        if len(t2) >= 3:
            out.append(t2)
    return out


def _attendance(sid):
    r = db.one("SELECT COUNT(*) t, SUM(status='P') p, SUM(status='A') a, SUM(status='L') l FROM sl_attendance WHERE studentId=%s", (sid,))
    m = db.one("SELECT COUNT(*) t, SUM(status IN ('P','L')) p FROM sl_attendance WHERE studentId=%s AND att_date>=DATE_SUB(CURDATE(), INTERVAL 30 DAY)", (sid,))
    return r, m


def _dob_text(dob):
    v = _clean(dob)
    if not v:
        return None, None
    import datetime as dt
    d = None
    if hasattr(dob, "year"):
        d = dob
    else:
        for f in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                d = dt.datetime.strptime(v[:10], f).date(); break
            except ValueError:
                continue
    if not d:
        return v, None
    today = dt.date.today()
    age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return d.strftime("%d %b %Y"), age


# ------------------------------------------------------------------ the engine
def answer(user, q, p):
    """-> None (not a question we handle) | {"status": "ok"|"none", "say", "groups", "chips"}"""
    ql = q.lower()
    p["_ql"] = ql
    words = [_stem(w.replace("'s", "").strip("'.,?!-")) for w in re.findall(r"[a-z0-9'@.,-]+", ql)]
    words = [w for w in words if w]
    A = Access(user)
    if not (A.admin or A.teacher or A.parent):
        return None

    has_parent_word = any(w in PARENT_WORDS or w.startswith("parent") for w in words)
    fields = {WORD_FIELD[w] for w in words if w in WORD_FIELD and w != "no"}
    if "no" in words and "number" not in words and not fields and has_parent_word:
        fields.add("phone")
    attrs = {WORD_ATTR[w] for w in words if w in WORD_ATTR}
    if re.search(r"\breport\s*card\b|\bmark\s*sheet\b", ql):
        attrs.add("report_card")
    marks_q = bool(re.search(r"\b(marks?|score|scores|result|results|grades?|percentage|rank)\b", ql))
    is_me = any(w in ME_WORDS for w in words) or any(w in CHILD_WORDS for w in words)
    class_teacher_q = bool(re.search(r"\b(class|form)\s*teacher\b", ql))
    who_teaches = bool(re.search(r"\bwho\s+(teach|teaches|is teaching|takes)\b|\bteachers?\s+(of|for|in)\b|\bsubject\s*teachers?\b|\btaught by\b", ql)) and not class_teacher_q
    teachers_q = bool(re.search(r"\bteach(?:er|ers|ing)?\b|\bfaculty\b|\bstaff\b|\bsirs?\b|\bmiss(?:es)?\b|\bmadams?\b", ql)) and not class_teacher_q
    who_teaches = who_teaches or teachers_q
    count_q = bool(re.search(r"\b(how many|total|count|strength|number of)\b", ql)) and bool(re.search(r"\b(students?|pupils?|children|kids|teachers?|boys|girls|sections?|classes|parents?)\b", ql))
    roll_attr = bool(re.search(r"\broll\b", ql)) and not p.get("roll")
    p_cls = bool(p.get("cls"))

    # "number" next to roll / admission means that id, not a phone number
    if roll_attr:
        fields.discard("phone")
    if "admission" in attrs:
        fields.discard("phone")

    qtoks = []
    for t in p["tokens"]:
        t = _stem(t.replace("'s", "").strip("'.,?!-"))
        if not t or t in FILLER or t in PARENT_WORDS or t in WORD_FIELD or t in WORD_ATTR or t in TEACHER_HINT or t.isdigit():
            continue
        if len(norm(t)) >= 2:
            qtoks.append(t)
    adm_tokens = [t for t in p["tokens"] if t.isdigit() and len(t) >= 3]
    subj_tokens = []

    question = bool(has_parent_word or fields or (attrs - {"section", "profile"}) or class_teacher_q or who_teaches or count_q or roll_attr or is_me
                    or re.search(r"\b(which|who|whose|when|how|where|what)\b", ql))
    if not question:
        return None

    if (attrs & {"events", "announcements"}) and not qtoks and not A.parent:
        return _school_info(A, attrs, p)

    # ---------------- parent login: only their own children
    if A.parent:
        return _parent_answer(A, q, p, qtoks, attrs, fields, class_teacher_q, who_teaches, marks_q, roll_attr, is_me)

    sections = _find_sections(p)
    # ---------------- counts
    if count_q and not qtoks:
        return _counts(A, p, ql)

    students, teachers = _load()

    if sections and not qtoks and not adm_tokens and not (class_teacher_q or who_teaches) and (has_parent_word or fields or (attrs & {"admission", "dob", "code", "house"})):
        return _roster(A, sections, p, has_parent_word, fields, attrs)

    # ---------------- class / section questions ("class teacher of 5 b", "who teaches maths in class 6 a")
    section_intent = p_cls and (class_teacher_q or who_teaches or "teaches" in attrs)
    if section_intent or who_teaches:                      # subject words ("maths") are not part of a person's name here
        sw = {w for r in db.query("SELECT subject_name FROM subjects WHERE isDelete='0'") for w in re.findall(r"[a-z]+", r["subject_name"].lower())}
        qtoks = [t for t in qtoks if not (len(SUBJECT_ALIAS.get(t, t)) >= 3 and any(w.startswith(SUBJECT_ALIAS.get(t, t)) for w in sw))]
    if section_intent:
        named = _rank(students, qtoks) if qtoks else []
        ids = {r["class_id"] for r in sections}
        named = [c for c in named if not ids or c[1]["class_id"] in ids]
        if not named or not any(A.student_ok(c[1]) for c in named):
            return _section_answer(A, sections, p, ql, words, class_teacher_q, who_teaches)

    if not qtoks and not adm_tokens:
        if teachers_q and not p_cls and not class_teacher_q:
            return _teacher_list(A)
        if class_teacher_q and not p_cls:
            return _none("Tell me the class too, for example “who is the class teacher of class 5 b”.")
        return None

    # ---------------- who is the person?
    teacher_hint = any(w in TEACHER_HINT for w in words) and not class_teacher_q
    s_c = _rank([s for s in students], qtoks) if qtoks else []
    if adm_tokens:
        s_c = [(1.0, s) for s in students if any(a in (str(s["ADMNO"] or ""), str(s["student_code"] or ""), str(s["studentUID"] or "")) for a in adm_tokens)] or s_c
    if p.get("cls"):
        ids = {r["class_id"] for r in sections} or set()
        s_c = [c for c in s_c if not ids or c[1]["class_id"] in ids]
        if p.get("sec"):
            s_c = [c for c in s_c if (c[1]["section_name"] or "").upper() == p["sec"]]
    if p.get("roll"):
        s_c = [c for c in s_c if str(c[1]["student_rollNumber"]) == str(p["roll"])]
    t_c = _rank(_load()[1], qtoks) if (qtoks and (A.admin or A.teacher)) else []
    pick_teacher = bool(t_c) and (teacher_hint or not s_c or t_c[0][0] > s_c[0][0] + 0.02)
    if pick_teacher and not (class_teacher_q and s_c):
        return _teacher_answer(A, t_c, qtoks, attrs, fields, words)

    if not s_c:
        shown = " ".join(t.upper() for t in qtoks) or " ".join(adm_tokens)
        if (has_parent_word or fields or attrs - {"section", "profile"} or class_teacher_q or who_teaches or roll_attr):
            if A.teacher:
                return _none(f"I couldn't find a student matching “{shown}” in your classes.")
            return _none(f"I couldn't find a student or teacher matching “{shown}”. Please check the spelling, or add the class, for example “{shown.lower()} class 5”.")
        return None

    # keep only students this account may see
    visible = [(s, st) for s, st in s_c if A.student_ok(st)]
    if not visible:
        return _none("I couldn't find a student with that name in the classes you can access.")
    top = visible[0][0]
    picks = [(s, st) for s, st in visible if s >= top - 0.04][:4]
    return _student_answer(A, picks, attrs, fields, has_parent_word, class_teacher_q, who_teaches, marks_q, roll_attr, p)


# ------------------------------------------------------------------ student questions
def _student_answer(A, picks, attrs, fields, has_parent_word, class_teacher_q, who_teaches, marks_q, roll_attr, p):
    wants_parent = bool(has_parent_word or fields)
    if wants_parent:
        picks = [x for x in picks if A.parent_contact_ok(x[1])]
        if not picks:
            return _ok("Parent details can only be viewed by an administrator or by the class teacher of that student.", [], [])
    generic = not (wants_parent or class_teacher_q or who_teaches or roll_attr or (attrs - {"section", "profile"}) or marks_q)
    if marks_q and not (wants_parent or class_teacher_q or who_teaches or roll_attr or (attrs - {"section", "profile", "report_card"})):
        return None                                           # marks / report cards are handled by the regular search below
    items, says = [], []
    for score, st in picks:
        sub = f"{st['class_name']} · {st['section_name']} · Roll {st['student_rollNumber']}"
        facts = []
        full = "profile" in attrs or generic
        if full or roll_attr or "section" in attrs:
            facts += [fact("Class", f"{st['class_name']} · Section {st['section_name']}"), fact("Roll no.", st["student_rollNumber"])]
        if full or "admission" in attrs:
            facts.append(fact("Admission no.", st["ADMNO"]))
        if full or "code" in attrs:
            facts += [fact("Student code", st["student_code"]), fact("Student UID", st["studentUID"])] if "code" in attrs else [fact("Student code", st["student_code"])]
        if full or "dob" in attrs:
            d, age = _dob_text(st["DOB"])
            facts.append(fact("Date of birth", d))
            if age is not None:
                facts.append(fact("Age", f"{age} years"))
        if "house" in attrs or full:
            house = db.scalar("SELECT house FROM student_house WHERE studentId=%s ORDER BY 1 LIMIT 1", (st["studentId"],)) if _has_col("student_house", "house") else None
            if house or "house" in attrs:
                facts.append(fact("House", house))
        if class_teacher_q or full:
            ct = _class_teacher(st["class_id"], st["section_id"])
            if ct or class_teacher_q:
                facts.append(fact("Class teacher", ", ".join(r["nm"] for r in ct)))
        if who_teaches or "teaches" in attrs:
            for r in _subject_teachers(st["class_id"], st["section_id"]):
                facts.append(fact(r["subject_name"], r["nm"]))
        if "attendance" in attrs:
            tot, mon = _attendance(st["studentId"])
            if tot and tot["t"]:
                facts.append(fact("Attendance (all)", f"{int(tot['p'] or 0)} present, {int(tot['a'] or 0)} absent of {tot['t']} days"))
                if mon and mon["t"]:
                    facts.append(fact("Last 30 days", f"{round(int(mon['p'] or 0) * 100 / mon['t'])}% present"))
            else:
                facts.append(fact("Attendance", None))
        if "comment" in attrs:
            cm = db.one("SELECT * FROM studentComment WHERE studentId=%s ORDER BY 1 DESC LIMIT 1", (st["studentId"],)) if _has_col("studentComment", "studentId") else None
            txt = next((v for k, v in (cm or {}).items() if "comment" in k.lower() and isinstance(v, str) and v.strip()), None)
            facts.append(fact("Teacher's comment", txt))
        if wants_parent:
            par = db.one("SELECT p.*, u.fname AS account_name FROM parents p LEFT JOIN new_users u ON u.id=p.user_id AND u.deleted_at IS NULL "
                         "WHERE p.id=%s AND p.deleted_at IS NULL", (st["parent_id"],)) if st["parent_id"] else None
            want = fields or {"phone", "email", "address", "occupation", "religion", "second"}
            if not par:
                says.append(f"No parent record is linked to {st['student_name']}.")
            else:
                facts.append(fact("Parent", PI.name(par)))
                if "second" in want:
                    facts.append(fact("Second parent", par.get("secondary_name")))
                if "phone" in want:
                    p1, p2 = par.get("phone_1"), par.get("phone_2")
                    facts.append(fact("Phone", p1, tel=True))
                    if _digits(p2) and _digits(p2) != _digits(p1):
                        facts.append(fact("Alternate phone", p2, tel=True))
                if "email" in want:
                    em = _clean(par.get("email"))
                    facts.append(fact("Email", em if "@" in em else None))     # some records keep the mobile number here
                for key, label in (("address", "Address"), ("occupation", "Occupation"), ("religion", "Religion")):
                    if key in want:
                        facts.append(fact(label, par.get(key)))
        if not facts:
            continue
        items.append(_item(st["student_name"], sub, facts, "" if score >= 0.97 else "Closest spelling match", _student_actions(A, st, wants_parent)))
    if not items:
        return None
    if len(picks) > 1:
        say = f"{len(picks)} students match that name. Showing each one with their class."
    else:
        miss = [f["k"] for f in items[0]["facts"] if f["v"] is None]
        got = [f for f in items[0]["facts"] if f["v"] is not None]
        name = picks[0][1]["student_name"]
        say = " ".join(says) or (f"I don't have {', '.join(m.lower() for m in miss)} for {name}." if miss and not got
                                else f"Found details for {name}. I don't have: {', '.join(m.lower() for m in miss)}." if miss else f"Here is what I have for {name}.")
    return _ok(say, [{"title": "Parent details" if wants_parent else "Student details", "items": items}], ["Parent details" if wants_parent else "Student details"])


_COLS = {}


def _has_col(table, col):
    key = (table, col)
    if key not in _COLS:
        try:
            _COLS[key] = bool(db.query(f"SHOW COLUMNS FROM `{table}` LIKE %s", (col,)))
        except Exception:
            _COLS[key] = False
    return _COLS[key]


def _student_actions(A, st, wants_parent):
    from flask import url_for
    acts = []
    try:
        if A.admin and A.can("student"):
            acts.append({"label": "Profile", "url": url_for("students.edit", sid=st["studentId"])})
        if wants_parent and A.admin and st["parent_id"]:
            acts.append({"label": "Parent profile", "url": url_for("parents.detail", pid=st["parent_id"])})
    except Exception:
        pass
    return acts


# ------------------------------------------------------------------ whole section lists
def _roster(A, sections, p, has_parent_word, fields, attrs):
    from flask import url_for
    wants_parent = bool(has_parent_word or fields)
    scope = A.scope()
    sections = [s for s in sections if scope is None or (s["class_id"], s["sectionId"]) in scope]
    if not sections:
        return _none("You do not have access to that class or section.")
    if wants_parent:
        allowed = [s for s in sections if A.admin and A.can("parent") or (s["class_id"], s["sectionId"]) in A.class_teacher_pairs()]
        if not allowed:
            return _ok("Parent details can only be viewed by an administrator or by the class teacher of that section.", [], [])
        sections = allowed
    ids = [(s["class_id"], s["sectionId"]) for s in sections]
    rows = db.query("SELECT st.studentId, st.student_name, st.student_rollNumber, st.ADMNO, st.student_code, st.DOB, st.class_id, st.section_id, s.section_name, c.class_name, "
                    "p.fname, p.mname, p.lname, p.phone_1, p.phone_2, p.email, p.address, p.occupation, p.religion, p.secondary_name, u.fname AS account_name "
                    "FROM students st JOIN sections s ON s.sectionId=st.section_id JOIN classes c ON c.classId=st.class_id "
                    "LEFT JOIN parents p ON p.id=st.parent_id AND p.deleted_at IS NULL LEFT JOIN new_users u ON u.id=p.user_id AND u.deleted_at IS NULL "
                    "WHERE st.isDelete='0' AND (" + " OR ".join(["(st.class_id=%s AND st.section_id=%s)"] * len(ids)) + ") "
                    "ORDER BY st.class_id, s.section_name, st.student_rollNumber, st.student_name", [x for pair in ids for x in pair])
    if not rows:
        return _none("There are no students in that section.")
    cols, tel = ["Roll", "Student"], []
    multi = len(sections) > 1
    if multi:
        cols.insert(0, "Sec")
    if wants_parent:
        cols.append("Parent")
        want = fields or {"phone"}
        if "phone" in want:
            tel += [len(cols), len(cols) + 1]; cols += ["Phone", "Alt phone"]
        if "email" in want:
            cols.append("Email")
        if "address" in want:
            cols.append("Address")
        if "occupation" in want:
            cols.append("Occupation")
        if "religion" in want:
            cols.append("Religion")
        if "second" in want:
            cols.append("Second parent")
    if "admission" in attrs:
        cols.append("Adm no.")
    if "code" in attrs:
        cols.append("Student code")
    if "dob" in attrs:
        cols.append("Date of birth")
    out, have, total = [], 0, len(rows)
    for r in rows[:80]:
        row = ([r["section_name"]] if multi else []) + [r["student_rollNumber"], r["student_name"]]
        if wants_parent:
            row.append(PI.name(r) or "-")
            want = fields or {"phone"}
            if "phone" in want:
                p1, p2 = _clean(r["phone_1"]), _clean(r["phone_2"])
                have += 1 if p1 else 0
                row += [p1 or "-", p2 if p2 and _digits(p2) != _digits(p1) else "-"]
            if "email" in want:
                em = _clean(r["email"]); row.append(em if "@" in em else "-")
            for key, name in (("address", "address"), ("occupation", "occupation"), ("religion", "religion")):
                if key in want:
                    row.append(_clean(r[name]) or "-")
            if "second" in want:
                row.append(_clean(r["secondary_name"]) or "-")
        if "admission" in attrs:
            row.append(_clean(r["ADMNO"]) or "-")
        if "code" in attrs:
            row.append(_clean(r["student_code"]) or "-")
        if "dob" in attrs:
            row.append(_dob_text(r["DOB"])[0] or "-")
        out.append([str(x) if x is not None else "-" for x in row])
    label = f"{sections[0]['class_name']}" + (f" · Section {sections[0]['section_name']}" if len(sections) == 1 else "")
    more = None
    try:
        if A.admin or A.class_teacher_pairs():
            more = url_for("parents.all_parents", class_id=sections[0]["class_id"], section_id=sections[0]["sectionId"] if len(sections) == 1 else None)
    except Exception:
        pass
    say = f"{label}: {total} students" + (f", parent phone saved for {have} of {min(total, 80)} shown." if wants_parent and ("phone" in (fields or {"phone"})) else ".")
    if total > 80:
        say += " Showing the first 80. Open the full list for the rest."
    grp = {"title": ("Parents of " if wants_parent else "Students of ") + label, "items": [], "table": {"cols": cols, "rows": out, "tel": tel}}
    if more and wants_parent:
        grp["more"] = more
    return _ok(say, [grp], ["Parent details" if wants_parent else "Student details"])


# ------------------------------------------------------------------ class / section questions
def _section_answer(A, sections, p, ql, words, class_teacher_q, who_teaches):
    scope = A.scope()
    if scope is not None:
        sections = [s for s in sections if (s["class_id"], s["sectionId"]) in scope] if A.teacher else sections
    if not sections:
        return _none("I couldn't find that class and section, or you do not have access to it.")
    subject_words = []
    if who_teaches or not class_teacher_q:
        stop = FILLER | WORD_ATTR.keys() | PARENT_WORDS | TEACHER_HINT | {"class", "section", "teaches", "teach", "who"}
        subject_words = _subject_words([w for w in re.findall(r"[a-z]+", ql) if w not in stop and not re.fullmatch(r"[ivx]{1,4}|[a-e]", w)])
    groups = []
    for s in sections[:4]:
        facts = []
        label = f"{s['class_name']} · Section {s['section_name']}"
        ct = _class_teacher(s["class_id"], s["sectionId"])
        if class_teacher_q or not subject_words:
            facts.append(fact("Class teacher", ", ".join(r["nm"] for r in ct)))
            if A.can("teacher") and ct and len(sections) == 1 and class_teacher_q and A.admin:
                facts.append(fact("Phone", ct[0]["phone_1"], tel=True))
        if who_teaches or subject_words or not class_teacher_q:
            for r in _subject_teachers(s["class_id"], s["sectionId"], subject_words or None):
                facts.append(fact(r["subject_name"], r["nm"]))
            if subject_words and not any(f["v"] for f in facts):
                facts.append(fact(" ".join(subject_words).title(), None))
        n = db.scalar("SELECT COUNT(*) FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (s["class_id"], s["sectionId"])) or 0
        if not subject_words:
            facts.append(fact("Students", n))
        groups.append(_item(label, f"{n} students", facts))
    say = f"Here is the information for {sections[0]['class_name']}" + (f" section {sections[0]['section_name']}." if len(sections) == 1 else ".")
    return _ok(say, [{"title": "Class & section", "items": groups}], ["Class & section"])


# ------------------------------------------------------------------ teachers
def _teacher_answer(A, cands, qtoks, attrs, fields, words):
    top = cands[0][0]
    picks = [(s, t) for s, t in cands if s >= top - 0.04][:4]
    contact_ok = A.admin and A.can("teacher")
    items, says = [], []
    asks_contact = bool(fields & {"phone", "email", "address"})
    if asks_contact and not contact_ok:
        return _ok("Teacher contact details can only be viewed by an administrator.", [], [])
    for score, t in picks:
        facts = []
        full = not (asks_contact or "teaches" in attrs)
        teaching = db.query("SELECT sb.subject_name, c.class_name, s.section_name, a.classId, a.sectionId FROM assign_teacher a JOIN subjects sb ON sb.subjectId=a.subjectId "
                            "JOIN classes c ON c.classId=a.classId JOIN sections s ON s.sectionId=a.sectionId WHERE a.t_id=%s AND a.isDelete='0' "
                            "ORDER BY a.classId, s.section_name, sb.subject_name", (t["user_id"],))
        cts = db.query("SELECT c.class_name, s.section_name FROM classTeacher k JOIN classes c ON c.classId=k.classId JOIN sections s ON s.sectionId=k.sectionId "
                       "WHERE k.teacherId=%s AND k.isDelete='0' ORDER BY k.classId, s.section_name", (t["user_id"],))
        if asks_contact or full:
            if contact_ok:
                if "phone" in fields or full:
                    facts.append(fact("Phone", t["phone_1"], tel=True))
                    if _digits(t["phone_2"]) and _digits(t["phone_2"]) != _digits(t["phone_1"]):
                        facts.append(fact("Alternate phone", t["phone_2"], tel=True))
                if "email" in fields or full:
                    em = _clean(t["login"])
                    facts.append(fact("Email", em if "@" in em else None))
                if "address" in fields or full:
                    facts.append(fact("Address", t["address"]))
        if cts and (full or "teaches" in attrs):
            facts.append(fact("Class teacher of", ", ".join(f"{r['class_name']} {r['section_name']}" for r in cts)))
        if full or "teaches" in attrs:
            by = {}
            for r in teaching:
                by.setdefault(f"{r['class_name']} {r['section_name']}", []).append(r["subject_name"])
            for k, v in list(by.items())[:12]:
                facts.append(fact(k, ", ".join(v)))
            if not by:
                facts.append(fact("Teaching", None))
        items.append(_item(t["nm"], "Teacher", facts, "" if score >= 0.97 else "Closest spelling match"))
    say = f"{len(picks)} teachers match that name." if len(picks) > 1 else f"Here is what I have for {picks[0][1]['nm']}."
    return _ok(say, [{"title": "Teacher details", "items": items}], ["Teacher details"])


def _teacher_list(A):
    """Names of teachers: everyone for an administrator, colleagues of the same sections for a teacher."""
    scope = A.scope()
    if scope is None:
        rows = db.query("SELECT t.user_id, TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) nm, t.phone_1 FROM teachers t WHERE t.deleted_at IS NULL ORDER BY t.fname, t.lname")
    else:
        if not scope:
            return _none("No classes are assigned to you yet.")
        ph = " OR ".join(["(a.classId=%s AND a.sectionId=%s)"] * len(scope))
        args = [x for pair in sorted(scope) for x in pair]
        rows = db.query("SELECT DISTINCT t.user_id, TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) nm, t.phone_1 FROM assign_teacher a JOIN teachers t ON t.user_id=a.t_id "
                        "WHERE a.isDelete='0' AND t.deleted_at IS NULL AND (" + ph + ") ORDER BY nm", args)
    if not rows:
        return _none("I could not find any teachers.")
    cts = {}
    for r in db.query("SELECT k.teacherId, c.class_name, s.section_name FROM classTeacher k JOIN classes c ON c.classId=k.classId JOIN sections s ON s.sectionId=k.sectionId WHERE k.isDelete='0'"):
        cts.setdefault(r["teacherId"], []).append(f"{r['class_name']} {r['section_name']}")
    show_phone = A.admin and A.can("teacher")
    cols = ["Teacher", "Class teacher of"] + (["Phone"] if show_phone else [])
    out = [[r["nm"], ", ".join(cts.get(r["user_id"], [])) or "-"] + ([_clean(r["phone_1"]) or "-"] if show_phone else []) for r in rows[:80]]
    say = f"{len(rows)} teachers" + (". Showing the first 80." if len(rows) > 80 else ".") + " Add a class to see who teaches what, for example “teachers of class 5 a”."
    return _ok(say, [{"title": "Teachers", "items": [], "table": {"cols": cols, "rows": out, "tel": [2] if show_phone else []}}], ["Teachers"])


# ------------------------------------------------------------------ counts
def _counts(A, p, ql):
    if re.search(r"\bteachers?\b", ql) and not p.get("cls"):
        if A.parent:
            return _none("I can only share information about your own children.")
        n = db.scalar("SELECT COUNT(*) FROM teachers WHERE deleted_at IS NULL") or 0
        return _ok(f"There are {n} teachers.", [], ["Count"])
    sections = _find_sections(p)
    scope = A.scope()
    where, args = ["st.isDelete='0'"], []
    label = "in the school"
    if sections:
        ids = [(s["class_id"], s["sectionId"]) for s in sections]
        if scope is not None:
            ids = [i for i in ids if i in scope]
            if not ids:
                return _none("You do not have access to that class.")
        where.append("(" + " OR ".join(["(st.class_id=%s AND st.section_id=%s)"] * len(ids)) + ")")
        for c, s in ids:
            args += [c, s]
        label = f"in {sections[0]['class_name']}" + (f" section {sections[0]['section_name']}" if p.get("sec") else "")
    elif scope is not None:
        if not scope:
            return _none("No classes are assigned to you yet.")
        where.append("(" + " OR ".join(["(st.class_id=%s AND st.section_id=%s)"] * len(scope)) + ")")
        for c, s in sorted(scope):
            args += [c, s]
        label = "in your classes"
    n = db.scalar("SELECT COUNT(*) FROM students st WHERE " + " AND ".join(where), args) or 0
    items = []
    if sections and not p.get("sec") and len(sections) > 1:
        for s in sections[:12]:
            if scope is not None and (s["class_id"], s["sectionId"]) not in scope:
                continue
            c = db.scalar("SELECT COUNT(*) FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (s["class_id"], s["sectionId"])) or 0
            items.append(_item(f"Section {s['section_name']}", "", [fact("Students", c)]))
    return _ok(f"There are {n} students {label}.", [{"title": "Strength", "items": items}] if items else [], ["Count"])


# ------------------------------------------------------------------ events and announcements
def _school_info(A, attrs, p, kids=None):
    from flask import url_for
    groups = []
    audience = {(k["class_id"], k["section_id"]) for k in (kids or [])}

    def ok(cid, sid):
        if not kids:
            return True
        return cid is None or any(c == cid and (sid is None or s == sid) for c, s in audience)
    if "events" in attrs:
        rows = db.query("SELECT title, start_date, end_date FROM sl_event WHERE deleted=0 AND COALESCE(end_date, start_date)>=CURDATE() ORDER BY start_date LIMIT 6")
        facts = [fact(r["title"], r["start_date"].strftime("%d %b %Y") if hasattr(r["start_date"], "strftime") else r["start_date"]) for r in rows]
        groups.append(_item("Upcoming events", "", facts or [fact("Events", None)]))
    if "announcements" in attrs:
        rows = [r for r in db.query("SELECT title, created_at, classId, sectionId FROM sl_announcement WHERE deleted=0 ORDER BY id DESC LIMIT 20") if ok(r["classId"], r["sectionId"])][:5]
        facts = [fact(r["title"], r["created_at"].strftime("%d %b %Y") if hasattr(r["created_at"], "strftime") else r["created_at"]) for r in rows]
        groups.append(_item("Latest announcements", "", facts or [fact("Announcements", None)]))
    say = "Here is the latest from the school." if any(f["v"] for g in groups for f in g["facts"]) else "There is nothing to show right now."
    return _ok(say, [{"title": "School updates", "items": groups}], ["School updates"])


# ------------------------------------------------------------------ parent login
def _parent_answer(A, q, p, qtoks, attrs, fields, class_teacher_q, who_teaches, marks_q, roll_attr, is_me):
    ql = q.lower()
    from flask import url_for
    kids = A.kids
    if not kids:
        return _none("I could not find a child linked to your account. Please contact the school office.")
    sw_all = {w for r in db.query("SELECT subject_name FROM subjects WHERE isDelete='0'") for w in re.findall(r"[a-z]+", r["subject_name"].lower())}
    subj_tokens = [x for x in qtoks if len(SUBJECT_ALIAS.get(x, x)) >= 3 and any(w.startswith(SUBJECT_ALIAS.get(x, x)) for w in sw_all)]
    qtoks = [x for x in qtoks if x not in subj_tokens]               # "english" in "who teaches english" is a subject, not a name
    picks = kids
    if qtoks:
        ranked = _rank([dict(k, _toks=[norm(t) for t in re.findall(r"[a-z]+", (k["student_name"] or "").lower())]) for k in kids], qtoks, 0.72)
        if not ranked:
            students, teachers = _load()
            if _rank(students, qtoks) or _rank(teachers, qtoks):      # names someone else's child or a teacher
                return _none("I can only share information about your own children.")
            picks = kids                                                # other words are just chatter ("published", "upcoming" ...)
            qtoks = []
        else:
            picks = [r for _, r in ranked][:1]
    if fields & {"email", "address", "occupation", "religion"} or (fields & {"phone"} and not (attrs & {"teaches"} or class_teacher_q or who_teaches)) or any(w in PARENT_WORDS for w in re.findall(r"[a-z]+", q.lower())):
        return _ok("For privacy, parent contact details are not shown in search. You can update them by contacting the school office.", [], [])
    if (attrs & {"events", "announcements"}) and not (class_teacher_q or who_teaches or roll_attr or marks_q or (attrs & {"attendance", "report_card", "timetable", "leave"})):
        return _school_info(A, attrs, p, kids)
    items = []
    for k in picks[:3]:
        st = db.one("SELECT st.*, c.class_name, s.section_name FROM students st JOIN classes c ON c.classId=st.class_id JOIN sections s ON s.sectionId=st.section_id WHERE st.studentId=%s", (k["studentId"],))
        if not st:
            continue
        facts, acts = [], []
        full = not (attrs - {"section", "profile"}) and not (class_teacher_q or who_teaches or roll_attr or marks_q or re.search(r"\b(classmates?|how many|strength|total)\b", ql))
        if full or roll_attr or "section" in attrs:
            facts += [fact("Class", f"{st['class_name']} · Section {st['section_name']}"), fact("Roll no.", st["student_rollNumber"])]
        if full or "admission" in attrs:
            facts.append(fact("Admission no.", st["ADMNO"]))
        if "dob" in attrs or full:
            d, age = _dob_text(st["DOB"])
            facts.append(fact("Date of birth", d))
        if class_teacher_q or full:
            facts.append(fact("Class teacher", ", ".join(r["nm"] for r in _class_teacher(st["class_id"], st["section_id"]))))
        if who_teaches or "teaches" in attrs:
            sw = _subject_words(subj_tokens)
            if not sw:
                facts.append(fact("Class teacher", ", ".join(r["nm"] for r in _class_teacher(st["class_id"], st["section_id"]))))
            for r in _subject_teachers(st["class_id"], st["section_id"], sw or None):
                facts.append(fact(r["subject_name"], r["nm"]))
        if re.search(r"\b(classmates?|how many students|strength|total students)\b", ql):
            n = db.scalar("SELECT COUNT(*) FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (st["class_id"], st["section_id"])) or 0
            facts.append(fact("Students in class", n))
        if "attendance" in attrs:
            tot, mon = _attendance(st["studentId"])
            if tot and tot["t"]:
                facts.append(fact("Attendance (all)", f"{int(tot['p'] or 0)} present, {int(tot['a'] or 0)} absent of {tot['t']} days"))
                if mon and mon["t"]:
                    facts.append(fact("Last 30 days", f"{round(int(mon['p'] or 0) * 100 / mon['t'])}% present"))
            else:
                facts.append(fact("Attendance", None))
            acts.append({"label": "Open attendance", "url": url_for("parentpanel.attendance", child=st["studentId"])})
        if marks_q or "report_card" in attrs:
            rel = bool(db.one("SELECT 1 AS x FROM releaseResult WHERE studentId=%s AND isOpen='1' AND documentName LIKE 'report_card%%'", (st["studentId"],)))
            facts.append(fact("Report card", "Published. Open it with the button below." if rel else "Not published yet"))
            if rel:
                acts.append({"label": "Open report card", "url": url_for("parentpanel.card", child=st["studentId"])})
        if "timetable" in attrs:
            acts.append({"label": "Open timetable", "url": url_for("parentpanel.timetable", child=st["studentId"])})
        if "events" in attrs or "announcements" in attrs:
            tgt = "parentpanel.announcements" if "announcements" in attrs else "parentpanel.events"
            try:
                acts.append({"label": "Open announcements" if "announcements" in attrs else "Open events", "url": url_for(tgt)})
            except Exception:
                pass
        if "leave" in attrs:
            try:
                acts.append({"label": "Open leave requests", "url": url_for("parentpanel.leave")})
            except Exception:
                pass
        if facts or acts:
            items.append(_item(st["student_name"], f"{st['class_name']} · {st['section_name']}", facts, "", acts))
    if not items:
        return None
    return _ok("Here is what I found for your child." if len(items) == 1 else "Here is what I found for your children.", [{"title": "My child", "items": items}], ["My child"])


