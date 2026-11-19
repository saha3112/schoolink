"""Thin PyMySQL helper. One connection per request, dict rows, autocommit off."""
import pymysql
import pymysql.cursors
from flask import g, current_app


def get_db():
    if "db" not in g:
        c = current_app.config
        g.db = pymysql.connect(
            host=c["DB_HOST"], port=c["DB_PORT"], user=c["DB_USER"],
            password=c["DB_PASSWORD"], database=c["DB_NAME"], charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor, autocommit=False,
        )
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass


def query(sql, args=None):
    with get_db().cursor() as cur:
        cur.execute(sql, args or ())
        return list(cur.fetchall())


def one(sql, args=None):
    rows = query(sql, args)
    return rows[0] if rows else None


def scalar(sql, args=None, default=None):
    r = one(sql, args)
    if not r:
        return default
    return next(iter(r.values()))


def execute(sql, args=None, commit=True):
    db = get_db()
    with db.cursor() as cur:
        cur.execute(sql, args or ())
        last = cur.lastrowid
        n = cur.rowcount
    if commit:
        db.commit()
    return last if last else n


def executemany(sql, rows, commit=True):
    db = get_db()
    with db.cursor() as cur:
        cur.executemany(sql, rows)
    if commit:
        db.commit()


def commit():
    get_db().commit()


def rollback():
    get_db().rollback()
