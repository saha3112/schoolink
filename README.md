# Schoolink Report Card — Python (Flask) application

A fresh Python rewrite of the old CodeIgniter `schoollink-report-card` panel. Same database structure, same
calculations, same report designs — new, responsive admin UI and role based menus.

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# database (a private copy of schoolink-reportCard-Thomas is used by default: schoolink_py)
export DB_NAME=schoolink_py DB_USER=root DB_PASSWORD=...      # see config.py
.venv/bin/python run.py          # http://127.0.0.1:8120
```

PDF export needs Google Chrome (`CHROME_BIN` in `config.py`).

## Roles & menus

| Role (`new_users.user_type`) | Panel |
|---|---|
| `1` Admin / `0`,`9` Super admin | everything (masters, mappings, exams, students, reports, users, settings) |
| `2` Teacher | only the menus the teacher's *role* allows: **subject teacher** (has rows in `assign_teacher`) → Marks Entry, Special Subjects, Marks List; **class teacher** (has rows in `classTeacher`) → Attendance, Comments, Development Skills, Rank, House Points, Average & Award, Tabulation / Weighted / Report Cards of *their* section |
| anyone else | profile menu → **Change Password** only |

Every signed-in user can change their own password from the profile circle (top right). No old password is asked.
Admins can also reset any user's password (*Users & Passwords*).

## What changed compared with the old app

* **Teacher Mapping** — one row per teacher; subjects, classes and sections are comma separated. *Manage* opens the exact
  class/section/subject rows and lets you add (multi class-section × subject) or remove them.
* Duplicated pages of the old app (bulk entry / master entry / list variants, 3 rank pages, …) are merged into one page per task.
* **Student roll numbers** — roll numbers of a section are always 1…N (alphabetical). When a student *leaves school* or *moves to another class / section*
  (subject / stream change) the gap is closed automatically in the old section and the student gets a roll in the new
  section (alphabetical position or end of list). Every change is logged in `student_transfer_log`
  (the only table added — created on first use). Attendance / comments / house points of the student follow to the new section.
* **Tabulation + weighted average sheets** export on **23 × 35 inch** (landscape); **report cards** on **A4**.
  Use *Download PDF* or the browser print button.

## Report card / tabulation engine

`app/services/reportdata.py` and `app/services/reportcard.py` are line by line ports of the old PHP calculations.
The original PHP report templates were converted with `tools/php2py.py` (a small PHP→Python transpiler, runtime in
`app/phpr.py`) so the printed designs are byte-for-byte the same markup. Re-generate after changing the originals:

```bash
tools/build_views.sh /path/to/old/application/views
```

## Layout

```
app/            flask app (blueprints, services, templates, static)
app/views_py/   generated report templates (do not edit by hand)
tools/          php2py transpiler + helpers
subject_groups.json   hard coded subject groups per class/section, exported from the old MarksModel
```
