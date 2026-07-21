"""Painting public-PDF proof harness regression tests."""

from __future__ import annotations

import os
import builtins
from pathlib import Path

import fitz
import pytest

from scripts import painting_public_pdf_proof as proof


def _proof_pdf(path: Path) -> None:
    doc = fitz.open()
    pages = [
        [
            "SECTION 099000 PAINTING",
            "Apply mockups of each paint system indicated and each color and finish selected.",
            "Vertical and Horizontal Surfaces: Provide samples of at least 100 sq. ft.",
        ],
        [
            "SCHEDULE OF PAINTS",
            "Gypsum Board: (At or Near Wet Areas): 3 Coats:",
            "1st Coat: Pittsburg Speedhide Interior QD Latex Primer-Sealer 6-2",
            "2nd & 3rd Coats: Pittsburg Aquapon Epoxy 97-Line",
        ],
    ]
    for source_lines in pages:
        page = doc.new_page(width=612, height=792)
        lines = source_lines + [f"Public proof source evidence line {index}." for index in range(1, 25)]
        for index, line in enumerate(lines):
            page.insert_text((40, 50 + index * 22), line, fontsize=9)
    doc.save(path)
    doc.close()


def test_public_painting_proof_reaches_internal_preview_without_persistent_estimate(tmp_path, monkeypatch):
    from app.config import settings
    from app.extraction.cache import ExtractionCacheKey, extraction_cache

    original_provider = settings.extraction_provider
    monkeypatch.setattr(extraction_cache, "_store", dict(extraction_cache._store))
    sentinel_key = ExtractionCacheKey(
        tenant_id="cache_tenant",
        company_id="cache_company",
        project_id="cache_project",
        trade_code="painting",
        provider="mock",
        model="cache-model",
        prompt_version="cache-prompt",
        trade_schema_version="1.0",
        provider_schema_version="1.0",
        page_checksums=("a" * 64,),
    )
    extraction_cache.set(sentinel_key, {"sentinel": True})

    # ``run_proof`` intentionally reconfigures the process for a standalone local
    # harness. Register the pre-test values with monkeypatch so the full pytest run
    # cannot leak ``source_text`` into legacy mock-provider tests.
    for attribute in (
        "db_path",
        "upload_dir",
        "enabled_trades",
        "extraction_provider",
        "enable_live_extraction",
        "extraction_cache_enabled",
    ):
        monkeypatch.setattr(settings, attribute, getattr(settings, attribute))
    for name in (
        "MOBI_DB_PATH",
        "MOBI_UPLOAD_DIR",
        "MOBI_DEPLOYMENT_ENVIRONMENT",
        "MOBI_ENGINE_AUTH_MODE",
        "MOBI_ENABLED_TRADES",
        "MOBI_EXTRACTION_PROVIDER",
        "MOBI_ENABLE_LIVE_EXTRACTION",
    ):
        # Register the current value with pytest before the harness overwrites it
        # directly through os.environ. Teardown restores the original value.
        monkeypatch.setenv(name, os.environ.get(name, ""))
    pdf = tmp_path / "painting-proof.pdf"
    _proof_pdf(pdf)
    monkeypatch.setattr(
        proof,
        "TARGET_PAGES",
        {1: ("099000-1", "PAINTING"), 2: ("099000-2", "PAINTING")},
    )

    report = proof.run_proof(
        pdf,
        tmp_path / "run",
        enforce_registered_source_hash=False,
    )

    assert report["status"] == "pass", report.get("failures")
    assert report["sheet_count"] == 2
    assert len(report["painting_scope_items"]) == 1
    item = report["painting_scope_items"][0]
    assert item["scope_item"]["quantity"] == "100"
    assert item["scope_item"]["unit"] == "SF"
    assert len(item["evidence"]) == 2
    assert report["internal_preview_summary"]["estimate_version_created"] is False
    assert report["internal_preview_summary"]["scope_items_considered_count"] == 1
    assert report["internal_preview_summary"]["proposed_mapping_count"] == 1
    assert report["internal_preview_summary"]["blocking_exception_count"] == 0
    assert report["stages"]["estimate_version_absence_check"]["body"]["items"] == []
    assert report["stages"]["proposal_absence_check"]["body"]["items"] == []
    assert report["persistence_absence"] == {
        "estimates_verified_empty": True,
        "proposals_verified_empty": True,
    }
    assert report["source"]["internal_testing_only"] is True
    assert len(report["source"]["sha256"]) == 64
    customer_preview = report["customer_safe_preview"]
    assert customer_preview["status"] == "internal_preview_only"
    assert customer_preview["line_items"][0]["quantity"] == ""
    assert customer_preview["line_items"][0]["unit"] == ""
    assert customer_preview["summary"]["quantity_abstained_count"] == 1
    assert customer_preview["summary"]["unsupported_scope_count"] == 1
    assert all(value is False for value in report["safety"].values())
    assert settings.extraction_provider == original_provider
    assert extraction_cache.get(sentinel_key) == {"sentinel": True}


def test_public_painting_proof_refuses_existing_database(tmp_path):
    workdir = tmp_path / "existing"
    workdir.mkdir()
    (workdir / "mobi.db").write_bytes(b"existing database sentinel")

    with pytest.raises(ValueError, match="existing database"):
        proof.run_proof(
            tmp_path / "unused.pdf",
            workdir,
            enforce_registered_source_hash=False,
        )


def test_public_painting_proof_restores_environment_when_settings_import_fails(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MOBI_DEPLOYMENT_ENVIRONMENT", "worker_service")
    monkeypatch.setenv("MOBI_ENGINE_AUTH_MODE", "api_key")
    before = {
        "MOBI_DEPLOYMENT_ENVIRONMENT": os.environ["MOBI_DEPLOYMENT_ENVIRONMENT"],
        "MOBI_ENGINE_AUTH_MODE": os.environ["MOBI_ENGINE_AUTH_MODE"],
    }
    original_import = builtins.__import__

    def fail_config_import(name, *args, **kwargs):
        if name == "app.config":
            raise RuntimeError("forced settings import failure")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_config_import)
    with pytest.raises(RuntimeError, match="forced settings import failure"):
        proof.run_proof(
            tmp_path / "unused.pdf",
            tmp_path / "fresh-workdir",
            enforce_registered_source_hash=False,
        )

    assert os.environ["MOBI_DEPLOYMENT_ENVIRONMENT"] == before["MOBI_DEPLOYMENT_ENVIRONMENT"]
    assert os.environ["MOBI_ENGINE_AUTH_MODE"] == before["MOBI_ENGINE_AUTH_MODE"]
