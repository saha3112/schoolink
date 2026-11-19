"""Automatic rank calculation (port of the old Exammark::autoRankPage rules)."""
from .. import db
from . import layouts

SCI = ("PHYSICS", "CHEMISTRY", "BIOLOGY")
ENG = ("ENGLISH LANGUAGE", "ENGLISH LITERATURE")
SOC = ("HISTORY & CIVICS", "GEOGRAPHY")
COMP9 = ("COMP.APPL/TECH.DRG.APPL./PHYSICAL EDU./ECO.APPL.", "COMPUTER APPLICATIONS", "TECHNICAL DRAWING APPLICATION")
ROBO = ("ROBOTICS", "ROBOTICS / AI", "ROBOTICS AND AI")


def _round(x):
    """PHP round(): half away from zero."""
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def _apply_formula(formula, sm):
    """sm = {SUBJECT NAME (upper): marks}. Components first (in order), then the leftover subjects."""
    comps = [({n.strip().upper() for n in c["subjects"]}, float(c.get("divisor") or 1), bool(c.get("round"))) for c in formula["components"]]
    sums = [0] * len(comps)
    rest_mode, rest = formula.get("rest", "ignore"), 0
    for n, m in sm.items():
        for i, (names, _d, _r) in enumerate(comps):
            if n in names:
                sums[i] += m
                break
        else:                                   # not part of any component
            if rest_mode == "sum":
                rest += m
            elif rest_mode == "sum_rounded":
                rest += _round(m)
    total = 0
    for (names, d, rnd), v in zip(comps, sums):
        v = v / d if d != 1 else v
        total = total + (_round(v) if rnd else v)
    return total + rest


def student_totals(cid, sid, exam_id):
    rows = db.query("SELECT em.studentId, s.subject_name, MAX(em.marks) AS marks FROM exam_marks em "
                    "JOIN subjects s ON em.subjectId=s.subjectId "
                    "WHERE em.classId=%s AND em.sectionId=%s AND em.examId=%s AND em.isDelete='0' "
                    "GROUP BY em.studentId, em.subjectId, s.subject_name, em.exam_subtype_id", (cid, sid, exam_id))
    per = {}
    for r in rows:
        v = str(r["marks"]).strip()
        try:
            f = float(v)
        except ValueError:
            continue
        d = per.setdefault(r["studentId"], {})
        n = r["subject_name"].strip().upper()
        d[n] = d.get(n, 0) + f
    formula = layouts.get_formula(layouts.rank_mode(cid, sid))
    totals = {}
    for stu in db.query("SELECT studentId FROM students WHERE class_id=%s AND section_id=%s AND isDelete='0'", (cid, sid)):
        sm = per.get(stu["studentId"], {})
        total = _apply_formula(formula, sm)
        totals[stu["studentId"]] = total
    return totals


def auto_ranks(cid, sid, exam_id):
    """{studentId: (rank, total)} with competition ranking (1, 1, 3)."""
    totals = student_totals(cid, sid, exam_id)
    order = sorted(totals.items(), key=lambda kv: -kv[1])
    out, prev, rank = {}, None, 0
    for i, (stu, t) in enumerate(order, 1):
        if t != prev:
            rank = i
        out[stu] = (rank, t)
        prev = t
    return out
