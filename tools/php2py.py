#!/usr/bin/env python3
"""PHP view -> Python module transpiler (subset sufficient for the Schoolink report templates).

    python tools/php2py.py view.php  out.py

The generated module exposes  render(ctx) -> str  and relies on app/phpr.py for PHP semantics.
"""
import json, re, subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))


def tokenize(path):
    raw = subprocess.check_output(["php", os.path.join(HERE, "tokens.php"), path])
    toks = json.loads(raw)
    out = []
    for n, t in toks:
        if n in ("T_WHITESPACE", "T_COMMENT", "T_DOC_COMMENT"):
            continue
        if n == "T_OPEN_TAG":
            continue
        if n == "T_CLOSE_TAG":
            out.append((";", ";"))
            continue
        out.append((n, t))
    return out


class P:
    def __init__(self, toks):
        self.t, self.i = toks, 0
        self.funcs = []          # hoisted function defs
        self.func_stack = []

    # ---- helpers
    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else ("EOF", "")

    def nxt(self):
        x = self.peek(); self.i += 1; return x

    def is_(self, name, k=0):
        return self.peek(k)[0] == name

    def expect(self, name):
        x = self.nxt()
        if x[0] != name:
            raise SyntaxError(f"expected {name} got {x} near token {self.i}: {self.t[max(0,self.i-8):self.i+4]}")
        return x

    def accept(self, name):
        if self.is_(name):
            return self.nxt()
        return None

    # ---- statements
    def program(self):
        stmts = []
        while not self.is_("EOF"):
            stmts.append(self.statement())
        return stmts

    def block_until(self, *ends):
        stmts = []
        while self.peek()[0] not in ends:
            if self.is_("EOF"):
                raise SyntaxError("unexpected EOF")
            stmts.append(self.statement())
        return stmts

    def body(self, alt_ends=None):
        """statement or { block } or alt syntax (':' ... end)"""
        if self.accept("{"):
            b = self.block_until("}")
            self.expect("}")
            return b
        if alt_ends is not None and self.is_(":"):
            self.nxt()
            return self.block_until(*alt_ends)
        return [self.statement()]

    def statement(self):
        n, t = self.peek()
        if n == "T_INLINE_HTML":
            self.nxt(); return ("html", t)
        if n == ";":
            self.nxt(); return ("nop",)
        if n == "{":
            self.nxt(); b = self.block_until("}"); self.expect("}"); return ("block", b)
        if n == "T_IF":
            return self.if_stmt()
        if n == "T_FOR":
            return self.for_stmt()
        if n == "T_FOREACH":
            return self.foreach_stmt()
        if n == "T_ECHO":
            self.nxt(); es = [self.expr()]
            while self.accept(","):
                es.append(self.expr())
            self.end_stmt()
            return ("echo", es)
        if n == "T_FUNCTION":
            return self.func_def()
        if n == "T_RETURN":
            self.nxt()
            e = None if self.is_(";") else self.expr()
            self.end_stmt(); return ("return", e)
        if n in ("T_BREAK", "T_CONTINUE"):
            self.nxt()
            lvl = 1
            if self.is_("T_LNUMBER"):
                lvl = int(self.nxt()[1])
            self.end_stmt(); return ("break" if n == "T_BREAK" else "continue", lvl)
        if n == "T_ENDIF" or n == "T_ENDFOREACH":
            raise SyntaxError("stray " + n)
        e = self.expr()
        self.end_stmt()
        return ("expr", e)

    def end_stmt(self):
        # PHP allows ?> to end a statement; we turned it into ';'
        if not self.accept(";"):
            if self.is_("T_INLINE_HTML") or self.is_("}") or self.is_("EOF"):
                return
            raise SyntaxError(f"expected ; got {self.peek()} at {self.i}: {self.t[max(0,self.i-8):self.i+4]}")

    def skip_semis(self):
        while self.is_(";"):
            self.nxt()

    def if_stmt(self):
        self.expect("T_IF"); self.expect("(")
        cond = self.expr(); self.expect(")")
        alt = self.is_(":")
        branches = []
        if alt:
            self.nxt()
            b = self.block_until("T_ELSEIF", "T_ELSE", "T_ENDIF")
            branches.append((cond, b))
            els = None
            while True:
                if self.accept("T_ELSEIF"):
                    self.expect("("); c = self.expr(); self.expect(")"); self.expect(":")
                    bb = self.block_until("T_ELSEIF", "T_ELSE", "T_ENDIF"); branches.append((c, bb))
                elif self.accept("T_ELSE"):
                    if self.is_("T_IF"):       # else if (...) : not valid alt syntax; treat as nested
                        raise SyntaxError("else if in alt syntax")
                    self.expect(":")
                    els = self.block_until("T_ENDIF")
                else:
                    break
            self.expect("T_ENDIF"); self.end_stmt()
            return ("if", branches, els)
        branches.append((cond, self.body()))
        els = None
        while True:
            if self.accept("T_ELSEIF"):
                self.expect("("); c = self.expr(); self.expect(")")
                branches.append((c, self.body()))
            elif self.is_("T_ELSE") and self.is_("T_IF", 1):
                self.nxt(); self.nxt(); self.expect("("); c = self.expr(); self.expect(")")
                branches.append((c, self.body()))
            elif self.accept("T_ELSE"):
                els = self.body()
                break
            else:
                break
        return ("if", branches, els)

    def for_stmt(self):
        self.expect("T_FOR"); self.expect("(")
        def exprs(end):
            es = []
            while not self.is_(end):
                es.append(self.expr())
                if not self.accept(","):
                    break
            self.expect(end); return es
        init = exprs(";"); cond = exprs(";"); step = exprs(")")
        return ("for", init, cond, step, self.body())

    def foreach_stmt(self):
        self.expect("T_FOREACH"); self.expect("(")
        subj = self.expr(); self.expect("T_AS")
        k = None; byref = False
        if self.accept("T_AMPERSAND_FOLLOWED_BY_VAR_OR_VARARG") or self.accept("&"):
            byref = True
        v = self.expr_prefix_var()
        if self.accept("T_DOUBLE_ARROW"):
            k = v
            if self.accept("T_AMPERSAND_FOLLOWED_BY_VAR_OR_VARARG") or self.accept("&"):
                byref = True
            v = self.expr_prefix_var()
        self.expect(")")
        if self.is_(":"):
            self.nxt(); b = self.block_until("T_ENDFOREACH"); self.expect("T_ENDFOREACH"); self.end_stmt()
        else:
            b = self.body()
        return ("foreach", subj, k, v, byref, b)

    def expr_prefix_var(self):
        n, t = self.expect("T_VARIABLE")
        return ("var", t[1:])

    def func_def(self):
        self.expect("T_FUNCTION")
        name = self.expect("T_STRING")[1]
        self.expect("(")
        params = []
        while not self.is_(")"):
            ref = False
            while self.peek()[0] in ("T_STRING", "T_ARRAY", "?"):   # type hints
                self.nxt()
            if self.accept("T_AMPERSAND_FOLLOWED_BY_VAR_OR_VARARG") or self.accept("&"):
                ref = True
            pn = self.expect("T_VARIABLE")[1][1:]
            default = None
            if self.accept("="):
                default = self.expr()
            params.append((pn, default, ref))
            if not self.accept(","):
                break
        self.expect(")")
        if self.accept(":"):
            while self.peek()[0] in ("T_STRING", "T_ARRAY", "?"):
                self.nxt()
        self.expect("{")
        b = self.block_until("}"); self.expect("}")
        node = ("funcdef", name, params, b)
        return node

    # ---- expressions (precedence climbing)
    BIN = {
        "or": 1, "xor": 2, "and": 3,
        "??": 7, "||": 8, "&&": 9, "|": 10, "^": 11, "&": 12,
        "==": 13, "!=": 13, "===": 13, "!==": 13, "<>": 13, "<=>": 13,
        "<": 14, "<=": 14, ">": 14, ">=": 14,
        ".": 15,           # PHP 8: lower than +/- and shifts
        "<<": 16, ">>": 16, "+": 17, "-": 17, "*": 18, "/": 18, "%": 18, "**": 20,
    }
    TOKOP = {"T_BOOLEAN_AND": "&&", "T_BOOLEAN_OR": "||", "T_IS_EQUAL": "==", "T_IS_NOT_EQUAL": "!=", "T_IS_IDENTICAL": "===",
             "T_IS_NOT_IDENTICAL": "!==", "T_IS_SMALLER_OR_EQUAL": "<=", "T_IS_GREATER_OR_EQUAL": ">=", "T_COALESCE": "??",
             "T_SPACESHIP": "<=>", "T_SL": "<<", "T_SR": ">>", "T_POW": "**", "T_LOGICAL_AND": "and", "T_LOGICAL_OR": "or", "T_LOGICAL_XOR": "xor", "T_AMPERSAND_FOLLOWED_BY_VAR_OR_VARARG": "&", "T_AMPERSAND_NOT_FOLLOWED_BY_VAR_OR_VARARG": "&"}
    ASSIGN = {"=": "=", "T_PLUS_EQUAL": "+", "T_MINUS_EQUAL": "-", "T_MUL_EQUAL": "*", "T_DIV_EQUAL": "/", "T_CONCAT_EQUAL": ".",
              "T_MOD_EQUAL": "%", "T_COALESCE_EQUAL": "??"}

    def binop_of(self, tok):
        n, t = tok
        if n in self.TOKOP:
            return self.TOKOP[n]
        if n in self.BIN:
            return n
        return None

    def expr(self, minp=0):
        left = self.unary()
        while True:
            n, t = self.peek()
            if n in self.ASSIGN and left[0] in ("var", "idx"):
                if minp > 6 and False:
                    break
                self.nxt()
                right = self.expr(6)         # right assoc
                left = ("assign", self.ASSIGN[n], left, right)
                continue
            if n == "?" and minp <= 6:
                self.nxt()
                if self.accept(":"):
                    b = self.expr(7); left = ("elvis", left, b)
                else:
                    a = self.expr(7); self.expect(":"); b = self.expr(7)
                    left = ("tern", left, a, b)
                continue
            op = self.binop_of((n, t))
            if op is None:
                break
            p = self.BIN[op]
            if p < minp:
                break
            self.nxt()
            right = self.expr(p if op in ("??", "**") else p + 1)
            left = ("bin", op, left, right)
        return left

    def unary(self):
        n, t = self.peek()
        if n == "!":
            self.nxt(); return ("not", self.expr(19))
        if n == "-":
            self.nxt(); return ("neg", self.expr(19))
        if n == "+":
            self.nxt(); return ("pos", self.expr(19))
        if n == "@":
            self.nxt(); return self.unary()
        if n in ("T_INT_CAST", "T_DOUBLE_CAST", "T_STRING_CAST", "T_ARRAY_CAST", "T_BOOL_CAST"):
            self.nxt(); return ("cast", n, self.expr(19))
        if n in ("T_INC", "T_DEC"):
            self.nxt(); tgt = self.postfix(); return ("incdec", "+" if n == "T_INC" else "-", True, tgt)
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            n, t = self.peek()
            if n == "[":
                self.nxt()
                if self.is_("]"):
                    self.nxt(); e = ("idx", e, None)
                else:
                    k = self.expr(); self.expect("]"); e = ("idx", e, k)
            elif n in ("T_INC", "T_DEC"):
                self.nxt(); e = ("incdec", "+" if n == "T_INC" else "-", False, e)
            else:
                break
        return e

    def primary(self):
        n, t = self.nxt()
        if n == "T_VARIABLE":
            return ("var", t[1:])
        if n == "T_LNUMBER":
            return ("num", int(t, 0) if not t.startswith("0") or t == "0" else int(t, 8))
        if n == "T_DNUMBER":
            return ("num", float(t))
        if n == "T_CONSTANT_ENCAPSED_STRING":
            return ("str", unquote(t))
        if n == '"':
            return self.interp()
        if n == "(":
            e = self.expr(); self.expect(")"); return ("paren", e)
        if n == "[":
            return self.array_lit("]")
        if n == "T_ARRAY":
            self.expect("("); return self.array_lit(")")
        if n == "T_ISSET":
            self.expect("("); es = [self.expr()]
            while self.accept(","):
                es.append(self.expr())
            self.expect(")"); return ("isset", es)
        if n == "T_EMPTY":
            self.expect("("); e = self.expr(); self.expect(")"); return ("empty", e)
        if n == "T_STRING":
            if self.is_("("):
                self.nxt(); args = []
                while not self.is_(")"):
                    args.append(self.expr())
                    if not self.accept(","):
                        break
                self.expect(")")
                return ("call", t, args)
            return ("const", t)
        if n == "T_NS_SEPARATOR":
            return self.primary()
        raise SyntaxError(f"unexpected token {n} {t!r} at {self.i}: {self.t[max(0,self.i-8):self.i+4]}")

    def array_lit(self, end):
        items = []
        while not self.is_(end):
            e = self.expr()
            if self.accept("T_DOUBLE_ARROW"):
                v = self.expr(); items.append((e, v))
            else:
                items.append((None, e))
            if not self.accept(","):
                break
        self.expect(end)
        return ("arr", items)

    def interp(self):
        parts = []
        while not self.is_('"'):
            n, t = self.nxt()
            if n == "T_ENCAPSED_AND_WHITESPACE":
                parts.append(("str", unescape_dq(t)))
            elif n == "T_VARIABLE":
                e = ("var", t[1:])
                if self.is_("["):             # "$a[0]" / "$a[key]" simple syntax
                    self.nxt(); kn, kt = self.nxt()
                    k = ("num", int(kt)) if kn == "T_NUM_STRING" else ("var", kt[1:]) if kn == "T_VARIABLE" else ("str", kt)
                    self.expect("]"); e = ("idx", e, k)
                parts.append(e)
            elif n == "T_CURLY_OPEN":
                e = self.expr(); self.expect("}"); parts.append(e)
            elif n == "T_DOLLAR_OPEN_CURLY_BRACES":
                raise SyntaxError("${ not supported")
            else:
                raise SyntaxError(f"bad interpolation token {n} {t!r}")
        self.expect('"')
        return ("interp", parts)


