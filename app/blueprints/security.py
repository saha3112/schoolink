"""Administrator account creation, page permissions and SMTP setup."""
from collections import defaultdict
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from .. import db
from ..auth import admin_required, current_user, hash_password
from ..services import user_access as UA, mailer

bp = Blueprint('security', __name__, url_prefix='/admin/security')


def _target(uid):
    row = db.one("SELECT id,fname,email,user_type,active FROM new_users WHERE id=%s AND deleted_at IS NULL", (uid,))
    if not row:
        abort(404)
    if str(row['user_type']) == '3':
        from ..services import parent_identity as PI
        row['fname'] = PI.for_users([uid]).get(uid) or 'Name not recorded'
    row['is_admin'] = str(row['user_type']) in ('0','1','9')
    return row


def _groups(actor):
    groups = defaultdict(list)
    for group, key, label in UA.catalog():
        if UA.has(actor, key):
            groups[group].append({'key':key, 'label':label})
    return groups


@bp.route('/admins', methods=['GET','POST'])
@admin_required
def admin_accounts():
    actor = current_user()
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        login = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        submitted = set(request.form.getlist('permissions'))
        if not name or len(name)>150 or not login or len(login)>150 or any(c.isspace() for c in login):
            flash('Enter a name and a valid email or mobile login.', 'error')
        elif '@' in login and not mailer.valid_email(login):
            flash('Enter a valid email address.', 'error')
        elif '@' not in login and (not login.isdigit() or not 10<=len(login)<=15):
            flash('Use an email address or a mobile number with 10–15 digits.', 'error')
        elif len(password)<8 or len(password.encode())>72:
            flash('Use a password of at least 8 characters and at most 72 bytes.', 'error')
        elif password != request.form.get('confirm_password'):
            flash('The passwords do not match.', 'error')
        elif not submitted <= UA.allowed_keys(actor):
            abort(403)
        elif db.one('SELECT id FROM new_users WHERE email=%s', (login,)):
            flash('That login is already in use.', 'error')
        else:
            UA.ensure()
            try:
                uid = db.execute("""INSERT INTO new_users
                    (fname,email,password,user_type,active,gcm_id,device_type,remember_token,created_at,updated_at)
                    VALUES (%s,%s,%s,'1','1',0,'','',NOW(),NOW())""", (name,login,hash_password(password)), commit=False)
                UA.save(uid,submitted,'reset_passwords' in submitted,actor['id'],commit=False)
                UA.audit(actor['id'],'admin_created',uid,commit=False)
                db.commit()
                flash('Admin account created with the selected page access.', 'success')
                return redirect(url_for('security.permissions', user=uid)) if UA.has(actor,'security.permissions') else redirect(url_for('security.admin_accounts'))
            except Exception:
                db.rollback()
                flash('The account could not be created. Check whether the login is already in use.', 'error')
    rows = db.query("SELECT id,fname,email,user_type,active FROM new_users WHERE user_type IN ('0','1','9') AND deleted_at IS NULL ORDER BY user_type,fname")
    return render_template('admin_accounts.html',rows=rows,permission_groups=_groups(actor))


@bp.route('/permissions', methods=['GET','POST'])
@admin_required
def permissions():
    actor=current_user()
    uid=request.values.get('user',type=int)
    target=_target(uid) if uid else None
    if target and not UA.can_manage(actor,target):
        abort(403)
    if request.method=='POST':
        if not target:
            abort(400)
        submitted=set(request.form.getlist('permissions')) if str(target['user_type'])=='1' else set()
        reset=bool(request.form.get('reset_passwords'))
        if reset:
            if not UA.has(actor,'reset_passwords'): abort(403)
            if str(target['user_type'])=='1': submitted.add('reset_passwords')
        else:
            submitted.discard('reset_passwords')
        if not submitted<=UA.allowed_keys(actor): abort(403)
        UA.save(uid,submitted,reset,actor['id'],commit=False)
        UA.audit(actor['id'],'permissions_changed',uid,','.join(sorted(submitted)) + ('; delegated reset enabled' if reset else ''),commit=False)
        db.commit()
        flash('Permissions saved. Changes apply on the user’s next request.', 'success')
        return redirect(url_for('security.permissions',user=uid))
    q=(request.args.get('q') or '').strip()[:100]
    rows=db.query("SELECT id,fname,email,user_type,active FROM new_users WHERE deleted_at IS NULL AND (fname LIKE %s OR email LIKE %s OR EXISTS (SELECT 1 FROM parents px WHERE px.user_id=new_users.id AND px.deleted_at IS NULL AND CONCAT_WS(' ',px.fname,px.mname,px.lname) LIKE %s)) ORDER BY user_type,fname LIMIT 60", ('%'+q+'%','%'+q+'%','%'+q+'%'))
    from ..services import parent_identity as PI
    parent_names=PI.for_users([r['id'] for r in rows if str(r['user_type'])=='3'])
    for r in rows:
        if str(r['user_type'])=='3': r['fname']=parent_names.get(r['id']) or 'Name not recorded'
    rows=[r for r in rows if UA.can_manage(actor,{**r,'is_admin':str(r['user_type']) in ('0','1','9')})]
    selected=UA.allowed_keys(target) if target else set()
    reset=UA.has(target,'reset_passwords') if target else False
    recent=db.query('SELECT action,detail,created_at FROM sl_security_audit WHERE target_id=%s ORDER BY id DESC LIMIT 8',(uid,)) if target else []
    return render_template('user_permissions.html',rows=rows,target=target,selected=selected,reset_enabled=reset,
                           permission_groups=_groups(actor),q=q,recent=recent,can_delegate_reset=UA.has(actor,'reset_passwords'))


@bp.route('/smtp', methods=['GET','POST'])
@admin_required
def smtp():
    actor=current_user()
    if request.method=='POST':
        try:
            if request.form.get('action')=='test':
                recipient=(request.form.get('recipient') or '').strip()
                mailer.send_test(recipient)
                UA.audit(actor['id'],'smtp_test_sent',detail=recipient)
                flash('Test email sent. Check the recipient’s inbox.', 'success')
            else:
                config,password=mailer.validate(request.form)
                mailer.save(config,password,bool(request.form.get('clear_password')))
                UA.audit(actor['id'],'smtp_settings_saved')
                flash('SMTP settings saved.', 'success')
        except ValueError as exc:
            flash(str(exc),'error')
        except Exception:
            flash('Mail could not connect or authenticate. Check the host, port, encryption and credentials.','error')
        return redirect(url_for('security.smtp'))
    return render_template('smtp_settings.html',smtp=mailer.get_config(),password_set=mailer.password_set())
