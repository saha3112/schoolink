"""Which class sections each feature applies to.

A feature that does not exist for a class (e.g. house points outside classes I-V, report cards for classes without a
design, development skills that were never configured) must not offer that class or section anywhere."""
from .. import cache, db
from . import layouts

def card_supported(cid, sid):
    """Report card (and everything printed on it) exists for this section - a layout rule with a card design (Admin > Report layouts)."""
    return layouts.card_supported(cid, sid)


def _set(sql):
    return {(int(r["c"]), int(r["s"])) for r in db.query(sql)}


_NAMES = ("entry", "special", "development", "house", "attendance", "comments", "rank", "average", "card", "sheet")


def sections_for(feature):
    """Set of (classId, sectionId) where the feature makes sense, every active section of the school considered."""
    return cache.get(("features.sections_for", feature), lambda: _sections_for(feature), 120, copy_result=False)


def _sections_for(feature):
    if feature == "entry":          # at least one exam sub-type with full marks is configured
        return _set("SELECT DISTINCT classId c, sectionId s FROM assign_exam_subtype WHERE isDelete='0'")
    if feature == "special":
        return _set("SELECT DISTINCT class_id c, section_id s FROM assign_subject WHERE isDelete='0' AND isSpecialSubject='1'")
    if feature == "development":
        return _set("SELECT DISTINCT classId c, sectionId s FROM developmentSkill WHERE isDelete='0'")
    base = _set("SELECT DISTINCT st.class_id c, st.section_id s FROM students st WHERE st.isDelete='0'")
    if feature == "house":          # house points are printed only on the junior (I-V) sheets
        return {p for p in base if layouts.is_junior(*p)}
    if feature in ("attendance", "comments", "rank", "average", "card", "sheet"):
        return {p for p in base if card_supported(*p)}
    return base


def pairs(feature, user):
    """Rows {classId, sectionId} the user may use for the feature, already narrowed to where it applies."""
    from . import access
    if feature in ('entry','special'):
        return [{'classId':cid,'sectionId':sid} for cid,sid in sorted({(row['classId'],row['sectionId']) for row in mark_contexts(user,feature)})]
    ok = sections_for(feature)
    src = access.subject_pairs(user) if feature in ("entry", "special") else access.class_pairs(user)
    seen, out = set(), []
    for p in src:
        k = (p["classId"], p["sectionId"])
        if feature in ('attendance','comments','development','rank','house') and not access.exams_for(*k):
            continue
        if k in ok and k not in seen:
            seen.add(k); out.append({"classId": k[0], "sectionId": k[1]})
    return out


def available(user):
    """Feature names the user has at least one section for - used to hide menu entries."""
    return cache.get(("features.available", "admin" if user["is_admin"] else int(user["id"])), lambda: _available(user), 90, copy_result=False)


def _available(user):
    from flask import g,has_app_context
    cache=g.setdefault('_feature_available',{}) if has_app_context() else {}
    key=(int(user['id']),bool(user['is_admin']))
    if key not in cache:cache[key]={f for f in _NAMES if pairs(f,user)}
    return cache[key]


def mark_contexts(user,feature='entry'):
    """Actual writable subject/exam contexts, not just any subject in a section."""
    return cache.get(("features.mark_contexts","admin" if user["is_admin"] else int(user["id"]),feature), lambda: _mark_contexts(user,feature), 120, copy_result=False)


def _mark_contexts(user,feature='entry'):
    from flask import g,has_app_context
    from . import enrollment
    enrollment.ensure()
    cache_key=(int(user['id']),feature,bool(user['is_admin']))
    cache=g.setdefault('_mark_contexts',{}) if has_app_context() else {}
    if cache_key in cache:return cache[cache_key]
    special=feature=='special'
    source=('assign_exam' if special else 'assign_exam_subtype')
    extra='' if special else " JOIN exam_subtype x ON x.id=a.exam_subtype_id AND x.isDelete='0' "
    teacher='' if user['is_admin'] else " JOIN assign_teacher t ON t.classId=a.classId AND t.sectionId=a.sectionId AND t.subjectId=a.subjectId AND t.isDelete='0' AND t.t_id=%s "
    sql=f'''SELECT DISTINCT a.classId,a.sectionId,a.examId,a.subjectId
        FROM {source} a JOIN assign_subject ass ON ass.class_id=a.classId AND ass.section_id=a.sectionId
        AND ass.subject_id=a.subjectId AND ass.isDelete='0' AND ass.isSpecialSubject=%s
        JOIN classes c ON c.classId=a.classId AND c.isDelete='0'
        JOIN sections s ON s.sectionId=a.sectionId AND s.class_id=a.classId AND s.isDelete='0'
        JOIN subjects sb ON sb.subjectId=a.subjectId AND sb.isDelete='0'
        JOIN exams e ON e.examId=a.examId AND e.isDelete='0' {extra} {teacher}
        WHERE a.isDelete='0' AND EXISTS (SELECT 1 FROM students st
        WHERE st.class_id=a.classId AND st.section_id=a.sectionId AND st.isDelete='0'
        AND NOT EXISTS (SELECT 1 FROM student_subject_exclusion ex WHERE ex.studentId=st.studentId AND ex.subjectId=a.subjectId))'''
    rows=db.query(sql,(['1' if special else '0']+([] if user['is_admin'] else [user['id']])))
    cache[cache_key]=[{k:int(row[k]) for k in ('classId','sectionId','examId','subjectId')} for row in rows]
    return cache[cache_key]


def mark_exams(user,feature='entry',cid=None,sid=None):
    ids=sorted({row['examId'] for row in mark_contexts(user,feature) if (not cid or row['classId']==cid) and (not sid or row['sectionId']==sid)})
    if not ids:return []
    return db.query('SELECT examId,exam_name FROM exams WHERE isDelete=\'0\' AND examId IN ('+','.join(['%s']*len(ids))+') ORDER BY examId',ids)


WRITE_ENDPOINTS={'marks.entry','marks.special','classteacher.attendance','classteacher.comments','classteacher.development','classteacher.rank','classteacher.house','classteacher.average'}

def nav_allowed(user,endpoint):
    from . import access
    return not user or not user.get('is_teacher') or endpoint not in WRITE_ENDPOINTS or access.editing_enabled()
