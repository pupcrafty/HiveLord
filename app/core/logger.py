"""Event logging system - logs all external interactions to database."""
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.storage.db import get_db_sync
from app.storage.models import Event


# Secrets to redact from logs
SECRET_PATTERNS = [
    r'token["\s:=]+([^\s"\'\),]+)',
    r'password["\s:=]+([^\s"\'\),]+)',
    r'secret["\s:=]+([^\s"\'\),]+)',
    r'api[_-]?key["\s:=]+([^\s"\'\),]+)',
    r'authorization["\s:=]+([^\s"\'\),]+)',
]


def redact_secrets(text: str) -> str:
    """Redact secrets from text."""
    result = text
    for pattern in SECRET_PATTERNS:
        result = re.sub(pattern, r'\1***REDACTED***', result, flags=re.IGNORECASE)
    return result


def log_event(
    source: str,
    event_type: str,
    payload: Dict[str, Any] | None = None,
    db: Session | None = None
) -> None:
    """
    Log an event to the database.
    
    Args:
        source: Source of the event (e.g., 'instagram', 'discord', 'lovense')
        event_type: Type of event (e.g., 'api_request', 'message_sent', 'device_connected')
        payload: Event payload (will be JSON serialized and redacted)
        db: Optional database session (creates new if not provided)
    """
    close_db = False
    if db is None:
        db = get_db_sync()
        close_db = True
    
    try:
        # Prepare payload
        if payload is None:
            payload = {}
        
        # Serialize and redact
        payload_str = json.dumps(payload, default=str)
        payload_str = redact_secrets(payload_str)
        
        # Create event
        event = Event(
            ts=datetime.now(timezone.utc),
            source=source,
            type=event_type,
            payload_json=payload_str
        )
        
        db.add(event)
        db.commit()
    except Exception as e:
        db.rollback()
        # Try to log the error itself
        try:
            error_event = Event(
                ts=datetime.now(timezone.utc),
                source="logger",
                type="log_error",
                payload_json=json.dumps({"error": str(e)}, default=str)
            )
            db.add(error_event)
            db.commit()
        except Exception:
            pass
    finally:
        if close_db:
            db.close()


def log_api_request(source: str, method: str, url: str, status_code: int | None = None) -> None:
    """Log an API request."""
    log_event(
        source=source,
        event_type="api_request",
        payload={
            "method": method,
            "url": url,
            "status_code": status_code
        }
    )


def log_api_response(source: str, status_code: int, response_data: Any | None = None) -> None:
    """Log an API response (sanitized)."""
    payload = {"status_code": status_code}
    if response_data:
        # Only log metadata, not full response
        if isinstance(response_data, dict):
            payload["has_data"] = True
            payload["keys"] = list(response_data.keys())[:10]  # First 10 keys only
        else:
            payload["data_type"] = type(response_data).__name__
    
    log_event(
        source=source,
        event_type="api_response",
        payload=payload
    )


def log_message_sent(channel: str, recipient: str, message_preview: str | None = None) -> None:
    """Log a message sent to Discord/Telegram."""
    payload = {
        "channel": channel,
        "recipient": recipient,
    }
    if message_preview:
        payload["message_preview"] = message_preview[:100]  # First 100 chars
    
    log_event(
        source=channel,
        event_type="message_sent",
        payload=payload
    )


def log_error(source: str, error: Exception | str, context: Dict[str, Any] | None = None) -> None:
    """Log an error."""
    payload = {
        "error": str(error),
        "error_type": type(error).__name__ if isinstance(error, Exception) else "string"
    }
    if context:
        payload.update(context)
    
    log_event(
        source=source,
        event_type="error",
        payload=payload
    )

