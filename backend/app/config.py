from __future__ import annotations

from functools import lru_cache

from typing import Annotated, Any
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    session_secret: SecretStr | None = Field(default=None, alias="SESSION_SECRET")
    # flutter development toggles — extra cors origins and enabled api docs
    flutter_dev_cors: bool = Field(default=False, alias="FLUTTER_DEV_CORS")
    flutter_dev_docs: bool = Field(default=False, alias="FLUTTER_DEV_DOCS")
    # IPs of reverse proxies whose X-Forwarded-For header should be trusted
    # e.g. TRUSTED_PROXY_IPS=127.0.0.1,10.0.0.1
    trusted_proxy_ips: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="TRUSTED_PROXY_IPS"
    )

    @field_validator("trusted_proxy_ips", mode="before")
    @classmethod
    def parse_trusted_proxy_ips(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [s.strip() for s in v if s.strip()]
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return []

    moderator_chat_id: int | None = Field(default=None, alias="MODERATOR_CHAT_ID")
    admin_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ADMIN_IDS"
    )

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> list[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            val = v.strip()
            if not val:
                return []
            if val.startswith("[") and val.endswith("]"):
                try:
                    import json

                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        return [int(x) for x in parsed]
                except Exception:
                    pass
            try:
                # strip brackets just in case json parsing failed but brackets exist
                clean_val = val.lstrip("[").rstrip("]")
                return [int(x.strip()) for x in clean_val.split(",") if x.strip()]
            except ValueError as exc:
                raise ValueError(f"Invalid ADMIN_IDS format: {v}") from exc
        if isinstance(v, int):
            return [v]
        return v

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
    email_resend_cooldown_seconds: int = Field(
        default=60, alias="EMAIL_RESEND_COOLDOWN_SECONDS"
    )

    media_max_upload_bytes: int = Field(
        default=5_000_000, alias="MEDIA_MAX_UPLOAD_BYTES"
    )
    media_cover_cache_ttl: int = Field(default=86400, alias="MEDIA_COVER_CACHE_TTL")
    media_avatar_cache_ttl: int = Field(default=21600, alias="MEDIA_AVATAR_CACHE_TTL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# returns cached application settings
# get settings
@lru_cache
def get_settings() -> Settings:
    return Settings()
