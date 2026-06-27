"""Centralized application settings.

All configuration is sourced from environment variables (optionally loaded from a
local ``.env`` file) using a single ``Settings`` object. Importing
``app.config.settings`` anywhere in the codebase guarantees one consistent,
validated configuration surface.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated, environment-driven application configuration.

    Environment variables are prefixed with ``MOBI_`` (e.g. ``MOBI_DB_PATH``).
    A ``.env`` file in the working directory is loaded automatically when present.
    """

    model_config = SettingsConfigDict(
        env_prefix="MOBI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Mobi Automated Estimating API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"

    # Storage
    db_path: Path = Field(default=Path("data/mobi.db"))
    upload_dir: Path = Field(default=Path("data/uploads"))

    # Upload limits
    max_upload_bytes: int = Field(
        default=100 * 1024 * 1024,  # 100 MiB
        ge=1,
        description="Maximum accepted PDF upload size in bytes.",
    )
    upload_chunk_bytes: int = Field(default=1024 * 1024, ge=1024)

    # Logging
    log_level: str = "INFO"
    # Emit machine-readable JSON access logs when true, human-readable otherwise.
    json_logs: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton ``Settings`` instance."""
    return Settings()


# Module-level singleton for convenient imports.
settings = get_settings()
