"""Runtime support for templates transpiled from PHP (tools/php2py.py).

Implements the PHP 8 semantics the report-card views rely on: ordered arrays with int/string keys, loose
comparison, numeric strings, float -> string conversion (precision 14) and a handful of string/array functions.
"""
import base64
import datetime as _dt
import html as _html
import math
import os
import re

FCPATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static") + os.sep
APPEND = object()


# ----------------------------------------------------------------------------- arrays
def _norm_key(k):
    if isinstance(k, bool):
        return int(k)
    if isinstance(k, int):
        return k
    if k is None:
        return ""
    if isinstance(k, float):
        return int(k)
    if isinstance(k, str):
        if re.fullmatch(r"-?(0|[1-9]\d*)", k) and len(k) < 19:
            return int(k)
        return k
    return k


class PA(dict):
    """PHP array: insertion ordered, missing keys read as None, remembers the next free integer key."""
    __slots__ = ("nxt",)

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.nxt = 0
        for k in self:
            if isinstance(k, int) and k >= self.nxt:
                self.nxt = k + 1

    def __missing__(self, key):
        return None

    def append(self, v):
        self[self.nxt] = v

    def __setitem__(self, k, v):
        k = _norm_key(k)
        super().__setitem__(k, v)
        if isinstance(k, int) and k >= self.nxt:
            self.nxt = k + 1

    def __getitem__(self, k):
        return super().get(_norm_key(k))

    def __contains__(self, k):
        return super().__contains__(_norm_key(k))

    def copy(self):
        n = PA()
        for k, v in self.items():
            dict.__setitem__(n, k, v)
        n.nxt = self.nxt
        return n


class K:
    __slots__ = ("k", "v")

    def __init__(self, k, v):
        self.k, self.v = k, v


def arr(*items):
    a = PA()
    for it in items:
        if isinstance(it, K):
            a[it.k] = it.v
        else:
            a.append(it)
    return a


def wrap(x):
    """Convert python lists / dicts (query results etc.) to PA recursively."""
    if isinstance(x, PA):
        return x
    if isinstance(x, dict):
        a = PA()
        for k, v in x.items():
            a[k] = wrap(v)
        return a
    if isinstance(x, (list, tuple)):
        a = PA()
        for v in x:
            a.append(wrap(v))
        return a
    return x


def idx(a, k):
    if a is None:
        return None
    if isinstance(a, str):
        try:
            return a[int(k)]
        except (ValueError, IndexError, TypeError):
            return None
    if isinstance(a, dict):
        return a.get(_norm_key(k)) if not isinstance(a, PA) else a[k]
    return None


def setidx(root, keys, value):
    """root[k1][k2]... = value with autovivification. Returns the (possibly new) root."""
    if root is None or root == "" or root is False:
        root = PA()
    cur = root
    for i, k in enumerate(keys):
        last = i == len(keys) - 1
        if k is APPEND:
            if last:
                cur.append(value)
            else:
                n = PA(); cur.append(n); cur = n
            continue
        if last:
            cur[k] = value
        else:
            nxt = cur[k]
            if not isinstance(nxt, PA):
                nxt = PA(); cur[k] = nxt
            cur = nxt
    return root


def items_of(a):
    if isinstance(a, dict):
        return list(a.items())
    if isinstance(a, (list, tuple)):
        return list(enumerate(a))
    return []


def keys_of(a):
    return list(a.keys()) if isinstance(a, dict) else []


def to_arr(x):
    if isinstance(x, PA):
        return x
    if x is None:
        return PA()
    return arr(x)


# ----------------------------------------------------------------------------- scalars
_NUM_RE = re.compile(r"^[ \t\n\r\v\f]*[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?[ \t\n\r\v\f]*$")


def is_numeric_str(s):
    return bool(_NUM_RE.match(s))


def to_num(x):
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return x
    if x is None:
        return 0
    if isinstance(x, str):
        m = re.match(r"^[ \t\n\r\v\f]*([+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?)", x)
        if not m:
            return 0
        t = m.group(1)
        if re.fullmatch(r"[+-]?\d+", t):
            return int(t)
        return float(t)
    if isinstance(x, dict):
        return 1 if x else 0
    return 0


