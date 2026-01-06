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
    enable_bluesky: bool = Field(default=True, description="Enable Bluesky client")
    enable_lovense: bool = Field(default=True, description="Enable Lovense client")
    enable_database: bool = Field(default=True, description="Enable database")
    
    # Bluesky - Optional
    bsky_handle: str | None = Field(default=None, description="Bluesky Handle")
    bsky_app_password: str | None = Field(default=None, description="Bluesky App Password")
    bsky_pds_host: str = Field(default="https://bsky.social", description="Bluesky PDS Host")
    
    # Discord - Optional
    discord_bot_token: str | None = Field(default=None, description="Discord Bot Token")
    discord_user_id: str | None = Field(default=None, description="Discord User ID")
    discord_guild_id: str | None = Field(default=None, description="Discord Guild ID")
    
    # Lovense - Optional
    lovense_developer_token: str | None = Field(default=None, description="Lovense Developer Token")
    lovense_callback_url: str | None = Field(default=None, description="Lovense Callback URL")
    lovense_mode: str = Field(default="events", description="Lovense Mode: events | standard | socket")
    
    def __repr__(self) -> str:
        """Safe representation that never prints secrets."""
        return (
            f"Settings("
            f"bsky_handle='{self.bsky_handle}', "
            f"discord_user_id='{self.discord_user_id}', "
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

