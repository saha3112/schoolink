"""Brute-force protection for the sign-in form.

Failed attempts are stored (table sl_login_attempts) so the limits hold across restarts and server processes:
  * 6 failures for the same login from the same address     -> that pair waits 15 minutes
  * 25 failures from one address (any logins)               -> that address waits 15 minutes
  * 40 failures against one login from anywhere             -> sign-in for that login waits 15 minutes
Locking the pair first means a stranger guessing someone's login cannot lock the real owner out from their own address."""
from .. import db

WINDOW = 15 * 60
PAIR_LIMIT, IP_LIMIT, IDENT_LIMIT = 6, 25, 40
_ready = [False]


def _ensure():
    if _ready[0]:
        return
    db.execute("CREATE TABLE IF NOT EXISTS sl_login_attempts (id BIGINT AUTO_INCREMENT PRIMARY KEY, ident VARCHAR(190) NOT NULL, ip VARCHAR(64) NOT NULL, "
               "at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, KEY k_ident (ident, at), KEY k_ip (ip, at)) ENGINE=InnoDB")
    _ready[0] = True


def norm(ident):
    return (ident or "").strip().lower()[:190]


def _wait(where, args, limit):
    r = db.one(f"SELECT COUNT(*) c, TIMESTAMPDIFF(SECOND, MAX(at), NOW()) age FROM sl_login_attempts WHERE {where} AND at > NOW() - INTERVAL {WINDOW} SECOND", args)
    if r and r["c"] >= limit:
        return max(0, WINDOW - int(r["age"] or 0))
    return 0


def wait_seconds(ident, ip):
    """0 = the sign-in may be tried; otherwise how many seconds to wait."""
    _ensure()
    ident = norm(ident)
    return max(_wait("ident=%s AND ip=%s", (ident, ip), PAIR_LIMIT), _wait("ip=%s", (ip,), IP_LIMIT), _wait("ident=%s", (ident,), IDENT_LIMIT))


def failed(ident, ip):
    _ensure()
    ident = norm(ident)
    db.execute("INSERT INTO sl_login_attempts (ident, ip) VALUES (%s,%s)", (ident, ip))
    if wait_seconds(ident, ip):                              # this failure just tripped a limit: leave a trace for the administrators
        n = db.scalar("SELECT COUNT(*) FROM sl_login_attempts WHERE ident=%s AND ip=%s AND at > NOW() - INTERVAL 900 SECOND", (ident, ip)) or 0
        if n == PAIR_LIMIT:
            try:
                from . import user_access as UA
                UA.audit(0, "login.locked", None, f"Too many failed sign-ins for '{ident[:60]}' from {ip}")
            except Exception:
                pass
    if db.scalar("SELECT FLOOR(RAND()*100)") == 0:           # housekeeping now and then
        db.execute("DELETE FROM sl_login_attempts WHERE at < NOW() - INTERVAL 2 DAY")


def succeeded(ident, ip):
    _ensure()
    db.execute("DELETE FROM sl_login_attempts WHERE ident=%s AND ip=%s", (norm(ident), ip))
