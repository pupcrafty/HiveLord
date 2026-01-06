"""Lightweight task scheduler for periodic tasks."""
import asyncio
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Coroutine, Any

from app.core.logger import log_event


class Scheduler:
    """Simple task scheduler that can be cancelled."""
    
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._one_shot_tasks: Dict[str, asyncio.Task] = {}
        self._cancelled = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
    
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
        interval: float
    ) -> None:
        """
        Schedule a periodic task.
        
        Args:
            name: Unique name for the task
            func: Function to call (can be async or sync)
            interval: Interval in seconds
        """
        loop = self._ensure_loop()
        
        # Cancel existing task with same name
        if name in self._tasks:
            self._tasks[name].cancel()
        
        # Create new task
        task = loop.create_task(self._periodic_task(name, func, interval))
        self._tasks[name] = task
        
        log_event(
            source="scheduler",
            event_type="task_scheduled",
            payload={
                "task_name": name,
                "interval": interval
            }
        )
    
    def cancel_task(self, name: str) -> None:
        """Cancel a specific task."""
        if name in self._tasks:
            self._tasks[name].cancel()
            del self._tasks[name]
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
            await coro_fn()
            
            log_event(
                source="scheduler",
                event_type="one_shot_completed",
                payload={"task_id": task_id, "name": name}
            )
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
        name: Optional[str] = None
    ) -> str:
        """
        Schedule a one-shot task to run at a specific UTC datetime.
        
        Args:
            when_dt_utc: UTC datetime when the task should run
            coro_fn: Coroutine function to execute
            name: Optional name for the task (for logging)
            
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
        task = loop.create_task(
            self._one_shot_task(task_id, when_dt_utc, coro_fn, name)
        )
        self._one_shot_tasks[task_id] = task
        
        return task_id
    
    def cancel_task(self, task_id: str) -> bool:
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
            log_event(
                source="scheduler",
                event_type="one_shot_cancelled",
                payload={"task_id": task_id}
            )
            return True
        return False
    
    def cancel_all(self) -> None:
        """Cancel all tasks and enter safe mode."""
        self._cancelled = True
        for name, task in list(self._tasks.items()):
            task.cancel()
        self._tasks.clear()
        
        # Cancel all one-shot tasks
        for task_id, task in list(self._one_shot_tasks.items()):
            task.cancel()
        self._one_shot_tasks.clear()
        
        log_event(
            source="scheduler",
            event_type="all_tasks_cancelled",
            payload={}
        )
    
    def stop(self) -> None:
        """Stop the scheduler."""
        self.cancel_all()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=1.0)


# Global scheduler instance
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


