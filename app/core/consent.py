"""Consent management system with safety gates."""
import json
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy.orm import Session

from app.core.logger import log_event
from app.storage.db import get_db_sync
from app.storage.models import ConsentLedger


# Default consent expiration (10 minutes)
DEFAULT_CONSENT_DURATION = timedelta(minutes=10)


def is_consent_active(db: Session | None = None) -> bool:
    """Check if consent is currently active."""
    close_db = False
    if db is None:
        db = get_db_sync()
        close_db = True
    
    try:
        latest = db.query(ConsentLedger).order_by(ConsentLedger.ts.desc()).first()
        if latest is None:
            return False
        
        if not latest.consent_active:
            return False
        
        # Check if expired
        if latest.armed_until_ts and latest.armed_until_ts < datetime.now(timezone.utc):
            return False
        
        return True
    finally:
        if close_db:
            db.close()


def get_allowed_modes(db: Session | None = None) -> List[str]:
    """Get list of allowed modes/topics."""
    close_db = False
    if db is None:
        db = get_db_sync()
        close_db = True
    
    try:
        latest = db.query(ConsentLedger).order_by(ConsentLedger.ts.desc()).first()
        if latest is None:
            return []
        
        try:
            return json.loads(latest.allowed_modes_json)
        except (json.JSONDecodeError, AttributeError):
            return []
    finally:
        if close_db:
            db.close()


def can_execute_device_command(db: Session | None = None) -> bool:
    """
    Check if device commands can be executed.
    
    Requires:
    - consent_active == true
    - armed_until_ts > now
    - topic "device" is allowed
    """
    close_db = False
    if db is None:
        db = get_db_sync()
        close_db = True
    
    try:
        if not is_consent_active(db):
            return False
        
        latest = db.query(ConsentLedger).order_by(ConsentLedger.ts.desc()).first()
        if latest is None:
            return False
        
        # Check armed_until_ts
        if not latest.armed_until_ts or latest.armed_until_ts < datetime.now(timezone.utc):
            return False
        
        # Check if "device" topic is allowed
        try:
            allowed_modes = json.loads(latest.allowed_modes_json)
            if "device" not in allowed_modes:
                return False
        except (json.JSONDecodeError, AttributeError):
            return False
        
        return True
    finally:
        if close_db:
            db.close()


def arm_consent(
    duration: timedelta = DEFAULT_CONSENT_DURATION,
    allowed_modes: List[str] | None = None,
    db: Session | None = None
) -> None:
    """
    Arm consent for device commands.
    
    Args:
        duration: How long consent should last
        allowed_modes: List of allowed modes/topics (default: ["device"])
        db: Optional database session
    """
    close_db = False
    if db is None:
        db = get_db_sync()
        close_db = True
    
    try:
        if allowed_modes is None:
            allowed_modes = ["device"]
        
        armed_until = datetime.now(timezone.utc) + duration
        
        entry = ConsentLedger(
            ts=datetime.now(timezone.utc),
            consent_active=True,
            allowed_modes_json=json.dumps(allowed_modes),
            revoked_topics_json="[]",
            armed_until_ts=armed_until
        )
        
        db.add(entry)
        db.commit()
        
        log_event(
            source="consent",
            event_type="armed",
            payload={
                "armed_until": armed_until.isoformat(),
                "allowed_modes": allowed_modes
            },
            db=db
        )
    except Exception as e:
        db.rollback()
        log_event(
            source="consent",
            event_type="arm_error",
            payload={"error": str(e)},
            db=db
        )
        raise
    finally:
        if close_db:
            db.close()


def disarm_consent(db: Session | None = None) -> None:
    """Disarm consent (set consent_active to false)."""
    close_db = False
    if db is None:
        db = get_db_sync()
        close_db = True
    
    try:
        entry = ConsentLedger(
            ts=datetime.now(timezone.utc),
            consent_active=False,
            allowed_modes_json="[]",
            revoked_topics_json="[]",
            armed_until_ts=None
        )
        
        db.add(entry)
        db.commit()
        
        log_event(
            source="consent",
            event_type="disarmed",
            payload={},
            db=db
        )
    except Exception as e:
        db.rollback()
        log_event(
            source="consent",
            event_type="disarm_error",
            payload={"error": str(e)},
            db=db
        )
        raise
    finally:
        if close_db:
            db.close()


def safe_mode(db: Session | None = None) -> None:
    """
    Enter SAFE MODE: Disable all consent and clear armed_until_ts.
    
    This function:
    - Sets consent_active = false
    - Clears armed_until_ts
    - Logs the event
    
    Note: Scheduler cancellation must be handled by the caller.
    """
    close_db = False
    if db is None:
        db = get_db_sync()
        close_db = True
    
    try:
        entry = ConsentLedger(
            ts=datetime.now(timezone.utc),
            consent_active=False,
            allowed_modes_json="[]",
            revoked_topics_json="[]",
            armed_until_ts=None
        )
        
        db.add(entry)
        db.commit()
        
        log_event(
            source="consent",
            event_type="safe_mode",
            payload={"message": "SAFE MODE activated - all consent disabled"},
            db=db
        )
    except Exception as e:
        db.rollback()
        log_event(
            source="consent",
            event_type="safe_mode_error",
            payload={"error": str(e)},
            db=db
        )
        raise
    finally:
        if close_db:
            db.close()

