"""Roll number management.

Rules
-----
* Roll numbers of a section are always 1..N without gaps, ordered alphabetically (this matches the existing data).
* When a student leaves a section (school leave / moves to another class or section) the remaining
  students keep their relative order and the gap is closed automatically.
* A student joining a section gets a roll number by name (default) or at the end of the list.
"""
from .. import db
from . import enrollment

# tables that carry class/section next to a student id and are shown on that student's report card
_FOLLOW_TABLES = ("studentComment", "student_house", "rankAvarageOther", "weighted_rank")


def _ordered(class_id, section_id, mode="keep"):
    """Active students of a section. mode: keep (current roll, then name) | name (alphabetical)."""
    order = "student_name, studentId" if mode == "name" else "student_rollNumber, student_name, studentId"
    return db.query(f"SELECT studentId, student_name, student_rollNumber FROM students "
                    f"WHERE class_id=%s AND section_id=%s AND isDelete='0' ORDER BY {order}", (class_id, section_id))


def renumber(class_id, section_id, mode="keep", commit=False):
    """Rewrite roll numbers 1..N. Returns the number of students whose roll changed."""
    changed = 0
    for i, s in enumerate(_ordered(class_id, section_id, mode), start=1):
        if s["student_rollNumber"] != i:
            db.execute("UPDATE students SET student_rollNumber=%s WHERE studentId=%s", (i, s["studentId"]), commit=False)
            changed += 1
    if commit:
        db.commit()
    return changed


def next_roll(class_id, section_id):
    return (db.scalar("SELECT COALESCE(MAX(student_rollNumber),0) FROM students "
                      "WHERE class_id=%s AND section_id=%s AND isDelete='0'", (class_id, section_id)) or 0) + 1


def _log(student, action, from_c, from_s, from_r, to_c, to_s, to_r, note, user_id):
    db.execute("""CREATE TABLE IF NOT EXISTS student_transfer_log (
        id INT AUTO_INCREMENT PRIMARY KEY, studentId INT NOT NULL, action VARCHAR(20) NOT NULL,
        from_class INT, from_section INT, from_roll INT, to_class INT, to_section INT, to_roll INT,
        note VARCHAR(255), done_by INT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""", commit=False)
    db.execute("INSERT INTO student_transfer_log (studentId, action, from_class, from_section, from_roll, to_class, to_section, to_roll, note, done_by) "
               "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (student, action, from_c, from_s, from_r, to_c, to_s, to_r, note, user_id), commit=False)


def move_student(student_id, to_class, to_section, place="name", note="", user_id=None):
    """Move a student to another class/section (e.g. subject/stream change).

    1. source section: roll gap is closed, everybody else keeps their order.
    2. destination section: student gets a roll by name (place='name', whole section renumbered) or at the end.
    Everything runs in one transaction."""
    st = db.one("SELECT * FROM students WHERE studentId=%s AND isDelete='0'", (student_id,))
    if not st:
        raise ValueError("Student not found.")
    src_c, src_s, old_roll = st["class_id"], st["section_id"], st["student_rollNumber"]
    if (src_c, src_s) == (to_class, to_section):
        raise ValueError("Student is already in that class and section.")
    if not db.one("SELECT 1 FROM sections WHERE sectionId=%s AND class_id=%s AND isDelete='0'", (to_section, to_class)):
        raise ValueError("Selected section does not belong to the class.")
    try:
        # park the student in the destination first, with a temporary roll, then renumber both sides
        db.execute("UPDATE students SET class_id=%s, section_id=%s, student_rollNumber=%s WHERE studentId=%s",
                   (to_class, to_section, next_roll(to_class, to_section), student_id), commit=False)
        renumber(src_c, src_s, "keep")                       # close the gap behind the student
        if place == "name":
            renumber(to_class, to_section, "name")
        new_roll = db.scalar("SELECT student_rollNumber FROM students WHERE studentId=%s", (student_id,))
        for t in _FOLLOW_TABLES:                              # keep attendance/comments/house points on the report card
            db.execute(f"UPDATE {t} SET classId=%s, sectionId=%s WHERE studentId=%s AND classId=%s AND sectionId=%s",
                       (to_class, to_section, student_id, src_c, src_s), commit=False)
        enrollment.forget_student(student_id)                 # subject set of the new section differs
        _log(student_id, "move", src_c, src_s, old_roll, to_class, to_section, new_roll, note, user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"from": (src_c, src_s, old_roll), "to": (to_class, to_section, new_roll)}


def leave_student(student_id, note="", user_id=None):
    """School leave: student is deactivated, the rest of the section is renumbered."""
    st = db.one("SELECT * FROM students WHERE studentId=%s AND isDelete='0'", (student_id,))
    if not st:
        raise ValueError("Student not found.")
    try:
        db.execute("UPDATE students SET isDelete='1' WHERE studentId=%s", (student_id,), commit=False)
        renumber(st["class_id"], st["section_id"], "keep")
        _log(student_id, "leave", st["class_id"], st["section_id"], st["student_rollNumber"], None, None, None, note, user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return st


def add_student(values, place="name"):
    """Insert a new student into a section and give the roll number."""
    cid, sid = values["class_id"], values["section_id"]
    values = dict(values, student_rollNumber=next_roll(cid, sid))
    cols = ",".join(values)
    new_id = db.execute(f"INSERT INTO students ({cols}) VALUES ({','.join(['%s'] * len(values))})", list(values.values()), commit=False)
    if place == "name":
        renumber(cid, sid, "name")
    db.commit()
    return new_id