def unquote(s):
    q = s[0]
    body = s[1:-1]
    if q == "'":
        return body.replace("\\\\", "\0").replace("\\'", "'").replace("\0", "\\")
    return unescape_dq(body)


def unescape_dq(s):
    m = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "$": "$", "e": "\x1b", "v": "\v", "f": "\f"}
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s) and s[i + 1] in m:
            out.append(m[s[i + 1]]); i += 2
        else:
            out.append(c); i += 1
    return "".join(out)


# ------------------------------------------------------------------ emitter
BUILTIN = {  # php name -> runtime function
    "count", "round", "empty", "in_array", "trim", "strtoupper", "strtolower", "is_numeric", "htmlspecialchars", "html_escape",
    "substr", "strpos", "str_replace", "sprintf", "date", "strtotime", "ucwords", "array_fill", "array_key_exists", "array_map",
    "end", "explode", "is_array", "base_url", "base64_encode", "basename", "pathinfo", "is_file", "is_readable", "file_get_contents",
    "function_exists", "implode", "abs", "max", "min", "floor", "ceil", "intval", "floatval", "strlen", "number_format", "is_null",
    "array_values", "array_keys", "str_pad", "array_sum", "array_merge", "array_slice", "ucfirst", "print_r", "str_repeat", "is_string",
    "is_int", "is_float", "array_unique", "array_filter", "array_key_last", "array_search", "mb_strtoupper", "nl2br", "strrev",
}
CONSTS = {"PATHINFO_EXTENSION": "'extension'", "FCPATH": "FCPATH", "PHP_EOL": "'\\n'", "NULL": "None", "null": "None",
          "TRUE": "True", "true": "True", "FALSE": "False", "false": "False", "E_ALL": "0", "ENT_QUOTES": "3", "ENT_HTML5": "48", "ENT_COMPAT": "2", "ENT_NOQUOTES": "0", "PHP_INT_MAX": "9223372036854775807", "SORT_STRING": "2"}


