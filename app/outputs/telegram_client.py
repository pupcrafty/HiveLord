"""Telegram bot client (optional mirror channel)."""
import asyncio
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from app.config.settings import get_settings
from app.core.consent import arm_consent, disarm_consent, safe_mode
from app.core.logger import log_event, log_message_sent, log_error
from app.core.scheduler import get_scheduler


class TelegramBot:
    """Telegram bot for DM-based control (optional mirror)."""
    
    def __init__(self):
        self.settings = get_settings()
        self.app: Optional[Application] = None
        self.chat_id: Optional[str] = None
        
        # Parse chat ID
        if self.settings.telegram_chat_id:
            try:
                self.chat_id = str(self.settings.telegram_chat_id)
            except (ValueError, AttributeError):
                log_error("telegram", f"Invalid TELEGRAM_CHAT_ID: {self.settings.telegram_chat_id}", {})
    
    def is_enabled(self) -> bool:
        """Check if Telegram bot is enabled (has token and chat ID)."""
        return bool(self.settings.telegram_bot_token and self.chat_id)
    
    async def send_message(self, message: str) -> None:
        """Send a message to the configured chat."""
        if not self.is_enabled() or not self.app:
            return
        
        try:
            await self.app.bot.send_message(chat_id=self.chat_id, text=message)
            log_message_sent("telegram", self.chat_id, message[:100])
        except Exception as e:
            log_error("telegram", e, {"action": "send_message", "chat_id": self.chat_id})
    
    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle command messages."""
        if not update.message or not update.effective_chat:
            return
        
        # Only process messages from configured chat
        if str(update.effective_chat.id) != self.chat_id:
            return
        
        content = update.message.text.strip().upper()
        
        log_event(
            source="telegram",
            event_type="command_received",
            payload={"command": content, "chat_id": update.effective_chat.id}
        )
        
        # Handle commands
        if content == "ARM":
            try:
                arm_consent()
                await update.message.reply_text("✅ Consent ARMED (10 minutes)")
            except Exception as e:
                log_error("telegram", e, {"command": "ARM"})
                await update.message.reply_text(f"❌ Error: {str(e)}")
        
        elif content == "DISARM":
            try:
                disarm_consent()
                await update.message.reply_text("✅ Consent DISARMED")
            except Exception as e:
                log_error("telegram", e, {"command": "DISARM"})
                await update.message.reply_text(f"❌ Error: {str(e)}")
        
        elif content == "SAFE MODE":
            try:
                safe_mode()
                # Cancel all scheduled tasks
                scheduler = get_scheduler()
                scheduler.cancel_all()
                await update.message.reply_text("🔒 SAFE MODE ACTIVATED - All consent disabled, tasks cancelled")
            except Exception as e:
                log_error("telegram", e, {"command": "SAFE MODE"})
                await update.message.reply_text(f"❌ Error: {str(e)}")
        
        else:
            await update.message.reply_text(
                f"Unknown command: {content}\nAvailable: ARM, DISARM, SAFE MODE"
            )
    
    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages."""
        await self._handle_command(update, context)
    
    async def start(self) -> None:
        """Start the Telegram bot."""
        if not self.is_enabled():
            log_event(
                source="telegram",
                event_type="bot_disabled",
                payload={"reason": "Missing token or chat_id"}
            )
            return
        
        self.app = Application.builder().token(self.settings.telegram_bot_token).build()
        
        # Add handlers
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))
        self.app.add_handler(CommandHandler("arm", lambda u, c: self._handle_command(u, c) if u.message else None))
        self.app.add_handler(CommandHandler("disarm", lambda u, c: self._handle_command(u, c) if u.message else None))
        self.app.add_handler(CommandHandler("safemode", lambda u, c: self._handle_command(u, c) if u.message else None))
        
        # Start bot in background
        asyncio.create_task(self.app.run_polling(allowed_updates=Update.ALL_TYPES))
        
        log_event(
            source="telegram",
            event_type="bot_started",
            payload={"chat_id": self.chat_id}
        )
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if self.app:
            await self.app.stop()
            await self.app.shutdown()

