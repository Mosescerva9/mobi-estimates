"""Centralized application settings.

All configuration is sourced from environment variables (optionally loaded from a
local ``.env`` file) using a single ``Settings`` object. Importing
``app.config.settings`` anywhere in the codebase guarantees one consistent,
validated configuration surface.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # --- Security ----------------------------------------------------------
    # Optional shared secret. When set, every request except health probes must
    # present a matching ``X-API-Key`` (or ``Authorization: Bearer <key>``)
    # header. Unset (default) leaves the API open — intended only for
    # local development and tests, never for a publicly exposed deployment.
    api_key: str | None = None  # secret; never logged or returned

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

    # --- Phase 2: deterministic blueprint processing -----------------------
    # Full-resolution render DPI for the review image.
    render_dpi: int = Field(default=150, ge=36, le=600)
    # Thumbnail maximum width in pixels (height scales proportionally).
    thumbnail_max_width: int = Field(default=320, ge=32, le=2048)
    # Pages with fewer embedded-text characters than this are flagged for OCR.
    min_text_chars: int = Field(default=12, ge=0)
    # Pages above the hard OCR floor but below this usable-text threshold are
    # treated as low-information text-layer pages for extraction routing. They
    # may have enough text to identify a sheet, but not enough to trust scope,
    # quantity, or schedule extraction without OCR/vision follow-up.
    low_information_text_chars: int = Field(default=300, ge=0)
    # Very sparse text-layer pages should be prioritized for OCR/vision before
    # downstream extraction attempts.
    very_low_information_text_chars: int = Field(default=60, ge=0)
    # Hard cap on the number of pages processed from a single PDF.
    max_page_count: int = Field(default=1000, ge=1)
    # Decompression-bomb guard: maximum rendered pixels per page. Effective DPI
    # is reduced automatically so width*height never exceeds this value.
    max_render_pixels: int = Field(default=40_000_000, ge=100_000)
    # Run processing synchronously inside the request (True) or via a FastAPI
    # background task (False). Inline is the deterministic default for tests and
    # the lean single-process MVP; production should move to an external worker.
    process_inline: bool = True

    # --- Phase 3: trade-agnostic extraction framework ----------------------
    # Trades registered/enabled at startup. Comma-separated in the environment,
    # e.g. MOBI_ENABLED_TRADES=painting,demo_concrete
    enabled_trades: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["painting"]
    )
    # Provider selection. "mock" is deterministic and offline (the default).
    extraction_provider: str = "mock"
    openai_api_key: str | None = None  # secret; never logged or returned
    openai_model: str = "gpt-4o-mini"
    # Live provider calls are OFF by default; the app runs fully without a key.
    enable_live_extraction: bool = False
    extraction_max_pages: int = Field(default=50, ge=1)
    extraction_max_pages_per_trade: int = Field(default=50, ge=1)
    extraction_max_text_chars_per_page: int = Field(default=20_000, ge=100)
    extraction_timeout_seconds: int = Field(default=60, ge=1)
    extraction_max_retries: int = Field(default=2, ge=0)
    # Raw provider responses may contain customer plan text; off by default.
    extraction_store_raw_response: bool = False
    # Run extraction inline (deterministic default) vs FastAPI background task.
    extraction_inline: bool = True
    extraction_cache_enabled: bool = True

    @field_validator("enabled_trades", mode="before")
    @classmethod
    def _split_trades(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    # Logging
    log_level: str = "INFO"
    # Emit machine-readable JSON access logs when true, human-readable otherwise.
    json_logs: bool = False

    @property
    def data_root(self) -> Path:
        """Root data directory that contains all per-project upload folders.

        Artifact-serving endpoints resolve requested files strictly inside this
        directory to prevent path traversal.
        """
        return self.upload_dir


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton ``Settings`` instance."""
    return Settings()


# Module-level singleton for convenient imports.
settings = get_settings()
