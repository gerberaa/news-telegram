"""Configuration management for the news telegram bot."""

import os
from typing import Optional
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
    
    # Apify Configuration
    apify_token: str = Field(..., description="Apify API token")
    apify_actor: str = Field(
        default="apipi/crypto-news-scraper", 
        description="Apify actor to run"
    )
    apify_run_mode: str = Field(
        default="pull", 
        description="Run mode: pull or webhook"
    )
    apify_timeout_sec: int = Field(
        default=300, 
        description="Timeout for Apify run in seconds"
    )
    
    # Telegram Configuration
    telegram_bot_token: str = Field(..., description="Telegram bot token")
    telegram_channel: str = Field(..., description="Telegram channel ID or username")
    
    # Database Configuration
    db_path: str = Field(default="./news.db", description="SQLite database path")
    
    # Application Settings
    poll_interval_sec: int = Field(
        default=300, 
        description="Polling interval in seconds"
    )
    max_articles: int = Field(
        default=100, 
        description="Maximum articles to process in one run"
    )
    log_level: str = Field(default="INFO", description="Logging level")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_backoff_base: int = Field(
        default=2, 
        description="Base for exponential backoff"
    )
    
    # Optional Webhook Configuration
    webhook_url: Optional[str] = Field(
        default=None, 
        description="Webhook URL for Apify notifications"
    )
    webhook_port: int = Field(
        default=8080, 
        description="Port for webhook server"
    )
    
    @property
    def is_webhook_mode(self) -> bool:
        """Check if webhook mode is enabled."""
        return self.apify_run_mode.lower() == "webhook"


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