def to_int(x):
    n = to_num(x)
    if isinstance(n, float):
        if math.isnan(n) or math.isinf(n):
            return 0
        return int(n)
    return n


def to_float(x):
    return float(to_num(x))


def _fmt_float(f):
    if math.isnan(f):
        return "NAN"
    if math.isinf(f):
        return "INF" if f > 0 else "-INF"
    if f == int(f) and abs(f) < 1e15:
        return str(int(f)) if f != 0 else ("-0" if math.copysign(1, f) < 0 else "0")
    s = "%.14G" % f
    if "E" in s:
        m, e = s.split("E")
        if "." not in m:
            m += ".0"
        return m + "E" + e[0] + e[1:].lstrip("0")
    return s


def to_str(x):
    if isinstance(x, str):
        return x
    if x is None or x is False:
        return ""
    if x is True:
        return "1"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        return _fmt_float(x)
    if isinstance(x, dict):
        return "Array"
    return str(x)


def concat(*parts):
    return "".join(to_str(p) for p in parts)


def cat(a, b):
    return to_str(a) + to_str(b)


def T(x):
    if x is None or x is False:
        return False
    if x is True:
        return True
    if isinstance(x, (int, float)):
        return x != 0
    if isinstance(x, str):
        return x not in ("", "0")
    if isinstance(x, dict):
        return len(x) > 0
    return True


