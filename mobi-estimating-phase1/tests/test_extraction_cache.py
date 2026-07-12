"""Extraction cache tenant-boundary tests (audit P0-2)."""

from __future__ import annotations

from app.extraction.cache import ExtractionCache, ExtractionCacheKey, tenant_cache_identity


def _cache_key(**overrides: str) -> ExtractionCacheKey:
    values = {
        "tenant_id": "tenant_a",
        "company_id": "company_a",
        "project_id": "project_shared_uuid",
        "trade_code": "painting",
        "provider": "mock",
        "model": "mock-v1",
        "prompt_version": "scope_extractor_v1",
        "trade_schema_version": "painting_v1",
        "provider_schema_version": "provider_v1",
        "page_checksums": ("page_sha256",),
    }
    values.update(overrides)
    return ExtractionCacheKey(**values)  # type: ignore[arg-type]


def test_extraction_cache_key_includes_tenant_and_company_identity() -> None:
    """A tenant-B job must never reuse a tenant-A provider response cache key."""

    tenant_a = _cache_key(tenant_id="tenant_a", company_id="company_a")
    tenant_b = _cache_key(tenant_id="tenant_b", company_id="company_b")
    legacy_unscoped = _cache_key(tenant_id="", company_id="")

    assert tenant_a.digest() != tenant_b.digest()
    assert tenant_a.digest() != legacy_unscoped.digest()
    assert tenant_b.digest() != legacy_unscoped.digest()


def test_extraction_cache_storage_is_partitioned_by_tenant_company_key() -> None:
    cache = ExtractionCache()
    tenant_a = _cache_key(tenant_id="tenant_a", company_id="company_a")
    tenant_b = _cache_key(tenant_id="tenant_b", company_id="company_b")

    cache.set(tenant_a, {"tenant": "a", "candidates": []})

    assert cache.get(tenant_a) == {"tenant": "a", "candidates": []}
    assert cache.get(tenant_b) is None


def test_tenant_cache_identity_trims_scoped_rows_and_disables_legacy_cache() -> None:
    assert tenant_cache_identity({"tenant_id": " tenant_a ", "company_id": " company_a "}) == (
        "tenant_a",
        "company_a",
    )
    assert tenant_cache_identity({"tenant_id": None, "company_id": None}) is None
    assert tenant_cache_identity({"tenant_id": "tenant_a", "company_id": ""}) is None
