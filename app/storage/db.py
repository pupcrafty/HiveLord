"""Database initialization and session management."""
from sqlalchemy import text
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.storage.models import Base


# SQLite database file
DB_FILE = "local.db"
ENGINE = create_engine(f"sqlite:///{DB_FILE}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


def init_db() -> None:
    """Initialize database tables. May raise exceptions on failure."""
    try:
        Base.metadata.create_all(bind=ENGINE)
        _migrate_scheduler_tasks()
    except Exception:
        # Re-raise to allow caller to handle
        raise


def _migrate_scheduler_tasks() -> None:
    """
    Lightweight SQLite migration for added scheduler_tasks columns.
    SQLite can't ALTER COLUMN easily, but it can ADD COLUMN.
    """
    with ENGINE.begin() as conn:
        # If table doesn't exist yet, nothing to migrate (create_all will create it with full schema)
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduler_tasks'")).fetchall()
        if not tables:
            return

        existing_cols = conn.execute(text("PRAGMA table_info(scheduler_tasks)")).fetchall()
        col_names = {row[1] for row in existing_cols}  # row[1] = name

        # New cron-related columns
        if "cron_expression" not in col_names:
            conn.execute(text("ALTER TABLE scheduler_tasks ADD COLUMN cron_expression TEXT"))
        if "timezone_name" not in col_names:
            conn.execute(text("ALTER TABLE scheduler_tasks ADD COLUMN timezone_name VARCHAR(100)"))
        if "last_run_at" not in col_names:
            conn.execute(text("ALTER TABLE scheduler_tasks ADD COLUMN last_run_at DATETIME"))
        if "next_run_at" not in col_names:
            conn.execute(text("ALTER TABLE scheduler_tasks ADD COLUMN next_run_at DATETIME"))


def get_db() -> Session:
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_sync() -> Session:
    """Get a database session (synchronous, callers must close)."""
    return SessionLocal()

