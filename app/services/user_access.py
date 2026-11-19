"""Per-user admin page permissions, reset delegation and session revocation."""
import json
from .. import db
from ..menu import MENU

_ready = False
EXTRA = [
    ('Administration', 'account.users', 'Users & password resets'),
    ('Administration', 'admin.settings', 'School settings'),
    ('Administration', 'security.admin_accounts', 'Create admin accounts'),
    ('Administration', 'security.permissions', 'Manage user permissions'),
    ('Administration', 'security.smtp', 'Mail / SMTP settings'),
    ('Administration', 'manage_user_accounts', 'Trash / restore / remove user accounts'),
    ('Administration', 'reset_passwords', 'Reset other users’ passwords'),
]

def catalog():
    rows = []
    for label, endpoint, _icon, _cap, children in MENU:
        if endpoint and endpoint != 'main.dashboard':
            rows.append((label, endpoint, label))
        for child in children or []:
            rows.append((label, child[1], child[0]))
    return rows + EXTRA


def keys():
    return {row[1] for row in catalog()}


def ensure():
    global _ready
    if _ready:
        return
    db.execute('''CREATE TABLE IF NOT EXISTS sl_user_access (
        user_id INT PRIMARY KEY, permissions LONGTEXT NULL, reset_passwords TINYINT NOT NULL DEFAULT 0,
        session_version INT NOT NULL DEFAULT 0, updated_by INT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB''')
    db.execute('''CREATE TABLE IF NOT EXISTS sl_security_audit (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, actor_id INT NOT NULL, target_id INT NULL,
        action VARCHAR(80) NOT NULL, detail VARCHAR(500) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, KEY (target_id, id)) ENGINE=InnoDB''')
    _ready = True


def record(uid):
    ensure()
    return db.one('SELECT * FROM sl_user_access WHERE user_id=%s', (uid,))


def is_super(user):
    return bool(user and str(user.get('user_type')) in ('0', '9'))


def allowed_keys(user):
    if not user:
        return set()
    if is_super(user):
        return keys()
    row = user.get('_access') if '_access' in user else record(user['id'])
    if str(user.get('user_type')) != '1':
        return {'reset_passwords', 'account.users'} if row and row['reset_passwords'] else set()
    if not row or row['permissions'] is None:
        return keys()  # existing administrators retain their access
    try:
        return set(json.loads(row['permissions'])) & keys()
    except (ValueError, TypeError):
        return set()  # invalid settings never grant access


def has(user, key):
    return key in allowed_keys(user)


def restricted(user):
    return bool(user and user.get('is_admin') and allowed_keys(user) != keys())


def can_manage(actor, target):
    if not actor or not target or actor['id'] == target['id']:
        return False
    if is_super(target):
        return False
    if is_super(actor):
        return True
    return (actor.get('is_admin') and has(actor, 'security.permissions')
            and (str(target['user_type']) != '1' or allowed_keys(target) <= allowed_keys(actor)))


def can_reset(actor, target):
    if not actor or not target or actor['id'] == target['id'] or not has(actor, 'reset_passwords'):
        return False
    if is_super(actor):
        return True
    if is_super(target):
        return False
    if str(target['user_type']) == '1':
        return bool(actor.get('is_admin') and allowed_keys(target) <= allowed_keys(actor))
    return str(target['user_type']) in ('2', '3')


def save(uid, permissions, reset, actor_id, commit=True):
    ensure()
    db.execute('''INSERT INTO sl_user_access (user_id,permissions,reset_passwords,updated_by)
        VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE permissions=VALUES(permissions),
        reset_passwords=VALUES(reset_passwords),updated_by=VALUES(updated_by)''',
        (uid, json.dumps(sorted(set(permissions) & keys())), int(bool(reset)), actor_id), commit=commit)


def audit(actor_id, action, target_id=None, detail='', commit=True):
    ensure()
    db.execute('INSERT INTO sl_security_audit (actor_id,target_id,action,detail) VALUES (%s,%s,%s,%s)',
               (actor_id, target_id, action, detail[:500]), commit=commit)


def revoke(uid, commit=True):
    ensure()
    db.execute('''INSERT INTO sl_user_access (user_id,session_version) VALUES (%s,1)
        ON DUPLICATE KEY UPDATE session_version=session_version+1''', (uid,), commit=commit)


ALIASES = {
 'signatures_admin.history_file':'signatures_admin.manage',
 'students.edit':'students.student_list', 'students.api_students':'students.student_list',
 'admin.teacher_mapping_edit':'admin.teacher_mapping',
 'parents.create':'parents.all_parents','parents.detail':'parents.all_parents','parents.export':'parents.all_parents',
 'school.gallery_add':'school.gallery', 'school.attachment_delete':'school.gallery',
 'reports.tabulation':'reports.tabulation_index','reports.weighted':'reports.weighted_index',
 'reports.section_students':'reports.report_cards','reports.section_cards':'reports.report_cards','reports.card':'reports.report_cards',
 'reports.bulk_start':'reports.report_cards','reports.bulk_status':'reports.report_cards','reports.bulk_cancel':'reports.report_cards','reports.bulk_download':'reports.report_cards',
 'layouts_admin.design_preview':'layouts_admin.designs','layouts_admin.builtin_preview':'layouts_admin.designs',
 'layouts_admin.designs_targets':'layouts_admin.designs','layouts_admin.builtin_apply':'layouts_admin.designs',
 'layouts_admin.students_json':'layouts_admin.designs',
 'account.reset_password':'reset_passwords', 'account.reset_delegation':'security.permissions',
}
CSV_KEYS = {'marks':'marks.entry','special':'marks.special','attendance':'classteacher.attendance',
 'comments':'classteacher.comments','development':'classteacher.development','rank':'classteacher.rank',
 'house':'classteacher.house','average':'classteacher.average','students':'students.upload','parents':'parents.all_parents'}
COMMON = {'static','main.index','main.dashboard','auth.login','auth.logout','account.change_password',
          'account.profile','account.profile_image','search.api'}


def endpoint_allowed(user, endpoint, values=None):
    if not user or not user.get('is_admin') or is_super(user):
        return True
    permissions = allowed_keys(user)
    if endpoint == 'account.users':
        return bool(permissions & {'account.users','reset_passwords'})
    if endpoint in COMMON or endpoint.startswith(('notify.', 'live.')):
        return True
    if endpoint.startswith('csvio.'):
        return CSV_KEYS.get((values or {}).get('kind')) in permissions
    if endpoint.startswith('media.'):
        return 'media.library' in permissions
    if endpoint == 'admin.api_sections' or endpoint == 'school.api_sections':
        return bool(permissions - {'reset_passwords','account.users','security.permissions','security.smtp','security.admin_accounts'})
    if endpoint in ('admin.api_subjects','admin.api_section_subjects'):
        return bool(permissions & {'admin.class_subjects','admin.assign_subtype','admin.teacher_mapping','students.subjects','marks.entry','marks.special'})
    if endpoint in ('school.file','school.attachment_delete'):
        if endpoint == 'school.file':
            attachment = db.one('SELECT owner_type FROM sl_attachment WHERE path=%s', ('uploads/' + (values or {}).get('p',''),))
        else:
            attachment = db.one('SELECT owner_type FROM sl_attachment WHERE id=%s', ((values or {}).get('fid'),))
        if not attachment:
            return False
        key = {'album':'school.gallery','announcement':'school.announcements','work':'school.work'}.get(attachment['owner_type'])
        return key in permissions
    if endpoint.startswith('signatures.'):
        return 'signatures_admin.manage' in permissions
    return ALIASES.get(endpoint, endpoint) in permissions
