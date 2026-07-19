from __future__ import annotations

from functools import lru_cache

from typing import Annotated, Any
from pydantic import Field, SecretStr, field_validator, model_validator
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
    flutter_event_submit_rate_limit: int = Field(
        default=20,
        ge=1,
        alias="FLUTTER_EVENT_SUBMIT_RATE_LIMIT",
    )
    flutter_event_submit_rate_window_seconds: int = Field(
        default=3600,
        ge=1,
        alias="FLUTTER_EVENT_SUBMIT_RATE_WINDOW_SECONDS",
    )

    # ── University superapp identity bridge ──────────────────────────────────
    # All optional and OFF by default: until an issuer + a verification key are
    # set, the bridge is inert and the Flutter app keeps using its own tokens.
    # When the superapp is ready, set these to have Flutter endpoints ALSO accept
    # superapp-issued JWTs (dual-mode migration; see web/superapp_bridge.py).
    superapp_jwt_issuer: str | None = Field(default=None, alias="SUPERAPP_JWT_ISSUER")
    superapp_jwt_audience: str | None = Field(
        default=None, alias="SUPERAPP_JWT_AUDIENCE"
    )
    superapp_jwt_algorithm: str = Field(default="RS256", alias="SUPERAPP_JWT_ALGORITHM")
    # RS256/ES256 public key (PEM) — preferred, asymmetric so we never hold the
    # superapp's signing key. Or an HS256 shared secret if that is all they offer.
    superapp_jwt_public_key: str | None = Field(
        default=None, alias="SUPERAPP_JWT_PUBLIC_KEY"
    )
    superapp_jwt_secret: SecretStr | None = Field(
        default=None, alias="SUPERAPP_JWT_SECRET"
    )
    # which claim carries the stable subject id, and (optionally) the role
    superapp_user_id_claim: str = Field(default="sub", alias="SUPERAPP_USER_ID_CLAIM")
    superapp_role_claim: str | None = Field(default=None, alias="SUPERAPP_ROLE_CLAIM")
    # the exact value of the role claim that should map to coordinator/admin
    superapp_admin_role_value: str | None = Field(
        default=None, alias="SUPERAPP_ADMIN_ROLE_VALUE"
    )

    @property
    def superapp_bridge_enabled(self) -> bool:
        # inert until an issuer and at least one verification key are configured
        has_key = bool(self.superapp_jwt_public_key) or bool(self.superapp_jwt_secret)
        return bool(self.superapp_jwt_issuer) and has_key

    # PyJWT does not enforce a minimum key length for HMAC algorithms, so a short
    # SUPERAPP_JWT_SECRET would be brute-forceable. Only guard when the bridge is
    # actually enabled with a symmetric (HS*) algorithm — the RS256/ES256 default
    # and the inert (disabled) state are unaffected, so this cannot regress the
    # current production posture.
    @model_validator(mode="after")
    def _guard_superapp_hmac_secret_strength(self) -> "Settings":
        if not self.superapp_bridge_enabled:
            return self
        if not self.superapp_jwt_algorithm.upper().startswith("HS"):
            return self
        secret = (
            self.superapp_jwt_secret.get_secret_value()
            if self.superapp_jwt_secret is not None
            else ""
        )
        if len(secret.encode()) < 32:
            raise ValueError(
                "SUPERAPP_JWT_SECRET must be at least 32 bytes when "
                "SUPERAPP_JWT_ALGORITHM is HS256/HS384/HS512."
            )
        return self

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

    # private telegram channel for cover storage
    media_storage_chat_id: int | None = Field(
        default=None, alias="MEDIA_STORAGE_CHAT_ID"
    )
    media_cover_staging_ttl: int = Field(default=3600, alias="MEDIA_COVER_STAGING_TTL")
    # legacy bot cover step stays off for flutter covers
    bot_poster_upload_enabled: bool = Field(
        default=False, alias="BOT_POSTER_UPLOAD_ENABLED"
    )

    @field_validator("media_storage_chat_id", mode="before")
    @classmethod
    def parse_media_storage_chat_id(cls, v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # the dev toggles widen CORS to localhost and expose the OpenAPI docs; they
    # must never be left on in production. Refuse to boot if either is enabled
    # while LOG_LEVEL is not DEBUG, so a stray FLUTTER_DEV_* in the prod .env
    # fails loudly at startup instead of silently exposing the API surface.
    @model_validator(mode="after")
    def _guard_dev_flags_in_production(self) -> "Settings":
        if (self.flutter_dev_cors or self.flutter_dev_docs) and (
            self.log_level.upper() != "DEBUG"
        ):
            raise ValueError(
                "FLUTTER_DEV_CORS/FLUTTER_DEV_DOCS must not be enabled unless "
                "LOG_LEVEL=DEBUG (development only)."
            )
        return self

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
