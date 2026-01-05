"""Database initialization and session management."""
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
    except Exception:
        # Re-raise to allow caller to handle
        raise


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

