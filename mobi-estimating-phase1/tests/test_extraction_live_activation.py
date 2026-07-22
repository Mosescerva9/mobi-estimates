"""Staff live GPT-5.6 activation: fail-closed safety + readiness contract.

These tests cover the smallest safe connected activation path for exact GPT-5.6
Medium live scope extraction. The critical invariant: a request that explicitly
asks for the live provider must NEVER silently create a mock run when live
extraction is disabled or keyless — it must fail closed *before* any run row is
created, and never make a network call in the offline suite.
"""

from __future__ import annotations

import app.routers_extraction as routers_extraction
from app.config import settings
from app.extraction import mock_provider
from app.extraction.service import run_extraction as service_run_extraction
from tests.conftest import TEST_TENANT_HEADERS, prepare_verified_project

_MARKER_KEY = "configured-provider-key-marker"


def _extract(client, pid, trade="painting", headers=TEST_TENANT_HEADERS, **body):
    return client.post(
        f"/api/v1/projects/{pid}/trades/{trade}/extractions",
        json=body,
        headers=headers,
    )


def _run_total(client, pid, trade="painting") -> int:
    return client.get(
        f"/api/v1/projects/{pid}/trades/{trade}/extractions"
    ).json()["total"]


# ---------------------------------------------------------------------------
# Fail-closed: live requested but not available -> no run row, no mock fallback
# ---------------------------------------------------------------------------
def test_live_requested_but_disabled_returns_409_and_no_run(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", False)
    pid = prepare_verified_project(client)

    resp = _extract(client, pid, use_live_provider=True)

    assert resp.status_code == 409
    assert resp.json()["error"]["message"] == "Live extraction is not enabled"
    # Critical: no run row was created (no silent mock fallback).
    assert _run_total(client, pid) == 0


def test_live_requested_enabled_but_keyless_returns_503_and_no_run(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", None)
    pid = prepare_verified_project(client)

    resp = _extract(client, pid, use_live_provider=True)

    assert resp.status_code == 503
    assert resp.json()["error"]["message"] == "Live extraction is not available"
    assert _run_total(client, pid) == 0


def test_non_live_request_still_creates_mock_run(client, monkeypatch):
    # The guard must only fire when the caller explicitly requests the live
    # provider; the default offline mock path is unaffected.
    monkeypatch.setattr(settings, "enable_live_extraction", False)
    pid = prepare_verified_project(client)

    resp = _extract(client, pid)  # use_live_provider defaults to False

    assert resp.status_code == 202
    assert resp.json()["provider"] == "mock"
    assert _run_total(client, pid) == 1


# ---------------------------------------------------------------------------
# Successful staff live activation payload contract (no network call)
# ---------------------------------------------------------------------------
def test_live_ready_claims_openai_run_with_locked_model(client, monkeypatch):
    """With live enabled + a configured key, an explicit live request claims a
    real ``openai`` / ``gpt-5.6`` run. The extraction executor is stubbed so the
    contract is verified without any provider network call."""
    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", _MARKER_KEY)

    calls: list[tuple] = []

    def _no_network_run(project_id, trade_code, run_id):
        calls.append((project_id, trade_code, run_id))
        return {"status": "queued"}

    # The router looks up ``run_extraction`` as a module global at dispatch time.
    monkeypatch.setattr(routers_extraction, "run_extraction", _no_network_run)

    pid = prepare_verified_project(client)
    resp = _extract(client, pid, use_live_provider=True)

    assert resp.status_code == 202
    body = resp.json()
    assert body["provider"] == "openai"
    assert body["model_identifier"] == "gpt-5.6"
    assert body["dry_run"] is False
    # A run row was claimed and the (stubbed) executor was invoked exactly once.
    assert len(calls) == 1
    assert _run_total(client, pid) == 1


# ---------------------------------------------------------------------------
# TOCTOU: an openai-labeled run whose live flag/key is revoked between claim and
# execution must fail closed at dispatch — never call mock / persist mock output.
# ---------------------------------------------------------------------------
def _claim_queued_openai_run(client, pid, monkeypatch) -> str:
    """Claim a real openai/gpt-5.6 run without executing it (executor stubbed)."""
    claimed: dict[str, str] = {}

    def _defer(project_id, trade_code, run_id):
        claimed["run_id"] = str(run_id)
        return {"status": "queued"}

    monkeypatch.setattr(routers_extraction, "run_extraction", _defer)
    resp = _extract(client, pid, use_live_provider=True)
    assert resp.status_code == 202
    assert resp.json()["provider"] == "openai"
    return claimed["run_id"]


def test_openai_run_fails_closed_when_flag_revoked_before_execution(client, monkeypatch):
    from uuid import UUID

    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", _MARKER_KEY)
    pid = prepare_verified_project(client)
    run_id = _claim_queued_openai_run(client, pid, monkeypatch)

    # Prove the offline mock is never dispatched for the openai-labeled run.
    mock_calls: list[object] = []
    real_extract = mock_provider.MockExtractionProvider.extract_scope

    def _spy_extract(self, request):  # pragma: no cover - must never run
        mock_calls.append(request)
        return real_extract(self, request)

    monkeypatch.setattr(
        mock_provider.MockExtractionProvider, "extract_scope", _spy_extract
    )

    # The live gate is revoked AFTER the run was claimed (flag flipped / restart).
    monkeypatch.setattr(settings, "enable_live_extraction", False)

    result = service_run_extraction(UUID(pid), "painting", UUID(run_id))

    assert result["status"] == "failed"
    assert result["error_code"] == "live_extraction_unavailable"
    assert mock_calls == []  # no mock dispatch
    # No mock candidates were persisted.
    total = client.get(
        f"/api/v1/projects/{pid}/scope-items?trade_code=painting"
    ).json()["total"]
    assert total == 0
    # The run row itself is recorded as failed (fail-closed), not needs_review.
    run = client.get(
        f"/api/v1/projects/{pid}/trades/painting/extractions/{run_id}"
    ).json()
    assert run["status"] == "failed"
    assert run["error_code"] == "live_extraction_unavailable"


def test_openai_run_fails_closed_when_key_revoked_before_execution(client, monkeypatch):
    from uuid import UUID

    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", _MARKER_KEY)
    pid = prepare_verified_project(client)
    run_id = _claim_queued_openai_run(client, pid, monkeypatch)

    mock_calls: list[object] = []
    real_extract = mock_provider.MockExtractionProvider.extract_scope

    def _spy_extract(self, request):  # pragma: no cover - must never run
        mock_calls.append(request)
        return real_extract(self, request)

    monkeypatch.setattr(
        mock_provider.MockExtractionProvider, "extract_scope", _spy_extract
    )

    # Key de-provisioned after claim: still fail closed, still never mock.
    monkeypatch.setattr(settings, "openai_api_key", None)

    result = service_run_extraction(UUID(pid), "painting", UUID(run_id))

    assert result["status"] == "failed"
    assert result["error_code"] == "live_extraction_unavailable"
    assert mock_calls == []
    assert (
        client.get(f"/api/v1/projects/{pid}/scope-items?trade_code=painting").json()[
            "total"
        ]
        == 0
    )


# ---------------------------------------------------------------------------
# Trade allowlist / validation (never arbitrary unchecked pass-through)
# ---------------------------------------------------------------------------
def test_live_request_unknown_trade_404(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", _MARKER_KEY)
    pid = prepare_verified_project(client)

    resp = _extract(client, pid, trade="no_such_trade", use_live_provider=True)

    assert resp.status_code == 404
    # No painting run leaked either — the unknown trade never reached a claim.
    assert _run_total(client, pid) == 0


def test_live_request_disabled_trade_409(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", _MARKER_KEY)
    # Registered but not enabled for this project's registry state.
    from app.trades.registry import trade_registry

    monkeypatch.setattr(
        trade_registry, "_enabled", trade_registry._enabled - {"demo_concrete"}
    )
    pid = prepare_verified_project(client)

    resp = _extract(client, pid, trade="demo_concrete", use_live_provider=True)

    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------
def test_live_request_wrong_tenant_forbidden_and_no_run(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", _MARKER_KEY)
    pid = prepare_verified_project(client)

    resp = _extract(
        client,
        pid,
        use_live_provider=True,
        headers={"X-Mobi-Tenant-Id": "attacker", "X-Mobi-Company-Id": "attacker"},
    )

    assert resp.status_code == 403
    # Same-tenant read confirms no run row leaked from the cross-tenant attempt.
    assert _run_total(client, pid) == 0


# ---------------------------------------------------------------------------
# Readiness surface (no key material)
# ---------------------------------------------------------------------------
def test_live_readiness_reports_disabled_without_key_material(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", False)
    monkeypatch.setattr(settings, "openai_api_key", None)
    pid = prepare_verified_project(client)

    body = client.get(f"/api/v1/projects/{pid}/extraction/live-readiness").json()

    live = body["live"]
    assert live["live_enabled"] is False
    assert live["api_key_present"] is False
    assert live["ready_for_live_call"] is False
    assert live["model"] == "gpt-5.6"
    assert live["reasoning_effort"] == "medium"
    assert live["api"] == "responses"
    assert live["structured_outputs"] is True
    assert live["tools"] == []
    assert live["store"] is False
    # Never leak key material under any field (non-key-shaped sentinel too).
    assert _MARKER_KEY not in str(body)
    assert "sk-" not in str(body)
    # The trade allowlist is present and only lists enabled trades.
    codes = {t["trade_code"] for t in body["enabled_trades"]}
    assert "painting" in codes


def test_live_readiness_reports_ready_when_armed(client, monkeypatch):
    monkeypatch.setattr(settings, "enable_live_extraction", True)
    monkeypatch.setattr(settings, "openai_api_key", _MARKER_KEY)
    pid = prepare_verified_project(client)

    body = client.get(f"/api/v1/projects/{pid}/extraction/live-readiness").json()
    live = body["live"]

    assert live["live_enabled"] is True
    assert live["api_key_present"] is True
    assert live["ready_for_live_call"] is True
    # With a key actually configured, the readiness surface must still never echo
    # the configured key value (proved here against the configured sentinel).
    assert _MARKER_KEY not in str(body)


def test_live_readiness_wrong_tenant_forbidden(client):
    pid = prepare_verified_project(client)
    resp = client.get(
        f"/api/v1/projects/{pid}/extraction/live-readiness",
        headers={"X-Mobi-Tenant-Id": "attacker", "X-Mobi-Company-Id": "attacker"},
    )
    assert resp.status_code == 403
