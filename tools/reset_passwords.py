"""Give every teacher and every parent their own new password and write the login list to ~/Downloads.
usage: .venv/bin/python tools/reset_passwords.py   (admins / super admin are not touched)"""
import os, secrets, string, sys
sys.path.insert(0, ".")
from app import create_app
from app.auth import hash_password

SAFE = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def teacher_pw():
    return "".join(secrets.choice(SAFE) for _ in range(5)) + secrets.choice("@#$%") + "".join(secrets.choice(string.digits) for _ in range(3)) + "".join(secrets.choice(SAFE) for _ in range(3))


def parent_pw():
    return "".join(secrets.choice(SAFE) for _ in range(4)) + "".join(secrets.choice("23456789") for _ in range(3)) + "".join(secrets.choice(SAFE) for _ in range(2))


app = create_app()
with app.app_context():
    from app import db
    teachers = db.query("SELECT id, fname, email FROM new_users WHERE deleted_at IS NULL AND user_type='2' ORDER BY fname")
    parents = db.query("""SELECT u.id, u.email, TRIM(CONCAT_WS(' ', p.fname, NULLIF(p.mname,''), p.lname)) AS pname,
        (SELECT GROUP_CONCAT(CONCAT(st.student_name, ' (', c.class_name, ' ', s.section_name, ')') ORDER BY st.student_name SEPARATOR '; ')
           FROM students st JOIN classes c ON c.classId=st.class_id JOIN sections s ON s.sectionId=st.section_id WHERE st.parent_id=p.id AND st.isDelete='0') AS kids,
        (SELECT MIN(st.class_id*1000+st.section_id) FROM students st WHERE st.parent_id=p.id AND st.isDelete='0') AS ord
        FROM new_users u JOIN parents p ON p.user_id=u.id WHERE u.deleted_at IS NULL AND u.user_type='3' ORDER BY ord, kids""")
    pw = {}
    for r in teachers + parents:
        pw[r["id"]] = teacher_pw() if r in teachers else parent_pw()
        db.execute("UPDATE new_users SET password=%s WHERE id=%s", (hash_password(pw[r["id"]]), r["id"]), commit=False)
    db.commit()
    print("passwords reset:", len(teachers), "teachers,", len(parents), "parents")
    ct = {r["teacherId"] for r in db.query("SELECT teacherId FROM classTeacher WHERE isDelete='0'")}
    st = {r["t_id"] for r in db.query("SELECT DISTINCT t_id FROM assign_teacher WHERE isDelete='0'")}

from docx import Document
from docx.shared import Pt


def table(doc, head, rows):
    t = doc.add_table(rows=1, cols=len(head)); t.style = "Light Grid Accent 1"
    for i, h in enumerate(head): t.rows[0].cells[i].text = h
    for r in rows:
        c = t.add_row().cells
        for i, v in enumerate(r): c[i].text = str(v or "")
    for row in t.rows:
        for c in row.cells:
            for p in c.paragraphs:
                for run in p.runs: run.font.size = Pt(8)


d = Document(); d.add_heading("Schoolink - Teacher & Parent Logins", 1)
d.add_paragraph("Login URL: http://127.0.0.1:8120/login\nLogin = mobile number (or email). Every person has their own password. Each person can change it from the profile menu (top right).\nParents see their own panel; teachers see the menus of their role.")
d.add_heading(f"Teachers ({len(teachers)})", 2)
table(d, ["Name", "Login", "Password", "Role"], [[t["fname"].strip(), t["email"], pw[t["id"]], ", ".join(x for x, ok in (("subject teacher", t["id"] in st), ("class teacher", t["id"] in ct)) if ok)] for t in teachers])
d.add_heading(f"Parents ({len(parents)})", 2)
table(d, ["Parent", "Login (mobile)", "Password", "Children (class section)"], [[p["pname"] or "", p["email"], pw[p["id"]], p["kids"]] for p in parents])
out = os.path.expanduser("~/Downloads/Schoolink_Parent_Teacher_Logins.docx"); d.save(out); print("saved", out)
