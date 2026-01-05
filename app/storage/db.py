"""Database initialization and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.storage.models import Base


# SQLite database file
DB_FILE = "local.db"
ENGINE = create_engine(f"sqlite:///{DB_FILE}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)


def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=ENGINE)


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

