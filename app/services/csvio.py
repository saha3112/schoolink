"""CSV import / sample download for everything a teacher or class teacher types in bulk.

A CSV is read from memory, checked completely, and only then written (all or nothing - a file with a problem changes
nothing).  The file itself is never stored: it is gone as soon as the request ends."""
import csv
import io
import re

from .. import db
from ..utils import to_int
from . import access, enrollment, features

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
DEV_GRADES = ["EXCELLENT", "GOOD", "NEEDS IMPROVEMENT", "UNSATISFACTORY", "ABSENT"]

KINDS = {
    "marks": dict(title="Marks", feature="entry", need_exam=True, page="marks.entry"),
    "special": dict(title="Special subject grades", feature="special", need_exam=True, page="marks.special"),
    "attendance": dict(title="Attendance", feature="attendance", need_exam=True, page="classteacher.attendance"),
    "comments": dict(title="Teacher comments", feature="comments", need_exam=True, page="classteacher.comments"),
    "development": dict(title="Development skills", feature="development", need_exam=True, page="classteacher.development"),
    "rank": dict(title="Ranks", feature="rank", need_exam=True, page="classteacher.rank"),
    "house": dict(title="House points", feature="house", need_exam=True, page="classteacher.house"),
    "average": dict(title="Average, award & promotion", feature="average", need_exam=False, page="classteacher.average"),
    "students": dict(title="Students", feature=None, need_exam=False, page="students.upload", admin_only=True),
    "parents": dict(title="Parents", feature=None, need_exam=False, page="parents.all_parents", admin_only=True),
}
ENDPOINT_KIND = {v["page"]: k for k, v in KINDS.items()}


class CsvError(Exception):
    pass


def norm(h):
    return re.sub(r"[^a-z0-9]+", "", (h or "").lower())


