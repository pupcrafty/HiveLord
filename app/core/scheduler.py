"""Lightweight task scheduler for periodic tasks."""
import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Coroutine, Any

from app.core.logger import log_event
from app.storage.db import get_db_sync
from app.storage.models import SchedulerTask


class Scheduler:
    """Simple task scheduler that can be cancelled."""
    
    def __init__(self, enable_persistence: bool = True):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._one_shot_tasks: Dict[str, asyncio.Task] = {}
        self._cron_tasks: Dict[str, asyncio.Task] = {}
        self._cancelled = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._enable_persistence = enable_persistence
        # Registry for task restoration handlers
        self._restore_handlers: Dict[str, Callable] = {}
    
    def start(self) -> None:
        """Start the scheduler in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        
        self._cancelled = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def _run_loop(self) -> None:
        """Run the asyncio event loop in this thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """Ensure the event loop is running."""
        if self._loop is None or not self._loop.is_running():
            self.start()
            # Wait a bit for loop to start
            import time
            time.sleep(0.1)
        return self._loop
    
    def _save_periodic_task(
        self,
        name: str,
        interval: float,
        handler_type: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> None:
        """Save a periodic task to the database."""
        if not self._enable_persistence:
            return
        
        try:
            db = get_db_sync()
            try:
                # Check if task already exists
                existing = db.query(SchedulerTask).filter(
                    SchedulerTask.task_id == name
                ).first()
                
                if existing:
                    # Update existing
                    existing.task_type = "periodic"
                    existing.name = name
                    existing.status = "scheduled"
                    existing.interval_seconds = interval
                    existing.handler_type = handler_type
                    existing.parameters_json = json.dumps(parameters) if parameters else None
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    # Create new
                    task = SchedulerTask(
                        task_id=name,
                        task_type="periodic",
                        name=name,
                        status="scheduled",
                        interval_seconds=interval,
                        handler_type=handler_type,
                        parameters_json=json.dumps(parameters) if parameters else None
                    )
                    db.add(task)
                
                db.commit()
            except Exception as e:
                db.rollback()
                log_event(
                    source="scheduler",
                    event_type="persistence_error",
                    payload={
                        "action": "save_periodic_task",
                        "task_name": name,
                        "error": str(e)
                    }
                )
            finally:
                db.close()
        except Exception as e:
            log_event(
                source="scheduler",
                event_type="persistence_error",
                payload={
                    "action": "save_periodic_task",
                    "task_name": name,
                    "error": str(e)
                }
            )
    
    def _save_one_shot_task(
        self,
        task_id: str,
        when_dt_utc: datetime,
        name: Optional[str] = None,
        handler_type: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> None:
        """Save a one-shot task to the database."""
        if not self._enable_persistence:
            return
        
        try:
            db = get_db_sync()
            try:
                task = SchedulerTask(
                    task_id=task_id,
                    task_type="one_shot",
                    name=name,
                    status="scheduled",
                    scheduled_for=when_dt_utc,
                    handler_type=handler_type,
                    parameters_json=json.dumps(parameters) if parameters else None
                )
                db.add(task)
                db.commit()
            except Exception as e:
                db.rollback()
                log_event(
                    source="scheduler",
                    event_type="persistence_error",
                    payload={
                        "action": "save_one_shot_task",
                        "task_id": task_id,
                        "error": str(e)
                    }
                )
            finally:
                db.close()
        except Exception as e:
            log_event(
                source="scheduler",
                event_type="persistence_error",
                payload={
                    "action": "save_one_shot_task",
                    "task_id": task_id,
                    "error": str(e)
                }
            )

    def _save_cron_task(
        self,
        task_id: str,
        cron_expression: str,
        timezone_name: str,
        name: Optional[str] = None,
        handler_type: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        next_run_at_utc: Optional[datetime] = None,
    ) -> None:
        """Save or update a cron task definition to the database."""
        if not self._enable_persistence:
            return

        try:
            db = get_db_sync()
            try:
                existing = db.query(SchedulerTask).filter(
                    SchedulerTask.task_id == task_id
                ).first()

                params_json = json.dumps(parameters) if parameters else None
                now = datetime.now(timezone.utc)

                if existing:
                    existing.task_type = "cron"
                    existing.name = name
                    existing.status = "scheduled"
                    existing.handler_type = handler_type
                    existing.parameters_json = params_json
                    # Optional columns (may be absent in older DBs; handled by init_db migration)
                    if hasattr(existing, "cron_expression"):
                        existing.cron_expression = cron_expression
                    if hasattr(existing, "timezone_name"):
                        existing.timezone_name = timezone_name
                    if hasattr(existing, "next_run_at"):
                        existing.next_run_at = next_run_at_utc
                    existing.updated_at = now
                else:
                    task = SchedulerTask(
                        task_id=task_id,
                        task_type="cron",
                        name=name,
                        status="scheduled",
                        handler_type=handler_type,
                        parameters_json=params_json
                    )
                    # Optional columns
                    if hasattr(task, "cron_expression"):
                        task.cron_expression = cron_expression
                    if hasattr(task, "timezone_name"):
                        task.timezone_name = timezone_name
                    if hasattr(task, "next_run_at"):
                        task.next_run_at = next_run_at_utc
                    db.add(task)

                db.commit()
            except Exception as e:
                db.rollback()
                log_event(
                    source="scheduler",
                    event_type="persistence_error",
                    payload={
                        "action": "save_cron_task",
                        "task_id": task_id,
                        "error": str(e)
                    }
                )
            finally:
                db.close()
        except Exception as e:
            log_event(
                source="scheduler",
                event_type="persistence_error",
                payload={
                    "action": "save_cron_task",
                    "task_id": task_id,
                    "error": str(e)
                }
            )
    
    def _update_task_status(
        self,
        task_id: str,
        status: str,
        completed_at: Optional[datetime] = None
    ) -> None:
        """Update task status in the database."""
        if not self._enable_persistence:
            return
        
        try:
            db = get_db_sync()
            try:
                task = db.query(SchedulerTask).filter(
                    SchedulerTask.task_id == task_id
                ).first()
                
                if task:
                    task.status = status
                    task.updated_at = datetime.now(timezone.utc)
                    if completed_at:
                        task.completed_at = completed_at
                    db.commit()
            except Exception as e:
                db.rollback()
                log_event(
                    source="scheduler",
                    event_type="persistence_error",
                    payload={
                        "action": "update_task_status",
                        "task_id": task_id,
                        "error": str(e)
                    }
                )
            finally:
                db.close()
        except Exception as e:
            log_event(
                source="scheduler",
                event_type="persistence_error",
                payload={
                    "action": "update_task_status",
                    "task_id": task_id,
                    "error": str(e)
                }
            )
    
    async def _periodic_task(self, name: str, func: Callable, interval: float) -> None:
        """Run a periodic task."""
        while not self._cancelled:
            try:
                if asyncio.iscoroutinefunction(func):
                    await func()
                else:
                    func()
            except Exception as e:
                log_event(
                    source="scheduler",
                    event_type="task_error",
                    payload={
                        "task_name": name,
                        "error": str(e)
                    }
                )
            
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
    
    def schedule_periodic(
        self,
        name: str,
        func: Callable,
        interval: float,
        handler_type: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Schedule a periodic task.
        
        Args:
            name: Unique name for the task
            func: Function to call (can be async or sync)
            interval: Interval in seconds
            handler_type: Optional handler type identifier for restoration
            parameters: Optional parameters dict for restoration
        """
        loop = self._ensure_loop()
        
        # Cancel existing task with same name
        if name in self._tasks:
            self._tasks[name].cancel()
            self._update_task_status(name, "cancelled")
        
        # Create new task
        task = loop.create_task(self._periodic_task(name, func, interval))
        self._tasks[name] = task
        
        # Save to database
        self._save_periodic_task(name, interval, handler_type, parameters)
        
        log_event(
            source="scheduler",
            event_type="task_scheduled",
            payload={
                "task_name": name,
                "interval": interval
            }
        )
    
    def cancel_periodic_task(self, name: str) -> None:
        """Cancel a specific periodic task."""
        if name in self._tasks:
            self._tasks[name].cancel()
            del self._tasks[name]
            self._update_task_status(name, "cancelled")
            log_event(
                source="scheduler",
                event_type="task_cancelled",
                payload={"task_name": name}
            )
    
    async def _one_shot_task(
        self,
        task_id: str,
        when_dt_utc: datetime,
        coro_fn: Coroutine[Any, Any, None],
        name: Optional[str] = None
    ) -> None:
        """Run a one-shot task at a specific time."""
        now = datetime.now(timezone.utc)
        if when_dt_utc < now:
            log_event(
                source="scheduler",
                event_type="one_shot_rejected_past",
                payload={
                    "task_id": task_id,
                    "when": when_dt_utc.isoformat(),
                    "now": now.isoformat()
                }
            )
            return
        
        # Calculate delay
        delay = (when_dt_utc - now).total_seconds()
        
        log_event(
            source="scheduler",
            event_type="one_shot_scheduled",
            payload={
                "task_id": task_id,
                "name": name,
                "when": when_dt_utc.isoformat(),
                "delay_seconds": delay
            }
        )
        
        try:
            await asyncio.sleep(delay)
            
            # Check if cancelled
            if task_id not in self._one_shot_tasks:
                log_event(
                    source="scheduler",
                    event_type="one_shot_cancelled_before_run",
                    payload={"task_id": task_id}
                )
                return
            
            # Execute the coroutine
            log_event(
                source="scheduler",
                event_type="one_shot_executing",
                payload={"task_id": task_id, "name": name}
            )
            await coro_fn
            
            log_event(
                source="scheduler",
                event_type="one_shot_completed",
                payload={"task_id": task_id, "name": name}
            )
            # Mark as completed in database
            self._update_task_status(task_id, "completed", datetime.now(timezone.utc))
        except asyncio.CancelledError:
            log_event(
                source="scheduler",
                event_type="one_shot_cancelled",
                payload={"task_id": task_id, "name": name}
            )
            raise
        except Exception as e:
            log_event(
                source="scheduler",
                event_type="one_shot_error",
                payload={
                    "task_id": task_id,
                    "name": name,
                    "error": str(e)
                }
            )
            raise
        finally:
            # Remove from tracking
            self._one_shot_tasks.pop(task_id, None)
    
    def schedule_at(
        self,
        when_dt_utc: datetime,
        coro_fn: Coroutine[Any, Any, None],
        name: Optional[str] = None,
        handler_type: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Schedule a one-shot task to run at a specific UTC datetime.
        
        Args:
            when_dt_utc: UTC datetime when the task should run
            coro_fn: Coroutine function to execute
            name: Optional name for the task (for logging)
            handler_type: Optional handler type identifier for restoration
            parameters: Optional parameters dict for restoration
            
        Returns:
            Task ID (string) that can be used to cancel the task
        """
        loop = self._ensure_loop()
        
        # Generate unique task ID
        task_id = str(uuid.uuid4())
        
        # Validate time is in the future
        now = datetime.now(timezone.utc)
        if when_dt_utc < now:
            raise ValueError(f"Cannot schedule task in the past: {when_dt_utc} < {now}")
        
        # Create and schedule the task
        self._schedule_one_shot_in_memory(task_id, when_dt_utc, coro_fn, name, loop=loop)
        
        # Save to database
        self._save_one_shot_task(task_id, when_dt_utc, name, handler_type, parameters)
        
        return task_id

    def _schedule_one_shot_in_memory(
        self,
        task_id: str,
        when_dt_utc: datetime,
        coro_fn: Coroutine[Any, Any, None],
        name: Optional[str],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Schedule a one-shot task in-memory without touching persistence."""
        loop = loop or self._ensure_loop()
        task = loop.create_task(
            self._one_shot_task(task_id, when_dt_utc, coro_fn, name)
        )
        self._one_shot_tasks[task_id] = task

    def restore_one_shot_in_memory(
        self,
        task_id: str,
        when_dt_utc: datetime,
        coro_fn: Coroutine[Any, Any, None],
        name: Optional[str] = None,
    ) -> None:
        """Restore a persisted one-shot task into the in-memory scheduler (no DB insert)."""
        # Avoid duplicating if already scheduled in-memory
        if task_id in self._one_shot_tasks:
            return
        self._schedule_one_shot_in_memory(task_id, when_dt_utc, coro_fn, name)

    async def _cron_loop(
        self,
        task_id: str,
        cron_expression: str,
        timezone_name: str,
        handler_type: str,
        parameters: Dict[str, Any],
        name: Optional[str] = None,
    ) -> None:
        """Run a cron-based recurring task: compute next occurrence, sleep, execute, repeat."""
        # Local imports to keep optional deps localized
        from croniter import croniter
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(timezone_name)

        while not self._cancelled:
            now_local = datetime.now(tz)
            itr = croniter(cron_expression, now_local)
            next_local = itr.get_next(datetime)
            # Ensure tz-aware
            if next_local.tzinfo is None:
                next_local = next_local.replace(tzinfo=tz)
            next_utc = next_local.astimezone(timezone.utc)

            # Persist next_run_at for observability (best-effort)
            try:
                if self._enable_persistence:
                    db = get_db_sync()
                    try:
                        task = db.query(SchedulerTask).filter(SchedulerTask.task_id == task_id).first()
                        if task and hasattr(task, "next_run_at"):
                            task.next_run_at = next_utc
                            task.updated_at = datetime.now(timezone.utc)
                            db.commit()
                    finally:
                        db.close()
            except Exception:
                pass

            delay = (next_utc - datetime.now(timezone.utc)).total_seconds()
            if delay > 0:
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    break

            if self._cancelled:
                break

            # Execute via registered handler
            if handler_type not in self._restore_handlers:
                log_event(
                    source="scheduler",
                    event_type="cron_handler_missing",
                    payload={"task_id": task_id, "handler_type": handler_type, "name": name},
                )
            else:
                try:
                    log_event(
                        source="scheduler",
                        event_type="cron_executing",
                        payload={
                            "task_id": task_id,
                            "name": name,
                            "handler_type": handler_type,
                            "scheduled_for": next_utc.isoformat(),
                        },
                    )
                    coro = self._restore_handlers[handler_type](parameters)
                    await coro

                    # Update last_run_at (best-effort)
                    try:
                        if self._enable_persistence:
                            db = get_db_sync()
                            try:
                                task = db.query(SchedulerTask).filter(SchedulerTask.task_id == task_id).first()
                                if task:
                                    if hasattr(task, "last_run_at"):
                                        task.last_run_at = datetime.now(timezone.utc)
                                    task.updated_at = datetime.now(timezone.utc)
                                    db.commit()
                            finally:
                                db.close()
                    except Exception:
                        pass

                    log_event(
                        source="scheduler",
                        event_type="cron_completed",
                        payload={"task_id": task_id, "name": name},
                    )
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log_event(
                        source="scheduler",
                        event_type="cron_error",
                        payload={"task_id": task_id, "name": name, "error": str(e)},
                    )

    def schedule_cron(
        self,
        task_id: str,
        cron_expression: str,
        timezone_name: str,
        handler_type: str,
        parameters: Dict[str, Any],
        name: Optional[str] = None,
        persist: bool = True,
    ) -> None:
        """Schedule a cron-based recurring task (Option A)."""
        loop = self._ensure_loop()

        # Cancel existing cron task with same id
        if task_id in self._cron_tasks:
            self._cron_tasks[task_id].cancel()
            del self._cron_tasks[task_id]
            if persist:
                self._update_task_status(task_id, "cancelled")

        # Compute next run for persistence/UI visibility (best-effort)
        next_run_utc = None
        try:
            from croniter import croniter
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(timezone_name)
            now_local = datetime.now(tz)
            next_local = croniter(cron_expression, now_local).get_next(datetime)
            if next_local.tzinfo is None:
                next_local = next_local.replace(tzinfo=tz)
            next_run_utc = next_local.astimezone(timezone.utc)
        except Exception:
            next_run_utc = None

        if persist:
            self._save_cron_task(
                task_id=task_id,
                cron_expression=cron_expression,
                timezone_name=timezone_name,
                name=name,
                handler_type=handler_type,
                parameters=parameters,
                next_run_at_utc=next_run_utc,
            )

        task = loop.create_task(
            self._cron_loop(task_id, cron_expression, timezone_name, handler_type, parameters, name=name)
        )
        self._cron_tasks[task_id] = task

        log_event(
            source="scheduler",
            event_type="cron_scheduled",
            payload={
                "task_id": task_id,
                "name": name,
                "cron": cron_expression,
                "timezone": timezone_name,
                "next_run_at_utc": next_run_utc.isoformat() if next_run_utc else None,
            },
        )
    
    def cancel_one_shot_task(self, task_id: str) -> bool:
        """
        Cancel a scheduled one-shot task.
        
        Args:
            task_id: Task ID returned from schedule_at
            
        Returns:
            True if task was found and cancelled, False otherwise
        """
        if task_id in self._one_shot_tasks:
            task = self._one_shot_tasks[task_id]
            task.cancel()
            del self._one_shot_tasks[task_id]
            self._update_task_status(task_id, "cancelled")
            log_event(
                source="scheduler",
                event_type="one_shot_cancelled",
                payload={"task_id": task_id}
            )
            return True
        return False
    
    def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task (tries one-shot first, then periodic).
        
        Args:
            task_id: Task ID or periodic task name
            
        Returns:
            True if task was found and cancelled, False otherwise
        """
        # Try one-shot first
        if self.cancel_one_shot_task(task_id):
            return True
        # Try periodic
        if task_id in self._tasks:
            self.cancel_periodic_task(task_id)
            return True
        return False
    
    def cancel_all(self, persist_db: bool = True) -> None:
        """Cancel all tasks and enter safe mode (optionally persists cancellation to DB)."""
        self._cancelled = True
        for name, task in list(self._tasks.items()):
            task.cancel()
            if persist_db:
                self._update_task_status(name, "cancelled")
        self._tasks.clear()
        
        # Cancel all one-shot tasks
        for task_id, task in list(self._one_shot_tasks.items()):
            task.cancel()
            if persist_db:
                self._update_task_status(task_id, "cancelled")
        self._one_shot_tasks.clear()

        # Cancel all cron tasks
        for task_id, task in list(self._cron_tasks.items()):
            task.cancel()
            if persist_db:
                self._update_task_status(task_id, "cancelled")
        self._cron_tasks.clear()
        
        log_event(
            source="scheduler",
            event_type="all_tasks_cancelled",
            payload={"persist_db": persist_db}
        )
    
    def stop(self, persist_db: bool = False) -> None:
        """Stop the scheduler (by default, cancels in-memory tasks without marking DB as cancelled)."""
        self.cancel_all(persist_db=persist_db)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
    
    def register_restore_handler(
        self,
        handler_type: str,
        handler_func: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]
    ) -> None:
        """
        Register a handler function for restoring tasks of a specific type.
        
        Args:
            handler_type: Handler type identifier (e.g., 'discord_schedule_message')
            handler_func: Async function that takes parameters dict and returns a coroutine
        """
        self._restore_handlers[handler_type] = handler_func
    
    def restore_pending_tasks(self) -> Dict[str, Any]:
        """
        Restore pending tasks from the database using registered handlers.
        
        Returns:
            Dictionary with restoration results
        """
        pending = self.load_pending_tasks()
        restored = {"periodic": 0, "one_shot": 0, "failed": 0, "errors": []}
        
        # Restore periodic tasks
        for task in pending["periodic"]:
            try:
                # For periodic tasks, we need the handler to return a callable
                # This is more complex, so we'll skip automatic restoration for now
                # They can be manually restored by the application
                log_event(
                    source="scheduler",
                    event_type="periodic_task_restore_skipped",
                    payload={"task_id": task["task_id"], "name": task["name"]}
                )
            except Exception as e:
                restored["failed"] += 1
                restored["errors"].append(f"Periodic task {task['task_id']}: {str(e)}")
        
        # Restore one-shot tasks
        for task in pending["one_shot"]:
            try:
                handler_type = task.get("handler_type")
                if not handler_type or handler_type not in self._restore_handlers:
                    log_event(
                        source="scheduler",
                        event_type="one_shot_task_restore_skipped",
                        payload={
                            "task_id": task["task_id"],
                            "reason": "no_handler" if not handler_type else f"handler_not_registered: {handler_type}"
                        }
                    )
                    continue
                
                # Get the handler and create the coroutine
                handler_func = self._restore_handlers[handler_type]
                parameters = task.get("parameters") or {}
                coro = handler_func(parameters)
                
                # Reschedule the task
                when_dt = task["scheduled_for"]
                if isinstance(when_dt, str):
                    when_dt = datetime.fromisoformat(when_dt.replace("Z", "+00:00"))
                
                # Ensure timezone-aware
                if when_dt.tzinfo is None:
                    when_dt = when_dt.replace(tzinfo=timezone.utc)
                else:
                    when_dt = when_dt.astimezone(timezone.utc)
                
                # Only restore if still in the future
                now = datetime.now(timezone.utc)
                if when_dt > now:
                    # Restore in-memory WITHOUT inserting a new DB row (use original task_id)
                    self.restore_one_shot_in_memory(
                        task_id=task["task_id"],
                        when_dt_utc=when_dt,
                        coro_fn=coro,
                        name=task.get("name"),
                    )
                    restored["one_shot"] += 1
                    log_event(
                        source="scheduler",
                        event_type="one_shot_task_restored",
                        payload={"task_id": task["task_id"]}
                    )
                else:
                    # Task is in the past, mark as completed
                    self._update_task_status(task["task_id"], "completed", now)
                    log_event(
                        source="scheduler",
                        event_type="one_shot_task_expired",
                        payload={"task_id": task["task_id"], "scheduled_for": when_dt.isoformat()}
                    )
            except Exception as e:
                restored["failed"] += 1
                restored["errors"].append(f"One-shot task {task.get('task_id', 'unknown')}: {str(e)}")
                log_event(
                    source="scheduler",
                    event_type="task_restore_error",
                    payload={
                        "task_id": task.get("task_id"),
                        "error": str(e)
                    }
                )

        # Restore cron tasks
        for task in pending.get("cron", []):
            try:
                handler_type = task.get("handler_type")
                cron_expression = task.get("cron_expression")
                timezone_name = task.get("timezone_name") or "UTC"
                if not cron_expression:
                    log_event(
                        source="scheduler",
                        event_type="cron_task_restore_skipped",
                        payload={"task_id": task.get("task_id"), "reason": "missing_cron_expression"},
                    )
                    continue
                if not handler_type or handler_type not in self._restore_handlers:
                    log_event(
                        source="scheduler",
                        event_type="cron_task_restore_skipped",
                        payload={
                            "task_id": task.get("task_id"),
                            "reason": "no_handler" if not handler_type else f"handler_not_registered: {handler_type}",
                        },
                    )
                    continue

                self.schedule_cron(
                    task_id=task["task_id"],
                    cron_expression=cron_expression,
                    timezone_name=timezone_name,
                    handler_type=handler_type,
                    parameters=task.get("parameters") or {},
                    name=task.get("name"),
                    # Avoid flipping DB state just because we restored it
                    persist=False,
                )
                restored["periodic"] += 0
                restored["one_shot"] += 0
                # Track cron restorations in 'periodic' bucket? keep separate count via log
                log_event(
                    source="scheduler",
                    event_type="cron_task_restored",
                    payload={"task_id": task["task_id"], "cron": cron_expression, "timezone": timezone_name},
                )
            except Exception as e:
                restored["failed"] += 1
                restored["errors"].append(f"Cron task {task.get('task_id', 'unknown')}: {str(e)}")
                log_event(
                    source="scheduler",
                    event_type="task_restore_error",
                    payload={
                        "task_id": task.get("task_id"),
                        "error": str(e)
                    }
                )
        
        log_event(
            source="scheduler",
            event_type="tasks_restored",
            payload=restored
        )
        
        return restored
    
    def load_pending_tasks(self) -> Dict[str, Any]:
        """
        Load pending tasks from the database.
        
        Returns:
            Dictionary with 'periodic' and 'one_shot' lists of task records
        """
        if not self._enable_persistence:
            return {"periodic": [], "one_shot": []}
        
        try:
            db = get_db_sync()
            try:
                # Load pending periodic tasks
                periodic_tasks = db.query(SchedulerTask).filter(
                    SchedulerTask.task_type == "periodic",
                    SchedulerTask.status == "scheduled"
                ).all()
                
                # Load pending one-shot tasks (only future ones)
                now = datetime.now(timezone.utc)
                one_shot_tasks = db.query(SchedulerTask).filter(
                    SchedulerTask.task_type == "one_shot",
                    SchedulerTask.status == "scheduled",
                    SchedulerTask.scheduled_for > now
                ).all()
                
                # Optional cron tasks (status scheduled)
                cron_tasks = db.query(SchedulerTask).filter(
                    SchedulerTask.task_type == "cron",
                    SchedulerTask.status == "scheduled",
                ).all()

                result = {
                    "periodic": [
                        {
                            "task_id": t.task_id,
                            "name": t.name,
                            "interval_seconds": t.interval_seconds,
                            "handler_type": t.handler_type,
                            "parameters": json.loads(t.parameters_json) if t.parameters_json else None
                        }
                        for t in periodic_tasks
                    ],
                    "one_shot": [
                        {
                            "task_id": t.task_id,
                            "name": t.name,
                            "scheduled_for": t.scheduled_for,
                            "handler_type": t.handler_type,
                            "parameters": json.loads(t.parameters_json) if t.parameters_json else None
                        }
                        for t in one_shot_tasks
                    ],
                    "cron": [
                        {
                            "task_id": t.task_id,
                            "name": t.name,
                            "cron_expression": getattr(t, "cron_expression", None),
                            "timezone_name": getattr(t, "timezone_name", None),
                            "handler_type": t.handler_type,
                            "parameters": json.loads(t.parameters_json) if t.parameters_json else None,
                        }
                        for t in cron_tasks
                    ],
                }
                
                log_event(
                    source="scheduler",
                    event_type="tasks_loaded",
                    payload={
                        "periodic_count": len(result["periodic"]),
                        "one_shot_count": len(result["one_shot"]),
                        "cron_count": len(result["cron"]),
                    }
                )
                
                return result
            except Exception as e:
                log_event(
                    source="scheduler",
                    event_type="persistence_error",
                    payload={
                        "action": "load_pending_tasks",
                        "error": str(e)
                    }
                )
                return {"periodic": [], "one_shot": []}
            finally:
                db.close()
        except Exception as e:
            log_event(
                source="scheduler",
                event_type="persistence_error",
                payload={
                    "action": "load_pending_tasks",
                    "error": str(e)
                }
            )
            return {"periodic": [], "one_shot": []}
    
    def get_status(self) -> dict:
        """
        Get current scheduler status including all tasks.
        
        Returns:
            Dictionary with scheduler status and task information
        """
        periodic_tasks = []
        for name, task in self._tasks.items():
            periodic_tasks.append({
                "name": name,
                "status": "running" if not task.done() else "done",
                "cancelled": task.cancelled(),
                "exception": str(task.exception()) if task.done() and task.exception() else None
            })
        
        one_shot_tasks = []
        for task_id, task in self._one_shot_tasks.items():
            one_shot_tasks.append({
                "task_id": task_id,
                "status": "scheduled" if not task.done() else "done",
                "cancelled": task.cancelled(),
                "exception": str(task.exception()) if task.done() and task.exception() else None
            })
        
        return {
            "running": self._loop is not None and self._loop.is_running(),
            "cancelled": self._cancelled,
            "periodic_tasks": periodic_tasks,
            "one_shot_tasks": one_shot_tasks,
            "periodic_count": len(periodic_tasks),
            "one_shot_count": len(one_shot_tasks)
        }


# Global scheduler instance
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


