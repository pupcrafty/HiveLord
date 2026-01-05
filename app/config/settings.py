"""Configuration management using Pydantic settings."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Module enable flags
    enable_discord: bool = Field(default=True, description="Enable Discord bot")
    enable_telegram: bool = Field(default=True, description="Enable Telegram bot")
    enable_bluesky: bool = Field(default=True, description="Enable Bluesky client")
    enable_instagram: bool = Field(default=True, description="Enable Instagram client")
    enable_lovense: bool = Field(default=True, description="Enable Lovense client")
    enable_database: bool = Field(default=True, description="Enable database")
    
    # Instagram (Meta) - Optional
    ig_app_id: str | None = Field(default=None, description="Instagram App ID")
    ig_app_secret: str | None = Field(default=None, description="Instagram App Secret")
    ig_page_id: str | None = Field(default=None, description="Instagram Page ID")
    ig_ig_user_id: str | None = Field(default=None, description="Instagram User ID")
    ig_long_lived_access_token: str | None = Field(default=None, description="Instagram Long-Lived Access Token")
    
    # Bluesky - Optional
    bsky_handle: str | None = Field(default=None, description="Bluesky Handle")
    bsky_app_password: str | None = Field(default=None, description="Bluesky App Password")
    bsky_pds_host: str = Field(default="https://bsky.social", description="Bluesky PDS Host")
    
    # Discord - Optional
    discord_bot_token: str | None = Field(default=None, description="Discord Bot Token")
    discord_user_id: str | None = Field(default=None, description="Discord User ID")
    discord_guild_id: str | None = Field(default=None, description="Discord Guild ID")
    
    # Telegram - Optional
    telegram_bot_token: str | None = Field(default=None, description="Telegram Bot Token")
    telegram_chat_id: str | None = Field(default=None, description="Telegram Chat ID")
    
    # Lovense - Optional
    lovense_developer_token: str | None = Field(default=None, description="Lovense Developer Token")
    lovense_callback_url: str | None = Field(default=None, description="Lovense Callback URL")
    lovense_mode: str = Field(default="events", description="Lovense Mode: events | standard | socket")
    
    def __repr__(self) -> str:
        """Safe representation that never prints secrets."""
        return (
            f"Settings("
            f"ig_app_id='***', "
            f"bsky_handle='{self.bsky_handle}', "
            f"discord_user_id='{self.discord_user_id}', "
            f"telegram_chat_id={self.telegram_chat_id}, "
            f"lovense_mode='{self.lovense_mode}'"
            f")"
        )


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the singleton settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

