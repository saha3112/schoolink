"""Transactional parent Trash, restore and permanent deletion; students are kept."""
from .. import db
from . import user_access as UA

_ready=False


class ParentActionError(ValueError):
    pass


def ensure():
    global _ready
    if _ready:return
    db.execute('''CREATE TABLE IF NOT EXISTS sl_parent_trash (
        parent_id INT PRIMARY KEY,user_id INT NOT NULL,previous_active VARCHAR(11) NOT NULL,
        previous_user_deleted DATETIME NULL,trashed_by INT NOT NULL,
        trashed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB''')
    _ready=True


def apply(actor,action,values):
    if not actor or not actor.get('is_admin'):
        raise PermissionError('Only administrators can manage parent Trash.')
    if action not in ('trash','restore','purge'):
        raise ParentActionError('Choose a valid parent action.')
    try:
        ids=sorted({int(value) for value in values})
    except (ValueError,TypeError):
        raise ParentActionError('Choose valid parent records.')
    if not ids or len(ids)>100 or any(pid<1 for pid in ids):
        raise ParentActionError('Select between 1 and 100 parents.')
    ensure();UA.ensure()
    if action=='purge':
        from . import notifications, filestore
        notifications.ensure();filestore.ensure()
    try:
        rows=db.query('SELECT * FROM parents WHERE id IN ('+','.join(['%s']*len(ids))+') ORDER BY id FOR UPDATE',ids)
        if len(rows)!=len(ids):raise ParentActionError('A selected parent no longer exists. Reload the list.')
        for parent in rows:
            trashed=parent['deleted_at'] is not None
            if (action=='trash' and trashed) or (action!='trash' and not trashed):
                raise ParentActionError('The selection contains records from a different tab. Reload and select again.')
            try:uid=int(parent['user_id'])
            except (TypeError,ValueError):raise ParentActionError('A selected parent has an invalid login mapping. Correct that mapping first.')
            user=db.one('SELECT id,email,user_type,active,deleted_at FROM new_users WHERE id=%s FOR UPDATE',(uid,))
            if user and str(user['user_type'])!='3':
                raise ParentActionError('A selected parent is linked to a non-parent login. Correct that mapping first.')
            shared=db.scalar('SELECT COUNT(*) FROM parents WHERE user_id=%s AND id<>%s',(str(uid),parent['id']))
            if shared:raise ParentActionError('A selected parent shares a login with another parent record. Correct that mapping first.')
            if action=='trash':
                db.execute('''INSERT INTO sl_parent_trash (parent_id,user_id,previous_active,previous_user_deleted,trashed_by)
                    VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE user_id=VALUES(user_id),previous_active=VALUES(previous_active),
                    previous_user_deleted=VALUES(previous_user_deleted),trashed_by=VALUES(trashed_by),trashed_at=CURRENT_TIMESTAMP''',
                    (parent['id'],uid,str(user['active']) if user else '0',user['deleted_at'] if user else None,actor['id']),commit=False)
                db.execute('UPDATE parents SET deleted_at=NOW(),updated_at=NOW() WHERE id=%s',(parent['id'],),commit=False)
                if user:
                    db.execute("UPDATE new_users SET deleted_at=NOW(),active='0',updated_at=NOW() WHERE id=%s",(uid,),commit=False)
                    UA.revoke(uid,commit=False)
            elif action=='restore':
                saved=db.one('SELECT * FROM sl_parent_trash WHERE parent_id=%s FOR UPDATE',(parent['id'],))
                if not user or not saved:
                    raise ParentActionError('This parent has no restorable login snapshot. Contact the administrator to repair it.')
                login_conflict=db.one('SELECT id FROM new_users WHERE email=%s AND id<>%s AND deleted_at IS NULL FOR UPDATE',(user['email'],uid))
                parent_conflict=db.one("SELECT id FROM parents WHERE REGEXP_REPLACE(phone_1,'[^0-9]','')=REGEXP_REPLACE(%s,'[^0-9]','') AND id<>%s AND deleted_at IS NULL FOR UPDATE",(parent['phone_1'],parent['id']))
                if login_conflict or parent_conflict:
                    raise ParentActionError('Restore blocked: another active account uses a selected parent’s mobile/login. Resolve the duplicate first.')
                db.execute('UPDATE parents SET deleted_at=NULL,updated_at=NOW() WHERE id=%s',(parent['id'],),commit=False)
                db.execute('UPDATE new_users SET deleted_at=%s,active=%s,updated_at=NOW() WHERE id=%s',
                           (saved['previous_user_deleted'],saved['previous_active'],uid),commit=False)
                db.execute('DELETE FROM sl_parent_trash WHERE parent_id=%s',(parent['id'],),commit=False)
            else:
                if user and user['deleted_at'] is None:
                    raise ParentActionError('The selected parent login is still active. Move the parent to Trash first.')
                # A permanent deletion removes the guardian link, never the student.
                db.execute('UPDATE students SET parent_id=NULL WHERE parent_id=%s',(parent['id'],),commit=False)
                db.execute('DELETE FROM parents WHERE id=%s AND deleted_at IS NOT NULL',(parent['id'],),commit=False)
                db.execute('DELETE FROM sl_parent_trash WHERE parent_id=%s',(parent['id'],),commit=False)
                if user:
                    db.execute('DELETE FROM sl_notification WHERE user_id=%s',(uid,),commit=False)
                    db.execute('DELETE FROM app_files WHERE path=%s',(f'profile/{uid}.png',),commit=False)
                    db.execute('DELETE FROM sl_user_access WHERE user_id=%s',(uid,),commit=False)
                    db.execute("DELETE FROM new_users WHERE id=%s AND user_type='3' AND deleted_at IS NOT NULL",(uid,),commit=False)
            UA.audit(actor['id'],'parent_'+action,uid,detail=f'Parent record {parent["id"]}; student records preserved',commit=False)
        db.commit()
    except Exception:
        db.rollback();raise
    return len(ids)