# ----------------------------------------------------------------------------- arithmetic / comparison
def add(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        r = a.copy()
        for k, v in b.items():
            if k not in r:
                r[k] = v
        return r
    return to_num(a) + to_num(b)


def sub(a, b):
    return to_num(a) - to_num(b)


def mul(a, b):
    return to_num(a) * to_num(b)


def div(a, b):
    a, b = to_num(a), to_num(b)
    if b == 0:
        raise ZeroDivisionError("Division by zero")
    r = a / b
    if isinstance(a, int) and isinstance(b, int) and a % b == 0:
        return a // b
    return r


def mod(a, b):
    a, b = to_int(a), to_int(b)
    if b == 0:
        raise ZeroDivisionError("Modulo by zero")
    r = abs(a) % abs(b)
    return -r if a < 0 else r


def neg(a):
    return -to_num(a)


def pow_(a, b):
    return to_num(a) ** to_num(b)


def shl(a, b): return to_int(a) << to_int(b)
def shr(a, b): return to_int(a) >> to_int(b)
def band(a, b): return to_int(a) & to_int(b)
def bor(a, b): return to_int(a) | to_int(b)
def bxor(a, b): return to_int(a) ^ to_int(b)


def _cmp(a, b):
    """PHP 8 loose comparison -> -1/0/1 (or None for uncomparable)."""
    if a is None and isinstance(b, str):
        a = ""
    if b is None and isinstance(a, str):
        b = ""
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        x, y = T(a), T(b)
        return (x > y) - (x < y)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return (a > b) - (a < b)
    if isinstance(a, (int, float)) and isinstance(b, str):
        if is_numeric_str(b):
            nb = to_num(b)
            return (a > nb) - (a < nb)
        sa = to_str(a)
        return (sa > b) - (sa < b)
    if isinstance(a, str) and isinstance(b, (int, float)):
        r = _cmp(b, a)
        return -r
    if isinstance(a, str) and isinstance(b, str):
        if is_numeric_str(a) and is_numeric_str(b):
            na, nb = to_num(a), to_num(b)
            return (na > nb) - (na < nb)
        return (a > b) - (a < b)
    if isinstance(a, dict) and isinstance(b, dict):
        if len(a) != len(b):
            return (len(a) > len(b)) - (len(a) < len(b))
        for k, v in a.items():
            if k not in b:
                return 1
            c = _cmp(v, b[k])
            if c:
                return c
        return 0
    if isinstance(a, dict):
        return 1
    if isinstance(b, dict):
        return -1
    return 0


def eq(a, b): return _cmp(a, b) == 0
def ne(a, b): return _cmp(a, b) != 0
def lt(a, b): return _cmp(a, b) < 0
def le(a, b): return _cmp(a, b) <= 0
def gt(a, b): return _cmp(a, b) > 0
def ge(a, b): return _cmp(a, b) >= 0
def spaceship(a, b): return _cmp(a, b)


def ident(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return list(a.items()) == list(b.items())
    return a == b


def nident(a, b):
    return not ident(a, b)


# ----------------------------------------------------------------------------- builtin functions
def f_count(a):
    return len(a) if isinstance(a, (dict, list, tuple)) else (0 if a is None else 1)


def php_round(x, nd=0):
    x = to_num(x)
    nd = to_int(nd)
    m = 10 ** nd
    v = abs(x) * m
    r = math.floor(v + 0.5 + 1e-9 * (v < 1e15))
    # guard against binary representation errors (PHP pre-rounds using precision 15)
    r2 = round(v, 14)
    r = math.floor(r2 + 0.5)
    res = r / m
    return float(math.copysign(res, x)) if x != 0 else 0.0


def f_round(x, nd=0):
    return php_round(x, nd)


def f_trim(s, chars=None):
    return to_str(s).strip(" \t\n\r\0\x0b") if chars is None else to_str(s).strip(chars)


def f_strtoupper(s): return to_str(s).upper()
def f_strtolower(s): return to_str(s).lower()
def f_mb_strtoupper(s): return to_str(s).upper()
def f_strlen(s): return len(to_str(s).encode())
def f_ucfirst(s):
    s = to_str(s)
    return s[:1].upper() + s[1:]


def f_ucwords(s):
    return re.sub(r"(^|[ \t\r\n\f\v])([a-z])", lambda m: m.group(1) + m.group(2).upper(), to_str(s))


def f_is_numeric(x):
    if isinstance(x, bool):
        return False
    if isinstance(x, (int, float)):
        return True
    return isinstance(x, str) and is_numeric_str(x)


def f_is_array(x): return isinstance(x, dict)
def f_is_null(x): return x is None
def f_is_string(x): return isinstance(x, str)
def f_is_int(x): return isinstance(x, int) and not isinstance(x, bool)
def f_is_float(x): return isinstance(x, float)


def f_htmlspecialchars(s, flags=None, enc=None, dbl=True):
    return _html.escape(to_str(s), quote=True).replace("&#x27;", "&#039;")


f_html_escape = f_htmlspecialchars


def f_substr(s, start, length=None):
    s = to_str(s)
    start = to_int(start)
    if start < 0:
        start = max(len(s) + start, 0)
    if length is None:
        return s[start:]
    length = to_int(length)
    if length < 0:
        return s[start:len(s) + length]
    return s[start:start + length]


def f_strpos(h, n, off=0):
    r = to_str(h).find(to_str(n), to_int(off))
    return False if r < 0 else r


def f_str_replace(search, rep, subj):
    subj = to_str(subj)
    if isinstance(search, dict):
        reps = list(rep.values()) if isinstance(rep, dict) else None
        for i, s in enumerate(search.values()):
            r = (reps[i] if reps and i < len(reps) else "") if reps is not None else rep
            subj = subj.replace(to_str(s), to_str(r))
        return subj
    return subj.replace(to_str(search), to_str(rep))


def f_str_repeat(s, n): return to_str(s) * to_int(n)


def f_str_pad(s, n, pad=" ", typ=1):
    s = to_str(s); n = to_int(n)
    return s.rjust(n, pad) if typ == 0 else s.ljust(n, pad)


def f_nl2br(s): return to_str(s).replace("\n", "<br />\n")
def f_strrev(s): return to_str(s)[::-1]


def f_explode(d, s, limit=None):
    parts = to_str(s).split(to_str(d)) if limit is None else to_str(s).split(to_str(d), to_int(limit) - 1)
    return arr(*parts)


def f_implode(glue, pieces=None):
    if pieces is None:
        pieces, glue = glue, ""
    return to_str(glue).join(to_str(v) for v in pieces.values())


def f_in_array(needle, hay, strict=False):
    for v in hay.values():
        if (ident(needle, v) if strict else eq(needle, v)):
            return True
    return False


def f_array_search(needle, hay, strict=False):
    for k, v in hay.items():
        if (ident(needle, v) if strict else eq(needle, v)):
            return k
    return False


def f_array_key_exists(k, a):
    return isinstance(a, dict) and (_norm_key(k) in a)


def f_array_fill(start, n, value):
    a = PA()
    for i in range(to_int(n)):
        a[to_int(start) + i] = value.copy() if isinstance(value, PA) else value
    return a


def f_array_map(fn, a):
    f = fn if callable(fn) else globals().get("f_" + to_str(fn))
    r = PA()
    for k, v in a.items():
        r[k] = f(v)
    return r


def f_array_values(a): return arr(*a.values())
def f_array_keys(a): return arr(*a.keys())
def f_array_sum(a): return sum(to_num(v) for v in a.values())
def f_array_unique(a):
    seen, r = [], PA()
    for k, v in a.items():
        if not any(eq(v, s) and to_str(v) == to_str(s) for s in seen):
            seen.append(v); r[k] = v
    return r
def f_array_merge(*arrs):
    r = PA()
    for a in arrs:
        for k, v in a.items():
            if isinstance(k, int):
                r.append(v)
            else:
                r[k] = v
    return r
def f_array_slice(a, off, length=None):
    items = list(a.values())
    off = to_int(off)
    items = items[off:] if length is None else items[off:off + to_int(length)]
    return arr(*items)
def f_array_filter(a, fn=None):
    r = PA()
    for k, v in a.items():
        if (T(v) if fn is None else T(fn(v))):
            r[k] = v
    return r
def f_array_key_last(a): return list(a.keys())[-1] if a else None


def f_end(a):
    return list(a.values())[-1] if isinstance(a, dict) and a else False


def f_max(*a):
    vals = list(a[0].values()) if len(a) == 1 and isinstance(a[0], dict) else list(a)
    best = vals[0]
    for v in vals[1:]:
        if _cmp(v, best) > 0:
            best = v
    return best


def f_min(*a):
    vals = list(a[0].values()) if len(a) == 1 and isinstance(a[0], dict) else list(a)
    best = vals[0]
    for v in vals[1:]:
        if _cmp(v, best) < 0:
            best = v
    return best


def f_abs(x): return abs(to_num(x))
def f_floor(x): return float(math.floor(to_num(x)))
def f_ceil(x): return float(math.ceil(to_num(x)))
def f_intval(x): return to_int(x)
def f_floatval(x): return to_float(x)


def f_number_format(x, dec=0, dp=".", ts=","):
    s = f"{php_round(x, dec):,.{to_int(dec)}f}"
    return s.replace(",", "\0").replace(".", to_str(dp)).replace("\0", to_str(ts))


def f_sprintf(fmt, *args):
    fmt = to_str(fmt)
    it = iter(args)

    def rep(m):
        flags, width, prec, conv = m.group(1), m.group(2), m.group(3), m.group(4)
        if conv == "%":
            return "%"
        v = next(it, None)
        left = "-" in flags
        pad = "0" if "0" in flags and not left else " "
        plus = "+" in flags
        if conv == "d" or conv == "i":
            s = str(to_int(v)); s = ("+" + s) if plus and to_int(v) >= 0 else s
        elif conv in "fF":
            s = f"{php_round(v, to_int(prec) if prec != '' else 6):.{to_int(prec) if prec != '' else 6}f}"
        elif conv == "s":
            s = to_str(v)
            if prec != "":
                s = s[:to_int(prec)]
        elif conv == "x":
            s = format(to_int(v), "x")
        elif conv == "X":
            s = format(to_int(v), "X")
        else:
            s = to_str(v)
        w = to_int(width) if width else 0
        return s.ljust(w) if left else s.rjust(w, pad)

    return re.sub(r"%([-+0 ]*)(\d*)(?:\.(\d+))?([a-zA-Z%])", lambda m: rep(re.match(r"(.*)", "") and _M(m)), fmt)


class _M:
    """adapter so rep() sees empty-string groups instead of None"""
    def __init__(self, m): self.m = m
    def group(self, i): return self.m.group(i) or ""


FILE_HOOK = None          # set by the app: (path) -> bytes | None for files that live in the database
SIG_PREFIX = FCPATH + "assets/signature/"


def _db_file(p):
    p = to_str(p)
    if FILE_HOOK and p.startswith(SIG_PREFIX):
        return FILE_HOOK(p[len(SIG_PREFIX):])
    return None


def f_is_file(p):
    if to_str(p).startswith(SIG_PREFIX) and FILE_HOOK:
        return _db_file(p) is not None
    return os.path.isfile(to_str(p))


def f_is_readable(p):
    if to_str(p).startswith(SIG_PREFIX) and FILE_HOOK:
        return _db_file(p) is not None
    return os.access(to_str(p), os.R_OK)
def f_basename(p): return os.path.basename(to_str(p).rstrip("/"))


def f_pathinfo(p, opt=None):
    ext = os.path.splitext(to_str(p))[1].lstrip(".")
    if opt == "extension":
        return ext
    return arr(K("extension", ext), K("basename", os.path.basename(to_str(p))))


def f_file_get_contents(p):
    if to_str(p).startswith(SIG_PREFIX) and FILE_HOOK:
        d = _db_file(p)
        return d if d is not None else False
    try:
        with open(to_str(p), "rb") as fh:
            return fh.read()
    except OSError:
        return False


def f_base64_encode(b):
    if isinstance(b, str):
        b = b.encode()
    return base64.b64encode(b).decode()


def f_base_url(p=""):
    return "/static/" + to_str(p)


def f_function_exists(_n): return True


def f_print_r(x, ret=False):
    return str(x) if ret else ""


_DATE_FORMATS = ["%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %B %Y", "%d %b %Y", "%Y/%m/%d", "%d.%m.%Y", "%B %d, %Y"]


def f_strtotime(s):
    s = to_str(s).strip()
    if not s:
        return False
    if s.lower() == "now":
        return int(_dt.datetime.now().timestamp())
    for f in _DATE_FORMATS:
        try:
            return int(_dt.datetime.strptime(s, f).timestamp())
        except ValueError:
            continue
    m = re.fullmatch(r"(\d{1,2})[-/ ]([A-Za-z]{3,9})[-/ ,]+(\d{2,4})", s)      # e.g. 31-Apr-2015 -> PHP rolls over to 1 May
    if m:
        try:
            mon = _dt.datetime.strptime(m.group(2)[:3], "%b").month
            yr = int(m.group(3)); yr += 2000 if yr < 70 and len(m.group(3)) == 2 else 1900 if len(m.group(3)) == 2 else 0
            return int((_dt.datetime(yr, mon, 1) + _dt.timedelta(days=int(m.group(1)) - 1)).timestamp())
        except ValueError:
            pass
    return False


def f_date(fmt, ts=None):
    d = _dt.datetime.now() if ts is None else _dt.datetime.fromtimestamp(to_num(ts) if ts is not False else 0)
    out = []
    for c in to_str(fmt):
        out.append({
            "d": f"{d.day:02d}", "j": str(d.day), "m": f"{d.month:02d}", "n": str(d.month), "Y": str(d.year), "y": f"{d.year % 100:02d}",
            "F": d.strftime("%B"), "M": d.strftime("%b"), "D": d.strftime("%a"), "l": d.strftime("%A"), "H": f"{d.hour:02d}",
            "i": f"{d.minute:02d}", "s": f"{d.second:02d}", "A": d.strftime("%p"), "a": d.strftime("%p").lower(), "g": str(d.hour % 12 or 12),
            "h": f"{d.hour % 12 or 12:02d}", "N": str(d.isoweekday()), "t": str(_days_in_month(d)),
        }.get(c, c))
    return "".join(out)


def _days_in_month(d):
    nxt = (d.replace(day=28) + _dt.timedelta(days=4)).replace(day=1)
    return (nxt - _dt.timedelta(days=1)).day
