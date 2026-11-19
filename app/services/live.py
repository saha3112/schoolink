"""Real-time sync between panels.

Every successful change made through the app (a POST) is recorded as a small event; each open page polls /live/poll and,
when an event touches what it shows, quietly re-reads that data (see static/js/live.js).  Nothing but a tiny table of
(topic, class, section, exam) is kept - no page content - and old events are pruned automatically."""
import time

from .. import db

_ready = False
_last_prune = 0.0

# blueprint (topic) -> topics a page of that blueprint wants to hear about
INTEREST = {
    "main": ["marks", "classteacher", "students", "admin", "school", "leave", "parentpanel", "csvio", "reports"],
    "marks": ["marks", "csvio"],
    "classteacher": ["classteacher", "marks", "csvio"],
    "students": ["students", "admin", "csvio"],
    "school": ["school"],
    "parentpanel": ["marks", "classteacher", "school", "leave", "parentpanel", "reports", "csvio", "students", "admin"],
    "reports": ["marks", "classteacher", "reports", "csvio"],
    "leave": ["leave", "parentpanel"],
    "parents": ["students", "parents", "parentpanel", "csvio"],
    "admin": ["admin", "students"],
    "signatures_admin": ["signatures_admin", "media"],
    "layouts_admin": ["layouts_admin"],
    "media": ["media"],
}
# changes that alter what a user may see in the sidebar / dashboard (teacher assignments, class teachers, students moved …)
GLOBAL_TOPICS = ["admin", "students"]
PUBLISH_FROM = {"marks", "classteacher", "school", "students", "admin", "parents", "leave", "reports", "signatures_admin", "layouts_admin", "csvio", "media", "parentpanel"}


def ensure():
    global _ready
    if _ready:
        return
    db.execute("""CREATE TABLE IF NOT EXISTS sl_live_event (id BIGINT AUTO_INCREMENT PRIMARY KEY, topic VARCHAR(40) NOT NULL, class_id INT NULL, section_id INT NULL,
        exam_id INT NULL, actor INT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, KEY (created_at))""")
    _ready = True


def publish(topic, class_id=None, section_id=None, exam_id=None, actor=None):
    global _last_prune
    ensure()
    db.execute("INSERT INTO sl_live_event (topic, class_id, section_id, exam_id, actor) VALUES (%s,%s,%s,%s,%s)",
               (topic, class_id, section_id, exam_id, actor))
    if time.time() - _last_prune > 600:                       # keep only the last hour
        _last_prune = time.time()
        db.execute("DELETE FROM sl_live_event WHERE created_at < (NOW() - INTERVAL 1 HOUR)")


def latest():
    ensure()
    return db.scalar("SELECT COALESCE(MAX(id),0) FROM sl_live_event") or 0


def since(last_id, topics=None, limit=60):
    ensure()
    rows = db.query("SELECT id, topic, class_id, section_id, exam_id, actor FROM sl_live_event WHERE id>%s ORDER BY id LIMIT %s", (last_id, limit))
    if topics:
        rows = [r for r in rows if r["topic"] in topics]
    return rows
