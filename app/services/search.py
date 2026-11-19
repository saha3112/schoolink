"""Live search for the top bar (admin, super admin and teacher panels).

Understands plain sentences such as
    "class 1 section a"            -> the section, with links to its students / marks / report cards
    "aahil"                        -> students called Aahil (marks shown inline)
    "class 1 a aahil maths marks"  -> Aahil of 1-A and exactly his Mathematics marks
    "roll 5 class 2 b"             -> the student with roll 5 in 2-B
Everything is limited to what the logged in user may see (a teacher only gets their own sections / subjects)."""
import re

from flask import url_for

from .. import db
from . import access, features, parent_identity as PI

STOP = {"please", "plz", "find", "show", "me", "search", "get", "of", "in", "for", "the", "a", "an", "and", "to", "his", "her", "my",
        "student", "students", "marks", "mark", "result", "results", "score", "scores", "class", "section", "sec", "std", "standard",
        "roll", "no", "number", "report", "card", "data", "details", "detail", "with", "from", "is", "are", "what", "whats", "name",
        "obtained", "got", "list", "all", "who", "has", "have", "term", "exam", "teacher", "teachers", "parent", "parents"}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
ALIAS = {"maths": "math", "mathematics": "math", "eng": "english", "sci": "science", "comp": "computer", "cs": "computer",
         "gk": "general", "bangla": "bengali", "hist": "history", "geo": "geography", "phy": "physics", "chem": "chemistry", "bio": "biology"}
MARK_WORDS = {"marks", "mark", "result", "results", "score", "scores", "grade", "grades", "obtained", "got"}


def _num(text):
    text = (text or "").strip().lower()
    if text.isdigit():
        return int(text)
    return ROMAN.get(text)


def parse(q):
    """-> dict(cls=int|None, sec=str|None, roll=int|None, tokens=[...], marks=bool, card=bool)"""
    ql = " " + q.lower().strip() + " "
    out = {"cls": None, "sec": None, "roll": None, "marks": False, "card": False}

    def cut(m):
        nonlocal ql
        ql = ql[:m.start()] + " " + ql[m.end():]

    m = re.search(r"\broll\s*(?:no\.?|number|#)?\s*[-:]?\s*(\d{1,4})\b", ql)
    if m:
        out["roll"] = int(m.group(1)); cut(m)
    m = re.search(r"\b(?:class|std|standard|cl)\s*[-:]?\s*(\d{1,2}|[ivx]{1,4}(?![a-z]))(?:st|nd|rd|th)?(?:\s*[-/]?\s*([a-e])(?![a-z0-9]))?", ql) \
        or re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:class|std)\b", ql)
    if m and _num(m.group(1)):
        out["cls"] = _num(m.group(1))
        if m.lastindex and m.lastindex >= 2 and m.group(2):
            out["sec"] = m.group(2).upper()
        cut(m)
    m = re.search(r"\b(?:section|sec|sect)\s*[-:]?\s*([a-z0-9]{1,2})\b", ql)
    if m:
        out["sec"] = m.group(1).upper(); cut(m)
    if out["cls"] is None:                                   # "1a", "10-b"
        m = re.search(r"\b(\d{1,2})\s*[-/]?\s*([a-e])\b(?!\w)", ql)
        if m:
            out["cls"], out["sec"] = int(m.group(1)), (out["sec"] or m.group(2).upper()); cut(m)
    words = re.findall(r"[a-z0-9'.]+", ql)
    out["marks"] = any(w in MARK_WORDS for w in words)
    out["card"] = "report" in words or "card" in words
    out["tokens"] = [w for w in words if w not in STOP and len(w) >= 1]
    return out


def _scope(user):
    """None = everything (admin); else set of (classId, sectionId) the teacher works with."""
    if user["is_admin"]:
        return None
    return {(p["classId"], p["sectionId"]) for p in list(access.class_pairs(user)) + list(access.subject_pairs(user))}


def _classes():
    return db.query("SELECT classId, class_name FROM classes WHERE isDelete='0' ORDER BY classId")


