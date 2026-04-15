from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401 — ensures models are registered
    Base.metadata.create_all(bind=engine)

    # ── Schema migrations (SQLite ALTER TABLE for new columns) ───────────
    _migrate_columns()

    # Seed singleton NotificationSettings row if it doesn't exist
    db = SessionLocal()
    try:
        if not db.query(models.NotificationSettings).first():
            db.add(models.NotificationSettings())
            db.commit()
    finally:
        db.close()


def _migrate_columns():
    """Add new columns to existing tables without dropping data.

    Works on both SQLite and PostgreSQL:
    - SQLite: ALTER TABLE t ADD COLUMN c TYPE DEFAULT v
    - PostgreSQL: same syntax but we check column existence first
    """
    import sqlalchemy as _sa

    new_columns = [
        # (table, column, sql_type)
        ("notification_settings", "email_address_2",  "VARCHAR(254)"),
        ("notification_settings", "email_address_3",  "VARCHAR(254)"),
        ("notification_settings", "poll_frequency",   "VARCHAR(20)"),
        ("notification_settings", "poll_day",         "INTEGER"),
        ("notification_settings", "smtp_user",        "VARCHAR(254)"),
        ("notification_settings", "smtp_password",    "VARCHAR(500)"),
        ("notification_settings", "resend_api_key",   "VARCHAR(500)"),
        ("notification_settings", "scraperapi_key",   "VARCHAR(200)"),
        ("watchlist",             "user_id",          "INTEGER"),
        ("shopping_lists",        "user_id",          "INTEGER"),
    ]

    is_postgres = "postgresql" in settings.database_url or "postgres" in settings.database_url

    with engine.connect() as conn:
        for table, col, col_type in new_columns:
            try:
                if is_postgres:
                    # PostgreSQL: check information_schema before altering
                    exists = conn.execute(_sa.text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = :t AND column_name = :c"
                    ), {"t": table, "c": col}).fetchone()
                    if exists:
                        continue
                conn.execute(_sa.text(
                    f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"
                ))
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