class Emit:
    def __init__(self, userfuncs):
        self.lines = []
        self.ind = 1
        self.userfuncs = userfuncs
        self.tmp = 0
        self.vars = set()
        self.loopstack = []

    def w(self, s):
        self.lines.append("    " * self.ind + s)

    def v(self, name):
        self.vars.add(name)
        return "v_" + name

    # ---- expressions -> python source
    def ex(self, e):
        k = e[0]
        if k == "var":
            return self.v(e[1])
        if k == "num":
            return repr(e[1])
        if k == "str":
            return repr(e[1])
        if k == "paren":
            return "(" + self.ex(e[1]) + ")"
        if k == "interp":
            return "concat(" + ", ".join(self.ex(p) for p in e[1]) + ")"
        if k == "arr":
            parts = []
            for kk, vv in e[1]:
                parts.append(self.ex(vv) if kk is None else f"K({self.ex(kk)}, {self.ex(vv)})")
            return "arr(" + ", ".join(parts) + ")"
        if k == "idx":
            if e[2] is None:
                raise SyntaxError("[] in read context")
            return f"idx({self.ex(e[1])}, {self.ex(e[2])})"
        if k == "const":
            if e[1] in CONSTS:
                return CONSTS[e[1]]
            raise SyntaxError("unknown constant " + e[1])
        if k == "not":
            return f"(not T({self.ex(e[1])}))"
        if k == "neg":
            return f"neg({self.ex(e[1])})"
        if k == "pos":
            return f"to_num({self.ex(e[1])})"
        if k == "cast":
            fn = {"T_INT_CAST": "to_int", "T_DOUBLE_CAST": "to_float", "T_STRING_CAST": "to_str", "T_ARRAY_CAST": "to_arr", "T_BOOL_CAST": "T"}[e[1]]
            return f"{fn}({self.ex(e[2])})"
        if k == "isset":
            return "(" + " and ".join(self.isset1(x) for x in e[1]) + ")"
        if k == "empty":
            return f"(not T({self.quiet(e[1])}))"
        if k == "tern":
            return f"({self.ex(e[2])} if T({self.ex(e[1])}) else {self.ex(e[3])})"
        if k == "elvis":
            t = self.new_tmp()
            return f"({t} if T({t} := {self.ex(e[1])}) else {self.ex(e[2])})"
        if k == "bin":
            return self.binop(e)
        if k == "call":
            return self.call(e)
        if k == "assign":
            return self.assign_expr(e)
        if k == "incdec":
            return self.incdec_expr(e)
        raise SyntaxError("cannot emit expression " + k)

    def new_tmp(self):
        self.tmp += 1
        return f"_t{self.tmp}"

    def quiet(self, e):
        return self.ex(e)           # idx() already yields None for missing keys

    def isset1(self, e):
        return f"(({self.ex(e)}) is not None)"

    def binop(self, e):
        _, op, a, b = e
        A, B = self.ex(a), self.ex(b)
        if op == "&&" or op == "and":
            return f"(T({A}) and T({B}))"
        if op == "||" or op == "or":
            return f"(T({A}) or T({B}))"
        if op == "xor":
            return f"(T({A}) != T({B}))"
        if op == "??":
            t = self.new_tmp()
            return f"({t} if ({t} := {A}) is not None else {B})"
        fn = {"+": "add", "-": "sub", "*": "mul", "/": "div", "%": "mod", ".": "cat", "==": "eq", "!=": "ne", "<>": "ne", "===": "ident",
              "!==": "nident", "<": "lt", "<=": "le", ">": "gt", ">=": "ge", "<=>": "spaceship", "**": "pow_", "<<": "shl", ">>": "shr",
              "&": "band", "|": "bor", "^": "bxor"}[op]
        return f"{fn}({A}, {B})"

    def call(self, e):
        _, name, args = e
        if name == "function_exists":
            return "True"
        if name == "empty":
            return "T(None)"
        if name in self.userfuncs:
            return f"u_{name}(" + ", ".join(self.ex(a) for a in args) + ")"
        if name in BUILTIN:
            return f"f_{name}(" + ", ".join(self.ex(a) for a in args) + ")"
        raise SyntaxError("unknown function " + name)

    # ---- assignment
    def lvalue_path(self, t):
        """('var', root, [key exprs or None])"""
        keys = []
        while t[0] == "idx":
            keys.append(t[2]); t = t[1]
        if t[0] != "var":
            raise SyntaxError("unsupported assignment target")
        keys.reverse()
        return t[1], keys

    def assign_stmt(self, e):
        _, op, tgt, val = e
        root, keys = self.lvalue_path(tgt)
        r = self.v(root)
        V = self.ex(val)
        if not keys:
            self.w(f"{r} = {self.combine(op, r, V)}")
        else:
            kk = "[" + ", ".join("APPEND" if k is None else self.ex(k) for k in keys) + "]"
            cur = self.read_target(r, keys)
            self.w(f"{r} = setidx({r}, {kk}, {self.combine(op, cur, V)})")

    def read_target(self, r, keys):
        s = r
        for k in keys:
            s = f"idx({s}, {self.ex(k)})" if k is not None else "None"
        return s

    def combine(self, op, cur, V):
        if op == "=":
            return V
        if op == "??":
            return f"({cur} if {cur} is not None else {V})"
        fn = {"+": "add", "-": "sub", "*": "mul", "/": "div", ".": "cat", "%": "mod"}[op]
        return f"{fn}({cur}, {V})"

    def assign_expr(self, e):
        _, op, tgt, val = e
        if tgt[0] == "var":
            r = self.v(tgt[1])
            return f"({r} := {self.combine(op, r, self.ex(val))})"
        # assignment to array element inside an expression: use helper that returns the value
        t = self.new_tmp()
        root, keys = self.lvalue_path(tgt)
        r = self.v(root)
        kk = "[" + ", ".join("APPEND" if k is None else self.ex(k) for k in keys) + "]"
        cur = self.read_target(r, keys)
        return f"(({t} := {self.combine(op, cur, self.ex(val))}), ({r} := setidx({r}, {kk}, {t})), {t})[2]"

    def incdec_stmt(self, e):
        _, sign, prefix, tgt = e
        self.assign_stmt(("assign", sign, tgt, ("num", 1)))

    def incdec_expr(self, e):
        _, sign, prefix, tgt = e
        if tgt[0] != "var":
            raise SyntaxError("incdec on array element in expression")
        r = self.v(tgt[1])
        fn = "add" if sign == "+" else "sub"
        if prefix:
            return f"({r} := {fn}({r}, 1))"
        t = self.new_tmp()
        return f"(({t} := {r}), ({r} := {fn}({r}, 1)), {t})[0]"

    # ---- statements
    def stmts(self, ss):
        n0 = len(self.lines)
        for s in ss:
            self.stmt(s)
        if len(self.lines) == n0:
            self.w("pass")

    def stmt(self, s):
        k = s[0]
        if k == "html":
            if s[1]:
                self.w(f"out.append({s[1]!r})")
        elif k == "nop":
            pass
        elif k == "block":
            self.stmts(s[1])
        elif k == "echo":
            for x in s[1]:
                self.w(f"out.append(to_str({self.ex(x)}))")
        elif k == "expr":
            e = s[1]
            if e[0] == "assign":
                self.assign_stmt(e)
            elif e[0] == "incdec":
                self.incdec_stmt(e)
            else:
                self.w(self.ex(e))
        elif k == "if":
            first = True
            for cond, body in s[1]:
                self.w(("if " if first else "elif ") + f"T({self.ex(cond)}):")
                self.ind += 1; self.stmts(body); self.ind -= 1
                first = False
            if s[2] is not None:
                self.w("else:")
                self.ind += 1; self.stmts(s[2]); self.ind -= 1
        elif k == "for":
            _, init, cond, step, body = s
            for i in init:
                self.stmt(("expr", i))
            c = " and ".join(f"T({self.ex(x)})" for x in cond[-1:]) or "True"
            has_cont = contains_continue(body)
            self.w(f"while {c}:")
            self.ind += 1
            if has_cont:
                self.w("try:")
                self.ind += 1; self.loopstack.append("for"); self.stmts(body); self.loopstack.pop(); self.ind -= 1
                self.w("finally:")
                self.ind += 1
                for st in step: self.stmt(("expr", st))
                if not step: self.w("pass")
                self.ind -= 1
            else:
                self.loopstack.append("for"); self.stmts(body); self.loopstack.pop()
                for st in step: self.stmt(("expr", st))
            self.ind -= 1
        elif k == "foreach":
            _, subj, kv, vv, byref, body = s
            S = self.ex(subj)
            kn = self.v(kv[1]) if kv else "_k"
            vn = self.v(vv[1])
            tmp = self.new_tmp()
            if byref:
                tgt = self.ex(subj)
                root, keys = self.lvalue_path(subj)
                self.w(f"{tmp} = {S}")
                self.w(f"for {kn} in list(keys_of({tmp})):")
                self.ind += 1
                self.w(f"{vn} = idx({tmp}, {kn})")
                self.w("try:"); self.ind += 1
                self.loopstack.append("fe"); self.stmts(body); self.loopstack.pop(); self.ind -= 1
                self.w("finally:"); self.ind += 1
                self.w(f"{tmp} = setidx({tmp}, [{kn}], {vn})"); self.ind -= 1
                self.ind -= 1
            else:
                self.w(f"for {kn}, {vn} in items_of({S}):")
                self.ind += 1; self.loopstack.append("fe"); self.stmts(body); self.loopstack.pop(); self.ind -= 1
        elif k == "break":
            self.w("break" if s[1] == 1 else "break  # multi-level")
        elif k == "continue":
            self.w("continue")
        elif k == "return":
            self.w("return " + (self.ex(s[1]) if s[1] is not None else "None"))
        elif k == "funcdef":
            pass  # hoisted
        else:
            raise SyntaxError("stmt " + k)