def _class_matches(classes, n):
    out = []
    for c in classes:
        digits = re.search(r"\b(\d{1,2})\b", c["class_name"] or "")
        rom = re.search(r"\b([ivx]{1,4})\b", (c["class_name"] or "").lower())
        if (digits and int(digits.group(1)) == n) or (rom and ROMAN.get(rom.group(1)) == n):
            out.append(c)
    return out


def _subject_hits(tokens, subjects):
    """{subjectId: name} of subjects whose name contains the typed word (maths, eng, hindi…)."""
    hit = {}
    for t in tokens:
        if len(t) < 3:
            continue
        t2 = ALIAS.get(t, t)
        for s in subjects:
            words = re.findall(r"[a-z0-9]+", s["subject_name"].lower())
            if any(w == t2 or (len(t2) >= 3 and w.startswith(t2)) for w in words):
                hit[s["subjectId"]] = s["subject_name"]
    return hit


def _student_rows(user, scope, ctx, name_tokens, limit):
    where, args = ["st.isDelete='0'"], []
    if ctx["cls_ids"]:
        where.append("st.class_id IN (%s)" % ",".join(["%s"] * len(ctx["cls_ids"]))); args += ctx["cls_ids"]
    if ctx["sec_ids"]:
        where.append("st.section_id IN (%s)" % ",".join(["%s"] * len(ctx["sec_ids"]))); args += ctx["sec_ids"]
    if ctx["roll"]:
        where.append("st.student_rollNumber=%s"); args.append(ctx["roll"])
    for t in name_tokens:
        where.append("(st.student_name LIKE %s OR st.ADMNO=%s OR st.student_code LIKE %s OR st.studentUID=%s OR st.combineName LIKE %s)")
        args += [f"%{t}%", t, f"%{t}%", t, f"%{t}%"]
    if scope is not None:
        if not scope:
            return [], 0
        where.append("(" + " OR ".join(["(st.class_id=%s AND st.section_id=%s)"] * len(scope)) + ")")
        for c, s in sorted(scope):
            args += [c, s]
    base = ("FROM students st JOIN classes c ON c.classId=st.class_id JOIN sections s ON s.sectionId=st.section_id WHERE " + " AND ".join(where))
    total = db.scalar("SELECT COUNT(*) " + base, args) or 0
    rows = db.query("SELECT st.studentId, st.student_name, st.student_rollNumber, st.ADMNO, st.class_id, st.section_id, c.class_name, s.section_name "
                    + base + " ORDER BY st.class_id, st.section_id, st.student_rollNumber, st.student_name LIMIT %s", args + [limit])
    return rows, total


def _marks_for(user, rows, exam, subject_ids):
    """{studentId: {...}} marks of the chosen exam, only subjects the user may see."""
    if not rows:
        return {}
    ids = [r["studentId"] for r in rows]
    ph = ",".join(["%s"] * len(ids))
    data = db.query(f"""SELECT em.studentId, em.subjectId, sb.subject_name, x.exam_type, em.marks, em.fullmarsks
        FROM exam_marks em JOIN subjects sb ON sb.subjectId=em.subjectId JOIN exam_subtype x ON x.id=em.exam_subtype_id
        WHERE em.studentId IN ({ph}) AND em.examId=%s AND em.isDelete='0' ORDER BY sb.subject_name, em.fullmarsks DESC""", ids + [exam])
    allowed = {}
    if not user["is_admin"]:
        ct = {(p["classId"], p["sectionId"]) for p in access.class_pairs(user)}
        for r in rows:
            key = (r["class_id"], r["section_id"])
            if key in ct:
                allowed[r["studentId"]] = None                       # class teacher: every subject
            else:
                allowed[r["studentId"]] = {x["subjectId"] for x in db.query(
                    "SELECT subjectId FROM assign_teacher WHERE t_id=%s AND classId=%s AND sectionId=%s AND isDelete='0'", (user["id"], *key))}
    out = {}
    for d in data:
        sid = d["studentId"]
        if sid in allowed and allowed[sid] is not None and d["subjectId"] not in allowed[sid]:
            continue
        if subject_ids and d["subjectId"] not in subject_ids:
            continue
        subj = out.setdefault(sid, {}).setdefault(d["subjectId"], {"subject": d["subject_name"], "parts": [], "got": 0.0, "full": 0.0, "numeric": False})
        subj["parts"].append({"n": d["exam_type"], "m": d["marks"], "f": d["fullmarsks"]})
        try:
            subj["got"] += float(str(d["marks"]).strip()); subj["full"] += float(d["fullmarsks"] or 0); subj["numeric"] = True
        except ValueError:
            pass
    res = {}
    for sid, subs in out.items():
        rws, tg, tf = [], 0.0, 0.0
        for s in subs.values():
            rws.append({"subject": s["subject"], "parts": s["parts"], "total": _fmt(s["got"]) if s["numeric"] else None,
                        "full": _fmt(s["full"]) if s["numeric"] else None})
            if s["numeric"]:
                tg += s["got"]; tf += s["full"]
        res[sid] = {"rows": rws, "total": _fmt(tg), "full": _fmt(tf), "pct": round(100 * tg / tf, 1) if tf else None}
    return res