# ------------------------------------------------------------------------------------------------ reading
def read_csv(data):
    if not data:
        raise CsvError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise CsvError("The file is larger than 2 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if "\x00" in text:
        raise CsvError("This does not look like a CSV (text) file. Save your sheet as “CSV” and try again.")
    first = text.split("\n", 1)[0]
    delim = max((",", ";", "\t"), key=lambda d: first.count(d))
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise CsvError("The CSV has a heading row but no data rows.")
    if len(rows) > MAX_ROWS + 1:
        raise CsvError(f"Too many rows ({len(rows) - 1}). Import at most {MAX_ROWS} rows at a time.")
    return rows[0], rows[1:]


# ------------------------------------------------------------------------------------------------ context
def context(user, kind, args):
    spec = KINDS.get(kind)
    if not spec:
        raise CsvError("Unknown import type.")
    if spec.get("admin_only"):
        if not user["is_admin"]:
            raise PermissionError("Only administrators can import students.")
        return dict(kind=kind, spec=spec, user=user)
    pairs = features.pairs(spec["feature"], user)
    cls, sec, exam = (to_int(args.get(k)) for k in ("class_id", "section_id", "exam_id"))
    if not (cls and sec):
        raise CsvError("Choose a class and section first.")
    if (cls, sec) not in {(p["classId"], p["sectionId"]) for p in pairs}:
        raise PermissionError("You cannot import data for this class and section.")
    if spec["need_exam"]:
        if not exam:
            raise CsvError("Choose an exam first.")
        if not db.one("SELECT 1 FROM exams WHERE examId=%s AND isDelete='0'", (exam,)):
            raise CsvError("That exam does not exist.")
    if kind in ('marks','special'):
        feature='entry' if kind=='marks' else 'special'
        if not any((row['classId'],row['sectionId'],row['examId'])==(cls,sec,exam) for row in features.mark_contexts(user,feature)):
            raise PermissionError('This marks type or exam is not assigned to you for this section.')
    elif spec['need_exam'] and exam not in {row['examId'] for row in access.exams_for(cls,sec)}:
        raise PermissionError('This exam is not configured for this section.')
    return dict(kind=kind, spec=spec, user=user, cls=cls, sec=sec, exam=exam if spec["need_exam"] else None,
                students=access.students(cls, sec),
                class_name=db.scalar("SELECT class_name FROM classes WHERE classId=%s", (cls,)) or str(cls),
                section_name=db.scalar("SELECT section_name FROM sections WHERE sectionId=%s", (sec,)) or str(sec),
                exam_name=(db.scalar("SELECT exam_name FROM exams WHERE examId=%s", (exam,)) if exam else "") or "")


def file_name(ctx):
    bits = [ctx["kind"]] + ([ctx["class_name"], ctx["section_name"]] if "cls" in ctx else []) + ([ctx["exam_name"]] if ctx.get("exam_name") else [])
    return re.sub(r"[^A-Za-z0-9]+", "-", "_".join(bits)).strip("-_") + ".csv"


# ------------------------------------------------------------------------------------------------ student matching
def _cols(headers):
    return {norm(h): i for i, h in enumerate(headers)}


def match_rows(ctx, headers, rows):
    """-> ([(row_no, student, cells)], errors).  Matches on Student ID (if the column is there) else on Roll."""
    cols = _cols(headers)
    ci = next((cols[k] for k in ("studentid", "id") if k in cols), None)
    ri = next((cols[k] for k in ("roll", "rollno", "rollnumber", "rollno.") if k in cols), None)
    if ci is None and ri is None:
        raise CsvError("The CSV needs a “Student ID” or a “Roll” column. Download the sample to see the layout.")
    by_id = {s["studentId"]: s for s in ctx["students"]}
    by_roll = {str(s["student_rollNumber"]): s for s in ctx["students"]}
    out, errs, seen = [], [], set()
    for n, r in enumerate(rows, 2):
        cell = lambda i: (r[i].strip() if i is not None and i < len(r) else "")
        s = None
        if ci is not None and cell(ci):
            s = by_id.get(to_int(cell(ci)))
            if not s:
                errs.append(f"Row {n}: student ID {cell(ci)} is not in {ctx['class_name']} {ctx['section_name']}."); continue
        elif ri is not None and cell(ri):
            s = by_roll.get(re.sub(r"\.0+$", "", cell(ri)))
            if not s:
                errs.append(f"Row {n}: roll {cell(ri)} is not in {ctx['class_name']} {ctx['section_name']}."); continue
        else:
            errs.append(f"Row {n}: no Student ID or Roll."); continue
        if s["studentId"] in seen:
            errs.append(f"Row {n}: {s['student_name']} appears more than once."); continue
        seen.add(s["studentId"])
        out.append((n, s, r))
    return out, errs


def _who(s):
    return f"{s['student_name']} (roll {s['student_rollNumber']})"


def _cell(r, i):
    return r[i].strip() if i is not None and i < len(r) else ""


# ------------------------------------------------------------------------------------------------ definitions of each kind
def _mark_columns(ctx):
    """[(label, subject_id, subject_name, subtype_id, full)] in sheet order (normal subjects)."""
    out = []
    for sb in access.allowed_subjects(ctx["user"], ctx["cls"], ctx["sec"]):
        for st in access.subtypes(ctx["cls"], ctx["sec"], ctx["exam"], sb["subjectId"]):
            out.append((f"{sb['subject_name']} - {st['name']} (max {st['fullmarks']})", sb["subjectId"], sb["subject_name"], st["subtype_id"], st["fullmarks"]))
    return out


def _special_columns(ctx):
    out = []
    allowed={row['subjectId'] for row in features.mark_contexts(ctx['user'],'special') if (row['classId'],row['sectionId'],row['examId'])==(ctx['cls'],ctx['sec'],ctx['exam'])}
    for sb in access.allowed_subjects(ctx["user"], ctx["cls"], ctx["sec"], special=True):
        if sb['subjectId'] not in allowed:continue
        full = db.scalar("SELECT fullmarsks FROM assign_exam_subtype WHERE classId=%s AND sectionId=%s AND subjectId=%s AND examId=%s AND exam_subtype_id=2 AND isDelete='0' LIMIT 1",
                         (ctx["cls"], ctx["sec"], sb["subjectId"], ctx["exam"]), 0) or 0
        out.append((sb["subject_name"], sb["subjectId"], sb["subject_name"], 2, full))
    return out


BASE = ["Student ID", "Roll", "Student Name"]


def _base(s):
    return [s["studentId"], s["student_rollNumber"], s["student_name"]]


def sample(ctx, blank=False):
    """-> (headers, rows) pre-filled with what is saved now (or empty cells with blank=True)."""
    k, cls, sec, exam = ctx["kind"], ctx.get("cls"), ctx.get("sec"), ctx.get("exam")
    if k == "parents":
        head = ["mobile", "first_name", "middle_name", "last_name", "alternate_phone", "secondary_name", "address", "student_codes", "admission_numbers", "children_names", "initial_password", "email", "occupation"]
        if blank:
            return head, [[""] * len(head)]
        return head, [
            ["9000000001", "Rina", "", "Das", "9000000002", "Amit Das", "12 Example Road, Kolkata", "SAMPLE001; SAMPLE002", "ADM001; ADM002", "Aarav Das; Diya Das", "", "rina@example.com", "Teacher"],
            ["9000000003", "Anita", "", "Sen", "", "", "34 Example Road, Kolkata", "SAMPLE003", "ADM003", "Rohan Sen", "", "", ""],
        ]
    if k == "students":
        cl = db.one("SELECT c.class_name, s.section_name FROM sections s JOIN classes c ON c.classId=s.class_id WHERE s.isDelete='0' AND c.isDelete='0' ORDER BY c.classId, s.sectionId LIMIT 1") or {"class_name": "Class 1", "section_name": "A"}
        return (["student_id", "student_code", "first_name", "last_name", "roll", "class_name", "section_name"],
                [["", "STS/SS00000001", "Aarav", "Sharma", "1", cl["class_name"], cl["section_name"]], ["", "STS/SS00000002", "Diya", "Das", "", cl["class_name"], cl["section_name"]]])
    students = ctx["students"]
    if k in ("marks", "special"):
        cols = _mark_columns(ctx) if k == "marks" else _special_columns(ctx)
        ex = {(r["studentId"], r["subjectId"], r["exam_subtype_id"]): r["marks"] for r in db.query(
            "SELECT studentId, subjectId, exam_subtype_id, marks FROM exam_marks WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam))}
        excl = enrollment.excluded(cls, sec)
        rows = [_base(s) + [("" if blank or (s["studentId"], c[1]) in excl else ex.get((s["studentId"], c[1], c[3]), "")) for c in cols] for s in students]
        return BASE + [c[0] for c in cols], rows
    cm = {r["studentId"]: r for r in db.query("SELECT studentId, totalSession, attendSession, comment, `rank` FROM studentComment WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam))} if exam else {}
    g = lambda s, f: ("" if blank else (cm.get(s["studentId"], {}).get(f) if cm.get(s["studentId"], {}).get(f) not in (None,) else ""))
    if k == "attendance":
        return BASE + ["Total sessions", "Attended"], [_base(s) + [g(s, "totalSession"), g(s, "attendSession")] for s in students]
    if k == "comments":
        return BASE + ["Comment"], [_base(s) + [g(s, "comment")] for s in students]
    if k == "rank":
        return BASE + ["Rank"], [_base(s) + [g(s, "rank")] for s in students]
    if k == "house":
        hs = {r["studentId"]: r for r in db.query("SELECT studentId, houseName, housePoints FROM student_house WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam))}
        return BASE + ["House", "Points"], [_base(s) + ([] if blank or s["studentId"] not in hs else [hs[s["studentId"]]["houseName"], hs[s["studentId"]]["housePoints"]]) + ([""] * 2 if blank or s["studentId"] not in hs else []) for s in students]
    if k == "development":
        skills = db.query("SELECT id, skillName FROM developmentSkill WHERE classId=%s AND sectionId=%s AND isDelete='0' ORDER BY id", (cls, sec))
        ex = {(r["studentId"], r["subjectId"]): r["marks"] for r in db.query("SELECT studentId, subjectId, marks FROM exam_marks_development WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam))}
        return BASE + [s["skillName"] for s in skills], [_base(s) + [("" if blank else ex.get((s["studentId"], k_["id"]), "")) for k_ in skills] for s in students]
    if k == "average":
        out = []
        for s in students:
            r = None if blank else db.one("SELECT rankAvarage, award, promotion FROM rankAvarageOther WHERE studentId=%s AND isDelete='0' ORDER BY id DESC LIMIT 1", (s["studentId"],))
            out.append(_base(s) + ([r["rankAvarage"], r["award"], r["promotion"]] if r else ["", "", ""]))
        return BASE + ["Average", "Award", "Promotion"], out
    raise CsvError("Unknown import type.")


def to_csv_bytes(headers, rows):
    b = io.StringIO()
    w = csv.writer(b, lineterminator="\r\n")
    w.writerow(headers)
    w.writerows(rows)
    return ("﻿" + b.getvalue()).encode("utf-8")          # BOM so Excel shows every character correctly


# ------------------------------------------------------------------------------------------------ importing
def _summary(kind, saved, students, unchanged, warnings, noun="value"):
    msg = f"Imported {saved} {noun}{'s' if saved != 1 else ''} for {students} student{'s' if students != 1 else ''}."
    if unchanged:
        msg += f" {unchanged} {'were' if unchanged != 1 else 'was'} already up to date."
    if warnings:
        msg += f" {len(warnings)} note{'s' if len(warnings) != 1 else ''}."
    return msg


def run_import(ctx, data):
    """-> dict(ok, message, saved, errors[], warnings[])"""
    headers, rows = read_csv(data)
    user, k = ctx["user"], ctx["kind"]
    if k == "students":
        return _import_students(user, headers, rows)
    if k == "parents":
        return _import_parents(headers, rows)
    if not user["is_admin"] and not access.editing_enabled():
        raise CsvError("Entry is currently switched off by the administrator.")
    matched, errors = match_rows(ctx, headers, rows)
    cols = _cols(headers)
    warnings = []
    writes = []                      # callables executed only if there is no error
    touched, unchanged, saved = set(), 0, 0

    if k in ("marks", "special"):
        from ..blueprints.marks import parse_mark, upsert_mark
        defs = _mark_columns(ctx) if k == "marks" else _special_columns(ctx)
        lookup = {}
        for label, sid_, sname, stid, full in defs:
            lookup[norm(label)] = (sid_, sname, stid, full, label)
            lookup.setdefault(norm(label.rsplit(" (max", 1)[0]), (sid_, sname, stid, full, label))
        mapped = {i: lookup[norm(h)] for i, h in enumerate(headers) if norm(h) in lookup}
        for i, h in enumerate(headers):
            if i not in mapped and norm(h) not in ("studentid", "id", "roll", "rollno", "rollnumber", "studentname", "name", "student"):
                warnings.append(f"Column “{h}” is not a subject you can enter marks for - ignored.")
        if not mapped:
            raise CsvError("None of the CSV columns match your subjects. Download the sample and use its column headings.")
        existing = {(r["studentId"], r["subjectId"], r["exam_subtype_id"]): r["marks"] for r in db.query(
            "SELECT studentId, subjectId, exam_subtype_id, marks FROM exam_marks WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (ctx["cls"], ctx["sec"], ctx["exam"]))}
        excl = enrollment.excluded(ctx["cls"], ctx["sec"])
        for n, s, r in matched:
            for i, (sid_, sname, stid, full, label) in mapped.items():
                raw = _cell(r, i)
                if raw == "":
                    continue
                if (s["studentId"], sid_) in excl:
                    warnings.append(f"Row {n}: {s['student_name']} does not take {sname} - skipped."); continue
                if k == "marks":
                    val, err = parse_mark(raw, full)
                    if err:
                        errors.append(f"Row {n} · {_who(s)} · {label.rsplit(' (max', 1)[0]}: {err}"); continue
                else:
                    val = raw[:40]
                if existing.get((s["studentId"], sid_, stid)) == val:
                    unchanged += 1; continue
                writes.append((s["studentId"], sid_, stid, full, val)); touched.add(s["studentId"])
        if not errors:
            for stu, sid_, stid, full, val in writes:
                upsert_mark(ctx["cls"], ctx["sec"], stu, sid_, ctx["exam"], stid, full, val, user["id"])
            saved = len(writes)
            return _done(ctx, saved, touched, unchanged, warnings, errors, "mark" if k == "marks" else "grade")
        return _fail(errors, warnings)

    from ..blueprints.classteacher import _upsert_comment_row
    cls, sec, exam = ctx["cls"], ctx["sec"], ctx["exam"]
    cm = {r["studentId"]: r for r in db.query("SELECT studentId, totalSession, attendSession, comment, `rank` FROM studentComment WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam))} if exam else {}

    def col(*names):
        return next((cols[n] for n in names if n in cols), None)

    if k == "attendance":
        ti, ai = col("totalsessions", "total", "totalsession"), col("attended", "attend", "attendedsessions")
        if ti is None or ai is None:
            raise CsvError("The CSV needs “Total sessions” and “Attended” columns.")
        for n, s, r in matched:
            t, a = _cell(r, ti), _cell(r, ai)
            old = cm.get(s["studentId"]) or {}
            t = t or (str(old["totalSession"]) if old.get("totalSession") is not None else ""); a = a or (str(old["attendSession"]) if old.get("attendSession") is not None else "")
            if not t and not a:
                continue
            if not (t.isdigit() and a.isdigit()):
                errors.append(f"Row {n} · {_who(s)}: sessions must be whole numbers."); continue
            if int(a) > int(t):
                errors.append(f"Row {n} · {_who(s)}: attended ({a}) is more than total sessions ({t})."); continue
            if old.get("totalSession") == int(t) and old.get("attendSession") == int(a):
                unchanged += 1; continue
            writes.append(lambda s=s, t=t, a=a: _upsert_comment_row(cls, sec, exam, s["studentId"], user, totalSession=int(t), attendSession=int(a))); touched.add(s["studentId"])
    elif k == "comments":
        ci = col("comment", "comments", "remark", "remarks")
        if ci is None:
            raise CsvError("The CSV needs a “Comment” column.")
        for n, s, r in matched:
            txt = _cell(r, ci)
            if not txt:
                continue
            if len(txt) > 2000:
                errors.append(f"Row {n} · {_who(s)}: comment is longer than 2000 characters."); continue
            if (cm.get(s["studentId"]) or {}).get("comment") == txt:
                unchanged += 1; continue
            writes.append(lambda s=s, txt=txt: (_upsert_comment_row(cls, sec, exam, s["studentId"], user, comment=txt), db.execute("INSERT IGNORE INTO comment_templates (comment_text) VALUES (%s)", (txt[:500],), commit=False))); touched.add(s["studentId"])
    elif k == "rank":
        ri = col("rank", "ranks")
        if ri is None:
            raise CsvError("The CSV needs a “Rank” column.")
        for n, s, r in matched:
            v = _cell(r, ri)
            if not v:
                continue
            if len(v) > 20:
                errors.append(f"Row {n} · {_who(s)}: rank is too long."); continue
            if str((cm.get(s["studentId"]) or {}).get("rank") or "") == v:
                unchanged += 1; continue
            writes.append(lambda s=s, v=v: _upsert_comment_row(cls, sec, exam, s["studentId"], user, **{"rank": v})); touched.add(s["studentId"])
    elif k == "house":
        hi, pi = col("house", "housename"), col("points", "housepoints")
        if hi is None and pi is None:
            raise CsvError("The CSV needs “House” and “Points” columns.")
        cur = {r["studentId"]: r for r in db.query("SELECT id, studentId, houseName, housePoints FROM student_house WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam))}
        for n, s, r in matched:
            hn, hp = _cell(r, hi), _cell(r, pi)
            if not hn and not hp:
                continue
            if hp and not re.fullmatch(r"-?\d+", hp):
                errors.append(f"Row {n} · {_who(s)}: points must be a whole number."); continue
            old = cur.get(s["studentId"])
            if old and old["houseName"] == hn and str(old["housePoints"]) == str(int(hp or 0)):
                unchanged += 1; continue
            writes.append(lambda s=s, hn=hn, hp=hp, old=old: _write_house(cls, sec, exam, s["studentId"], hn, int(hp or 0), old, user)); touched.add(s["studentId"])
    elif k == "development":
        skills = db.query("SELECT id, skillName FROM developmentSkill WHERE classId=%s AND sectionId=%s AND isDelete='0' ORDER BY id", (cls, sec))
        smap = {norm(x["skillName"]): x for x in skills}
        mapped = {i: smap[norm(h)] for i, h in enumerate(headers) if norm(h) in smap}
        if not mapped:
            raise CsvError("None of the CSV columns match this class's skills. Download the sample and use its headings.")
        ex = {(r["studentId"], r["subjectId"]): r for r in db.query("SELECT id, studentId, subjectId, marks FROM exam_marks_development WHERE classId=%s AND sectionId=%s AND examId=%s AND isDelete='0'", (cls, sec, exam))}
        grades = {g.upper(): g for g in DEV_GRADES}
        for n, s, r in matched:
            for i, sk in mapped.items():
                v = _cell(r, i)
                if not v:
                    continue
                g = grades.get(re.sub(r"\s+", " ", v.upper()))
                if not g:
                    errors.append(f"Row {n} · {_who(s)} · {sk['skillName']}: “{v}” is not a grade (use {', '.join(DEV_GRADES)})."); continue
                old = ex.get((s["studentId"], sk["id"]))
                if old and old["marks"] == g:
                    unchanged += 1; continue
                writes.append(lambda s=s, sk=sk, g=g, old=old: _write_dev(cls, sec, exam, s["studentId"], sk["id"], g, old, user)); touched.add(s["studentId"])
    elif k == "average":
        ai_, wi, pi = col("average", "avg", "rankaverage", "rankavarage"), col("award"), col("promotion", "promoted")
        if ai_ is None and wi is None and pi is None:
            raise CsvError("The CSV needs “Average”, “Award” and/or “Promotion” columns.")
        for n, s, r in matched:
            avg, award, promo = _cell(r, ai_), _cell(r, wi), _cell(r, pi)
            if not (avg or award or promo):
                continue
            old = db.one("SELECT id, rankAvarage, award, promotion FROM rankAvarageOther WHERE studentId=%s AND isDelete='0' ORDER BY id DESC LIMIT 1", (s["studentId"],))
            if old and (old["rankAvarage"] or "") == avg and (old["award"] or "") == award and (old["promotion"] or "") == promo:
                unchanged += 1; continue
            writes.append(lambda s=s, avg=avg, award=award, promo=promo, old=old: _write_avg(cls, sec, s["studentId"], avg, award, promo, old, user)); touched.add(s["studentId"])
    else:
        raise CsvError("Unknown import type.")
    if errors:
        return _fail(errors, warnings)
    for w in writes:
        w()
    return _done(ctx, len(writes), touched, unchanged, warnings, errors, {"attendance": "attendance entry", "comments": "comment", "rank": "rank", "house": "house entry", "development": "grade", "average": "entry"}[k])


def _write_house(cls, sec, exam, stu, hn, hp, old, user):
    if old:
        db.execute("UPDATE student_house SET houseName=%s, housePoints=%s WHERE id=%s", (hn, hp, old["id"]), commit=False)
    else:
        nid = (db.scalar("SELECT COALESCE(MAX(id),0)+1 FROM student_house") or 1)
        db.execute("INSERT INTO student_house (id, classId, sectionId, examId, studentId, houseName, housePoints, teacherId) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (nid, cls, sec, exam, stu, hn, hp, user["id"]), commit=False)


def _write_dev(cls, sec, exam, stu, skill, g, old, user):
    if old:
        db.execute("UPDATE exam_marks_development SET marks=%s, teacherId=%s WHERE id=%s", (g, user["id"], old["id"]), commit=False)
    else:
        db.execute("INSERT INTO exam_marks_development (classId, sectionId, subjectId, examId, studentId, exam_subtype_id, fullmarsks, teacherId, marks) VALUES (%s,%s,%s,%s,%s,2,0,%s,%s)",
                   (cls, sec, skill, exam, stu, user["id"], g), commit=False)


def _write_avg(cls, sec, stu, avg, award, promo, old, user):
    if old:
        db.execute("UPDATE rankAvarageOther SET classId=%s, sectionId=%s, rankAvarage=%s, award=%s, promotion=%s, teacherId=%s WHERE id=%s", (cls, sec, avg, award, promo, user["id"], old["id"]), commit=False)
    else:
        db.execute("INSERT INTO rankAvarageOther (classId, sectionId, studentId, teacherId, rankAvarage, award, promotion) VALUES (%s,%s,%s,%s,%s,%s,%s)", (cls, sec, stu, user["id"], avg, award, promo), commit=False)


def _done(ctx, saved, touched, unchanged, warnings, errors, noun):
    db.commit()
    if not saved and unchanged:
        msg = "Nothing to change - everything in the file is already saved."
    elif not saved:
        msg = "The file had no values to import. Fill in the cells and try again."
    else:
        msg = _summary(ctx["kind"], saved, len(touched), unchanged, warnings, noun)
    return dict(ok=bool(saved or unchanged), saved=saved, unchanged=unchanged, errors=[], warnings=warnings[:30], message=msg)


def _fail(errors, warnings):
    db.rollback()
    n = len(errors)
    return dict(ok=False, saved=0, unchanged=0, errors=errors[:60], more=max(0, n - 60), warnings=warnings[:30],
                message=f"Nothing was imported — {n} problem{'s' if n != 1 else ''} found. Fix the file and upload it again.")


def _import_students(user, headers, rows):
    from . import rolls
    expected = ["studentid", "studentcode", "firstname", "lastname", "roll", "classname", "sectionname"]
    cols = _cols(headers)
    if "studentcode" in cols or "code" in cols:
        if "studentcode" not in cols:
            cols["studentcode"] = cols["code"]
        missing = [key for key in ("studentcode", "firstname", "classname", "sectionname") if key not in cols]
        if missing:
            raise CsvError("Missing student CSV columns: " + ", ".join(missing))
        rows = [[_cell(row, cols[key]) if key in cols else "" for key in expected] for row in rows]
    elif any(key in cols for key in expected):
        raise CsvError("The CSV needs a student_code column. Download the sample to see the layout.")
    else:
        rows = [headers] + rows                   # legacy CSV without headings
    added = skipped = 0
    errors, warnings = [], []
    classes = {r["class_name"].strip().lower(): r["classId"] for r in db.query("SELECT classId, class_name FROM classes WHERE isDelete='0'")}
    secs = {(r["class_id"], r["section_name"].strip().lower()): r["sectionId"] for r in db.query("SELECT sectionId, class_id, section_name FROM sections WHERE isDelete='0'")}
    codes = {r["student_code"] for r in db.query("SELECT student_code FROM students WHERE isDelete='0'")}
    plan = []
    for n, r in enumerate(rows, 2):
        if len(r) < 7 or not r[1].strip():
            if any(c.strip() for c in r):
                errors.append(f"Row {n}: needs 7 columns and a student code."); 
            continue
        c = classes.get(r[5].strip().lower())
        s = secs.get((c, r[6].strip().lower())) if c else None
        if not (c and s):
            errors.append(f"Row {n}: class / section “{r[5]} {r[6]}” was not found."); continue
        code = r[1].strip()
        if code in codes:
            skipped += 1; warnings.append(f"Row {n}: {code} already exists - skipped."); continue
        if code in {p[1] for p in plan}:
            errors.append(f"Row {n}: {code} appears twice in the file."); continue
        if r[4].strip() and not r[4].strip().isdigit():
            errors.append(f"Row {n}: roll must be a number."); continue
        if not (r[2].strip() or r[3].strip()):
            errors.append(f"Row {n}: student name is required."); continue
        if r[4].strip() and int(r[4]) < 1:
            errors.append(f"Row {n}: roll must be greater than zero."); continue
        plan.append((r[0].strip() or "N/A", code, (r[2].strip() + " " + r[3].strip()).strip(), c, s, to_int(r[4])))
    if errors:
        return _fail(errors, warnings)
    for sid_, code, name, c, s, roll in plan:
        roll = roll or rolls.next_roll(c, s)
        db.execute("INSERT INTO students (student_id, student_code, student_name, class_id, section_id, student_rollNumber) VALUES (%s,%s,%s,%s,%s,%s)", (sid_, code, name, c, s, roll), commit=False)
        added += 1
    db.commit()
    msg = f"{added} student{'s' if added != 1 else ''} added" + (f", {skipped} already existed." if skipped else ".")
    if not added and not skipped:
        msg = "The file had no student rows."
    return dict(ok=bool(added or skipped), saved=added, unchanged=skipped, errors=[], warnings=warnings[:30], message=msg)


def _import_parents(headers, rows):
    """Fill in / correct parent details by mobile number (the parent's login). Blank cells keep what is saved."""
    from .parent_links import resolve_children, LinkError, create_parent, valid_email
    cols = _cols(headers)
    mi = next((cols[k] for k in ("mobile", "mobilelogin", "phone", "phone1", "login") if k in cols), None)
    if mi is None:
        raise CsvError("The CSV needs a “mobile” column (the parent's login number). Download the sample to see the layout.")
    fields = {"fname": ("firstname", "fname"), "mname": ("middlename", "mname"), "lname": ("lastname", "lname"),
              "phone_2": ("alternatephone", "phone2", "altphone"), "secondary_name": ("secondaryname", "secondary"), "address": ("address",), "email": ("email", "emailid"), "occupation": ("occupation",)}
    idx = {f: next((cols[k] for k in ks if k in cols), None) for f, ks in fields.items()}
    student_col = next((cols[k] for k in ("studentcodes", "studentcode") if k in cols), None)
    admission_col = next((cols[k] for k in ("admissionnumbers", "admissionnumber", "admno") if k in cols), None)
    password_col = cols.get("initialpassword")
    if all(v is None for v in idx.values()) and student_col is None and admission_col is None:
        raise CsvError("None of the detail columns were found (first_name, last_name, address …). Download the sample to see the layout.")
    digits = lambda v: re.sub(r"\D", "", v or "")
    by_phone = {}
    for r in db.query("SELECT id, phone_1, fname, mname, lname, phone_2, secondary_name, address, email, occupation FROM parents WHERE deleted_at IS NULL"):
        by_phone.setdefault(digits(r["phone_1"]), r)
    students = db.query("SELECT studentId, student_code, ADMNO, parent_id FROM students WHERE isDelete='0'") if student_col is not None or admission_col is not None else []
    creates = {}
    mappings, assigned = {}, {}
    errors, warnings, plan, seen = [], [], [], set()
    unchanged = 0
    for n, r in enumerate(rows, 2):
        mob = digits(_cell(r, mi))
        if not 10 <= len(mob) <= 15:
            errors.append(f"Row {n}: mobile must contain 10–15 digits."); continue
        p = by_phone.get(mob)
        if not p:
            password = _cell(r, password_col) if password_col is not None else ""
            if len(password) < 6:
                errors.append(f"Row {n}: new parent needs initial_password with at least 6 characters."); continue
            if db.one("SELECT id FROM new_users WHERE email=%s AND deleted_at IS NULL", (mob,)):
                errors.append(f"Row {n}: this mobile is already used by another login."); continue
            p = dict(id="new:" + mob, phone_1=mob, **{key: "" for key in fields})
            creates[p["id"]] = (mob, password)
        if mob in seen:
            errors.append(f"Row {n}: {_cell(r, mi)} appears more than once."); continue
        seen.add(mob)
        row_mappings = []
        try:
            children = resolve_children(students, _cell(r, student_col) if student_col is not None else "", _cell(r, admission_col) if admission_col is not None else "")
        except LinkError as error:
            errors.append(f"Row {n}: {error}"); continue
        for student in children:
            sid = student["studentId"]
            if sid in assigned and assigned[sid] != p["id"]:
                errors.append(f"Row {n}: student {student['student_code']} is assigned to more than one parent in this file."); continue
            assigned[sid] = p["id"]
            if student["parent_id"] != p["id"]:
                row_mappings.append((sid, p["id"]))
        for sid, pid in row_mappings:
            mappings[sid] = pid
        new = {}
        for f, i in idx.items():
            v = _cell(r, i) if i is not None else ""
            if v == "":
                continue
            lim = 500 if f == "address" else 150
            if len(v) > lim:
                errors.append(f"Row {n} · {_cell(r, mi)}: {f.replace('_', ' ')} is longer than {lim} characters."); new = None; break
            if f == "email" and not valid_email(v):
                errors.append(f"Row {n}: invalid email address."); new = None; break
            if (p.get(f) or "") != v:
                new[f] = v
        if new is None:
            continue
        if p["id"] in creates and not new.get("fname"):
            errors.append(f"Row {n}: first_name is required for a new parent."); continue
        if new:
            plan.append((p["id"], new))
        elif not row_mappings:
            unchanged += 1
    if errors:
        return _fail(errors, warnings)
    new_ids = {}
    for pid, new in plan:
        if pid in creates:
            mobile, password = creates[pid]
            new_ids[pid] = create_parent(mobile, new, password)
            continue
        db.execute("UPDATE parents SET " + ",".join(f"{k}=%s" for k in new) + " WHERE id=%s", list(new.values()) + [pid], commit=False)
    for sid, pid in mappings.items():
        db.execute("UPDATE students SET parent_id=%s WHERE studentId=%s", (new_ids.get(pid, pid), sid), commit=False)
    db.commit()
    if not plan and not mappings and unchanged:
        msg = "Nothing to change - every parent in the file is already up to date."
    elif not plan and not mappings:
        msg = "The file had no values to import."
    else:
        msg = f"Saved {len(plan)} parent{'s' if len(plan) != 1 else ''}." + (f" {unchanged} {'were' if unchanged != 1 else 'was'} already up to date." if unchanged else "")
    if mappings:
        msg += f" Linked {len(mappings)} student(s) to parents."
    return dict(ok=bool(plan or mappings or unchanged), saved=len(plan) + len(mappings), unchanged=unchanged, errors=[], warnings=warnings, message=msg)
