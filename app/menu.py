"""Role based navigation. Each item: (label, endpoint, icon, capability).
capability: 'admin' -> admin only, 'subject_teacher' / 'class_teacher' -> teachers with that role
(admins see every item), None -> everyone."""

MENU = [
    ("Dashboard", "main.dashboard", "home", None, None),
    ("Masters", None, "layers", "admin", [
        ("Classes", "admin.classes", "admin"),
        ("Sections", "admin.sections", "admin"),
        ("Subjects", "admin.subjects", "admin"),
    ]),
    ("Mapping", None, "link", "admin", [
        ("Class · Section · Subject", "admin.class_subjects", "admin"),
        ("Teacher Mapping", "admin.teacher_mapping", "admin"),
        ("Class Teacher", "admin.class_teachers", "admin"),
    ]),
    ("Exams", None, "file-text", "admin", [
        ("Exams", "admin.exams", "admin"),
        ("Assign Exam", "admin.assign_exam", "admin"),
        ("Exam Sub-type & Marks", "admin.assign_subtype", "admin"),
    ]),
    ("Report Setup", None, "settings", "admin", [
        ("Report layouts", "layouts_admin.rules", "admin"),
        ("Subject groups", "layouts_admin.groups", "admin"),
        ("Rank formulas", "layouts_admin.rank", "admin"),
        ("Card designs", "layouts_admin.designs", "admin"),
    ]),
    ("Students", None, "users", "admin", [
        ("Student List", "students.student_list", "admin"),
        ("Roll Numbers", "students.rolls_page", "admin"),
        ("Student Subjects", "students.subjects", "admin"),
        ("Move / Leave", "students.move", "admin"),
        ("CSV Upload", "students.upload", "admin"),
    ]),
    ("Parents", None, "users", "class_teacher", [
        ("All Parents", "parents.all_parents", "class_teacher"),
        ("Leave Requests", "leave.staff_list", "class_teacher"),
    ]),
    ("Signatures", "signatures_admin.manage", "image", "admin", None),
    ("Media Library", "media.library", "image", None, None),
    ("School Life", None, "calendar", None, [
        ("Announcements", "school.announcements", None),
        ("Events & Holidays", "school.events", None),
        ("Gallery", "school.gallery", None),
        ("Classwork & Homework", "school.work", "subject_teacher"),
        ("Daily Attendance", "school.daily_attendance", "class_teacher"),
        ("Timetable", "school.timetable", "any_class"),
    ]),
    ("Marks Entry", None, "edit", "subject_teacher", [
        ("Marks Entry", "marks.entry", "subject_teacher"),
        ("Special Subjects", "marks.special", "subject_teacher"),
        ("Marks List", "marks.marks_list", "subject_teacher"),
    ]),
    ("Class Teacher", None, "clipboard", "class_teacher", [
        ("Attendance", "classteacher.attendance", "class_teacher"),
        ("Comments", "classteacher.comments", "class_teacher"),
        ("Development Skills", "classteacher.development", "class_teacher"),
        ("Rank", "classteacher.rank", "class_teacher"),
        ("House Points", "classteacher.house", "class_teacher"),
        ("Average & Award", "classteacher.average", "class_teacher"),
    ]),
    ("Reports", None, "printer", "class_teacher", [
        ("Tabulation Sheet", "reports.tabulation_index", "class_teacher"),
        ("Weighted Average", "reports.weighted_index", "class_teacher"),
        ("Report Cards", "reports.report_cards", "class_teacher"),
        ("Result Release", "reports.release", "admin"),
    ]),
]

PROFILE_MENU = [
    ("My profile", "account.profile", "users", None),
    ("Change Password", "account.change_password", "key", None),
    ("Users & Passwords", "account.users", "shield", "admin"),
    ("Settings", "admin.settings", "settings", "admin"),
]

# menu entry -> feature that must apply to at least one of the user's sections
ENDPOINT_FEATURE = {
    "marks.entry": "entry", "marks.special": "special", "marks.marks_list": "entry",
    "classteacher.attendance": "attendance", "classteacher.comments": "comments", "classteacher.development": "development",
    "classteacher.rank": "rank", "classteacher.house": "house", "classteacher.average": "average",
    "reports.tabulation_index": "sheet", "reports.weighted_index": "sheet", "reports.report_cards": "card", "school.daily_attendance": "attendance", "parents.all_parents": "card", "leave.staff_list": "card", "school.work": "entry",
}


PARENT_MENU = [
    {"label": "Dashboard", "endpoint": "parentpanel.dashboard", "icon": "home", "children": None},
    {"label": "Report Card", "endpoint": "parentpanel.card", "icon": "file-text", "children": None},
    {"label": "Attendance", "endpoint": "parentpanel.attendance", "icon": "clipboard", "children": None},
    {"label": "Classwork & Homework", "endpoint": "parentpanel.work", "icon": "edit", "children": None},
    {"label": "Timetable", "endpoint": "parentpanel.timetable", "icon": "calendar", "children": None},
    {"label": "Announcements", "endpoint": "parentpanel.announcements", "icon": "bell", "children": None},
    {"label": "Events & Holidays", "endpoint": "parentpanel.events", "icon": "calendar", "children": None},
    {"label": "Gallery", "endpoint": "parentpanel.gallery", "icon": "image", "children": None},
    {"label": "Teachers", "endpoint": "parentpanel.teachers", "icon": "users", "children": None},
    {"label": "Leave Request", "endpoint": "parentpanel.leave", "icon": "layers", "children": None},
]
