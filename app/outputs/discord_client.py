"""Discord bot client for DM-based control."""
import asyncio
from typing import Optional, List, Tuple, Callable, Awaitable

import discord
from discord.ext import commands

from app.config.settings import get_settings, is_dom_mode_enabled
from app.core.consent import arm_consent, disarm_consent, safe_mode
from app.core.logger import log_event, log_message_sent, log_error
from app.core.scheduler import get_scheduler


class DiscordBot:
    """Discord bot for DM-based control."""
    
    def __init__(self, dom_bot=None):
        self.settings = get_settings()
        self.bot: Optional[commands.Bot] = None
        self.user_id: Optional[int] = None
        self._initialized = False
        self._ready = False
        self._ready_event = asyncio.Event()
        self._first_message: Optional[str] = None
        self._image_callback: Optional[Callable[[discord.Message, Tuple[bytes, str]], Awaitable[None]]] = None
        self.dom_bot = dom_bot
    
    def is_enabled(self) -> bool:
        """Check if Discord bot is enabled and has required configuration."""
        print("[DISCORD DEBUG] Checking if Discord bot is enabled...")
        if not self.settings.enable_discord:
            print("[DISCORD DEBUG] Discord is disabled (enable_discord=False)")
            return False
        if not (self.settings.discord_bot_token and self.settings.discord_user_id):
            print("[DISCORD DEBUG] Discord missing configuration (token or user_id)")
            return False
        try:
            int(self.settings.discord_user_id)
            print("[DISCORD DEBUG] Discord bot is enabled and configured")
            return True
        except (ValueError, TypeError):
            print(f"[DISCORD DEBUG] Invalid user_id: {self.settings.discord_user_id}")
            return False
    
    def _ensure_initialized(self) -> None:
        """Ensure bot is initialized."""
        print("[DISCORD DEBUG] Ensuring Discord bot is initialized...")
        if not self._initialized:
            if not self.is_enabled():
                print("[DISCORD DEBUG] ERROR: Discord bot is not enabled or missing configuration")
                raise RuntimeError("Discord bot is not enabled or missing configuration")
            # Parse user ID
            try:
                self.user_id = int(self.settings.discord_user_id)
                print(f"[DISCORD DEBUG] Parsed user_id: {self.user_id}")
            except (ValueError, AttributeError):
                print(f"[DISCORD DEBUG] ERROR: Invalid DISCORD_USER_ID: {self.settings.discord_user_id}")
                raise ValueError(f"Invalid DISCORD_USER_ID: {self.settings.discord_user_id}")
            self._initialized = True
            print("[DISCORD DEBUG] Discord bot initialized successfully")
    
    async def send_message(self, message: str) -> None:
        """Send a DM to the configured user."""
        print(f"[DISCORD DEBUG] send_message() called with message: {message[:50]}...")
        print(f"[DISCORD DEBUG] Bot exists: {self.bot is not None}")
        if self.bot:
            print(f"[DISCORD DEBUG] Bot is_ready(): {self.bot.is_ready()}")
            print(f"[DISCORD DEBUG] Internal _ready flag: {self._ready}")
        
        # Wait for bot to be ready (on_ready event fired)
        if not self._ready:
            print("[DISCORD DEBUG] Bot not ready yet, waiting for on_ready event...")
            try:
                await asyncio.wait_for(self._ready_event.wait(), timeout=30.0)
                print("[DISCORD DEBUG] Bot ready event received, proceeding with send")
            except asyncio.TimeoutError:
                print("[DISCORD DEBUG] ERROR: Timeout waiting for bot to be ready")
                log_error("discord", "Timeout waiting for bot ready", {"action": "send_message"})
                return
        
        if not self.bot or not self.bot.is_ready():
            print("[DISCORD DEBUG] ERROR: Bot not ready - cannot send message")
            log_error("discord", "Bot not ready", {"action": "send_message"})
            return
        
        try:
            print(f"[DISCORD DEBUG] Fetching user with ID: {self.user_id}")
            user = await self.bot.fetch_user(self.user_id)
            print(f"[DISCORD DEBUG] User fetched: {user.name}#{user.discriminator} (ID: {user.id})")
            print(f"[DISCORD DEBUG] Attempting to send DM to user...")
            await user.send(message)
            print(f"[DISCORD DEBUG] Message sent successfully!")
            log_message_sent("discord", str(self.user_id), message[:100])
        except discord.Forbidden as e:
            print(f"[DISCORD DEBUG] ERROR: Cannot send DM (forbidden) - {e}")
            log_error("discord", "Cannot send DM (forbidden)", {"user_id": self.user_id})
        except discord.HTTPException as e:
            print(f"[DISCORD DEBUG] ERROR: HTTPException - {e}")
            log_error("discord", e, {"action": "send_message", "user_id": self.user_id})
        except Exception as e:
            print(f"[DISCORD DEBUG] ERROR: Unexpected error - {type(e).__name__}: {e}")
            log_error("discord", e, {"action": "send_message"})
    
    async def _on_ready(self) -> None:
        """Called when bot is ready."""
        print("[DISCORD DEBUG] ===== BOT READY EVENT FIRED =====")
        if self.bot and self.bot.user:
            print(f"[DISCORD DEBUG] Bot user: {self.bot.user.name}#{self.bot.user.discriminator}")
            print(f"[DISCORD DEBUG] Bot ID: {self.bot.user.id}")
        else:
            print("[DISCORD DEBUG] WARNING: Bot user is None")
        print("[DISCORD DEBUG] Bot is_ready() status:", self.bot.is_ready() if self.bot else "N/A")
        
        # Mark bot as ready
        self._ready = True
        self._ready_event.set()
        print("[DISCORD DEBUG] Bot ready flag set to True")
        
        log_event(
            source="discord",
            event_type="bot_ready",
            payload={"user": str(self.bot.user) if self.bot.user else None}
        )
        
        # Send first message if one was registered
        if self._first_message:
            print(f"[DISCORD DEBUG] Sending first registered message: {self._first_message[:50]}...")
            await self.send_message(self._first_message)
            self._first_message = None
    
    async def _on_message(self, message: discord.Message) -> None:
        """Handle incoming messages."""
        # Only process DMs from the configured user
        if message.author.id != self.user_id:
            return
        
        if not isinstance(message.channel, discord.DMChannel):
            return
        
        # Ignore bot's own messages
        if message.author == self.bot.user:
            return
        
        content = message.content.strip()
        content_upper = content.upper()
        
        log_event(
            source="discord",
            event_type="command_received",
            payload={"command": content_upper, "user_id": message.author.id}
        )
        
        # Handle system commands (always available)
        if content_upper == "ARM":
            try:
                arm_consent()
                await message.channel.send("✅ Consent ARMED (10 minutes)")
            except Exception as e:
                log_error("discord", e, {"command": "ARM"})
                await message.channel.send(f"❌ Error: {str(e)}")
            return
        
        elif content_upper == "DISARM":
            try:
                disarm_consent()
                await message.channel.send("✅ Consent DISARMED")
            except Exception as e:
                log_error("discord", e, {"command": "DISARM"})
                await message.channel.send(f"❌ Error: {str(e)}")
            return
        
        elif content_upper == "SAFE MODE":
            try:
                safe_mode()
                # Cancel all scheduled tasks
                scheduler = get_scheduler()
                scheduler.cancel_all()
                await message.channel.send("🔒 SAFE MODE ACTIVATED - All consent disabled, tasks cancelled")
            except Exception as e:
                log_error("discord", e, {"command": "SAFE MODE"})
                await message.channel.send(f"❌ Error: {str(e)}")
            return
        
        # Check for Dom Bot mode
        if is_dom_mode_enabled() and self.dom_bot:
            # Route to Dom Bot
            try:
                # Check for image attachments
                image_data = await self.read_image_from_message(message)
                image_bytes = image_data[0] if image_data else None
                image_content_type = image_data[1] if image_data else None
                
                # Call Dom Bot
                response = await self.dom_bot.respond(
                    user_text=content,
                    channel_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    image_data=image_bytes,
                    image_content_type=image_content_type
                )
                
                # Send immediate message
                await message.channel.send(response.message)
                
                # Handle memory writes if any
                if response.memory_write:
                    from app.ai.tool_handlers import memory_upsert
                    for mem_write in response.memory_write:
                        await memory_upsert({
                            "key": mem_write.key,
                            "value": mem_write.value,
                            "metadata": mem_write.metadata
                        })
                
                # Log actions
                if response.actions:
                    log_event(
                        source="dom_bot",
                        event_type="actions_executed",
                        payload={
                            "actions_count": len(response.actions),
                            "actions": [
                                {
                                    "tool_name": action.tool_name,
                                    "task_id": action.task_id
                                }
                                for action in response.actions
                            ]
                        }
                    )
                
            except Exception as e:
                log_error("discord", e, {"action": "dom_bot_respond"})
                await message.channel.send(f"❌ Error processing request: {str(e)}")
            return
        
        # Dom mode disabled - send neutral response
        if not is_dom_mode_enabled():
            await message.channel.send("Dom mode disabled. Enable it in settings to use Dom Bot.")
            return
        
        # Fallback: check for image attachments (legacy handler)
        image_data = await self.read_image_from_message(message)
        if image_data:
            print("[DISCORD DEBUG] Image detected in message, calling image callback...")
            if self._image_callback:
                try:
                    await self._image_callback(message, image_data)
                    await message.channel.send("✅ Image received and processing...")
                except Exception as e:
                    print(f"[DISCORD DEBUG] ERROR in image callback: {type(e).__name__}: {e}")
                    log_error("discord", e, {"action": "image_callback"})
                    await message.channel.send(f"❌ Error processing image: {str(e)}")
            else:
                await message.channel.send("⚠️ Image received but no handler configured")
        else:
            await message.channel.send(f"Unknown command: {content_upper}\nAvailable: ARM, DISARM, SAFE MODE")
    
    def set_image_callback(self, callback: Callable[[discord.Message, Tuple[bytes, str]], Awaitable[None]]) -> None:
        """
        Set a callback function to handle image messages.
        
        Args:
            callback: Async function that takes (message, image_data) where
                     image_data is a tuple of (bytes, content_type)
        """
        print("[DISCORD DEBUG] Setting image callback...")
        self._image_callback = callback
    
    async def start(self) -> None:
        """Start the Discord bot."""
        print("[DISCORD DEBUG] ===== STARTING DISCORD BOT =====")
        self._ensure_initialized()
        print("[DISCORD DEBUG] Creating bot with intents...")
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        print(f"[DISCORD DEBUG] Intents configured - message_content: {intents.message_content}, dm_messages: {intents.dm_messages}")
        
        print("[DISCORD DEBUG] Creating commands.Bot instance...")
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        print("[DISCORD DEBUG] Bot instance created")
        
        @self.bot.event
        async def on_ready():
            print("[DISCORD DEBUG] on_ready event handler called")
            await self._on_ready()
        
        @self.bot.event
        async def on_message(message: discord.Message):
            print(f"[DISCORD DEBUG] on_message event - from: {message.author.name}, content: {message.content[:50]}")
            await self._on_message(message)
        
        print(f"[DISCORD DEBUG] Starting bot with token (length: {len(self.settings.discord_bot_token) if self.settings.discord_bot_token else 0})...")
        # Start bot in background task
        task = asyncio.create_task(self.bot.start(self.settings.discord_bot_token))
        print(f"[DISCORD DEBUG] Bot start task created: {task}")
        print("[DISCORD DEBUG] Bot start() method called - connection in progress...")
    
    def register_first_message(self, message: str) -> None:
        """Register a message to be sent when the bot is ready (in on_ready)."""
        print(f"[DISCORD DEBUG] register_first_message() called with: {message[:50]}...")
        self._first_message = message
        print(f"[DISCORD DEBUG] First message registered. Bot ready: {self._ready}")
    
    async def read_image_from_message(self, message: discord.Message) -> Optional[Tuple[bytes, str]]:
        """
        Read an image from a Discord message attachment.
        
        Args:
            message: Discord message object
            
        Returns:
            Tuple of (image_bytes, content_type) if image found, None otherwise
        """
        print("[DISCORD DEBUG] Reading image from message...")
        if not message.attachments:
            print("[DISCORD DEBUG] No attachments in message")
            return None
        
        # Find first image attachment
        for attachment in message.attachments:
            # Check if it's an image
            if attachment.content_type and attachment.content_type.startswith("image/"):
                print(f"[DISCORD DEBUG] Found image attachment: {attachment.filename}")
                print(f"[DISCORD DEBUG] Content type: {attachment.content_type}")
                print(f"[DISCORD DEBUG] Size: {attachment.size} bytes")
                
                try:
                    # Download the image
                    image_bytes = await attachment.read()
                    print(f"[DISCORD DEBUG] Downloaded {len(image_bytes)} bytes")
                    return (image_bytes, attachment.content_type)
                except Exception as e:
                    print(f"[DISCORD DEBUG] ERROR downloading image: {type(e).__name__}: {e}")
                    log_error("discord", e, {"action": "read_image", "filename": attachment.filename})
                    return None
        
        print("[DISCORD DEBUG] No image attachments found")
        return None
    
    async def stop(self) -> None:
        """Stop the Discord bot."""
        print("[DISCORD DEBUG] Stopping Discord bot...")
        if self.bot:
            print("[DISCORD DEBUG] Closing bot connection...")
            await self.bot.close()
            print("[DISCORD DEBUG] Bot closed")
        else:
            print("[DISCORD DEBUG] No bot instance to close")

