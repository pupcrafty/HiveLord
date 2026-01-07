"""SQLAlchemy models for database tables."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
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


class Memory(Base):
    """Stores key-value memory entries for the Dom Bot."""
    
    __tablename__ = "memory"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class SchedulerTask(Base):
    """Stores scheduler tasks for persistence across restarts."""
    
    __tablename__ = "scheduler_tasks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 'periodic' or 'one_shot'
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduled", index=True)  # 'scheduled', 'completed', 'cancelled'
    
    # For periodic tasks
    interval_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    # For one-shot tasks
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # For cron tasks (Option A)
    cron_expression: Mapped[Optional[str]] = mapped_column(Text, nullable=True, index=True)
    timezone_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    
    # Task parameters stored as JSON (for restoring task execution context)
    parameters_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Handler identifier (e.g., 'discord_schedule_message', 'bsky_schedule_post')
    handler_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


