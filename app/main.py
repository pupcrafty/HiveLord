"""Main entry point for the HiveLord system."""
import asyncio
import signal
import sys
from datetime import datetime, timezone
from typing import Optional, Dict, Literal, Tuple

import httpx

from app.config.settings import get_settings
from app.core.logger import log_event, log_error
from app.core.scheduler import get_scheduler
from app.ingest.bluesky_client import BlueskyClient
from app.ingest.lovense_client import LovenseClient
from app.outputs.discord_client import DiscordBot
from app.storage.db import init_db, get_db_sync
from app.storage.models import Run


class HiveLordApp:
    """Main application class."""
    
    def __init__(self):
        self.settings = get_settings()
        self.run_id: Optional[int] = None
        
        # Clients
        self.discord_bot: Optional[DiscordBot] = None
        self.bluesky_client: Optional[BlueskyClient] = None
        self.lovense_client: Optional[LovenseClient] = None
        
        # Scheduler
        self.scheduler = get_scheduler()
        
        # Shutdown flag
        self.shutdown_event = asyncio.Event()
        
        # Module status tracking: enabled, disabled, failed, active
        self.module_status: Dict[str, Literal["enabled", "disabled", "failed", "active"]] = {}
        
        # Test event tracking
        self._test_event_triggered = False
    
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
        print("[MAIN DEBUG] ===== INITIALIZING BLUESKY CLIENT =====")
        if not self.settings.enable_bluesky:
            print("[MAIN DEBUG] Bluesky is disabled in settings")
            self.module_status["bluesky"] = "disabled"
            log_event(
                source="main",
                event_type="bluesky_disabled",
                payload={"reason": "enable_bluesky=False"}
            )
            return False
        
        print("[MAIN DEBUG] Bluesky is enabled in settings")
        try:
            print("[MAIN DEBUG] Creating BlueskyClient instance...")
            client = BlueskyClient()
            print("[MAIN DEBUG] Checking if client is enabled...")
            if not client.is_enabled():
                print("[MAIN DEBUG] Client is not enabled (missing configuration)")
                self.module_status["bluesky"] = "disabled"
                # Check what's missing
                missing = []
                if not self.settings.bsky_handle:
                    missing.append("bsky_handle")
                if not self.settings.bsky_app_password:
                    missing.append("bsky_app_password")
                print(f"[MAIN DEBUG] Missing fields: {missing}")
                log_event(
                    source="main",
                    event_type="bluesky_disabled",
                    payload={
                        "reason": "missing_configuration",
                        "missing_fields": missing
                    }
                )
                return False
            
            print("[MAIN DEBUG] Client is enabled, attempting to create session...")
            # Try to create session
            try:
                client.create_session()
                print("[MAIN DEBUG] Session created successfully!")
            except httpx.HTTPStatusError as e:
                print(f"[MAIN DEBUG] ERROR: HTTPStatusError during session creation")
                print(f"[MAIN DEBUG] Status code: {e.response.status_code if e.response else 'None'}")
                # Extract more details from the error
                error_info = {
                    "status_code": e.response.status_code if e.response else None,
                    "error_type": "HTTPStatusError"
                }
                try:
                    if e.response:
                        error_detail = e.response.json()
                        error_info["error_detail"] = error_detail
                        print(f"[MAIN DEBUG] Error detail (JSON): {error_detail}")
                except Exception:
                    if e.response:
                        error_info["error_text"] = e.response.text[:200]
                        print(f"[MAIN DEBUG] Error detail (text): {error_info['error_text']}")
                
                self.module_status["bluesky"] = "failed"
                log_error("main", e, {
                    "service": "bluesky",
                    "action": "initialize",
                    **error_info
                })
                log_event(
                    source="main",
                    event_type="bluesky_failed",
                    payload={
                        "error": str(e)[:200],
                        **error_info
                    }
                )
                print(f"[MAIN DEBUG] Bluesky initialization FAILED - check error details above")
                return False
            except Exception as e:
                print(f"[MAIN DEBUG] ERROR: Unexpected error during session creation: {type(e).__name__}: {e}")
                self.module_status["bluesky"] = "failed"
                log_error("main", e, {
                    "service": "bluesky",
                    "action": "initialize",
                    "error_type": type(e).__name__
                })
                log_event(
                    source="main",
                    event_type="bluesky_failed",
                    payload={
                        "error": str(e)[:200],
                        "error_type": type(e).__name__
                    }
                )
                return False
            
            print("[MAIN DEBUG] Storing Bluesky client instance...")
            self.bluesky_client = client
            self.module_status["bluesky"] = "active"
            print("[MAIN DEBUG] Bluesky client marked as active")
            log_event(
                source="main",
                event_type="bluesky_initialized",
                payload={}
            )
            print("[MAIN DEBUG] ===== BLUESKY INITIALIZATION COMPLETE =====")
            return True
        except Exception as e:
            print(f"[MAIN DEBUG] ERROR: Exception during Bluesky initialization: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            self.module_status["bluesky"] = "failed"
            log_error("main", e, {
                "service": "bluesky",
                "action": "initialize",
                "error_type": type(e).__name__
            })
            log_event(
                source="main",
                event_type="bluesky_failed",
                payload={
                    "error": str(e)[:200],
                    "error_type": type(e).__name__
                }
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
        """Send 'System online' message to Discord."""
        message = "🚀 System online - Wiring phase initialized"
        
        print("[MAIN DEBUG] ===== SENDING SYSTEM ONLINE MESSAGE =====")
        # Discord message is sent automatically via on_ready callback (registered in startup)
    
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
        
        # 6. Initialize ingest clients (can fail gracefully)
        await self.initialize_bluesky()
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
        
        # 10. Setup test event handler (runs once when both Discord and Bluesky are ready)
        asyncio.create_task(self._setup_test_event_handler())
        
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
    
    async def _setup_test_event_handler(self) -> None:
        """
        Setup test event handler that runs once when both Discord and Bluesky are ready.
        This is a temporary test pipeline for image posting.
        """
        print("[MAIN DEBUG] Setting up test event handler...")
        
        # Wait for both services to be ready
        max_wait = 60.0  # Wait up to 60 seconds
        start_time = asyncio.get_event_loop().time()
        
        while True:
            discord_ready = (
                self.discord_bot is not None
                and self.discord_bot._ready
                and self.module_status.get("discord") == "active"
            )
            bluesky_ready = (
                self.bluesky_client is not None
                and self.bluesky_client.session is not None
                and self.module_status.get("bluesky") == "active"
            )
            
            if discord_ready and bluesky_ready:
                print("[MAIN DEBUG] Both Discord and Bluesky are ready!")
                if not self._test_event_triggered:
                    self._test_event_triggered = True
                    await self._trigger_test_event()
                break
            
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= max_wait:
                print(f"[MAIN DEBUG] Timeout waiting for services to be ready (waited {elapsed:.1f}s)")
                print(f"[MAIN DEBUG] Discord ready: {discord_ready}, Bluesky ready: {bluesky_ready}")
                break
            
            await asyncio.sleep(1.0)
    
    async def _trigger_test_event(self) -> None:
        """
        Trigger the test event: ask for a picture and set up image handler.
        """
        print("[MAIN DEBUG] ===== TRIGGERING TEST EVENT =====")
        
        # Ask for a picture via Discord
        try:
            await self.discord_bot.send_message("📸 Test event: Please send me a picture!")
            print("[MAIN DEBUG] Asked for picture via Discord")
        except Exception as e:
            print(f"[MAIN DEBUG] ERROR asking for picture: {type(e).__name__}: {e}")
            log_error("main", e, {"action": "trigger_test_event"})
            return
        
        # Set up image callback
        async def handle_image(message: discord.Message, image_data: Tuple[bytes, str]) -> None:
            """Handle image received from Discord and post to Bluesky."""
            print("[MAIN DEBUG] ===== HANDLING IMAGE FROM DISCORD =====")
            image_bytes, content_type = image_data
            print(f"[MAIN DEBUG] Image size: {len(image_bytes)} bytes, type: {content_type}")
            
            try:
                # Upload image blob to Bluesky
                print("[MAIN DEBUG] Uploading image blob to Bluesky...")
                blob_result = self.bluesky_client.upload_blob(image_bytes, content_type)
                print("[MAIN DEBUG] Image blob uploaded successfully")
                
                # Create post with image
                print("[MAIN DEBUG] Creating post with image on Bluesky...")
                post_text = "📸 Image received from Discord test event"
                images = [{
                    "blob": blob_result.get("blob", {}),
                    "alt": "Image received from Discord test event"
                }]
                
                post_result = self.bluesky_client.create_image_post(post_text, images)
                print("[MAIN DEBUG] Image post created successfully!")
                
                # Confirm via Discord
                await message.channel.send("✅ Image posted to Bluesky successfully!")
                log_event(
                    source="main",
                    event_type="test_image_posted",
                    payload={"bluesky_post_uri": post_result.get("uri", "unknown")}
                )
            except Exception as e:
                print(f"[MAIN DEBUG] ERROR posting image to Bluesky: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                log_error("main", e, {"action": "handle_image"})
                try:
                    await message.channel.send(f"❌ Error posting to Bluesky: {str(e)}")
                except:
                    pass
        
        # Register the callback
        self.discord_bot.set_image_callback(handle_image)
        print("[MAIN DEBUG] Image callback registered")
        log_event(source="main", event_type="test_event_triggered", payload={})
    
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
        
        # Stop Discord bot
        try:
            if self.discord_bot:
                await self.discord_bot.stop()
        except Exception as e:
            log_error("main", e, {"action": "stop_discord_bot"})
        
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

