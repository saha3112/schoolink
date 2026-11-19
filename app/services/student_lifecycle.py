"""Student Trash and restore preserve marks; purge rejects academic references."""
from .. import db
from . import rolls,enrollment,user_access as UA


class StudentActionError(ValueError):pass


def academic_references(student_id,legacy_id=None):
    columns=db.query("SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND COLUMN_NAME IN ('studentId','student_id')")
    ignore={'students','student_subject_exclusion','student_transfer_log'}
    found=[]
    for row in columns:
        if row['TABLE_NAME'] in ignore:continue
        values=[student_id]
        if row['COLUMN_NAME']=='student_id' and legacy_id and str(legacy_id).isdigit():values.append(legacy_id)
        marks=','.join(['%s']*len(values))
        if db.scalar(f"SELECT COUNT(*) FROM `{row['TABLE_NAME']}` WHERE `{row['COLUMN_NAME']}` IN ({marks})",values):found.append(row['TABLE_NAME'])
    return found


def apply(actor,action,values):
    if not actor or not actor.get('is_admin'):raise PermissionError('Only administrators can manage student Trash.')
    if action not in ('trash','restore','purge'):raise StudentActionError('Choose a valid student action.')
    try:ids=sorted({int(value) for value in values})
    except (ValueError,TypeError):raise StudentActionError('Select valid students.')
    if not ids or len(ids)>100 or any(sid<1 for sid in ids):raise StudentActionError('Select between 1 and 100 students.')
    UA.ensure();enrollment.ensure()
    try:
        rows=db.query('SELECT * FROM students WHERE studentId IN ('+','.join(['%s']*len(ids))+') ORDER BY studentId FOR UPDATE',ids)
        if len(rows)!=len(ids):raise StudentActionError('A selected student no longer exists. Reload the list.')
        pairs=set()
        for student in rows:
            trashed=str(student['isDelete'])=='1'
            if (action=='trash' and trashed) or (action!='trash' and not trashed):
                raise StudentActionError('The selection includes students from another tab. Reload and select again.')
            sid=student['studentId'];cid=student['class_id'];sec=student['section_id']
            if action=='trash':
                db.execute("UPDATE students SET isDelete='1' WHERE studentId=%s",(sid,),commit=False)
                pairs.add((cid,sec))
            elif action=='restore':
                if not db.one("SELECT 1 FROM sections s JOIN classes c ON c.classId=s.class_id WHERE s.sectionId=%s AND s.class_id=%s AND s.isDelete='0' AND c.isDelete='0'",(sec,cid)):
                    raise StudentActionError('Restore the student’s class and section first.')
                code=(student.get('student_code') or '').strip()
                if code and code.lower() not in ('n/a','na','-') and db.one("SELECT studentId FROM students WHERE student_code=%s AND studentId<>%s AND isDelete='0' FOR UPDATE",(code,sid)):
                    raise StudentActionError('Another active student uses a selected student code. Correct the duplicate before restoring.')
                db.execute("UPDATE students SET isDelete='0',student_rollNumber=%s WHERE studentId=%s",(rolls.next_roll(cid,sec),sid),commit=False)
                pairs.add((cid,sec))
            else:
                refs=academic_references(sid,student.get('student_id'))
                if refs:raise StudentActionError(f"{student['student_name']} has academic/history records ({', '.join(sorted(set(refs))[:3])}). Keep the student in Trash; permanent deletion is blocked.")
                db.execute('DELETE FROM student_subject_exclusion WHERE studentId=%s',(sid,),commit=False)
                db.execute('DELETE FROM students WHERE studentId=%s AND isDelete=\'1\'',(sid,),commit=False)
            UA.audit(actor['id'],'student_'+action,detail=f'Student record {sid}',commit=False)
        for cid,sec in sorted(pairs):rolls.renumber(cid,sec,'keep')
        db.commit()
    except Exception:
        db.rollback();raise
    return len(ids)
