"""One name resolver for legacy parent records and their login accounts."""
import html
import re
from .. import db

EMPTY = {'parent','user','n/a','na','none','null','-','—','0','not available','unknown'}


def clean_name(value):
    text = html.unescape(re.sub(r'<[^>]*>', ' ', str(value or '')))
    text = ' '.join(text.split()).strip()
    if text.lower() in EMPTY or re.fullmatch(r'PAR\d+',text,re.I) or not any(c.isalpha() for c in text):
        return ''
    return text


def name(parent):
    full = ' '.join(filter(None,(clean_name(parent.get(k)) for k in ('fname','mname','lname'))))
    return full or clean_name(parent.get('account_name'))


def fill(parent):
    if not any(clean_name(parent.get(k)) for k in ('fname','mname','lname')):
        parent['fname'] = name(parent)
    return parent


def for_users(ids):
    """Resolve parent-login names in one query, without overwriting stored data."""
    ids=list({int(uid) for uid in ids if uid})
    if not ids:return {}
    marks=','.join(['%s']*len(ids))
    rows=db.query(f'''SELECT p.user_id,p.fname,p.mname,p.lname,u.fname AS account_name
        FROM parents p LEFT JOIN new_users u ON u.id=p.user_id AND u.deleted_at IS NULL
        WHERE p.deleted_at IS NULL AND p.user_id IN ({marks}) ORDER BY p.id''',ids)
    out={}
    for row in rows:
        resolved=name(row)
        if resolved:out.setdefault(int(row['user_id']),resolved)
    return out


def sql_name(parent='p',account='u'):
    # Aliases are internal constants supplied by the caller, never user input.
    return f"COALESCE(NULLIF(TRIM(CONCAT_WS(' ',NULLIF(TRIM({parent}.fname),''),NULLIF(TRIM({parent}.mname),''),NULLIF(TRIM({parent}.lname),''))),''),NULLIF(TRIM({account}.fname),''),'')"
