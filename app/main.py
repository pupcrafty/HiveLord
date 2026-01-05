"""Main entry point for the HiveLord system."""
import asyncio
import signal
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Literal

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
        
        # Module status tracking: enabled, disabled, failed, active
        self.module_status: Dict[str, Literal["enabled", "disabled", "failed", "active"]] = {}
    
    def start_run(self) -> bool:
        """Start a run record in the database. Returns True if successful."""
        if not self.settings.enable_database:
            self.module_status["database"] = "disabled"
            log_event(
                source="main",
                event_type="database_disabled",
                payload={"reason": "enable_database=False"}
            )
            return False
        
        try:
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
                self.module_status["database"] = "active"
                log_event(
                    source="main",
                    event_type="run_started",
                    payload={"run_id": self.run_id, "version": run.version}
                )
                return True
            except Exception as e:
                db.rollback()
                log_error("main", e, {"action": "start_run"})
                self.module_status["database"] = "failed"
                return False
            finally:
                db.close()
        except Exception as e:
            log_error("main", e, {"action": "init_database"})
            self.module_status["database"] = "failed"
            return False
    
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
    
    async def initialize_bluesky(self) -> bool:
        """Initialize Bluesky client. Returns True if successful."""
        if not self.settings.enable_bluesky:
            self.module_status["bluesky"] = "disabled"
            log_event(
                source="main",
                event_type="bluesky_disabled",
                payload={"reason": "enable_bluesky=False"}
            )
            return False
        
        try:
            client = BlueskyClient()
            if not client.is_enabled():
                self.module_status["bluesky"] = "disabled"
                log_event(
                    source="main",
                    event_type="bluesky_disabled",
                    payload={"reason": "missing_configuration"}
                )
                return False
            
            client.create_session()
            self.bluesky_client = client
            self.module_status["bluesky"] = "active"
            log_event(
                source="main",
                event_type="bluesky_initialized",
                payload={}
            )
            return True
        except Exception as e:
            self.module_status["bluesky"] = "failed"
            log_error("main", e, {"service": "bluesky", "action": "initialize"})
            log_event(
                source="main",
                event_type="bluesky_failed",
                payload={"error": str(e)[:200]}
            )
            return False
    
    async def initialize_instagram(self) -> bool:
        """Initialize Instagram client. Returns True if successful."""
        if not self.settings.enable_instagram:
            self.module_status["instagram"] = "disabled"
            log_event(
                source="main",
                event_type="instagram_disabled",
                payload={"reason": "enable_instagram=False"}
            )
            return False
        
        try:
            client = InstagramClient()
            if not client.is_enabled():
                self.module_status["instagram"] = "disabled"
                log_event(
                    source="main",
                    event_type="instagram_disabled",
                    payload={"reason": "missing_configuration"}
                )
                return False
            
            # Just initialize, don't validate yet
            self.instagram_client = client
            self.module_status["instagram"] = "active"
            log_event(
                source="main",
                event_type="instagram_initialized",
                payload={}
            )
            return True
        except Exception as e:
            self.module_status["instagram"] = "failed"
            log_error("main", e, {"service": "instagram", "action": "initialize"})
            log_event(
                source="main",
                event_type="instagram_failed",
                payload={"error": str(e)[:200]}
            )
            return False
    
    async def initialize_lovense(self) -> bool:
        """Initialize Lovense client. Returns True if successful."""
        if not self.settings.enable_lovense:
            self.module_status["lovense"] = "disabled"
            log_event(
                source="main",
                event_type="lovense_disabled",
                payload={"reason": "enable_lovense=False"}
            )
            return False
        
        try:
            client = LovenseClient()
            if not client.is_enabled():
                self.module_status["lovense"] = "disabled"
                log_event(
                    source="main",
                    event_type="lovense_disabled",
                    payload={"reason": "missing_configuration"}
                )
                return False
            
            client.start()
            # Wait a moment to see if connection succeeds
            await asyncio.sleep(2.0)
            
            if client.is_connected():
                self.lovense_client = client
                self.module_status["lovense"] = "active"
                log_event(
                    source="main",
                    event_type="lovense_initialized",
                    payload={"status": "connected"}
                )
                return True
            else:
                # Still mark as active if enabled, connection may be in progress
                self.lovense_client = client
                self.module_status["lovense"] = "active"
                log_event(
                    source="main",
                    event_type="lovense_initialized",
                    payload={"status": "connecting"}
                )
                return True
        except Exception as e:
            self.module_status["lovense"] = "failed"
            log_error("main", e, {"service": "lovense", "action": "initialize"})
            log_event(
                source="main",
                event_type="lovense_failed",
                payload={"error": str(e)[:200]}
            )
            return False
    
    async def send_system_online(self) -> None:
        """Send 'System online' message to Discord and Telegram."""
        message = "🚀 System online - Wiring phase initialized"
        
        print("[MAIN DEBUG] ===== SENDING SYSTEM ONLINE MESSAGE =====")
        # Discord message is sent automatically via on_ready callback (registered in startup)
        # Only send to Telegram here
        if self.telegram_bot:
            try:
                await self.telegram_bot.send_message(message)
            except Exception as e:
                log_error("main", e, {"action": "send_system_online", "channel": "telegram"})
    
    async def startup(self) -> None:
        """Startup sequence - each module can fail gracefully."""
        log_event(source="main", event_type="startup_started", payload={})
        
        # 1. Initialize database (optional)
        if self.settings.enable_database:
            try:
                init_db()
                log_event(source="main", event_type="database_initialized", payload={})
            except Exception as e:
                log_error("main", e, {"action": "init_database"})
                self.module_status["database"] = "failed"
                log_event(
                    source="main",
                    event_type="database_failed",
                    payload={"error": str(e)[:200]}
                )
        else:
            self.module_status["database"] = "disabled"
        
        # 2. Start run record (if database is available)
        if self.settings.enable_database:
            self.start_run()
        
        # 3. Initialize logger (always available via imports)
        log_event(source="main", event_type="logger_initialized", payload={})
        
        # 4. Initialize consent system (always available via imports)
        log_event(source="main", event_type="consent_system_initialized", payload={})
        
        # 5. Start Discord bot (can fail gracefully)
        print("[MAIN DEBUG] ===== INITIALIZING DISCORD BOT =====")
        if self.settings.enable_discord:
            print("[MAIN DEBUG] Discord is enabled in settings")
            try:
                print("[MAIN DEBUG] Creating DiscordBot instance...")
                bot = DiscordBot()
                print("[MAIN DEBUG] Checking if bot is enabled...")
                if bot.is_enabled():
                    print("[MAIN DEBUG] Bot is enabled, starting bot...")
                    self.discord_bot = bot
                    # Register the first message to be sent when ready
                    self.discord_bot.register_first_message("🚀 System online - Wiring phase initialized")
                    await self.discord_bot.start()
                    print("[MAIN DEBUG] Bot start() called, bot will send message when on_ready fires")
                    self.module_status["discord"] = "active"
                    log_event(source="main", event_type="discord_bot_started", payload={})
                    print("[MAIN DEBUG] Discord bot marked as active")
                else:
                    print("[MAIN DEBUG] Bot is not enabled (missing configuration)")
                    self.module_status["discord"] = "disabled"
                    log_event(
                        source="main",
                        event_type="discord_bot_disabled",
                        payload={"reason": "missing_configuration"}
                    )
            except Exception as e:
                print(f"[MAIN DEBUG] ERROR starting Discord bot: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                self.module_status["discord"] = "failed"
                log_error("main", e, {"action": "start_discord_bot"})
                log_event(
                    source="main",
                    event_type="discord_bot_failed",
                    payload={"error": str(e)[:200]}
                )
        else:
            print("[MAIN DEBUG] Discord is disabled in settings")
            self.module_status["discord"] = "disabled"
            log_event(
                source="main",
                event_type="discord_bot_disabled",
                payload={"reason": "enable_discord=False"}
            )
        
        # 6. Start Telegram bot (can fail gracefully)
        if self.settings.enable_telegram:
            try:
                bot = TelegramBot()
                if bot.is_enabled():
                    self.telegram_bot = bot
                    await self.telegram_bot.start()
                    await asyncio.sleep(1.0)  # Wait for bot to connect
                    self.module_status["telegram"] = "active"
                    log_event(source="main", event_type="telegram_bot_started", payload={})
                else:
                    self.module_status["telegram"] = "disabled"
                    log_event(
                        source="main",
                        event_type="telegram_bot_disabled",
                        payload={"reason": "missing_configuration"}
                    )
            except Exception as e:
                self.module_status["telegram"] = "failed"
                log_error("main", e, {"action": "start_telegram_bot"})
                log_event(
                    source="main",
                    event_type="telegram_bot_failed",
                    payload={"error": str(e)[:200]}
                )
        else:
            self.module_status["telegram"] = "disabled"
            log_event(
                source="main",
                event_type="telegram_bot_disabled",
                payload={"reason": "enable_telegram=False"}
            )
        
        # 7. Initialize ingest clients (can fail gracefully)
        await self.initialize_bluesky()
        await self.initialize_instagram()
        await self.initialize_lovense()
        
        # 8. Send "System online" to available channels (Discord sends via on_ready callback)
        await self.send_system_online()
        
        # 9. Start scheduler (always available)
        try:
            self.scheduler.start()
            self.module_status["scheduler"] = "active"
            log_event(source="main", event_type="scheduler_started", payload={})
        except Exception as e:
            self.module_status["scheduler"] = "failed"
            log_error("main", e, {"action": "start_scheduler"})
            log_event(
                source="main",
                event_type="scheduler_failed",
                payload={"error": str(e)[:200]}
            )
        
        # Log final status
        log_event(
            source="main",
            event_type="startup_complete",
            payload={"module_status": self.module_status}
        )
        
        # Print status summary
        print("\n" + "="*60)
        print("HiveLord Startup Status:")
        print("="*60)
        for module, status in self.module_status.items():
            status_icon = {
                "active": "✓",
                "disabled": "-",
                "failed": "✗"
            }.get(status, "?")
            print(f"  {status_icon} {module.upper()}: {status}")
        print("="*60 + "\n")
    
    async def shutdown(self) -> None:
        """Shutdown sequence - handles missing/failed modules gracefully."""
        log_event(source="main", event_type="shutdown_started", payload={})
        
        # Stop scheduler
        try:
            if self.scheduler:
                self.scheduler.stop()
        except Exception as e:
            log_error("main", e, {"action": "stop_scheduler"})
        
        # Close Lovense connection
        try:
            if self.lovense_client:
                self.lovense_client.stop()
        except Exception as e:
            log_error("main", e, {"action": "stop_lovense"})
        
        # Stop Telegram bot
        try:
            if self.telegram_bot:
                await self.telegram_bot.stop()
        except Exception as e:
            log_error("main", e, {"action": "stop_telegram_bot"})
        
        # Stop Discord bot
        try:
            if self.discord_bot:
                await self.discord_bot.stop()
        except Exception as e:
            log_error("main", e, {"action": "stop_discord_bot"})
        
        # Close Instagram client
        try:
            if self.instagram_client:
                self.instagram_client.close()
        except Exception as e:
            log_error("main", e, {"action": "close_instagram"})
        
        # Close Bluesky client
        try:
            if self.bluesky_client:
                self.bluesky_client.close()
        except Exception as e:
            log_error("main", e, {"action": "close_bluesky"})
        
        # Mark run ended (if database is available)
        if self.settings.enable_database:
            try:
                self.end_run()
            except Exception as e:
                log_error("main", e, {"action": "end_run"})
        
        log_event(source="main", event_type="shutdown_complete", payload={})
    
    async def run(self) -> None:
        """Run the application - startup failures don't crash the app."""
        try:
            await self.startup()
            
            # Even if some modules failed, continue running
            if not any(status == "active" for status in self.module_status.values()):
                log_event(
                    source="main",
                    event_type="warning",
                    payload={"message": "No modules are active, but continuing..."}
                )
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
        except KeyboardInterrupt:
            log_event(source="main", event_type="keyboard_interrupt", payload={})
        except Exception as e:
            log_error("main", e, {"action": "run"})
            # Don't exit - try to continue
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

