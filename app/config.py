from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# stores runtime settings loaded from environment variables
class Settings(BaseSettings):
    bot_token: SecretStr = Field(alias="BOT_TOKEN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    app_timezone: str = Field(default="Asia/Almaty", alias="APP_TIMEZONE")
    database_url: str = Field(
        default="postgresql+asyncpg://events_bot:events_bot@localhost:5432/events_bot",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    miniapp_base_url: str | None = Field(default=None, alias="MINIAPP_BASE_URL")
    telegram_miniapp_short_name: str | None = Field(
        default="events",
        alias="TELEGRAM_MINIAPP_SHORT_NAME",
    )
    miniapp_session_ttl_seconds: int = Field(
        default=86400,
        alias="MINIAPP_SESSION_TTL_SECONDS",
    )
    moderator_chat_id: int | None = Field(default=None, alias="MODERATOR_CHAT_ID")
    admin_ids: list[int] = Field(default_factory=list, alias="ADMIN_IDS")
    telegram_delivery_delay_seconds: float = Field(
        default=0.15,
        alias="TELEGRAM_DELIVERY_DELAY_SECONDS",
    )
    telegram_delivery_max_retries: int = Field(
        default=3,
        alias="TELEGRAM_DELIVERY_MAX_RETRIES",
    )

    # email settings
    email_host: str | None = Field(default="console", alias="EMAIL_HOST")
    email_port: int = Field(default=587, alias="EMAIL_PORT")
    email_username: str | None = Field(default=None, alias="EMAIL_USERNAME")
    email_password: SecretStr | None = Field(default=None, alias="EMAIL_PASSWORD")
    email_from: str | None = Field(default=None, alias="EMAIL_FROM")
    email_code_ttl_minutes: int = Field(default=10, alias="EMAIL_CODE_TTL_MINUTES")
    email_resend_cooldown_seconds: int = Field(default=60, alias="EMAIL_RESEND_COOLDOWN_SECONDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# returns cached application settings
@lru_cache
def get_settings() -> Settings:
    return Settings()
