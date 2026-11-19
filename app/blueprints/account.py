from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from .. import db
from ..auth import login_required, admin_required, current_user, hash_password
from ..services import notifications as N
from ..utils import paginate, page_arg
from ..services import user_access as UA

bp = Blueprint("account", __name__, url_prefix="/account")


@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    """Any signed in user may change their own password. No old password is asked."""
    if request.method == "POST":
        new = request.form.get("new_password", "")
        conf = request.form.get("confirm_password", "")
        if len(new) < 8 or len(new.encode()) > 72:
            flash("Use at least 8 characters and at most 72 bytes.", "error")
        elif new != conf:
            flash("The two passwords do not match.", "error")
        else:
            uid=current_user()['id']
            UA.ensure()
            db.execute("UPDATE new_users SET password=%s,updated_at=NOW() WHERE id=%s", (hash_password(new), uid),commit=False)
            UA.revoke(uid,commit=False)
            UA.audit(uid,'own_password_changed',uid,commit=False)
            db.commit()
            session['auth_version']=UA.record(uid)['session_version']
            flash("Password changed successfully.", "success")
            return redirect(url_for("account.change_password"))
    return render_template("change_password.html")


@bp.route("/users", methods=["GET","POST"])
@login_required
def users():
    actor=current_user()
    if not (actor['is_admin'] and UA.has(actor,'account.users')) and not actor['can_reset_passwords']:
        abort(403)
    from ..services import user_lifecycle as lifecycle
    manage_accounts=actor['is_admin'] and UA.has(actor,'manage_user_accounts')
    if request.method=='POST':
        if not manage_accounts:abort(403)
        try:
            action=request.form.get('action','')
            count=lifecycle.apply(actor,action,request.form.getlist('ids'))
            flash(str(count)+' account(s) '+{'trash':'moved to Trash. Existing sessions were signed out.','restore':'restored with their previous status.','purge':'deleted permanently.'}[action],'success')
        except PermissionError:abort(403)
        except lifecycle.UserActionError as error:flash(str(error),'error')
        return redirect(url_for('account.users',q=request.args.get('q',''),trash=request.args.get('trash','')))
    trash=request.args.get('trash')=='1'
    if trash and not manage_accounts:abort(403)
    q = request.args.get("q", "").strip()[:100]
    types="('0','1','2','3','9')" if actor['is_admin'] else "('2','3')"
    where, args = "WHERE deleted_at IS " + ("NOT NULL" if trash else "NULL") + " AND user_type IN " + types, []
    if q:
        where += " AND (fname LIKE %s OR email LIKE %s OR new_users.id IN (SELECT CAST(px.user_id AS UNSIGNED) FROM parents px WHERE px.deleted_at IS NULL AND CONCAT_WS(' ',px.fname,px.mname,px.lname) LIKE %s))"
        args += [f"%{q}%"] * 3
    total = db.scalar(f"SELECT COUNT(*) FROM new_users {where}", args)
    p = paginate(total, 20, page_arg())
    rows = db.query(f"SELECT id, fname, email, user_type, active FROM new_users {where} "
                    f"ORDER BY user_type, fname LIMIT %s OFFSET %s", args + [p["per_page"], p["offset"]])
    from ..services import parent_identity as PI
    parent_names = PI.for_users([row['id'] for row in rows if str(row['user_type']) == '3'])
    for row in rows:
        if str(row['user_type']) == '3':
            row['fname'] = parent_names.get(row['id']) or 'Name not recorded'
        row['is_admin']=str(row['user_type']) in ('0','1','9')
        row['can_reset']=not trash and UA.can_reset(actor,row)
        row['can_lifecycle']=manage_accounts and lifecycle.can_manage(actor,row)
        row['can_manage']=not trash and UA.can_manage(actor,row)
        row['reset_enabled']=UA.has(row,'reset_passwords')
    return render_template("users.html", rows=rows, p=p, q=q, trash=trash, manage_accounts=manage_accounts, n_trash=db.scalar("SELECT COUNT(*) FROM new_users WHERE deleted_at IS NOT NULL AND user_type IN ('1','2','3')") if manage_accounts else 0)


@bp.route("/users/<int:uid>/reset", methods=["POST"])
@login_required
def reset_password(uid):
    actor=current_user()
    target=db.one("SELECT id,fname,user_type FROM new_users WHERE id=%s AND deleted_at IS NULL",(uid,))
    if not target: abort(404)
    target['is_admin']=str(target['user_type']) in ('0','1','9')
    if not UA.can_reset(actor,target): abort(403)
    new=request.form.get('new_password','')
    if len(new)<8 or len(new.encode())>72:
        flash('Use a password of at least 8 characters and at most 72 bytes.','error')
    else:
        UA.ensure()
        try:
            db.execute('UPDATE new_users SET password=%s,updated_at=NOW() WHERE id=%s',(hash_password(new),uid),commit=False)
            UA.revoke(uid,commit=False)
            UA.audit(actor['id'],'password_reset',uid,commit=False)
            db.commit()
        except Exception:
            db.rollback()
            raise
        N.notify([uid],'Your password was reset','An authorized user reset your password. Existing sessions have been signed out.',url_for('account.change_password'))
        flash('Password reset. The user’s existing sessions have been signed out.','success')
    return redirect(url_for('account.users'))


@bp.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    import io
    from PIL import Image, ImageOps, UnidentifiedImageError
    from ..services import filestore
    user=current_user()
    path=f"profile/{user['id']}.png"
    if request.method=='POST':
        if request.form.get('action')=='remove':
            filestore.delete(path)
            flash('Profile photo removed. Your initials will be shown.', 'success')
        else:
            file=request.files.get('photo')
            if not file or not file.filename:
                flash('Choose a JPG, PNG or WebP photo.', 'error')
            else:
                data=file.read(3*1024*1024+1)
                if len(data)>3*1024*1024:
                    flash('Choose a photo smaller than 3 MB.', 'error')
                else:
                    try:
                        with Image.open(io.BytesIO(data)) as source:
                            if source.format not in ('JPEG','PNG','WEBP') or source.width*source.height>16000000:
                                raise ValueError()
                            photo=ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'),(320,320))
                            output=io.BytesIO();photo.save(output,format='PNG',optimize=True)
                        filestore.put(path,output.getvalue(),user['id'])
                        flash('Profile photo updated.', 'success')
                    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                        flash('Use a valid JPG, PNG or WebP photo up to 16 megapixels.', 'error')
        return redirect(url_for('account.profile'))
    return render_template('user_profile.html')


@bp.route('/profile-photo/<int:uid>')
@login_required
def profile_image(uid):
    from flask import abort, Response
    from ..services import filestore
    if uid!=current_user()['id']:
        abort(403)
    photo=filestore.get(f'profile/{uid}.png')
    if not photo: abort(404)
    response=Response(photo['data'],mimetype='image/png')
    response.headers['Cache-Control']='private, no-cache'
    response.headers['X-Content-Type-Options']='nosniff'
    return response
