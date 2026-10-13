"""Process configuration. All settings are environment-driven."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str
    outbox_stream: str = "soc.outbox"
    outbox_batch_size: int = 100
    outbox_max_attempts: int = 5
    outbox_poll_interval_seconds: float = 1.0
    max_payload_bytes: int = 8 * 1024 * 1024
    api_cursor_secret: str = Field(
        default="dev-only-change-me",
        description="HMAC key for opaque list cursors. Override outside local development.",
    )
    service_name: str = "soc-api"
    environment: str = "local"
    otlp_endpoint: str = ""
    metrics_enabled: bool = True
    metrics_port: int = 9101
    log_format: str = "json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