def _fmt(v):
    return str(int(v)) if float(v).is_integer() else str(round(v, 2))


def run(user, q):
    q = (q or "").strip()[:100]
    res = {"q": q, "understood": [], "groups": []}
    if len(q) < 1:
        return res
    scope = _scope(user)
    p = parse(q)
    from . import smart_answer as SA
    smart = SA.answer(user, q, p)                          # free-form questions, answered within the account's own access
    if smart and smart["status"] == "ok":
        res["say"] = smart["say"]
        res["groups"].extend(smart["groups"])
        res["understood"] += smart["chips"]
        return res
    if p["tokens"] and all(t in SA.FILLER for t in p["tokens"]) and not (p["cls"] or p["roll"]):
        res["say"] = ("Tell me what you need, for example “list of students of class 6 c”, “parents phone numbers of class 6 c”, "
                      "“class teacher of 5 b” or “phone of <teacher name>”.")
        return res
    if user.get("is_parent"):                              # parents only ever get answers about their own children
        res["say"] = (smart or {}).get("say") or ("I can answer questions about your child, for example “who is my child's class teacher”, "
                                                    "“attendance of my child” or “is the report card published”.")
        return res
    classes = _classes()
    cls_ids, sec_ids, sec_rows = [], [], []
    if p["cls"]:
        cl = _class_matches(classes, p["cls"])
        cls_ids = [c["classId"] for c in cl]
        if cl:
            res["understood"].append(cl[0]["class_name"])
    if cls_ids:
        sec_rows = db.query("SELECT s.sectionId, s.section_name, s.class_id, c.class_name FROM sections s JOIN classes c ON c.classId=s.class_id "
                            "WHERE s.isDelete='0' AND s.class_id IN (%s) ORDER BY s.class_id, s.section_name" % ",".join(["%s"] * len(cls_ids)), cls_ids)
        if scope is not None:
            sec_rows = [s for s in sec_rows if (s["class_id"], s["sectionId"]) in scope]
        if p["sec"]:
            sec_rows = [s for s in sec_rows if (s["section_name"] or "").upper() == p["sec"]]
            sec_ids = [s["sectionId"] for s in sec_rows]
            if sec_rows:
                res["understood"].append("Section " + p["sec"])
    elif p["sec"]:                                           # "section a" alone is too vague - treat as a word
        p["tokens"].append(p["sec"].lower())
    if p["roll"]:
        res["understood"].append(f"Roll {p['roll']}")
    subjects = db.query("SELECT subjectId, subject_name FROM subjects WHERE isDelete='0'")
    sub_hit = _subject_hits(p["tokens"], subjects)
    exams = db.query("SELECT examId, exam_name FROM exams WHERE isDelete='0' ORDER BY examId")
    ql = q.lower()
    exam_pick = next((e for e in exams if e["exam_name"].lower() in ql), None)
    ctx_given = bool(cls_ids or p["roll"] or p["marks"])
    sub_tokens = [t for t in p["tokens"] if _subject_hits([t], subjects)]
    name_tokens = [t for t in p["tokens"] if t not in sub_tokens] if (sub_hit and ctx_given) else list(p["tokens"])
    ctx = {"cls_ids": cls_ids, "sec_ids": sec_ids, "roll": p["roll"]}
    fe = features.pairs("entry", user)
    fcard = {(x["classId"], x["sectionId"]) for x in features.pairs("card", user)}
    fentry = {(x["classId"], x["sectionId"]) for x in fe}
    ex_default = (exam_pick or (exams[0] if exams else None))

    def sec_actions(cid, sid):
        a = []
        if user["is_admin"]:
            a.append({"label": "Students", "url": url_for("students.student_list", class_id=cid, section_id=sid)})
        if (cid, sid) in fentry and ex_default:
            a.append({"label": "Marks", "url": url_for("marks.marks_list", class_id=cid, section_id=sid, exam_id=ex_default["examId"])})
        if (cid, sid) in fcard:
            a.append({"label": "Report cards", "url": url_for("reports.report_cards", class_id=cid, section_id=sid)})
        return a

    # ---- sections (when the sentence names a class)
    if cls_ids and not name_tokens and not p["roll"]:
        items = []
        for s in sec_rows[:12]:
            n = db.scalar("SELECT COUNT(*) FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (s["class_id"], s["sectionId"])) or 0
            ct = db.scalar("SELECT TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) FROM classTeacher k JOIN teachers t ON t.user_id=k.teacherId "
                           "WHERE k.classId=%s AND k.sectionId=%s AND k.isDelete='0' LIMIT 1", (s["class_id"], s["sectionId"]))
            acts = sec_actions(s["class_id"], s["sectionId"])
            items.append({"title": f"{s['class_name']} · Section {s['section_name']}", "sub": f"{n} students" + (f" · Class teacher: {ct}" if ct else ""),
                          "icon": "layers", "url": acts[0]["url"] if acts else None, "actions": acts[1:] if acts else []})
        if items:
            res["groups"].append({"title": "Class & section", "items": items})

    # ---- students
    want_students = bool(name_tokens or p["roll"] or (cls_ids and (p["sec"] or p["marks"])) or sub_hit and cls_ids)
    if want_students:
        rows, total = _student_rows(user, scope, ctx, name_tokens, 8)
        if not rows and sub_hit and name_tokens:                    # the subject-looking word may really be part of a name
            rows, total = _student_rows(user, scope, ctx, list(p["tokens"]), 8)
        show_marks = bool(rows) and (p["marks"] or bool(sub_hit) or len(rows) <= 3)
        mk = {}
        if show_marks:
            ex = ex_default
            if ex and not exam_pick:
                best = db.scalar("SELECT examId FROM exam_marks WHERE studentId=%s AND isDelete='0' GROUP BY examId ORDER BY examId DESC LIMIT 1", (rows[0]["studentId"],))
                ex = next((e for e in exams if e["examId"] == best), ex)
            if ex:
                mk = _marks_for(user, rows, ex["examId"], set(sub_hit))
                res["understood"].append(ex["exam_name"])
        if sub_hit and show_marks:
            res["understood"].append("Subject: " + ", ".join(sorted(set(sub_hit.values()))))
        items = []
        for r in rows:
            cid, sid = r["class_id"], r["section_id"]
            acts = []
            if (cid, sid) in fentry and ex_default:
                acts.append({"label": "Marks sheet", "url": url_for("marks.marks_list", class_id=cid, section_id=sid, exam_id=ex_default["examId"])})
            if (cid, sid) in fcard:
                acts.append({"label": "Report card", "url": url_for("reports.card", student_id=r["studentId"]), "popup": True})
            if user["is_admin"]:
                acts.append({"label": "Profile", "url": url_for("students.edit", sid=r["studentId"])})
            main = (acts[0]["url"] if (p["marks"] or sub_hit) and acts else (acts[-1]["url"] if user["is_admin"] else (acts[0]["url"] if acts else None)))
            items.append({"title": r["student_name"], "icon": "users", "badge": f"Roll {r['student_rollNumber']}",
                          "sub": f"{r['class_name']} · {r['section_name']}" + (f" · Adm {r['ADMNO']}" if r["ADMNO"] else ""),
                          "url": main, "actions": [a for a in acts if a["url"] != main], "marks": mk.get(r["studentId"])})
        if items:
            more = None
            if total > len(rows) and user["is_admin"]:
                more = url_for("students.student_list", q=" ".join(name_tokens), class_id=cls_ids[0] if len(cls_ids) == 1 else None, section_id=sec_ids[0] if len(sec_ids) == 1 else None)
            res["groups"].append({"title": f"Students ({total})", "items": items, "more": more})
        elif cls_ids or p["roll"] or name_tokens:
            res["groups"].append({"title": "Students", "items": [], "empty": "No student matches that."})

    # ---- a subject in a section: how far marks entry is
    if sub_hit and cls_ids and sec_ids and not name_tokens and ex_default:
        items = []
        for s in sec_rows[:4]:
            for sid_, sname in sub_hit.items():
                got = db.one("SELECT COUNT(DISTINCT studentId) n FROM exam_marks WHERE classId=%s AND sectionId=%s AND subjectId=%s AND examId=%s AND isDelete='0'",
                             (s["class_id"], s["sectionId"], sid_, ex_default["examId"]))
                tot = db.scalar("SELECT COUNT(*) FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (s["class_id"], s["sectionId"])) or 0
                if (s["class_id"], s["sectionId"]) in fentry:
                    items.append({"title": f"{sname} · {s['class_name']} {s['section_name']}", "icon": "edit", "sub": f"Marks entered for {got['n']} of {tot} students ({ex_default['exam_name']})",
                                  "url": url_for("marks.entry", class_id=s["class_id"], section_id=s["sectionId"], exam_id=ex_default["examId"]), "actions": []})
        if items:
            res["groups"].append({"title": "Subject marks", "items": items})

    # ---- admin only: teachers and parents
    if user["is_admin"] and name_tokens and not cls_ids and not p["roll"]:
        w, a = [], []
        for t in name_tokens:
            w.append("(t.fname LIKE %s OR t.mname LIKE %s OR t.lname LIKE %s OR t.phone_1 LIKE %s)"); a += [f"%{t}%"] * 4
        trs = db.query("SELECT t.user_id, TRIM(CONCAT_WS(' ', t.fname, NULLIF(t.mname,''), t.lname)) nm, t.phone_1 FROM teachers t WHERE t.deleted_at IS NULL AND "
                       + " AND ".join(w) + " ORDER BY t.fname LIMIT 5", a)
        if trs:
            res["groups"].append({"title": "Teachers", "items": [{"title": t["nm"], "icon": "users", "sub": "Teacher" + (f" · {t['phone_1']}" if t["phone_1"] else ""),
                                  "url": url_for("admin.teacher_mapping_edit", teacher_id=t["user_id"]), "actions": []} for t in trs]})
        w, a = [], []
        for t in name_tokens:
            w.append("(" + PI.sql_name() + " LIKE %s OR p.mname LIKE %s OR p.lname LIKE %s OR p.phone_1 LIKE %s OR p.email LIKE %s)"); a += [f"%{t}%"] * 5
        prs = db.query("SELECT p.*, u.fname AS account_name FROM parents p LEFT JOIN new_users u ON u.id=p.user_id AND u.deleted_at IS NULL WHERE p.deleted_at IS NULL AND "
                       + " AND ".join(w) + " ORDER BY p.fname LIMIT 5", a)
        for parent in prs:
            parent['nm'] = PI.name(parent) or 'Name not recorded'
        if prs:
            res["groups"].append({"title": "Parents", "items": [{"title": r["nm"], "icon": "users", "sub": "Parent" + (f" · {r['phone_1']}" if r["phone_1"] else ""),
                                  "url": url_for("parents.detail", pid=r["id"]), "actions": []} for r in prs]})
    if smart and not any(g.get("items") for g in res["groups"]):
        res["say"] = smart["say"]                           # asked a question but nothing matched
        res["groups"] = []
    return res
