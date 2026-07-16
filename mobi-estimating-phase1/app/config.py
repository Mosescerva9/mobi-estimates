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

from pydantic import Field, field_validator, model_validator
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
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "Mobi Automated Estimating API"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"

    # --- Security ----------------------------------------------------------
    # Environment label for fail-closed startup checks. It is intentionally
    # unset by default: every process that starts the engine must explicitly opt
    # into the local-only developer harness with MOBI_DEPLOYMENT_ENVIRONMENT=local
    # until tenant-scoped workload/JWT identity is implemented. Unlabeled
    # containers/previews/releases must not inherit an open local default.
    deployment_environment: str | None = None
    # Current engine auth is only suitable for local/internal single-tenant
    # development. The audit target is tenant-scoped JWT/workload identity;
    # until that is implemented, staging/production startup must fail closed.
    # ``local_dev_open`` is an explicit, honest label for the keyless local
    # harness; ``local_dev_shared_key`` may be selected only when a non-blank
    # MOBI_API_KEY is configured so the capability registry/config cannot claim
    # an auth boundary the middleware is not actually enforcing.
    engine_auth_mode: str = "local_dev_open"
    # Optional shared secret. When set, every request except health probes must
    # present exactly one matching ``X-API-Key`` header or Authorization
    # bearer-token header. Unset (default) leaves the API open — intended only for
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

    @field_validator("deployment_environment", "engine_auth_mode", mode="before")
    @classmethod
    def _normalize_security_label(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("engine_auth_mode")
    @classmethod
    def _fail_closed_unknown_engine_auth_mode(cls, value: str) -> str:
        """Do not let future/typo auth labels imply a tenant-safe boundary.

        The only implemented engine auth mode today is the local development
        shared-key scaffold. Tenant-scoped JWT/workload identity must be added
        with its own verifier, row/object tenant propagation, and tests before a
        new label can be accepted. Until then, every unknown/future label fails
        closed even in local/test config.
        """

        implemented_modes = {
            "local_dev_open",
            "local_dev_shared_key",
            # Deployable service-to-service worker boundary for the VPS OpenTakeoff
            # worker API. It is a shared-key + enforced-tenant-headers mode, not
            # the target tenant-scoped JWT/workload identity; it may only be
            # selected with a non-blank MOBI_API_KEY (validated below).
            "worker_service_shared_key",
        }
        if value not in implemented_modes:
            raise ValueError(
                "Unsupported MOBI_ENGINE_AUTH_MODE: tenant-scoped workload/JWT "
                "identity is not implemented or enforced yet."
            )
        return value

    @field_validator("api_key", mode="before")
    @classmethod
    def _normalize_api_key(cls, value: object) -> object:
        """Normalize local shared-key config without accepting blank secrets.

        The shared-key gate is temporary P0 scaffolding, not production tenant
        identity. If it is configured at all, it must be an auditable non-blank
        value; whitespace-only env values should fail closed instead of silently
        making the engine public or creating a trivially guessable key.
        """

        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("api_key must be a non-blank shared secret when configured")
            return normalized
        return value

    @field_validator("enabled_trades", mode="before")
    @classmethod
    def _split_trades(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _fail_closed_for_release_environment(self) -> "Settings":
        # Until tenant-scoped workload/JWT identity is implemented, only two
        # explicit environments may start: the local developer harness
        # ("local"), and the deployable service-to-service OpenTakeoff worker
        # ("worker_service"). Absent labels, containers, previews, "dev",
        # "test", "ci", and "production" are too easy to map to shared/public
        # infrastructure and must not become implicit release bypass labels.
        if self.deployment_environment not in {"local", "worker_service"}:
            raise ValueError(
                "The estimating engine is not release-startable yet: tenant-scoped "
                "workload/JWT identity is not implemented or enforced. Set "
                "MOBI_DEPLOYMENT_ENVIRONMENT=local for an explicit local developer "
                "harness, or MOBI_DEPLOYMENT_ENVIRONMENT=worker_service for the "
                "shared-key service-to-service OpenTakeoff worker API, until the P0 "
                "tenant boundary is complete."
            )

        # The deployable worker service must never start keyless or with an
        # unenforced tenant boundary. It requires the shared-key worker auth mode
        # and a non-blank MOBI_API_KEY so ApiKeyAuthMiddleware enforces both the
        # shared secret and tenant identity headers on every worker request.
        if self.deployment_environment == "worker_service":
            if self.engine_auth_mode != "worker_service_shared_key":
                raise ValueError(
                    "MOBI_DEPLOYMENT_ENVIRONMENT=worker_service requires "
                    "MOBI_ENGINE_AUTH_MODE=worker_service_shared_key so the shared "
                    "key and tenant headers are enforced service-to-service."
                )
            if self.api_key is None:
                raise ValueError(
                    "MOBI_ENGINE_AUTH_MODE=worker_service_shared_key requires a "
                    "non-blank MOBI_API_KEY; the worker API must not start keyless."
                )
        elif self.engine_auth_mode == "worker_service_shared_key":
            raise ValueError(
                "MOBI_ENGINE_AUTH_MODE=worker_service_shared_key is only valid with "
                "MOBI_DEPLOYMENT_ENVIRONMENT=worker_service."
            )

        if self.engine_auth_mode == "local_dev_shared_key" and self.api_key is None:
            raise ValueError(
                "MOBI_ENGINE_AUTH_MODE=local_dev_shared_key requires a non-blank "
                "MOBI_API_KEY; use MOBI_ENGINE_AUTH_MODE=local_dev_open only for "
                "the explicit keyless local developer harness."
            )
        if self.engine_auth_mode == "local_dev_open" and self.api_key is not None:
            raise ValueError(
                "MOBI_ENGINE_AUTH_MODE=local_dev_open must not be combined with "
                "MOBI_API_KEY; use local_dev_shared_key when the local shared-key "
                "middleware boundary is actually configured."
            )
        return self

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
