"""Flask web server for viewing database and scheduler status."""
import json
from datetime import datetime
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template

from app.core.scheduler import get_scheduler
from app.storage.db import get_db_sync
from app.storage.models import Run, Event, ConsentLedger, Memory, SchedulerTask


app = Flask(__name__, template_folder="templates", static_folder="static")


def serialize_datetime(obj: Any) -> str:
    """Convert datetime objects to ISO format strings."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


@app.route("/")
def index():
    """Render the main dashboard page."""
    return render_template("index.html")


@app.route("/api/database/runs")
def get_runs():
    """Get all runs from the database."""
    try:
        db = get_db_sync()
        try:
            runs = db.query(Run).order_by(Run.started_at.desc()).limit(100).all()
            result = []
            for run in runs:
                result.append({
                    "id": run.id,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                    "version": run.version,
                    "notes": run.notes
                })
            return jsonify({"success": True, "data": result, "count": len(result)})
        finally:
            db.close()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/database/events")
def get_events():
    """Get recent events from the database."""
    try:
        db = get_db_sync()
        try:
            events = db.query(Event).order_by(Event.ts.desc()).limit(500).all()
            result = []
            for event in events:
                try:
                    payload = json.loads(event.payload_json) if event.payload_json else {}
                except json.JSONDecodeError:
                    payload = {"raw": event.payload_json}
                
                result.append({
                    "id": event.id,
                    "ts": event.ts.isoformat() if event.ts else None,
                    "source": event.source,
                    "type": event.type,
                    "payload": payload
                })
            return jsonify({"success": True, "data": result, "count": len(result)})
        finally:
            db.close()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/database/consent")
def get_consent():
    """Get consent ledger entries."""
    try:
        db = get_db_sync()
        try:
            entries = db.query(ConsentLedger).order_by(ConsentLedger.ts.desc()).limit(100).all()
            result = []
            for entry in entries:
                try:
                    allowed_modes = json.loads(entry.allowed_modes_json) if entry.allowed_modes_json else []
                except json.JSONDecodeError:
                    allowed_modes = []
                
                try:
                    revoked_topics = json.loads(entry.revoked_topics_json) if entry.revoked_topics_json else []
                except json.JSONDecodeError:
                    revoked_topics = []
                
                result.append({
                    "id": entry.id,
                    "ts": entry.ts.isoformat() if entry.ts else None,
                    "consent_active": entry.consent_active,
                    "allowed_modes": allowed_modes,
                    "revoked_topics": revoked_topics,
                    "armed_until_ts": entry.armed_until_ts.isoformat() if entry.armed_until_ts else None
                })
            return jsonify({"success": True, "data": result, "count": len(result)})
        finally:
            db.close()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/database/memory")
def get_memory():
    """Get memory entries."""
    try:
        db = get_db_sync()
        try:
            memories = db.query(Memory).order_by(Memory.updated_at.desc()).limit(500).all()
            result = []
            for memory in memories:
                try:
                    metadata = json.loads(memory.metadata_json) if memory.metadata_json else {}
                except json.JSONDecodeError:
                    metadata = {}
                
                result.append({
                    "id": memory.id,
                    "key": memory.key,
                    "value": memory.value,
                    "metadata": metadata,
                    "created_at": memory.created_at.isoformat() if memory.created_at else None,
                    "updated_at": memory.updated_at.isoformat() if memory.updated_at else None
                })
            return jsonify({"success": True, "data": result, "count": len(result)})
        finally:
            db.close()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/scheduler/status")
def get_scheduler_status():
    """Get scheduler status and tasks."""
    try:
        scheduler = get_scheduler()
        status = scheduler.get_status()
        return jsonify({"success": True, "data": status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/database/scheduler_tasks")
def get_scheduler_tasks():
    """Get persisted scheduler tasks from the database."""
    try:
        db = get_db_sync()
        try:
            tasks = (
                db.query(SchedulerTask)
                .order_by(SchedulerTask.updated_at.desc())
                .limit(500)
                .all()
            )
            result = []
            for task in tasks:
                try:
                    parameters = json.loads(task.parameters_json) if task.parameters_json else None
                except json.JSONDecodeError:
                    parameters = {"raw": task.parameters_json}

                result.append({
                    "id": task.id,
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "name": task.name,
                    "status": task.status,
                    "interval_seconds": task.interval_seconds,
                    "scheduled_for": task.scheduled_for.isoformat() if task.scheduled_for else None,
                    "cron_expression": task.cron_expression,
                    "timezone_name": task.timezone_name,
                    "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
                    "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                    "handler_type": task.handler_type,
                    "parameters": parameters,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                })
            return jsonify({"success": True, "data": result, "count": len(result)})
        finally:
            db.close()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/database/stats")
def get_database_stats():
    """Get database statistics."""
    try:
        db = get_db_sync()
        try:
            stats = {
                "runs": db.query(Run).count(),
                "events": db.query(Event).count(),
                "consent_entries": db.query(ConsentLedger).count(),
                "memory_entries": db.query(Memory).count(),
                "scheduler_tasks": db.query(SchedulerTask).count(),
            }
            return jsonify({"success": True, "data": stats})
        finally:
            db.close()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def run_server(host: str = "127.0.0.1", port: int = 5000, debug: bool = False):
    """Run the Flask development server."""
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_server(debug=True)

