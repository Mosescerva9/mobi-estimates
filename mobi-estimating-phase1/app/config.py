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

# Reasoning efforts *documented* by OpenAI for the GPT-5.6 reasoning model
# (verified 2026-07-21). This set is informational only: GPT-5.6 supports all of
# these, but Mobi's production path intentionally locks to a single effort (below)
# so no other effort can ever reach a live call. Kept as a constant so docs/tests
# can reference the documented surface without implying Mobi accepts it.
DOCUMENTED_REASONING_EFFORTS: frozenset[str] = frozenset(
    {"none", "low", "medium", "high", "xhigh", "max"}
)

# The single model alias and reasoning effort Mobi enforces for every GPT-5.6
# structured-output call. GPT-5.6 documents more efforts, but this product path
# deliberately allows exactly one of each so a typo, drift, or future label can
# never silently change the model or downgrade/escalate reasoning against a live,
# billable model. Validated at config load AND independently re-checked in the
# client before any SDK/network dispatch.
ENFORCED_MODEL_ALIAS: str = "gpt-5.6"
ENFORCED_REASONING_EFFORT: str = "medium"


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
    # Exact model alias requested for the GPT-5.6 structured-output path. Docs
    # (verified 2026-07-21) show ``gpt-5.6`` aliases GPT-5.6 Sol and supports the
    # Responses API + Structured Outputs. Locked to exactly ``gpt-5.6`` below;
    # any other value (legacy, snapshot, or other model) fails closed at load.
    openai_model: str = ENFORCED_MODEL_ALIAS
    # Reasoning effort for the GPT-5.6 Responses API path. GPT-5.6 documents the
    # full DOCUMENTED_REASONING_EFFORTS set, but Mobi locks production to exactly
    # ``medium`` (validated below); any other effort fails closed at load.
    openai_reasoning_effort: str = ENFORCED_REASONING_EFFORT
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

    # --- GPT-5.6 structured project-analysis layer -------------------------
    # A fail-closed reasoning/review layer that turns already-extracted,
    # tenant-scoped source text into Pydantic-validated project analysis via the
    # OpenAI Responses API + Structured Outputs. It never authors measurements,
    # quantities, prices, arithmetic, totals, approval, or delivery status.
    #
    # Live calls are OFF by default and require BOTH a configured API key AND an
    # explicit enablement flag. The default posture makes zero network calls.
    enable_live_project_analysis: bool = False
    project_analysis_schema_version: str = "1.0"
    # Bounds on the model input. The layer only ever sees text the system already
    # extracted and passed in — never arbitrary files, URLs, tools, or secrets.
    project_analysis_max_source_documents: int = Field(default=40, ge=1)
    project_analysis_max_source_chars: int = Field(default=120_000, ge=100)
    project_analysis_max_chars_per_document: int = Field(default=20_000, ge=100)
    project_analysis_timeout_seconds: int = Field(default=120, ge=1)
    project_analysis_max_retries: int = Field(default=2, ge=0)

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
            # Canonical internal VPS engine boundary. One current FastAPI app/data
            # root serves BOTH the normal /api/v1 routes (upload/processing) AND
            # /internal/takeoff (OpenTakeoff worker) behind the same shared-key +
            # enforced-tenant-headers middleware. It is still a shared-key
            # boundary, not the target tenant-scoped JWT/workload identity, and
            # may only be selected with a non-blank MOBI_API_KEY (validated below).
            "internal_vps_shared_key",
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

    @field_validator("openai_model", mode="before")
    @classmethod
    def _enforce_exact_model_alias(cls, value: object) -> object:
        """Lock the configured model to exactly ``gpt-5.6``.

        Fail-closed: this product path is validated only against the GPT-5.6
        alias. A legacy model, a raw snapshot name, or any other value must never
        reach a live call, so anything but the exact alias is rejected at load.
        The client independently re-checks this before dispatch.
        """

        if isinstance(value, str):
            normalized = value.strip()
            if normalized != ENFORCED_MODEL_ALIAS:
                raise ValueError(
                    "Unsupported MOBI_OPENAI_MODEL: this build enforces the exact "
                    f"model alias {ENFORCED_MODEL_ALIAS!r}."
                )
            return normalized
        return value

    @field_validator("openai_reasoning_effort", mode="before")
    @classmethod
    def _enforce_medium_reasoning_effort(cls, value: object) -> object:
        """Lock the configured reasoning effort to exactly ``medium``.

        Fail-closed: GPT-5.6 documents ``none|low|medium|high|xhigh|max`` (see
        DOCUMENTED_REASONING_EFFORTS), but Mobi intentionally allows only
        ``medium`` in production so a typo, drift, or future label can never
        silently downgrade or escalate reasoning against a live, billable model.
        The client independently re-checks this before dispatch.
        """

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized != ENFORCED_REASONING_EFFORT:
                raise ValueError(
                    "Unsupported MOBI_OPENAI_REASONING_EFFORT: GPT-5.6 documents "
                    f"{', '.join(sorted(DOCUMENTED_REASONING_EFFORTS))}, but this "
                    f"build enforces exactly {ENFORCED_REASONING_EFFORT!r}."
                )
            return normalized
        return value

    def project_analysis_readiness(self) -> dict[str, object]:
        """Report configured project-analysis readiness *without* key material.

        Safe to surface in capability/config responses: it proves the requested
        model alias, reasoning effort, API surface, and whether the live gate is
        armed, but never returns or hints at the API key value itself.
        """

        return {
            "provider": "openai",
            "api": "responses",
            "structured_outputs": True,
            "model": self.openai_model,
            "reasoning_effort": self.openai_reasoning_effort,
            "schema_version": self.project_analysis_schema_version,
            "live_enabled": bool(self.enable_live_project_analysis),
            "api_key_present": bool(self.openai_api_key),
            "ready_for_live_call": bool(
                self.enable_live_project_analysis and self.openai_api_key
            ),
        }

    @model_validator(mode="after")
    def _fail_closed_for_release_environment(self) -> "Settings":
        # Until tenant-scoped workload/JWT identity is implemented, only three
        # explicit environments may start: the local developer harness
        # ("local"), the deployable service-to-service OpenTakeoff worker
        # ("worker_service"), and the canonical internal VPS engine that serves
        # the normal API and the takeoff worker from one app/data root
        # ("internal_vps"). Absent labels, containers, previews, "dev", "test",
        # "ci", "staging", and "production" are too easy to map to shared/public
        # infrastructure and must not become implicit release bypass labels.
        # Each service environment binds to exactly one shared-key auth mode.
        _service_auth_modes = {
            "worker_service": "worker_service_shared_key",
            "internal_vps": "internal_vps_shared_key",
        }
        if self.deployment_environment not in {"local", *_service_auth_modes}:
            raise ValueError(
                "The estimating engine is not release-startable yet: tenant-scoped "
                "workload/JWT identity is not implemented or enforced. Set "
                "MOBI_DEPLOYMENT_ENVIRONMENT=local for an explicit local developer "
                "harness, MOBI_DEPLOYMENT_ENVIRONMENT=worker_service for the "
                "shared-key service-to-service OpenTakeoff worker API, or "
                "MOBI_DEPLOYMENT_ENVIRONMENT=internal_vps for the canonical internal "
                "VPS engine (normal API + takeoff worker), until the P0 tenant "
                "boundary is complete."
            )

        # A deployable service environment must never start keyless or with an
        # unenforced tenant boundary. It requires its bound shared-key auth mode
        # and a non-blank MOBI_API_KEY so ApiKeyAuthMiddleware enforces both the
        # shared secret and tenant identity headers on every request.
        if self.deployment_environment in _service_auth_modes:
            required_mode = _service_auth_modes[self.deployment_environment]
            if self.engine_auth_mode != required_mode:
                raise ValueError(
                    f"MOBI_DEPLOYMENT_ENVIRONMENT={self.deployment_environment} requires "
                    f"MOBI_ENGINE_AUTH_MODE={required_mode} so the shared key and tenant "
                    "headers are enforced service-to-service."
                )
            if self.api_key is None:
                raise ValueError(
                    f"MOBI_ENGINE_AUTH_MODE={required_mode} requires a non-blank "
                    "MOBI_API_KEY; the service must not start keyless."
                )
        else:
            # Local harness: a service shared-key mode must not be selected
            # outside its own service environment.
            for service_env, service_mode in _service_auth_modes.items():
                if self.engine_auth_mode == service_mode:
                    raise ValueError(
                        f"MOBI_ENGINE_AUTH_MODE={service_mode} is only valid with "
                        f"MOBI_DEPLOYMENT_ENVIRONMENT={service_env}."
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
