"""SQLAlchemy models for database tables."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class Run(Base):
    """Tracks system runs/sessions."""
    
    __tablename__ = "runs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    version: Mapped[str] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Event(Base):
    """Logs all external interactions and events."""
    
    __tablename__ = "events"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)


class ConsentLedger(Base):
    """Tracks consent state and gates."""
    
    __tablename__ = "consent_ledger"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False, index=True)
    consent_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_modes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    revoked_topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    armed_until_ts: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


