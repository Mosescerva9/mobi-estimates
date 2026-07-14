"""Fail-closed engine auth configuration tests for audit P0 tenant boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, settings


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
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_explicit_local_environment_from_env_preserves_local_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local development remains available only after an explicit env opt-in."""

    monkeypatch.setenv("MOBI_DEPLOYMENT_ENVIRONMENT", "local")
    monkeypatch.delenv("MOBI_ENGINE_AUTH_MODE", raising=False)
    monkeypatch.delenv("MOBI_API_KEY", raising=False)

    settings = Settings()

    assert settings.deployment_environment == "local"
    assert settings.engine_auth_mode == "local_dev_open"
    assert settings.api_key is None


def test_container_files_do_not_reintroduce_implicit_local_release_default() -> None:
    """Docker defaults stay unlabeled; absent-label startup is covered by the fail-closed test."""

    project_root = Path(__file__).resolve().parents[1]
    dockerfile = (project_root / "Dockerfile").read_text(encoding="utf-8")
    compose = (project_root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "MOBI_DEPLOYMENT_ENVIRONMENT=local" not in dockerfile
    assert "MOBI_DEPLOYMENT_ENVIRONMENT: local" not in compose


def test_env_example_is_honest_about_keyless_local_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    """The copy-paste local env example must not claim shared-key auth with a blank key."""

    project_root = Path(__file__).resolve().parents[1]
    env_example_path = project_root / ".env.example"
    env_example = env_example_path.read_text(encoding="utf-8")

    monkeypatch.delenv("MOBI_ENGINE_AUTH_MODE", raising=False)
    monkeypatch.delenv("MOBI_API_KEY", raising=False)

    settings = Settings(_env_file=env_example_path)  # type: ignore[call-arg]

    assert "MOBI_ENGINE_AUTH_MODE=local_dev_open" in env_example
    assert "MOBI_ENGINE_AUTH_MODE=local_dev_shared_key\nMOBI_API_KEY=" not in env_example
    assert settings.engine_auth_mode == "local_dev_open"
    assert settings.api_key is None


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

    assert settings.engine_auth_mode == "local_dev_open"
    assert settings.api_key is None


def test_configured_api_key_is_normalized_for_local_shared_key_gate() -> None:
    settings = Settings(
        deployment_environment="local",
        engine_auth_mode="local_dev_shared_key",
        api_key="  local-secret  ",
    )

    assert settings.engine_auth_mode == "local_dev_shared_key"
    assert settings.api_key == "local-secret"


def test_blank_configured_api_key_fails_closed_instead_of_disabling_auth() -> None:
    with pytest.raises(ValidationError, match="api_key must be a non-blank shared secret"):
        Settings(deployment_environment="local", engine_auth_mode="local_dev_shared_key", api_key="   ")


def test_shared_key_auth_mode_requires_configured_key() -> None:
    """Config must not claim shared-key enforcement when no key is present."""

    with pytest.raises(ValidationError, match="local_dev_shared_key requires a non-blank"):
        Settings(deployment_environment="local", engine_auth_mode="local_dev_shared_key")


def test_open_local_auth_mode_cannot_silently_hold_a_key() -> None:
    """The keyless local harness label must stay visibly keyless."""

    with pytest.raises(ValidationError, match="local_dev_open must not be combined"):
        Settings(deployment_environment="local", engine_auth_mode="local_dev_open", api_key="local-secret")


def test_explicit_open_local_auth_mode_is_honest_about_keyless_harness() -> None:
    settings = Settings(deployment_environment="local", engine_auth_mode="local_dev_open")

    assert settings.engine_auth_mode == "local_dev_open"
    assert settings.api_key is None


def test_shared_key_gate_still_allows_health_without_tenant_identity(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Liveness/readiness probes remain reachable for local ops when the key gate is on."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    assert client.get("/health", headers={}).status_code == 200
    assert client.get("/api/v1/health", headers={}).status_code == 200


def test_shared_key_gate_rejects_missing_key_before_route_execution(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """A configured local shared key must not leave non-health routes open."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get("/api/v1/trades", headers={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_shared_key_gate_requires_tenant_identity_with_valid_key(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """The temporary shared-key path must not accept tenantless engine traffic."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get("/api/v1/trades", headers={"X-API-Key": "local-secret"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tenant_identity_required"


@pytest.mark.parametrize(
    "headers,missing_field",
    [
        ({"X-Mobi-Tenant-Id": "null", "X-Mobi-Company-Id": "company_a"}, "tenant_id"),
        ({"X-Mobi-Tenant-Id": "tenant_a", "X-Mobi-Company-Id": " undefined "}, "company_id"),
    ],
)
def test_shared_key_gate_rejects_null_sentinel_tenant_identity_headers(
    client,
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    missing_field: str,
) -> None:
    """Sentinel identity headers must not satisfy the temporary tenant gate."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get(
        "/api/v1/trades",
        headers={"X-API-Key": "local-secret", **headers},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "tenant_identity_required"
    assert missing_field in body["error"]["details"]["reason"]


def test_shared_key_gate_rejects_ambiguous_auth_credential_locations(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """The temporary shared-key gate must fail closed on multiple auth credentials."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get(
        "/api/v1/trades",
        headers={
            "X-API-Key": "local-secret",
            "Authorization": "Bearer local-secret",
            "X-Mobi-Tenant-Id": "tenant_a",
            "X-Mobi-Company-Id": "company_a",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_shared_key_gate_rejects_coalesced_api_key_header(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Comma-coalesced duplicate key headers must not satisfy local auth."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get(
        "/api/v1/trades",
        headers={
            "X-API-Key": "local-secret, attacker-key",
            "X-Mobi-Tenant-Id": "tenant_a",
            "X-Mobi-Company-Id": "company_a",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_shared_key_gate_rejects_coalesced_api_key_even_with_valid_bearer(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """An ambiguous key header must fail even if another credential is valid."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get(
        "/api/v1/trades",
        headers={
            "X-API-Key": "local-secret, attacker-key",
            "Authorization": "Bearer local-secret",
            "X-Mobi-Tenant-Id": "tenant_a",
            "X-Mobi-Company-Id": "company_a",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_shared_key_gate_rejects_coalesced_tenant_identity_header(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Coalesced tenant/company headers must not become a fake tenant identity."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get(
        "/api/v1/trades",
        headers={
            "X-API-Key": "local-secret",
            "X-Mobi-Tenant-Id": "tenant_a,tenant_b",
            "X-Mobi-Company-Id": "company_a",
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "tenant_identity_required"
    assert "tenant_id" in body["error"]["details"]["reason"]


def test_shared_key_gate_rejects_duplicate_api_key_header_instances(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated key headers must fail even when the first value is correct."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get(
        "/api/v1/trades",
        headers=[
            ("X-API-Key", "local-secret"),
            ("X-API-Key", "attacker-key"),
            ("X-Mobi-Tenant-Id", "tenant_a"),
            ("X-Mobi-Company-Id", "company_a"),
        ],
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_shared_key_gate_rejects_duplicate_tenant_header_instances(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated tenant headers must fail even when the first value is correct."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get(
        "/api/v1/trades",
        headers=[
            ("X-API-Key", "local-secret"),
            ("X-Mobi-Tenant-Id", "tenant_a"),
            ("X-Mobi-Tenant-Id", "tenant_b"),
            ("X-Mobi-Company-Id", "company_a"),
        ],
    )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "tenant_identity_required"
    assert "tenant_id" in body["error"]["details"]["reason"]


def test_shared_key_gate_accepts_authorized_tenant_scoped_local_request(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same-tenant local requests still work while release startup remains locked."""

    monkeypatch.setattr(settings, "api_key", "local-secret")

    response = client.get(
        "/api/v1/trades",
        headers={
            "Authorization": "Bearer local-secret",
            "X-Mobi-Tenant-Id": "tenant_a",
            "X-Mobi-Company-Id": "company_a",
        },
    )

    assert response.status_code == 200
    assert "trades" in response.json()
