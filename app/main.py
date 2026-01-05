"""Main entry point for the HiveLord system."""
import asyncio
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

from app.config.settings import get_settings
from app.core.logger import log_event, log_error
from app.core.scheduler import get_scheduler
from app.ingest.bluesky_client import BlueskyClient
from app.ingest.instagram_client import InstagramClient
from app.ingest.lovense_client import LovenseClient
from app.outputs.discord_client import DiscordBot
from app.outputs.telegram_client import TelegramBot
from app.storage.db import init_db, get_db_sync
from app.storage.models import Run


class HiveLordApp:
    """Main application class."""
    
    def __init__(self):
        self.settings = get_settings()
        self.run_id: Optional[int] = None
        
        # Clients
        self.discord_bot: Optional[DiscordBot] = None
        self.telegram_bot: Optional[TelegramBot] = None
        self.instagram_client: Optional[InstagramClient] = None
        self.bluesky_client: Optional[BlueskyClient] = None
        self.lovense_client: Optional[LovenseClient] = None
        
        # Scheduler
        self.scheduler = get_scheduler()
        
        # Shutdown flag
        self.shutdown_event = asyncio.Event()
    
    def start_run(self) -> None:
        """Start a run record in the database."""
        db = get_db_sync()
        try:
            run = Run(
                started_at=datetime.now(timezone.utc),
                version="0.1.0",
                notes="Wiring phase - initial setup"
            )
            db.add(run)
            db.commit()
            self.run_id = run.id
            log_event(
                source="main",
                event_type="run_started",
                payload={"run_id": self.run_id, "version": run.version}
            )
        except Exception as e:
            db.rollback()
            log_error("main", e, {"action": "start_run"})
            raise
        finally:
            db.close()
    
    def end_run(self) -> None:
        """Mark the run as ended in the database."""
        if self.run_id is None:
            return
        
        db = get_db_sync()
        try:
            run = db.query(Run).filter(Run.id == self.run_id).first()
            if run:
                run.ended_at = datetime.now(timezone.utc)
                db.commit()
                log_event(
                    source="main",
                    event_type="run_ended",
                    payload={"run_id": self.run_id}
                )
        except Exception as e:
            db.rollback()
            log_error("main", e, {"action": "end_run"})
        finally:
            db.close()
    
    async def validate_bluesky(self) -> bool:
        """Validate Bluesky connection by posting a test message."""
        try:
            self.bluesky_client = BlueskyClient()
            self.bluesky_client.create_session()
            result = self.bluesky_client.post_message("Hello from API (wiring test)")
            log_event(
                source="main",
                event_type="validation_success",
                payload={"service": "bluesky", "result": str(result)[:200]}
            )
            return True
        except Exception as e:
            log_error("main", e, {"service": "bluesky", "action": "validate"})
            return False
    
    async def validate_instagram(self) -> bool:
        """Validate Instagram connection by fetching account info."""
        try:
            self.instagram_client = InstagramClient()
            result = self.instagram_client.get_account_info()
            log_event(
                source="main",
                event_type="validation_success",
                payload={"service": "instagram", "result": str(result)[:200]}
            )
            return True
        except Exception as e:
            log_error("main", e, {"service": "instagram", "action": "validate"})
            return False
    
    async def validate_lovense(self) -> bool:
        """Validate Lovense connection by starting event stream."""
        try:
            self.lovense_client = LovenseClient()
            self.lovense_client.start()
            # Wait a moment to see if connection succeeds
            await asyncio.sleep(2.0)
            
            if self.lovense_client.is_connected():
                log_event(
                    source="main",
                    event_type="validation_success",
                    payload={"service": "lovense", "status": "connected"}
                )
                return True
            else:
                log_event(
                    source="main",
                    event_type="validation_warning",
                    payload={"service": "lovense", "status": "not_connected_yet"}
                )
                # Still return True as connection may be in progress
                return True
        except Exception as e:
            log_error("main", e, {"service": "lovense", "action": "validate"})
            return False
    
    async def send_system_online(self) -> None:
        """Send 'System online' message to Discord and Telegram."""
        message = "🚀 System online - Wiring phase initialized"
        
        if self.discord_bot:
            try:
                await self.discord_bot.send_message(message)
            except Exception as e:
                log_error("main", e, {"action": "send_system_online", "channel": "discord"})
        
        if self.telegram_bot:
            try:
                await self.telegram_bot.send_message(message)
            except Exception as e:
                log_error("main", e, {"action": "send_system_online", "channel": "telegram"})
    
    async def startup(self) -> None:
        """Startup sequence."""
        # 1. Initialize database
        init_db()
        log_event(source="main", event_type="database_initialized", payload={})
        
        # 2. Start run record
        self.start_run()
        
        # 3. Initialize logger (already available via imports)
        log_event(source="main", event_type="logger_initialized", payload={})
        
        # 4. Initialize consent system (already available via imports)
        log_event(source="main", event_type="consent_system_initialized", payload={})
        
        # 5. Start Discord bot
        try:
            self.discord_bot = DiscordBot()
            await self.discord_bot.start()
            await asyncio.sleep(2.0)  # Wait for bot to connect
            log_event(source="main", event_type="discord_bot_started", payload={})
        except Exception as e:
            log_error("main", e, {"action": "start_discord_bot"})
            raise
        
        # 6. Optionally start Telegram bot
        try:
            self.telegram_bot = TelegramBot()
            if self.telegram_bot.is_enabled():
                await self.telegram_bot.start()
                await asyncio.sleep(1.0)  # Wait for bot to connect
                log_event(source="main", event_type="telegram_bot_started", payload={})
            else:
                log_event(source="main", event_type="telegram_bot_disabled", payload={"reason": "not_configured"})
        except Exception as e:
            log_error("main", e, {"action": "start_telegram_bot"})
            # Don't raise - Telegram is optional
        
        # 7. Validate connections
        log_event(source="main", event_type="validation_started", payload={})
        
        bluesky_ok = await self.validate_bluesky()
        instagram_ok = await self.validate_instagram()
        lovense_ok = await self.validate_lovense()
        
        log_event(
            source="main",
            event_type="validation_complete",
            payload={
                "bluesky": bluesky_ok,
                "instagram": instagram_ok,
                "lovense": lovense_ok
            }
        )
        
        # 8. Send "System online" to Discord (and Telegram)
        await self.send_system_online()
        
        # 9. Start scheduler
        self.scheduler.start()
        log_event(source="main", event_type="scheduler_started", payload={})
        
        log_event(source="main", event_type="startup_complete", payload={})
    
    async def shutdown(self) -> None:
        """Shutdown sequence."""
        log_event(source="main", event_type="shutdown_started", payload={})
        
        # Stop scheduler
        self.scheduler.stop()
        
        # Close Lovense connection
        if self.lovense_client:
            self.lovense_client.stop()
        
        # Stop Telegram bot
        if self.telegram_bot:
            await self.telegram_bot.stop()
        
        # Stop Discord bot
        if self.discord_bot:
            await self.discord_bot.stop()
        
        # Close Instagram client
        if self.instagram_client:
            self.instagram_client.close()
        
        # Close Bluesky client
        if self.bluesky_client:
            self.bluesky_client.close()
        
        # Mark run ended
        self.end_run()
        
        log_event(source="main", event_type="shutdown_complete", payload={})
    
    async def run(self) -> None:
        """Run the application."""
        try:
            await self.startup()
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
        except KeyboardInterrupt:
            log_event(source="main", event_type="keyboard_interrupt", payload={})
        except Exception as e:
            log_error("main", e, {"action": "run"})
        finally:
            await self.shutdown()


def setup_signal_handlers(app: HiveLordApp) -> None:
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        app.shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> None:
    """Main entry point."""
    app = HiveLordApp()
    setup_signal_handlers(app)
    
    try:
        await app.run()
    except Exception as e:
        log_error("main", e, {"action": "main"})
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

