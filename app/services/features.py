"""Which class sections each feature applies to.

A feature that does not exist for a class (e.g. house points outside classes I-V, report cards for classes without a
design, development skills that were never configured) must not offer that class or section anywhere."""
from .. import db
from . import layouts

def card_supported(cid, sid):
    """Report card (and everything printed on it) exists for this section - a layout rule with a card design (Admin > Report layouts)."""
    return layouts.card_supported(cid, sid)


def _set(sql):
    return {(int(r["c"]), int(r["s"])) for r in db.query(sql)}


_NAMES = ("entry", "special", "development", "house", "attendance", "comments", "rank", "average", "card", "sheet")


def sections_for(feature):
    """Set of (classId, sectionId) where the feature makes sense, every active section of the school considered."""
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
    ok = sections_for(feature)
    src = access.subject_pairs(user) if feature in ("entry", "special") else access.class_pairs(user)
    seen, out = set(), []
    for p in src:
        k = (p["classId"], p["sectionId"])
        if k in ok and k not in seen:
            seen.add(k); out.append({"classId": k[0], "sectionId": k[1]})
    return out


def available(user):
    """Feature names the user has at least one section for - used to hide menu entries."""
    return {f for f in _NAMES if pairs(f, user)}
