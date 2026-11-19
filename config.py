"""Application configuration. Values come from the environment or a local .env file (see .env.example).
Nothing secret or school specific is hard-coded here."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env(path):
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except OSError:
        pass


# Secrets live in the git-ignored .secrets/ folder: $SCHOOLINK_ENV, else ./.secrets/.env, else ./.env
for _p in (os.environ.get("SCHOOLINK_ENV"),
           os.path.join(BASE_DIR, ".secrets", ".env"),
           os.path.join(BASE_DIR, ".env")):
    if _p and os.path.isfile(_p):
        _load_env(_p)
        break


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(32).hex()
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = _int("DB_PORT", 3306)
    DB_USER = os.environ.get("DB_USER", "")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "")
    MAX_CONTENT_LENGTH = _int("MAX_UPLOAD_MB", 40) * 1024 * 1024          # one request can never exceed this (uploads, CSV, bulk forms)
    ALLOWED_HOSTS = [h.strip().lower() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]   # public host names; empty = any
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = _int("SESSION_HOURS", 12) * 3600
    PER_PAGE = _int("PER_PAGE", 15)
    # Fallbacks only - the live values are edited in Settings and stored in the database.
    SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "School")
    SCHOOL_TAGLINE = os.environ.get("SCHOOL_TAGLINE", "Report Card System")
    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = _int("PORT", 8120)
    DEBUG = os.environ.get("DEBUG", "0") == "1"
    # Headless Chrome used for PDF export (tabulation / weighted / report card).
    CHROME_BIN = os.environ.get("CHROME_BIN", "")
