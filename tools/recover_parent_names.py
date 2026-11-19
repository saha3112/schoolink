"""Audit verified legacy parent names; --apply fills missing names only."""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app,db
from app.services.parent_identity import name,clean_name


def phone(value):
    digits=re.sub(r'\D','',value or '')
    if len(digits)==12 and digits.startswith('91'):digits=digits[2:]
    if len(digits)==11 and digits.startswith('0'):digits=digits[1:]
    return digits


def recovery_plan(current,sources):
    indexed=defaultdict(dict)
    for source in sources:
        value=name(source)
        key=phone(source.get('phone_1'))
        if value and len(key)>=10:
            indexed[key].setdefault(value.casefold(),source)
    plan=[];missing=[];ambiguous=[]
    for row in current:
        if name(row):continue
        matches=indexed.get(phone(row.get('phone_1')), {})
        if len(matches)==1:
            source=next(iter(matches.values()))
            fields={k:clean_name(source.get(k)) or None for k in ('fname','mname','lname')}
            if not any(fields.values()):fields['fname']=name(source)
            plan.append({'id':row['id'],'user_id':row['user_id'],'fields':fields,'source':source['_source']})
        elif matches:ambiguous.append(row['id'])
        else:missing.append(row['id'])
    return plan,missing,ambiguous


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    app=create_app()
    with app.app_context():
        current=db.query('SELECT p.*,u.fname AS account_name FROM parents p LEFT JOIN new_users u ON u.id=p.user_id AND u.deleted_at IS NULL WHERE p.deleted_at IS NULL')
        sources=[]
        configs=[('schoollink-ST-thomas',t,'users'+t[len('parents'):]) for t in ('parents_300825','parents_270825','parents_260624','parents_080823','parents_310723','parents_050723','parents')]
        configs += [(s,'parents','new_users') for s in ('schoolink-reportCard-Thomas','schoolink_py','schoolink-new app') if s!=app.config['DB_NAME']]
        for schema,table,users in configs:
            if not db.scalar('SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',(schema,table)):
                continue
            rows=db.query(f'''SELECT p.fname,p.mname,p.lname,p.phone_1,u.fname AS account_name
                FROM `{schema}`.`{table}` p LEFT JOIN `{schema}`.`{users}` u ON u.id=p.user_id WHERE p.phone_1<>'' ''')
            for row in rows:row['_source']=schema+'.'+table
            sources.extend(rows)
        plan,missing,ambiguous=recovery_plan(current,sources)
        print(json.dumps({'parents':len(current),'missing_name':sum(not name(r) for r in current),'verified_recoveries':len(plan),'not_in_sources':len(missing),'ambiguous':len(ambiguous)}))
        if args.apply and plan:
            try:
                for item in plan:
                    f=item['fields']
                    db.execute('UPDATE parents SET fname=%s,mname=%s,lname=%s WHERE id=%s AND TRIM(CONCAT_WS(\' \',fname,mname,lname))=\'\'',(f['fname'],f['mname'],f['lname'],item['id']),commit=False)
                    value=' '.join(filter(None,f.values()))
                    db.execute("UPDATE new_users SET fname=%s WHERE id=%s AND TRIM(fname)=''",(value,item['user_id']),commit=False)
                db.commit()
            except Exception:
                db.rollback();raise
            print('Recovered',len(plan),'verified parent names; existing names were preserved.')

if __name__=='__main__':main()
