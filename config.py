import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(32).hex())
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'data', 'logistic_hub.db')}"
    )
    # Railway / Render usano DATABASE_URL con postgresql://, SQLAlchemy vuole postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)

    _is_pooler = SQLALCHEMY_DATABASE_URI and "pooler.supabase.com" in SQLALCHEMY_DATABASE_URI and ":6543" in SQLALCHEMY_DATABASE_URI

    # Supabase pooler (transaction mode): non supporta prepared statements
    if _is_pooler and "pgbouncer" not in SQLALCHEMY_DATABASE_URI:
        sep = "&" if "?" in SQLALCHEMY_DATABASE_URI else "?"
        SQLALCHEMY_DATABASE_URI += f"{sep}pgbouncer=true"

    # Supabase / cloud Postgres richiedono SSL
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith("postgresql://") and "sslmode" not in SQLALCHEMY_DATABASE_URI:
        sep = "&" if "?" in SQLALCHEMY_DATABASE_URI else "?"
        SQLALCHEMY_DATABASE_URI += f"{sep}sslmode=require"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 5,
        "max_overflow": 5,
    }
    WTF_CSRF_ENABLED = True
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "data", "docs"))
    BACKUP_FOLDER = os.environ.get("BACKUP_FOLDER", os.path.join(BASE_DIR, "data", "backup"))
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
