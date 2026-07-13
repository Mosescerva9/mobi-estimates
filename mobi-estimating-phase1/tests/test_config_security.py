"""Fail-closed engine auth configuration tests for audit P0 tenant boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_environment_fails_closed_before_tenant_auth_exists() -> None:
    with pytest.raises(ValidationError, match="not release-startable yet"):
        Settings(
            deployment_environment="production",
            engine_auth_mode="local_dev_shared_key",
        )


def test_production_environment_fails_closed_when_sourced_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real startup settings path must fail closed from MOBI_* env vars."""

    monkeypatch.setenv("MOBI_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setenv("MOBI_ENGINE_AUTH_MODE", "local_dev_shared_key")
    monkeypatch.setenv("MOBI_API_KEY", "legacy-shared-key-is-not-release-auth")

    with pytest.raises(ValidationError, match="not release-startable yet"):
        Settings()


def test_absent_deployment_environment_fails_closed_for_unlabeled_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unlabeled container/release startup must not inherit local/open defaults."""

    monkeypatch.delenv("MOBI_DEPLOYMENT_ENVIRONMENT", raising=False)
    monkeypatch.delenv("MOBI_ENGINE_AUTH_MODE", raising=False)
    monkeypatch.delenv("MOBI_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="MOBI_DEPLOYMENT_ENVIRONMENT=local"):
        Settings()


def test_explicit_local_environment_from_env_preserves_local_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local development remains available only after an explicit env opt-in."""

    monkeypatch.setenv("MOBI_DEPLOYMENT_ENVIRONMENT", "local")
    monkeypatch.delenv("MOBI_ENGINE_AUTH_MODE", raising=False)
    monkeypatch.delenv("MOBI_API_KEY", raising=False)

    settings = Settings()

    assert settings.deployment_environment == "local"
    assert settings.engine_auth_mode == "local_dev_shared_key"
    assert settings.api_key is None


def test_container_files_do_not_reintroduce_implicit_local_release_default() -> None:
    """Docker defaults stay unlabeled; absent-label startup is covered by the fail-closed test."""

    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text(encoding="utf-8")
    compose = (project_root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "MOBI_DEPLOYMENT_ENVIRONMENT=local" not in dockerfile
    assert "MOBI_DEPLOYMENT_ENVIRONMENT: local" not in compose


def test_staging_environment_fails_closed_with_implemented_local_auth_mode() -> None:
    with pytest.raises(ValidationError, match="not release-startable yet"):
        Settings(
            deployment_environment="staging",
            engine_auth_mode="local_dev_shared_key",
        )


def test_staging_environment_fails_closed_even_with_future_auth_label() -> None:
    with pytest.raises(ValidationError, match="tenant-scoped workload/JWT identity"):
        Settings(
            deployment_environment="staging",
            engine_auth_mode="tenant_jwt",
        )


def test_preview_environment_fails_closed_before_public_preview_exposure() -> None:
    """Vercel/preview-like public environments must not start the engine early."""

    with pytest.raises(ValidationError, match="not release-startable yet"):
        Settings(
            deployment_environment=" preview ",
            engine_auth_mode="local_dev_shared_key",
            api_key="shared-preview-key-is-not-enough",
        )


def test_release_environment_label_is_normalized_before_fail_closed_check() -> None:
    with pytest.raises(ValidationError, match="not release-startable yet"):
        Settings(
            deployment_environment="PROD",
            engine_auth_mode="local_dev_shared_key",
        )


def test_unimplemented_engine_auth_mode_fails_closed_even_locally() -> None:
    """A future/typo auth label must not imply tenant-safe engine identity."""

    with pytest.raises(ValidationError, match="Unsupported MOBI_ENGINE_AUTH_MODE"):
        Settings(
            deployment_environment="local",
            engine_auth_mode="tenant_jwt",
        )


@pytest.mark.parametrize("label", ["stage", "prd", "live", "canary", "release", "production-us", "dev", "test", "ci"])
def test_unrecognized_environment_label_fails_closed(label: str) -> None:
    """Every non-local label must fail closed until tenant identity exists."""

    with pytest.raises(ValidationError, match="not release-startable yet"):
        Settings(deployment_environment=label)


def test_local_environment_label_still_supports_local_harness() -> None:
    settings = Settings(deployment_environment="local")

    assert settings.engine_auth_mode == "local_dev_shared_key"
    assert settings.api_key is None


def test_configured_api_key_is_normalized_for_local_shared_key_gate() -> None:
    settings = Settings(deployment_environment="local", api_key="  local-secret  ")

    assert settings.api_key == "local-secret"


def test_blank_configured_api_key_fails_closed_instead_of_disabling_auth() -> None:
    with pytest.raises(ValidationError, match="api_key must be a non-blank shared secret"):
        Settings(deployment_environment="local", api_key="   ")
