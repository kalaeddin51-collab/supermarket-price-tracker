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
    """Add new columns to existing tables without dropping data."""
    new_columns = [
        # (table, column, sql_type, default)
        ("notification_settings", "email_address_2",  "VARCHAR(254)", "NULL"),
        ("notification_settings", "email_address_3",  "VARCHAR(254)", "NULL"),
        ("notification_settings", "poll_frequency",   "VARCHAR(20)",  "'weekly'"),
        ("notification_settings", "poll_day",         "INTEGER",      "0"),
        ("notification_settings", "smtp_user",        "VARCHAR(254)", "NULL"),
        ("notification_settings", "smtp_password",    "VARCHAR(500)", "NULL"),
    ]
    with engine.connect() as conn:
        for table, col, col_type, default in new_columns:
            try:
                conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}"
                    )
                )
                conn.commit()
            except Exception:
                pass  # column already exists
