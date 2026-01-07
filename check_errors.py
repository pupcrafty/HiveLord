"""Check recent error logs from database."""
from app.storage.db import get_db_sync
from app.storage.models import Event
from sqlalchemy import desc
import json

db = get_db_sync()
try:
    # Get recent errors from dom_bot
    errors = db.query(Event).filter(
        Event.source == "dom_bot",
        Event.type == "error"
    ).order_by(desc(Event.ts)).limit(5).all()
    
    print(f"Found {len(errors)} recent errors:")
    print("=" * 60)
    
    for i, error in enumerate(errors, 1):
        print(f"\nError {i} (at {error.ts}):")
        try:
            payload = json.loads(error.payload_json)
            print(f"  Error type: {payload.get('error_type', 'unknown')}")
            print(f"  Error message: {payload.get('error', 'unknown')}")
            if 'error_details' in payload:
                print(f"  Error details: {json.dumps(payload['error_details'], indent=2)}")
            if 'error_body' in payload and payload['error_body']:
                print(f"  Error body: {payload['error_body']}")
            if 'using_structured_output' in payload:
                print(f"  Using structured output: {payload['using_structured_output']}")
            if 'using_tools' in payload:
                print(f"  Using tools: {payload['using_tools']}")
        except Exception as e:
            print(f"  Could not parse payload: {e}")
            print(f"  Raw payload: {error.payload_json[:500]}")
        print("-" * 60)
finally:
    db.close()

