"""Account Trash with hierarchy checks, restoration and reference-safe purge."""
from .. import db
from . import user_access as UA,notifications,filestore
_ready=False

class UserActionError(ValueError):pass


def ensure():
    global _ready
    if _ready:return
    db.execute('''CREATE TABLE IF NOT EXISTS sl_user_trash (
        user_id INT PRIMARY KEY,previous_active VARCHAR(11) NOT NULL,trashed_by INT NOT NULL,
        trashed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB''')
    _ready=True


def can_manage(actor,target):
    if not actor or not actor.get('is_admin') or actor['id']==target['id'] or UA.is_super(target):return False
    if UA.is_super(actor):return True
    return UA.has(actor,'manage_user_accounts') and (not target.get('is_admin') or UA.allowed_keys(target)<=UA.allowed_keys(actor))


def apply(actor,action,values):
    if not actor or not actor.get('is_admin') or not UA.has(actor,'manage_user_accounts'):
        raise PermissionError('You do not have permission to manage user accounts.')
    if action not in ('trash','restore','purge'):raise UserActionError('Choose a valid user action.')
    try:ids=sorted({int(value) for value in values})
    except (ValueError,TypeError):raise UserActionError('Select valid accounts.')
    if not ids or len(ids)>100 or any(uid<1 for uid in ids):raise UserActionError('Select between 1 and 100 accounts.')
    ensure();UA.ensure()
    if action=='purge':notifications.ensure();filestore.ensure()
    try:
        rows=db.query('SELECT id,email,fname,user_type,active,deleted_at FROM new_users WHERE id IN ('+','.join(['%s']*len(ids))+') ORDER BY id FOR UPDATE',ids)
        if len(rows)!=len(ids):raise UserActionError('A selected account no longer exists. Reload the list.')
        for user in rows:
            uid=user['id'];user['is_admin']=str(user['user_type']) in ('0','1','9')
            if str(user['user_type']) not in ('1','2','3') or not can_manage(actor,user):
                raise PermissionError('Your own account, super admins and more privileged accounts are protected.')
            trashed=user['deleted_at'] is not None
            if (action=='trash' and trashed) or (action!='trash' and not trashed):raise UserActionError('The selection contains accounts from another tab. Reload and select again.')
            if action=='trash':
                db.execute('INSERT INTO sl_user_trash (user_id,previous_active,trashed_by) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE previous_active=VALUES(previous_active),trashed_by=VALUES(trashed_by),trashed_at=CURRENT_TIMESTAMP',(uid,str(user['active']),actor['id']),commit=False)
                db.execute("UPDATE new_users SET active='0',deleted_at=NOW(),updated_at=NOW() WHERE id=%s",(uid,),commit=False)
                UA.revoke(uid,commit=False)
            elif action=='restore':
                if db.one('SELECT id FROM parents WHERE user_id=%s AND deleted_at IS NOT NULL',(str(uid),)):
                    raise UserActionError('Restore this user’s parent record from All Parents → Trash first.')
                if db.one('SELECT id FROM new_users WHERE email=%s AND id<>%s AND deleted_at IS NULL FOR UPDATE',(user['email'],uid)):
                    raise UserActionError('Another active account uses this login. Resolve the duplicate before restoring.')
                saved=db.one('SELECT previous_active FROM sl_user_trash WHERE user_id=%s',(uid,))
                db.execute('UPDATE new_users SET deleted_at=NULL,active=%s,updated_at=NOW() WHERE id=%s',(saved['previous_active'] if saved else user['active'],uid),commit=False)
                db.execute('DELETE FROM sl_user_trash WHERE user_id=%s',(uid,),commit=False)
            else:
                if db.one('SELECT id FROM parents WHERE user_id=%s',(str(uid),)):
                    raise UserActionError('This login has a parent record. Delete the parent permanently from All Parents → Trash to remove both safely.')
                if db.one('SELECT id FROM teachers WHERE user_id=%s',(str(uid),)) or db.one('SELECT 1 FROM assign_teacher WHERE t_id=%s LIMIT 1',(uid,)) or db.one('SELECT 1 FROM classTeacher WHERE teacherId=%s LIMIT 1',(uid,)):
                    raise UserActionError('This account has a teacher profile or teaching assignments. Keep it in Trash to preserve school records.')
                db.execute('DELETE FROM sl_notification WHERE user_id=%s',(uid,),commit=False)
                db.execute('DELETE FROM app_files WHERE path=%s',(f'profile/{uid}.png',),commit=False)
                db.execute('DELETE FROM sl_user_access WHERE user_id=%s',(uid,),commit=False)
                db.execute('DELETE FROM sl_user_trash WHERE user_id=%s',(uid,),commit=False)
                db.execute('DELETE FROM new_users WHERE id=%s AND deleted_at IS NOT NULL',(uid,),commit=False)
            UA.audit(actor['id'],'user_'+action,uid,commit=False)
        db.commit()
    except Exception:
        db.rollback();raise
    return len(ids)