def contains_continue(body):
    for s in body:
        k = s[0]
        if k == "continue":
            return True
        if k == "if":
            for _, b in s[1]:
                if contains_continue(b): return True
            if s[2] and contains_continue(s[2]): return True
        if k == "block" and contains_continue(s[1]):
            return True
        # continues inside nested loops belong to those loops
    return False


def collect_funcs(stmts, acc):
    for s in stmts:
        k = s[0]
        if k == "funcdef":
            acc.append(s); collect_funcs(s[3], acc)
        elif k == "if":
            for _, b in s[1]: collect_funcs(b, acc)
            if s[2]: collect_funcs(s[2], acc)
        elif k in ("block",):
            collect_funcs(s[1], acc)
        elif k in ("for",):
            collect_funcs(s[4], acc)
        elif k == "foreach":
            collect_funcs(s[5], acc)


def transpile(path):
    toks = tokenize(path)
    p = P(toks)
    prog = p.program()
    funcs = []
    collect_funcs(prog, funcs)
    names = {f[1] for f in funcs}
    out = ["# generated by tools/php2py.py from %s - do not edit" % os.path.basename(path),
           "from app.phpr import *", "", "out = []", ""]
    for f in funcs:
        _, name, params, body = f
        em = Emit(names)
        em.ind = 1
        em.stmts(body)
        sig = ", ".join(f"v_{pn}" + ("=" + Emit(names).ex(d) if d is not None else "=None") for pn, d, r in params)
        out.append(f"def u_{name}({sig}):")
        init = sorted(v for v in em.vars if v not in {pn for pn, _, _ in params})
        for v in init:
            out.append(f"    v_{v} = None")
        out += em.lines
        out.append("    return None")
        out.append("")
    em = Emit(names)
    em.stmts(prog)
    out.append("def render(ctx):")
    out.append("    global out")
    out.append("    out = []")
    for v in sorted(em.vars):
        out.append(f"    v_{v} = ctx.get({v!r})")
    out += em.lines
    out.append("    return ''.join(out)")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    code = transpile(src)
    open(dst, "w").write(code)
    print("wrote", dst, len(code.splitlines()), "lines")
