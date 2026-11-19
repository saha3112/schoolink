<p align="center">
  <img src="docs/logo.svg" alt="Schoolink" width="480">
</p>

<p align="center">
  A modern, role-based school management and report card platform built with Flask.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/MySQL-MariaDB-4479A1?logo=mysql&logoColor=white" alt="MySQL">
  <img src="https://img.shields.io/badge/HTML5-E34F26?logo=html5&logoColor=white" alt="HTML5">
  <img src="https://img.shields.io/badge/CSS3-1572B6?logo=css3&logoColor=white" alt="CSS3">
  <img src="https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=black" alt="JavaScript">
  <img src="https://img.shields.io/badge/Jinja2-B41717?logo=jinja&logoColor=white" alt="Jinja2">
</p>

---

## About

**Schoolink** is a complete rewrite of the legacy CodeIgniter report card panel. It keeps the same database
structure, the same calculations and the same printed report designs, but comes with a new responsive admin UI,
role based menus, live updates and a parent portal.

## Features

- **Role based panels** - admin, subject teacher, class teacher and parent each see only what they need
- **Marks management** - marks entry, special subjects, marks list, rank, average and awards
- **Class teacher tools** - attendance, comments, development skills, house points
- **Report cards and sheets** - tabulation and weighted average sheets (23 x 35 in), report cards (A4), PDF export
- **Student management** - admission, subject / stream changes, automatic roll number re-ordering, transfer log
- **CSV import / export** - bulk upload of students, parents, marks and attendance
- **Parent portal** - child profile, attendance, timetable, events, gallery, announcements, leave requests
- **Media library** - upload popup, gallery and file store
- **Live sync** - real-time updates across open sessions
- **Customisable layouts** - database driven report card layouts, groups and rules
- **Light / dark theme** and a fully responsive interface

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3 |
| Web framework | Flask 3 (blueprints, Jinja2 templates) |
| Database | MySQL / MariaDB via PyMySQL |
| Auth and security | bcrypt password hashing, signed sessions, role based access control |
| Images | Pillow |
| Documents | python-docx |
| PDF export | Headless Google Chrome |
| Frontend | HTML5, CSS3 (custom design system), vanilla JavaScript |
| Fonts | DM Sans, Plus Jakarta Sans (Google Fonts) |
| Tooling | Custom PHP to Python template transpiler (`tools/php2py.py`) |

## Getting started

### Requirements

- Python 3.10 or newer
- MySQL or MariaDB
- Google Chrome (only for PDF export)

### Installation

```bash
git clone https://github.com/saha3112/schoolink.git
cd schoolink

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env      # then fill in your values
.venv/bin/python run.py   # http://127.0.0.1:8120
```

### Configuration

All settings come from environment variables or a local `.env` file (see `.env.example`).

| Variable | Description |
|---|---|
| `SECRET_KEY` | Flask session secret |
| `DB_HOST`, `DB_PORT` | Database server |
| `DB_USER`, `DB_PASSWORD`, `DB_NAME` | Database credentials |
| `SCHOOL_NAME`, `SCHOOL_TAGLINE` | Fallback branding (editable later in Settings) |
| `CHROME_BIN` | Path to Google Chrome for PDF export |
| `HOST`, `PORT`, `DEBUG` | Server options |

## Roles and menus

| Role (`new_users.user_type`) | Panel |
|---|---|
| `1` Admin / `0`, `9` Super admin | Everything: masters, mappings, exams, students, reports, users, settings |
| `2` Teacher | Only the menus the teacher's role allows. **Subject teacher** (has rows in `assign_teacher`): Marks Entry, Special Subjects, Marks List. **Class teacher** (has rows in `classTeacher`): Attendance, Comments, Development Skills, Rank, House Points, Average and Award, Tabulation / Weighted / Report Cards of their section |
| Parent | Parent portal |
| Anyone else | Profile menu, Change Password only |

Every signed-in user can change their own password from the profile menu. Admins can reset any user's password.

## What changed from the old app

- **Teacher mapping** - one row per teacher; manage exact class / section / subject rows and add or remove them in bulk.
- **Merged pages** - duplicated pages of the old app (bulk entry, master entry, list variants, three rank pages) are now one page per task.
- **Roll numbers** - always 1...N per section. When a student leaves or moves class / section, gaps close automatically and every change is logged in `student_transfer_log`.
- **Print sizes** - tabulation and weighted sheets export on 23 x 35 inch landscape, report cards on A4.

## Report card engine

`app/services/reportdata.py` and `app/services/reportcard.py` are line by line ports of the old PHP calculations.
The original PHP report templates are converted with `tools/php2py.py`, so printed designs keep the same markup.
To regenerate after changing the originals:

```bash
tools/build_views.sh /path/to/old/application/views
```

## Project structure

```
app/
  blueprints/   routes (marks, students, reports, parents, media, live, ...)
  services/     business logic (report data, ranking, CSV, PDF, rolls, ...)
  templates/    Jinja2 templates
  static/       CSS, JavaScript, images
  views_py/     generated report templates (do not edit by hand)
docs/           logo and documentation assets
tests/          automated tests
tools/          php2py transpiler and helper scripts
config.py       configuration
run.py          application entry point
```

## Tests

```bash
.venv/bin/python -m pytest tests
```
