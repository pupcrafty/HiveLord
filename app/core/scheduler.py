"""Lightweight task scheduler for periodic tasks."""
import asyncio
import threading
from datetime import datetime
from typing import Callable, Dict, Optional

from app.core.logger import log_event


class Scheduler:
    """Simple task scheduler that can be cancelled."""
    
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
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
    
    def cancel_all(self) -> None:
        """Cancel all tasks and enter safe mode."""
        self._cancelled = True
        for name, task in list(self._tasks.items()):
            task.cancel()
        self._tasks.clear()
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


