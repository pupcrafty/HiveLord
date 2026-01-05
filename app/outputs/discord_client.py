"""Discord bot client for DM-based control."""
import asyncio
from typing import Optional

import discord
from discord.ext import commands

from app.config.settings import get_settings
from app.core.consent import arm_consent, disarm_consent, safe_mode
from app.core.logger import log_event, log_message_sent, log_error
from app.core.scheduler import get_scheduler


class DiscordBot:
    """Discord bot for DM-based control."""
    
    def __init__(self):
        self.settings = get_settings()
        self.bot: Optional[commands.Bot] = None
        self.user_id: Optional[int] = None
        
        # Parse user ID
        try:
            self.user_id = int(self.settings.discord_user_id)
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid DISCORD_USER_ID: {self.settings.discord_user_id}")
    
    async def send_message(self, message: str) -> None:
        """Send a DM to the configured user."""
        if not self.bot or not self.bot.is_ready():
            log_error("discord", "Bot not ready", {"action": "send_message"})
            return
        
        try:
            user = await self.bot.fetch_user(self.user_id)
            await user.send(message)
            log_message_sent("discord", str(self.user_id), message[:100])
        except discord.Forbidden:
            log_error("discord", "Cannot send DM (forbidden)", {"user_id": self.user_id})
        except discord.HTTPException as e:
            log_error("discord", e, {"action": "send_message", "user_id": self.user_id})
        except Exception as e:
            log_error("discord", e, {"action": "send_message"})
    
    async def _on_ready(self) -> None:
        """Called when bot is ready."""
        log_event(
            source="discord",
            event_type="bot_ready",
            payload={"user": str(self.bot.user) if self.bot.user else None}
        )
    
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
        
        content = message.content.strip().upper()
        
        log_event(
            source="discord",
            event_type="command_received",
            payload={"command": content, "user_id": message.author.id}
        )
        
        # Handle commands
        if content == "ARM":
            try:
                arm_consent()
                await message.channel.send("✅ Consent ARMED (10 minutes)")
            except Exception as e:
                log_error("discord", e, {"command": "ARM"})
                await message.channel.send(f"❌ Error: {str(e)}")
        
        elif content == "DISARM":
            try:
                disarm_consent()
                await message.channel.send("✅ Consent DISARMED")
            except Exception as e:
                log_error("discord", e, {"command": "DISARM"})
                await message.channel.send(f"❌ Error: {str(e)}")
        
        elif content == "SAFE MODE":
            try:
                safe_mode()
                # Cancel all scheduled tasks
                scheduler = get_scheduler()
                scheduler.cancel_all()
                await message.channel.send("🔒 SAFE MODE ACTIVATED - All consent disabled, tasks cancelled")
            except Exception as e:
                log_error("discord", e, {"command": "SAFE MODE"})
                await message.channel.send(f"❌ Error: {str(e)}")
        
        else:
            await message.channel.send(f"Unknown command: {content}\nAvailable: ARM, DISARM, SAFE MODE")
    
    async def start(self) -> None:
        """Start the Discord bot."""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        
        self.bot = commands.Bot(command_prefix="!", intents=intents)
        
        @self.bot.event
        async def on_ready():
            await self._on_ready()
        
        @self.bot.event
        async def on_message(message: discord.Message):
            await self._on_message(message)
        
        # Start bot in background task
        asyncio.create_task(self.bot.start(self.settings.discord_bot_token))
    
    async def stop(self) -> None:
        """Stop the Discord bot."""
        if self.bot:
            await self.bot.close()

