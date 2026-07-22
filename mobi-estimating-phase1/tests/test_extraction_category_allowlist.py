"""Authoritative category allowlist enforcement in the extraction service.

A provider candidate whose ``category_code`` is not one of the trade module's
authoritative ``scope_categories`` is untrusted and must be DROPPED entirely — it
is never persisted (not even as a blocked item), never counted, and never inserts
any scope item / evidence / derivation / conflict row. Valid categories still
persist normally.
"""

from __future__ import annotations

from uuid import uuid4

from app.estimating.quantities import QuantityBasis
from app.extraction import service
from app.extraction.provider_schemas import (
    ProviderEvidence,
    ProviderQuantity,
    ProviderScopeCandidate,
    ScopeExtractionResponse,
)
from app.extraction.schemas import EvidenceType
from app.trades.registry import trade_registry
from tests.conftest import TEST_TENANT_HEADERS, prepare_verified_project

_UNKNOWN_CATEGORY = "totally_not_a_real_category"
_VALID_CATEGORY = "interior_walls"


def _candidate(category_code: str, quote: str) -> ProviderScopeCandidate:
    return ProviderScopeCandidate(
        category_code=category_code,
        description=quote,
        quantity=ProviderQuantity(basis=QuantityBasis.UNKNOWN),
        evidence=[
            ProviderEvidence(
                pdf_page_number=1,
                evidence_type=EvidenceType.OTHER,
                description=quote,
                extracted_text_quote=quote,
            )
        ],
    )


def _extract(client, pid, trade="painting", **body):
    return client.post(
        f"/api/v1/projects/{pid}/trades/{trade}/extractions",
        json=body,
        headers=TEST_TENANT_HEADERS,
    )


def test_self_persist_candidate_drops_unknown_category_without_inserting(client, monkeypatch):
    """Direct callers are defended too: an unknown category returns None and never
    touches any insert path. (The ``client`` fixture boots the app so the trade
    registry is populated.)"""
    inserted: list[dict] = []
    monkeypatch.setattr(
        service, "insert_scope_item", lambda item: inserted.append(item) or item
    )
    # These must never be reached for an unknown category; make them explode if so.
    monkeypatch.setattr(
        service, "insert_evidence", lambda *a, **k: (_ for _ in ()).throw(AssertionError("evidence inserted"))
    )
    monkeypatch.setattr(
        service, "insert_conflict", lambda *a, **k: (_ for _ in ()).throw(AssertionError("conflict inserted"))
    )
    monkeypatch.setattr(
        service, "insert_quantity_derivation",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("derivation inserted")),
    )

    module = trade_registry.get("painting", require_enabled=True)
    result = service.self_persist_candidate(
        uuid4(), "painting", uuid4(), module,
        _candidate(_UNKNOWN_CATEGORY, "paint corridors"),
        sheets_by_page={},
    )

    assert result is None
    assert inserted == []


def test_run_persists_valid_category_only_and_drops_unknown(client, monkeypatch):
    """End-to-end: a run whose provider returns one unknown and one valid candidate
    persists exactly the valid one; zero rows for the unknown category."""
    pid = prepare_verified_project(client)

    raw = ScopeExtractionResponse(
        trade_code="painting",
        candidates=[
            _candidate(_UNKNOWN_CATEGORY, "paint corridors"),
            _candidate(_VALID_CATEGORY, "WALLS: PT-1 PAINT 2 COATS"),
        ],
    ).model_dump(mode="json")

    # Bypass the live/cache provider path and inject the crafted provider output.
    monkeypatch.setattr(service, "_call_provider_with_cache", lambda *a, **k: raw)

    resp = _extract(client, pid)
    assert resp.status_code == 202
    body = resp.json()
    # Only the valid candidate is persisted and counted; the unknown is dropped.
    assert body["candidate_count"] == 1

    listing = client.get(
        f"/api/v1/projects/{pid}/scope-items?trade_code=painting&limit=200",
        headers=TEST_TENANT_HEADERS,
    ).json()
    assert listing["total"] == 1
    categories = {item["category_code"] for item in listing["items"]}
    assert categories == {_VALID_CATEGORY}
    assert _UNKNOWN_CATEGORY not in categories
