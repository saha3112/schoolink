"""Resolve optional child identifiers consistently for forms and CSV imports."""
import re


class LinkError(ValueError):
    pass


def split_identifiers(value):
    return [part.strip() for part in re.split(r'[;\n]', value or '')]


def resolve_children(students, codes='', admissions=''):
    codes, admissions = split_identifiers(codes), split_identifiers(admissions)
    found = []
    for i in range(max(len(codes), len(admissions))):
        code = codes[i] if i < len(codes) else ''
        admission = admissions[i] if i < len(admissions) else ''
        if not code and not admission:
            continue
        matches = students
        for key, value, label in [('student_code', code, 'Student code'), ('ADMNO', admission, 'Admission number')]:
            if not value:
                continue
            identified = [s for s in students if str(s.get(key) or '').strip() == value]
            if len(identified) != 1:
                raise LinkError(f'{label} {value} was not found or is ambiguous.')
            matches = [s for s in matches if s['studentId'] == identified[0]['studentId']]
        if len(matches) != 1:
            raise LinkError(f'Student code {code} and admission number {admission} do not identify the same child.')
        if matches[0]['studentId'] not in {s['studentId'] for s in found}:
            found.append(matches[0])
    return found


def valid_email(value):
    return not value or (len(value) <= 150 and bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)))


def create_parent(mobile, details, password):
    """Create a parent and its login inside the caller's transaction."""
    from .. import db
    from ..auth import hash_password
    import uuid
    uid = db.execute("INSERT INTO new_users (fname, email, password, user_type, active, gcm_id, device_type, remember_token, created_at, updated_at) VALUES (%s,%s,%s,'3','1',0,'','',NOW(),NOW())",
                     (' '.join(details.get(k, '') for k in ('fname','mname','lname')).strip(), mobile, hash_password(password)), commit=False)
    return db.execute("INSERT INTO parents (user_id, code, fname, mname, lname, email, phone_1, phone_2, secondary_name, address, religion, occupation, created_at, updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'',%s,NOW(),NOW())",
                      (str(uid), 'P' + uuid.uuid4().hex[:12].upper(), details.get('fname',''), details.get('mname',''), details.get('lname',''), details.get('email',''), mobile, details.get('phone_2',''), details.get('secondary_name',''), details.get('address',''), details.get('occupation','')), commit=False)
