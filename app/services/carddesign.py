"""Report-card designs created in the admin screen (Admin > Report setup > Card designs).

A design is an HTML page written with Jinja placeholders and stored in the database.  It is rendered in a sandbox
(no file / python access) with the same data the built-in designs get.  Choose it for a class in Report layouts."""
import base64
import html as _html

from jinja2.sandbox import SandboxedEnvironment

from .. import db
from . import filestore, profile

_ready = False
_env = SandboxedEnvironment(autoescape=True)

STARTER = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{{ school.name }} - {{ student.student_name }}</title>
<style>
 body{margin:0;font-family:Arial,Helvetica,sans-serif;color:#111}
 .page{width:1123px;min-height:1590px;margin:0 auto;padding:40px 50px;box-sizing:border-box;border:6px double #0b2840}
 .head{text-align:center;border-bottom:3px solid #0b2840;padding-bottom:14px}
 .head h1{margin:0;font-size:34px;color:#0b2840;text-transform:uppercase}
 .head p{margin:4px 0;font-size:15px}
 .title{margin:22px auto;text-align:center;font-size:24px;font-weight:bold;text-transform:uppercase;color:#ed1d61}
 table{border-collapse:collapse;width:100%;font-size:15px}
 th,td{border:1px solid #444;padding:7px 9px;text-align:center}
 th{background:#0b2840;color:#fff}
 td.l,th.l{text-align:left}
 .info td{text-align:left;border:1px solid #bbb}
 .info td:nth-child(odd){background:#eef2f7;font-weight:bold;width:18%}
 h3{margin:26px 0 8px;color:#0b2840}
 .sign{display:flex;justify-content:space-between;margin-top:70px;text-align:center}
 .sign img{height:70px;display:block;margin:0 auto 4px}
</style></head><body>
<div class="page">
 <div class="head"><h1>{{ school.name }}{% if school.campus %} - {{ school.campus }}{% endif %}</h1>
  <p>{{ school.address }}</p><p>Phone: {{ school.phone }} &nbsp; e-mail: {{ school.email }} &nbsp; {{ school.website }}</p></div>
 <div class="title">Progress Report Card<br><span style="font-size:18px;color:#0b2840">{{ student.class_name }} {{ student.section_name }} ({{ school.session }})</span></div>

 <table class="info">
  <tr><td>Name</td><td>{{ student.student_name }}</td><td>Roll No.</td><td>{{ student.student_rollNumber }}</td></tr>
  <tr><td>Admission No.</td><td>{{ student.ADMNO }}</td><td>Date of birth</td><td>{{ student.DOB }}</td></tr>
  <tr><td>Parent / Guardian</td><td>{{ parent.parentName }}</td><td>Class strength</td><td>{{ strength }}</td></tr>
 </table>

 <h3>Academic performance</h3>
 <table>
  <tr><th class="l" rowspan="2">Subject</th>{% for ex in exams %}<th colspan="{{ ex.examSubtype|length or 1 }}">{{ ex.exam_name }}</th>{% endfor %}</tr>
  <tr>{% for ex in exams %}{% for st in ex.examSubtype %}<th>{{ st.exam_type }}<br><small>/{{ st.fullmarsks }}</small></th>{% else %}<th>-</th>{% endfor %}{% endfor %}</tr>
  {% for sub in subjects %}<tr><td class="l">{{ sub.subject_name }}</td>
   {% for ex in sub.exams %}{% for st in ex.subtypes %}<td>{{ st.marks_obtained }}</td>{% else %}<td>-</td>{% endfor %}{% endfor %}</tr>{% endfor %}
  {% for sub in special %}<tr><td class="l">{{ sub.subject_name }}</td>
   {% for ex in sub.exams %}{% for st in ex.subtypes %}<td>{{ st.marks_obtained }}</td>{% else %}<td>-</td>{% endfor %}{% endfor %}</tr>{% endfor %}
  <tr><td class="l"><b>Average</b></td>{% for ex in exams %}<td colspan="{{ ex.examSubtype|length or 1 }}"><b>{{ ex.avarage }}</b></td>{% endfor %}</tr>
 </table>

 {% if skills %}<h3>Personal &amp; social development</h3>
 <table><tr><th class="l">Skill</th>{% for ex in exams %}<th>{{ ex.exam_name }}</th>{% endfor %}</tr>
  {% for k in skills %}<tr><td class="l">{{ k.skill_name }}</td>{% for e in k.exams %}<td>{{ e.grade }}</td>{% endfor %}</tr>{% endfor %}</table>{% endif %}

 <h3>Attendance, rank &amp; remarks</h3>
 <table><tr><th>Exam</th><th>Total sessions</th><th>Attended</th><th>Rank</th><th class="l">Teacher's comment</th></tr>
  {% for ex in exams %}{% set a = attendance[loop.index0] %}<tr><td>{{ ex.exam_name }}</td><td>{{ a.totalSession }}</td><td>{{ a.attendSession }}</td><td>{{ a.rank }}</td><td class="l">{{ a.comment }}</td></tr>{% endfor %}</table>
 {% if rank %}<p><b>Result:</b> {{ rank.award }} {{ rank.promotion }}</p>{% endif %}

 <div class="sign">
  <div>{% if teacher_sig %}<img src="{{ teacher_sig }}">{% else %}<div style="height:74px"></div>{% endif %}Class Teacher<br>{{ teacher.classTeachString }}</div>
  <div>{% if principal_sig %}<img src="{{ principal_sig }}">{% else %}<div style="height:74px"></div>{% endif %}Principal</div>
 </div>
</div></body></html>
"""


# ------------------------------------------------------------------------------------------------ ready-made templates
_MODERN = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{{ school.name }} - {{ student.student_name }}</title>
<style>
 body{margin:0;font-family:"Segoe UI",Arial,sans-serif;color:#1c2540;background:#fff}
 .page{width:1123px;min-height:1590px;margin:0 auto;box-sizing:border-box;position:relative}
 .band{background:linear-gradient(110deg,#4338ca,#7c3aed);color:#fff;padding:34px 50px 26px}
 .band h1{margin:0;font-size:34px;letter-spacing:-.5px}.band p{margin:6px 0 0;opacity:.9;font-size:14px}
 .tag{display:inline-block;background:#ffffff26;border-radius:20px;padding:6px 16px;margin-top:14px;font-size:14px;font-weight:700;letter-spacing:.4px}
 .body{padding:28px 50px 40px}
 .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
 .box{background:#f3f4ff;border-radius:12px;padding:12px 14px}.box small{display:block;color:#6b7280;font-size:11px;text-transform:uppercase;letter-spacing:.7px}.box b{font-size:15px}
 h3{margin:26px 0 10px;font-size:17px;color:#4338ca}
 table{border-collapse:separate;border-spacing:0;width:100%;font-size:14px;border:1px solid #e5e7f5;border-radius:12px;overflow:hidden}
 th{background:#eef0ff;color:#4338ca;padding:10px;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
 td{padding:9px 10px;border-top:1px solid #eceefa;text-align:center}
 td.l,th.l{text-align:left}
 tr:nth-child(even) td{background:#fafaff}
 .sign{display:flex;justify-content:space-between;margin-top:70px;text-align:center;font-size:13px;color:#4b5563}
 .sign img{height:64px;display:block;margin:0 auto 4px}
</style></head><body><div class="page">
 <div class="band"><h1>{{ school.name }}{% if school.campus %} · {{ school.campus }}{% endif %}</h1><p>{{ school.address }} · {{ school.phone }} · {{ school.email }}</p>
  <span class="tag">PROGRESS REPORT · {{ school.session }}</span></div>
 <div class="body">
  <div class="grid"><div class="box"><small>Student</small><b>{{ student.student_name }}</b></div><div class="box"><small>Class</small><b>{{ student.class_name }} {{ student.section_name }}</b></div>
   <div class="box"><small>Roll no.</small><b>{{ student.student_rollNumber }}</b></div><div class="box"><small>Admission no.</small><b>{{ student.ADMNO }}</b></div>
   <div class="box"><small>Date of birth</small><b>{{ student.DOB }}</b></div><div class="box"><small>Parent</small><b>{{ parent.parentName }}</b></div>
   <div class="box"><small>Class strength</small><b>{{ strength }}</b></div><div class="box"><small>Class teacher</small><b>{{ teacher.classTeachString }}</b></div></div>
  <h3>Academic performance</h3>
  <table><tr><th class="l" rowspan="2">Subject</th>{% for ex in exams %}<th colspan="{{ ex.examSubtype|length or 1 }}">{{ ex.exam_name }}</th>{% endfor %}</tr>
   <tr>{% for ex in exams %}{% for st in ex.examSubtype %}<th>{{ st.exam_type }}</th>{% else %}<th>-</th>{% endfor %}{% endfor %}</tr>
   {% for sub in subjects %}<tr><td class="l"><b>{{ sub.subject_name }}</b></td>{% for ex in sub.exams %}{% for st in ex.subtypes %}<td>{{ st.marks_obtained }}</td>{% else %}<td>-</td>{% endfor %}{% endfor %}</tr>{% endfor %}
   {% for sub in special %}<tr><td class="l"><b>{{ sub.subject_name }}</b></td>{% for ex in sub.exams %}{% for st in ex.subtypes %}<td>{{ st.marks_obtained }}</td>{% else %}<td>-</td>{% endfor %}{% endfor %}</tr>{% endfor %}
   <tr><td class="l"><b>Average</b></td>{% for ex in exams %}<td colspan="{{ ex.examSubtype|length or 1 }}"><b>{{ ex.avarage }}</b></td>{% endfor %}</tr></table>
  {% if skills %}<h3>Personal &amp; social development</h3><table><tr><th class="l">Skill</th>{% for ex in exams %}<th>{{ ex.exam_name }}</th>{% endfor %}</tr>
   {% for k in skills %}<tr><td class="l">{{ k.skill_name }}</td>{% for e in k.exams %}<td>{{ e.grade }}</td>{% endfor %}</tr>{% endfor %}</table>{% endif %}
  <h3>Attendance &amp; remarks</h3>
  <table><tr><th>Exam</th><th>Sessions</th><th>Attended</th><th>Rank</th><th class="l">Comment</th></tr>
   {% for ex in exams %}{% set a = attendance[loop.index0] %}<tr><td>{{ ex.exam_name }}</td><td>{{ a.totalSession }}</td><td>{{ a.attendSession }}</td><td>{{ a.rank }}</td><td class="l">{{ a.comment }}</td></tr>{% endfor %}</table>
  <div class="sign"><div>{% if teacher_sig %}<img src="{{ teacher_sig }}">{% else %}<div style="height:68px"></div>{% endif %}Class Teacher</div><div>{% if principal_sig %}<img src="{{ principal_sig }}">{% else %}<div style="height:68px"></div>{% endif %}Principal</div></div>
 </div></div></body></html>
"""

_COMPACT = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{{ student.student_name }}</title>
<style>
 body{margin:0;font-family:Arial,Helvetica,sans-serif;color:#000;font-size:13px}
 .page{width:1123px;min-height:1590px;margin:0 auto;padding:34px 44px;box-sizing:border-box}
 .top{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #000;padding-bottom:8px}
 .top h1{margin:0;font-size:24px}.top p{margin:2px 0 0;font-size:12px}
 .meta{display:grid;grid-template-columns:repeat(3,1fr);gap:4px 20px;margin:12px 0;font-size:13px}
 table{border-collapse:collapse;width:100%;margin-bottom:12px}
 th,td{border:1px solid #333;padding:4px 6px;text-align:center}th{background:#e8e8e8;font-size:12px}td.l,th.l{text-align:left}
 h4{margin:10px 0 4px;text-transform:uppercase;font-size:12px;letter-spacing:.6px}
 .sign{display:flex;justify-content:space-between;margin-top:46px;text-align:center}.sign img{height:52px;display:block;margin:0 auto 2px}
</style></head><body><div class="page">
 <div class="top"><div><h1>{{ school.name }}</h1><p>{{ school.address }} · {{ school.phone }} · {{ school.website }}</p></div><div style="text-align:right"><b>REPORT CARD</b><br>{{ school.session }}</div></div>
 <div class="meta"><div><b>Name:</b> {{ student.student_name }}</div><div><b>Class:</b> {{ student.class_name }} {{ student.section_name }}</div><div><b>Roll:</b> {{ student.student_rollNumber }}</div>
  <div><b>Adm. no:</b> {{ student.ADMNO }}</div><div><b>DOB:</b> {{ student.DOB }}</div><div><b>Parent:</b> {{ parent.parentName }}</div></div>
 <table><tr><th class="l" rowspan="2">Subject</th>{% for ex in exams %}<th colspan="{{ ex.examSubtype|length or 1 }}">{{ ex.exam_name }}</th>{% endfor %}</tr>
  <tr>{% for ex in exams %}{% for st in ex.examSubtype %}<th>{{ st.exam_type }}/{{ st.fullmarsks }}</th>{% else %}<th>-</th>{% endfor %}{% endfor %}</tr>
  {% for sub in subjects %}<tr><td class="l">{{ sub.subject_name }}</td>{% for ex in sub.exams %}{% for st in ex.subtypes %}<td>{{ st.marks_obtained }}</td>{% else %}<td>-</td>{% endfor %}{% endfor %}</tr>{% endfor %}
  {% for sub in special %}<tr><td class="l">{{ sub.subject_name }}</td>{% for ex in sub.exams %}{% for st in ex.subtypes %}<td>{{ st.marks_obtained }}</td>{% else %}<td>-</td>{% endfor %}{% endfor %}</tr>{% endfor %}
  <tr><td class="l"><b>Average</b></td>{% for ex in exams %}<td colspan="{{ ex.examSubtype|length or 1 }}"><b>{{ ex.avarage }}</b></td>{% endfor %}</tr></table>
 {% if skills %}<h4>Development skills</h4><table><tr><th class="l">Skill</th>{% for ex in exams %}<th>{{ ex.exam_name }}</th>{% endfor %}</tr>{% for k in skills %}<tr><td class="l">{{ k.skill_name }}</td>{% for e in k.exams %}<td>{{ e.grade }}</td>{% endfor %}</tr>{% endfor %}</table>{% endif %}
 <h4>Attendance, rank &amp; remarks</h4><table><tr><th>Exam</th><th>Total</th><th>Attended</th><th>Rank</th><th class="l">Comment</th></tr>
  {% for ex in exams %}{% set a = attendance[loop.index0] %}<tr><td>{{ ex.exam_name }}</td><td>{{ a.totalSession }}</td><td>{{ a.attendSession }}</td><td>{{ a.rank }}</td><td class="l">{{ a.comment }}</td></tr>{% endfor %}</table>
 <div class="sign"><div>{% if teacher_sig %}<img src="{{ teacher_sig }}">{% endif %}Class Teacher — {{ teacher.classTeachString }}</div><div>{% if principal_sig %}<img src="{{ principal_sig }}">{% endif %}Principal</div></div>
</div></body></html>
"""

PRESETS = {
    "classic": ("Classic", "Bordered page, navy headings and a clear marks table. The all-round default.", STARTER),
    "modern": ("Modern", "Colour header band, student info tiles and soft striped tables.", _MODERN),
    "compact": ("Compact", "Small, plain, black & white - fits a lot of subjects on one page.", _COMPACT),
}


VARIABLES = [
    ("school.name / campus / address / phone / email / website / board / session", "School profile (Settings)"),
    ("student.student_name, student_rollNumber, ADMNO, DOB, studentUID, class_name, section_name", "The student"),
    ("parent.parentName, parent.address, parent.phone_1", "Parent / guardian"),
    ("teacher.classTeachString", "Class teacher's name"),
    ("teacher_sig, principal_sig", "Signature images (empty when none uploaded)"),
    ("exams  (name: exam_name, avarage, examSubtype[exam_type, fullmarsks])", "Exams with their sub-types"),
    ("subjects / special  (subject_name, exams[subtypes[marks_obtained, full_marks, subtype_name]])", "Marks per subject, per exam, per sub-type"),
    ("skills  (skill_name, exams[grade])", "Development skills"),
    ("attendance[i]  (totalSession, attendSession, rank, comment)  – same order as exams", "Attendance / rank / comment"),
    ("rank  (rankAvarage, award, promotion)", "Overall result"),
    ("strength, w_rank", "Class strength, weighted rank (when the layout rule enables them)"),
]


def ensure():
    global _ready
    if _ready:
        return
    db.execute("""CREATE TABLE IF NOT EXISTS sl_card_design (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(120) NOT NULL,
        html LONGTEXT NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)""")
    _ready = True


def all_designs():
    ensure()
    return db.query("SELECT id, name, updated_at FROM sl_card_design ORDER BY name")


def get(did):
    ensure()
    return db.one("SELECT id, name, html FROM sl_card_design WHERE id=%s", (did,))


def exists(did):
    return get(did) is not None


def check(html):
    """Raises jinja2 TemplateSyntaxError text for the editor."""
    _env.from_string(html)


def save(did, name, html):
    ensure()
    if did:
        db.execute("UPDATE sl_card_design SET name=%s, html=%s WHERE id=%s", (name, html, did))
        return did
    db.execute("INSERT INTO sl_card_design (name, html) VALUES (%s,%s)", (name, html))
    return db.scalar("SELECT MAX(id) FROM sl_card_design")


def delete(did):
    db.execute("DELETE FROM sl_card_design WHERE id=%s", (did,))


def _sig(path):
    if not path:
        return ""
    try:
        f = filestore.get("signature/" + str(path).lstrip("/"))
    except Exception:
        f = None
    if not f:
        return ""
    return "data:%s;base64,%s" % (f.get("mime") or "image/png", base64.b64encode(f["data"]).decode())


def render(did, data):
    """data = the plain python dict built by services.reportcard.build()."""
    d = get(did)
    if not d:
        return "<p>This report card design no longer exists.</p>"
    student = dict((data.get("studentData") or [{}])[0])
    student["class_name"], student["section_name"] = student.get("class_name", ""), student.get("section_name", "")
    teacher = data.get("teacher") or {}
    ctx = dict(
        school=profile.get(), student=student, parent=(data.get("parentData") or [{}])[0], teacher=teacher,
        exams=data.get("examDetails") or [], subjects=data.get("normalSubject") or [], special=data.get("specialSubject") or [],
        skills=data.get("developmentSkill") or [], attendance=data.get("AttendentData") or [],
        rank=(data.get("rankAvarage") or [None])[0], strength=data.get("classStrenth", ""), w_rank=(data.get("w_rank") or [None])[0],
        teacher_sig=_sig(teacher.get("signature")), principal_sig=_sig("PRINCIPAL_SIGNATURE_new.png"), sig=_sig)
    try:
        return _env.from_string(d["html"]).render(**ctx)
    except Exception as e:                                         # a broken design must never crash the report pages
        return "<pre style='color:#b00;padding:20px'>Design error: %s</pre>" % _html.escape(str(e))
