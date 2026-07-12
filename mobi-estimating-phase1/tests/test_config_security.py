"""Fail-closed engine auth configuration tests for audit P0 tenant boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_environment_fails_closed_before_tenant_auth_exists() -> None:
    with pytest.raises(ValidationError, match="not release-startable yet"):
        Settings(
            deployment_environment="production",
            engine_auth_mode="local_dev_shared_key",
        )


def test_staging_environment_fails_closed_even_with_future_auth_label() -> None:
    with pytest.raises(ValidationError, match="tenant-scoped workload/JWT identity"):
        Settings(
            deployment_environment="staging",
            engine_auth_mode="tenant_jwt",
        )


def test_release_environment_label_is_normalized_before_fail_closed_check() -> None:
    with pytest.raises(ValidationError, match="not release-startable yet"):
        Settings(
            deployment_environment="PROD",
            engine_auth_mode="TENANT_JWT",
        )


def test_local_environment_still_supports_default_test_harness() -> None:
    settings = Settings(deployment_environment="local")

    assert settings.engine_auth_mode == "local_dev_shared_key"
    assert settings.api_key is None
