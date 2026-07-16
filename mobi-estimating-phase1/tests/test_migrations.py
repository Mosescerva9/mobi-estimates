"""Migration and database-concurrency-guard tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app import database, pricing_db
from app.config import settings
from app.extraction_db import (
    append_review_event,
    claim_extraction_run,
    get_latest_derivation,
    get_run,
    get_scope_item,
    insert_conflict,
    insert_evidence,
    insert_quantity_derivation,
    insert_scope_item,
    list_conflicts,
    list_evidence,
    list_review_events,
    list_routing,
    list_runs,
    list_scope_items,
    set_manual_override,
    update_run,
    update_scope_item,
    upsert_routing_decision,
)
from app.customer_revisions import (
    create_revision_requests,
    list_revision_requests,
    list_revision_rescope_versions,
)
from app.migrations import apply_migrations, current_version
from app.qa_findings import list_qa_findings
from app.quantity_requirements import (
    QuantityRequirementError,
    draft_quantity_requirements,
    list_quantity_requirements,
)


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def _make_phase1_db(db_path: Path) -> str:
    """Create a database that looks exactly like a Phase 1 database."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                contractor_name TEXT,
                original_file_name TEXT,
                stored_file_path TEXT NOT NULL,
                status TEXT NOT NULL,
                page_count INTEGER NOT NULL DEFAULT 0,
                file_sha256 TEXT,
                file_size_bytes INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT
            )
            """
        )
        project_id = str(uuid4())
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, "Legacy Project", "/x/original.pdf", "uploaded",
             "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
    finally:
        conn.close()
    return project_id


def test_migration_from_phase1_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    project_id = _make_phase1_db(db_path)

    # Point the app database at the legacy file and migrate it in place.
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    tables = _table_names(db_path)
    assert {"projects", "processing_jobs", "sheets", "schema_migrations"} <= tables

    # The existing project row is preserved (no reset).
    project = database.get_project(__import__("uuid").UUID(project_id))
    assert project is not None
    assert project["name"] == "Legacy Project"


def test_migrations_are_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()
    first_version = None
    with database.get_connection() as conn:
        first_version = current_version(conn)
    # Running again applies nothing new.
    database.init_db()
    with database.get_connection() as conn:
        applied = apply_migrations(conn)
        assert applied == []
        assert current_version(conn) == first_version
    # Phase 1+2 (3) + Phase 3 (→v11) + Phase 4 (→v15) + Phase 5 (→v16)
    # + all-trade coverage matrix (→v17) + QA findings log (→v18)
    # + customer revision requests (→v19) + quantity requirements (→v20)
    # + customer revision rescope versions (→v21)
    # + project tenant identity (→v22)
    # + processing job tenant identity (→v23)
    # + sheet tenant identity (→v24)
    # + extraction run tenant identity (→v25)
    # + scope item tenant identity (→v26)
    # + quantity requirement tenant identity (→v27)
    # + evidence reference tenant identity (→v28)
    # + sheet routing decision tenant identity (→v29)
    # + QA finding tenant identity (→v30)
    # + estimate artifact tenant identity (→v31)
    # + customer revision tenant identity (→v32)
    # + scope-review child artifact tenant identity (→v33)
    # + proposal artifact tenant identity (→v34)
    # + scope assembly mapping tenant identity (→v35)
    # + trade coverage tenant identity (→v36)
    # + canonical takeoff evidence store (→v37)
    # + canonical takeoff evidence provider fields (→v38) = 38.
    assert first_version == 38

    with database.get_connection() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(scope_assembly_mappings)")}
        assert {"tenant_id", "company_id"} <= columns
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(scope_assembly_mappings)")}
        assert "uq_mapping_tenant_project_scope" in indexes
        assert "uq_mapping_active" not in indexes

        # Canonical takeoff evidence store: table + tenant/document/sheet indexes.
        assert "canonical_takeoff_evidence" in _table_names(db_path)
        evidence_indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(canonical_takeoff_evidence)")
        }
        assert {
            "idx_canonical_evidence_tenant_company_project",
            "idx_canonical_evidence_project",
            "idx_canonical_evidence_document",
            "idx_canonical_evidence_sheet",
        } <= evidence_indexes


def test_only_one_active_job_per_project(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(project_id), "P", "/x.pdf", "uploaded",
             "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00",
             "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO processing_jobs (id, project_id, status, attempt, "
            "created_at, updated_at) VALUES (?, ?, 'queued', 1, ?, ?)",
            (str(uuid4()), str(project_id), "t", "t"),
        )
        conn.commit()
        # A second active (queued) job for the same project must be rejected by
        # the partial unique index.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO processing_jobs (id, project_id, status, attempt, "
                "created_at, updated_at) VALUES (?, ?, 'processing', 2, ?, ?)",
                (str(uuid4()), str(project_id), "t", "t"),
            )
            conn.commit()


def test_claim_returns_active_when_job_in_progress(tmp_path, monkeypatch):
    db_path = tmp_path / "claim.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)",
            (str(project_id), "P", "/x.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO processing_jobs (id, project_id, status, attempt, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'processing', 1, ?, ?, ?, ?)",
            (str(uuid4()), str(project_id), "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()

    outcome, job, _ = database.claim_processing_slot(project_id, force=False)
    assert outcome == "active"
    assert job is not None


@pytest.mark.parametrize(
    ("job_tenant_id", "job_company_id"),
    [(None, None), ("tenant_b", "company_a"), ("tenant_a", "company_b"), ("null", "company_a")],
)
def test_claim_denies_active_job_with_missing_or_mismatched_tenant_identity(
    tmp_path, monkeypatch, job_tenant_id, job_company_id
):
    db_path = tmp_path / "claim-active-job-identity.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)",
            (str(project_id), "P", "/x.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO processing_jobs (id, project_id, status, attempt, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'processing', 1, ?, ?, ?, ?)",
            (str(uuid4()), str(project_id), "t", "t", job_tenant_id, job_company_id),
        )
        conn.commit()

    outcome, job, _ = database.claim_processing_slot(project_id, force=False)
    assert outcome == "tenant_unscoped"
    assert job is None


def test_claim_race_fallback_denies_mismatched_active_job(tmp_path, monkeypatch):
    db_path = tmp_path / "claim-race-active-job-identity.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)",
            (str(project_id), "P", "/x.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            """
            CREATE TRIGGER inject_mismatched_active_job_before_claim
            BEFORE INSERT ON processing_jobs
            WHEN NEW.status = 'queued'
            BEGIN
                INSERT INTO processing_jobs (
                    id, project_id, status, attempt, created_at, updated_at,
                    tenant_id, company_id
                ) VALUES (
                    'race-job', NEW.project_id, 'processing', NEW.attempt,
                    NEW.created_at, NEW.updated_at, 'tenant_b', NEW.company_id
                );
            END
            """
        )
        conn.commit()

    outcome, job, _ = database.claim_processing_slot(project_id, force=False)

    assert outcome == "tenant_unscoped"
    assert job is None


def test_processing_job_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "job-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    job_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)",
            (
                str(project_id),
                "Tenant Project",
                "/tenant.pdf",
                "t",
                "t",
                "tenant_a",
                "company_a",
            ),
        )
        conn.execute(
            "INSERT INTO processing_jobs (id, project_id, status, attempt, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'queued', 1, ?, ?, NULL, NULL)",
            (str(job_id), str(project_id), "t", "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 23")
        conn.commit()
        apply_migrations(conn)
        row = conn.execute(
            "SELECT tenant_id, company_id FROM processing_jobs WHERE id = ?",
            (str(job_id),),
        ).fetchone()

    assert tuple(row) == ("tenant_a", "company_a")


def test_claim_processing_slot_copies_project_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "claim-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)",
            (
                str(project_id),
                "Tenant P",
                "/tenant.pdf",
                "t",
                "t",
                "tenant_a",
                "company_a",
            ),
        )
        conn.commit()

    outcome, job, _project = database.claim_processing_slot(project_id, force=False)

    assert outcome == "created"
    assert job is not None
    assert job["tenant_id"] == "tenant_a"
    assert job["company_id"] == "company_a"


def test_sheet_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "sheet-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)",
            (str(project_id), "Tenant Project", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, ?, ?, NULL, NULL)",
            (str(sheet_id), str(project_id), "t", "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 24")
        conn.commit()
        apply_migrations(conn)
        row = conn.execute(
            "SELECT tenant_id, company_id FROM sheets WHERE id = ?",
            (str(sheet_id),),
        ).fetchone()

    assert tuple(row) == ("tenant_a", "company_a")


def test_insert_sheet_copies_project_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "insert-sheet-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant Project", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()

    sheet = database.insert_sheet(
        {
            "id": str(uuid4()),
            "project_id": str(project_id),
            "pdf_page_number": 1,
            "page_index": 0,
            "processing_status": "complete",
            "review_status": "pending",
            "requires_review": 1,
            "requires_ocr": 0,
            "text_char_count": 0,
            "rotation": 0,
        }
    )

    assert sheet["tenant_id"] == "tenant_a"
    assert sheet["company_id"] == "company_a"


def test_insert_sheet_denies_supplied_tenant_mismatch(tmp_path, monkeypatch):
    db_path = tmp_path / "insert-sheet-tenant-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant Project", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()

    with pytest.raises(ValueError, match="sheet tenant/company identity must match project"):
        database.insert_sheet(
            {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "tenant_id": "tenant_b",
                "company_id": "company_a",
                "pdf_page_number": 1,
                "page_index": 0,
                "processing_status": "complete",
                "review_status": "pending",
                "requires_review": 1,
                "requires_ocr": 0,
                "text_char_count": 0,
                "rotation": 0,
            }
        )


def test_insert_sheet_denies_cross_tenant_job_reference(tmp_path, monkeypatch):
    db_path = tmp_path / "insert-sheet-job-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_a = uuid4()
    project_b = uuid4()
    job_b = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_a), "Tenant A Project", "/tenant-a.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_b), "Tenant B Project", "/tenant-b.pdf", "t", "t", "tenant_b", "company_b"),
        )
        conn.execute(
            "INSERT INTO processing_jobs (id, project_id, status, attempt, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'processing', 1, ?, ?, ?, ?)",
            (str(job_b), str(project_b), "t", "t", "tenant_b", "company_b"),
        )
        conn.commit()

    with pytest.raises(ValueError, match="sheet job identity must match project tenant"):
        database.insert_sheet(
            {
                "id": str(uuid4()),
                "project_id": str(project_a),
                "job_id": str(job_b),
                "pdf_page_number": 1,
                "page_index": 0,
                "processing_status": "complete",
                "review_status": "pending",
                "requires_review": 1,
                "requires_ocr": 0,
                "text_char_count": 0,
                "rotation": 0,
            }
        )


def test_insert_sheet_denies_tenantless_project(tmp_path, monkeypatch):
    db_path = tmp_path / "insert-sheet-tenantless.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, NULL, NULL)",
            (str(project_id), "Tenantless Project", "/tenantless.pdf", "t", "t"),
        )
        conn.commit()

    with pytest.raises(ValueError, match="tenant_id and company_id are required"):
        database.insert_sheet(
            {
                "id": str(uuid4()),
                "project_id": str(project_id),
                "pdf_page_number": 1,
                "page_index": 0,
                "processing_status": "complete",
                "review_status": "pending",
            }
        )


def test_claim_processing_slot_denies_tenantless_project_without_creating_job(tmp_path, monkeypatch):
    db_path = tmp_path / "claim-tenantless.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, NULL, NULL)",
            (str(project_id), "Tenantless P", "/tenantless.pdf", "t", "t"),
        )
        conn.commit()

    outcome, job, project = database.claim_processing_slot(project_id, force=False)

    assert outcome == "tenant_unscoped"
    assert job is None
    assert project is not None
    with database.get_connection() as conn:
        job_count = conn.execute(
            "SELECT COUNT(*) FROM processing_jobs WHERE project_id = ?",
            (str(project_id),),
        ).fetchone()[0]
    assert job_count == 0


@pytest.mark.parametrize(
    ("tenant_id", "company_id"),
    [("   ", "company_a"), ("tenant_a", "   "), ("null", "company_a")],
)
def test_claim_processing_slot_denies_malformed_tenant_identity(
    tmp_path, monkeypatch, tenant_id, company_id
):
    db_path = tmp_path / "claim-malformed-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)",
            (str(project_id), "Malformed Tenant P", "/malformed.pdf", "t", "t", tenant_id, company_id),
        )
        conn.commit()

    outcome, job, _project = database.claim_processing_slot(project_id, force=False)

    assert outcome == "tenant_unscoped"
    assert job is None


def test_extraction_run_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "run-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    run_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant Project", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'queued', 'test', 1, ?, ?, NULL, NULL)",
            (str(run_id), str(project_id), "t", "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 25")
        conn.commit()
        apply_migrations(conn)
        row = conn.execute(
            "SELECT tenant_id, company_id FROM extraction_runs WHERE id = ?",
            (str(run_id),),
        ).fetchone()

    assert tuple(row) == ("tenant_a", "company_a")


def test_claim_extraction_run_copies_project_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "claim-run-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()

    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )

    assert outcome == "created"
    assert run["tenant_id"] == "tenant_a"
    assert run["company_id"] == "company_a"


def test_claim_extraction_run_denies_tenantless_project_without_creating_run(tmp_path, monkeypatch):
    db_path = tmp_path / "claim-run-tenantless.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, NULL, NULL)",
            (str(project_id), "Tenantless P", "/tenantless.pdf", "t", "t"),
        )
        conn.commit()

    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )

    assert outcome == "tenant_unscoped"
    assert run == {}
    with database.get_connection() as conn:
        run_count = conn.execute(
            "SELECT COUNT(*) FROM extraction_runs WHERE project_id = ?",
            (str(project_id),),
        ).fetchone()[0]
    assert run_count == 0


def test_claim_extraction_run_denies_mismatched_active_run_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "claim-run-mismatched-active.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'running', 'test', 1, ?, ?, ?, ?)",
            (str(uuid4()), str(project_id), "t", "t", "tenant_b", "company_a"),
        )
        conn.commit()

    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )

    assert outcome == "tenant_unscoped"
    assert run == {}


def test_update_run_rejects_identity_field_mutation(tmp_path, monkeypatch):
    db_path = tmp_path / "run-identity-immutable.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"

    with pytest.raises(ValueError, match="identity fields are immutable"):
        update_run(UUID(run["id"]), tenant_id="tenant_b")

    unchanged = get_run(project_id, UUID(run["id"]))
    assert unchanged is not None
    assert unchanged["tenant_id"] == "tenant_a"
    assert unchanged["company_id"] == "company_a"


def test_update_run_fails_closed_on_tenant_mismatched_run_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "run-identity-mismatch-update.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"

    with database.get_connection() as conn:
        conn.execute(
            "UPDATE extraction_runs SET tenant_id=?, company_id=? WHERE id=?",
            ("tenant_b", "company_b", run["id"]),
        )
        conn.commit()

    with pytest.raises(PermissionError, match="cross_tenant_project_access_denied"):
        update_run(UUID(run["id"]), status="running")

    hidden = get_run(project_id, UUID(run["id"]))
    assert hidden is None
    with database.get_connection() as conn:
        unchanged = conn.execute(
            "SELECT status, tenant_id, company_id FROM extraction_runs WHERE id=?",
            (run["id"],),
        ).fetchone()
    assert unchanged is not None
    assert unchanged["status"] == "queued"
    assert unchanged["tenant_id"] == "tenant_b"
    assert unchanged["company_id"] == "company_b"


def test_update_run_fails_closed_on_tenantless_run_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "run-identity-tenantless-update.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"

    with database.get_connection() as conn:
        conn.execute(
            "UPDATE extraction_runs SET tenant_id=NULL, company_id=NULL WHERE id=?",
            (run["id"],),
        )
        conn.commit()

    with pytest.raises(PermissionError, match="tenant_project_context_required"):
        update_run(UUID(run["id"]), status="running")

    hidden = get_run(project_id, UUID(run["id"]))
    assert hidden is None
    with database.get_connection() as conn:
        unchanged = conn.execute(
            "SELECT status, tenant_id, company_id FROM extraction_runs WHERE id=?",
            (run["id"],),
        ).fetchone()
    assert unchanged is not None
    assert unchanged["status"] == "queued"
    assert unchanged["tenant_id"] is None
    assert unchanged["company_id"] is None


def test_update_job_rejects_identity_field_mutation(tmp_path, monkeypatch):
    db_path = tmp_path / "job-identity-immutable.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, job, _project = database.claim_processing_slot(project_id, force=False)
    assert outcome == "created"
    assert job is not None

    with pytest.raises(ValueError, match="identity fields are immutable"):
        database.update_job(__import__("uuid").UUID(job["id"]), tenant_id="tenant_b")

    unchanged = database.get_job(__import__("uuid").UUID(job["id"]))
    assert unchanged is not None
    assert unchanged["tenant_id"] == "tenant_a"
    assert unchanged["company_id"] == "company_a"


def test_update_run_rejects_crafted_sql_field_identity_bypass(tmp_path, monkeypatch):
    db_path = tmp_path / "run-identity-crafted-field.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"

    with pytest.raises(ValueError, match="unsupported fields"):
        update_run(UUID(run["id"]), **{"status=status, tenant_id": "tenant_b"})

    unchanged = get_run(project_id, UUID(run["id"]))
    assert unchanged is not None
    assert unchanged["tenant_id"] == "tenant_a"
    assert unchanged["company_id"] == "company_a"
    assert unchanged["status"] == "queued"


def test_update_job_rejects_crafted_sql_field_identity_bypass(tmp_path, monkeypatch):
    db_path = tmp_path / "job-identity-crafted-field.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'uploaded', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, job, _project = database.claim_processing_slot(project_id, force=False)
    assert outcome == "created"
    assert job is not None

    with pytest.raises(ValueError, match="unsupported fields"):
        database.update_job(UUID(job["id"]), **{"status = status, tenant_id": "tenant_b"})

    unchanged = database.get_job(UUID(job["id"]))
    assert unchanged is not None
    assert unchanged["tenant_id"] == "tenant_a"
    assert unchanged["company_id"] == "company_a"
    assert unchanged["status"] == "queued"


def _base_scope_item(project_id: UUID, run_id: str) -> dict:
    return {
        "id": str(uuid4()),
        "project_id": str(project_id),
        "extraction_run_id": run_id,
        "trade_code": "painting",
        "trade_module_version": "test",
        "trade_schema_version": "test",
        "category_code": "walls",
        "description": "Paint walls",
        "location": "Room 1",
        "specification_section": None,
        "assembly_designation": None,
        "material_or_substrate": "gypsum",
        "existing_condition": None,
        "proposed_work": "paint",
        "quantity": "100",
        "unit": "SF",
        "quantity_basis": "test_fixture",
        "raw_quantity_inputs": {},
        "extraction_confidence": 0.9,
        "conflict_status": "none",
        "review_status": "pending",
        "blocking_issues": [],
        "assumptions": [],
        "exclusions": [],
        "trade_data": {},
        "original_provider_candidate": {},
        "calculation_id": None,
        "calculation_version": None,
        "reviewer_notes": None,
        "approved_at": None,
    }


def test_scope_item_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "scope-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    run_id = uuid4()
    scope_item_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant Project", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'completed', 'test', 1, ?, ?, ?, ?)",
            (str(run_id), str(project_id), "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "quantity_basis, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'test', 'test', 'walls', 'Paint walls', "
            "'test_fixture', ?, ?, NULL, NULL)",
            (str(scope_item_id), str(project_id), str(run_id), "t", "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 26")
        conn.commit()
        apply_migrations(conn)
        row = conn.execute(
            "SELECT tenant_id, company_id FROM scope_items WHERE id = ?",
            (str(scope_item_id),),
        ).fetchone()

    assert tuple(row) == ("tenant_a", "company_a")


def test_insert_scope_item_copies_project_and_run_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "scope-insert-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"

    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))

    assert scope_item["tenant_id"] == "tenant_a"
    assert scope_item["company_id"] == "company_a"


def test_scope_review_child_artifacts_copy_and_filter_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "scope-review-child-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))
    scope_item_id = UUID(scope_item["id"])

    derivation = insert_quantity_derivation(
        {
            "id": str(uuid4()),
            "project_id": str(project_id),
            "scope_item_id": scope_item["id"],
            "trade_code": "painting",
            "formula_id": "wall_area_v1",
            "formula_version": "1",
            "inputs": {"area": "100"},
            "output_value": "100",
            "output_unit": "SF",
        }
    )
    conflict = insert_conflict(
        {
            "id": str(uuid4()),
            "project_id": str(project_id),
            "scope_item_id": scope_item["id"],
            "code": "spec_conflict",
            "severity": "blocking",
            "description": "Spec and plan conflict",
        }
    )
    review = append_review_event(
        {
            "project_id": str(project_id),
            "scope_item_id": scope_item["id"],
            "trade_code": "painting",
            "action": "blocked",
            "new_state": "blocked",
            "reviewer_id": "qa",
        }
    )

    assert derivation["tenant_id"] == "tenant_a"
    assert conflict["company_id"] == "company_a"
    assert review["tenant_id"] == "tenant_a"
    latest_derivation = get_latest_derivation(project_id, scope_item_id)
    assert latest_derivation is not None
    assert latest_derivation["company_id"] == "company_a"
    assert list_conflicts(project_id, scope_item_id)[0]["tenant_id"] == "tenant_a"
    assert list_review_events(project_id, scope_item_id)[0]["company_id"] == "company_a"

    with database.get_connection() as conn:
        conn.execute("UPDATE scope_items SET tenant_id='tenant_b' WHERE id=?", (scope_item["id"],))
        conn.commit()

    assert get_latest_derivation(project_id, scope_item_id) is None
    assert list_conflicts(project_id, scope_item_id) == []
    assert list_review_events(project_id, scope_item_id) == []


def test_scope_review_tenant_identity_migration_backfills_from_scope_and_project(tmp_path, monkeypatch):
    db_path = tmp_path / "scope-review-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    run_id = uuid4()
    scope_item_id = uuid4()
    derivation_id = uuid4()
    conflict_id = uuid4()
    review_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant Project", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'completed', 'test', 1, ?, ?, ?, ?)",
            (str(run_id), str(project_id), "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "quantity_basis, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'test', 'test', 'walls', 'Paint walls', "
            "'test_fixture', ?, ?, 'tenant_a', 'company_a')",
            (str(scope_item_id), str(project_id), str(run_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO quantity_derivations (id, scope_item_id, trade_code, formula_id, "
            "formula_version, inputs, output_value, output_unit, calculated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'wall_area_v1', '1', '{}', '100', 'SF', ?, NULL, NULL)",
            (str(derivation_id), str(scope_item_id), "t"),
        )
        conn.execute(
            "INSERT INTO conflicts (id, scope_item_id, code, severity, description, "
            "competing_evidence, resolution_status, created_at, tenant_id, company_id) "
            "VALUES (?, ?, 'spec_conflict', 'blocking', 'Conflict', '[]', 'open', ?, NULL, NULL)",
            (str(conflict_id), str(scope_item_id), "t"),
        )
        conn.execute(
            "INSERT INTO review_events (id, project_id, scope_item_id, trade_code, action, "
            "reviewer_id, created_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'blocked', 'qa', ?, NULL, NULL)",
            (str(review_id), str(project_id), str(scope_item_id), "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 33")
        conn.commit()
        apply_migrations(conn)
        rows = {
            "quantity_derivations": conn.execute(
                "SELECT tenant_id, company_id FROM quantity_derivations WHERE id=?",
                (str(derivation_id),),
            ).fetchone(),
            "conflicts": conn.execute(
                "SELECT tenant_id, company_id FROM conflicts WHERE id=?",
                (str(conflict_id),),
            ).fetchone(),
            "review_events": conn.execute(
                "SELECT tenant_id, company_id FROM review_events WHERE id=?",
                (str(review_id),),
            ).fetchone(),
        }

    assert {table: tuple(row) for table, row in rows.items()} == {
        "quantity_derivations": ("tenant_a", "company_a"),
        "conflicts": ("tenant_a", "company_a"),
        "review_events": ("tenant_a", "company_a"),
    }


def test_quantity_requirement_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "quantity-requirement-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    requirement_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant Project", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        run_id = uuid4()
        scope_item_id = uuid4()
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'completed', 'test', 1, ?, ?, ?, ?)",
            (str(run_id), str(project_id), "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "quantity_basis, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'test', 'test', 'walls', 'Paint walls', "
            "'test_fixture', ?, ?, 'tenant_a', 'company_a')",
            (str(scope_item_id), str(project_id), str(run_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO quantity_requirements (id, project_id, scope_item_id, trade_code, "
            "status, requirement_type, suggested_method, basis_note, created_at, updated_at, "
            "tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'open', 'quantity_needed', 'takeoff', 'Need quantity', "
            "?, ?, NULL, NULL)",
            (str(requirement_id), str(project_id), str(scope_item_id), "t", "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 27")
        conn.commit()
        apply_migrations(conn)
        row = conn.execute(
            "SELECT tenant_id, company_id FROM quantity_requirements WHERE id = ?",
            (str(requirement_id),),
        ).fetchone()

    assert tuple(row) == ("tenant_a", "company_a")


def test_draft_quantity_requirements_copies_project_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "quantity-requirement-insert-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_payload = _base_scope_item(project_id, run["id"])
    scope_payload.update(
        quantity=None,
        unit=None,
        quantity_basis="quantity_required",
        blocking_issues=[{"code": "missing_quantity"}],
        review_status="blocked",
        conflict_status="blocking",
    )
    scope_item = insert_scope_item(scope_payload)

    drafted = draft_quantity_requirements(project_id)

    assert drafted["created_count"] == 1
    assert drafted["items"][0]["tenant_id"] == "tenant_a"
    assert drafted["items"][0]["company_id"] == "company_a"
    requirements = list_quantity_requirements(project_id)
    assert requirements[0]["scope_item_id"] == scope_item["id"]
    assert requirements[0]["tenant_id"] == "tenant_a"
    assert requirements[0]["company_id"] == "company_a"


def test_list_quantity_requirements_denies_mismatched_requirement_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "quantity-requirement-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        run_id = uuid4()
        scope_item_id = uuid4()
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'completed', 'test', 1, ?, ?, ?, ?)",
            (str(run_id), str(project_id), "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "quantity_basis, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'test', 'test', 'walls', 'Paint walls', "
            "'test_fixture', ?, ?, 'tenant_a', 'company_a')",
            (str(scope_item_id), str(project_id), str(run_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO quantity_requirements (id, project_id, scope_item_id, trade_code, "
            "status, requirement_type, suggested_method, basis_note, created_at, updated_at, "
            "tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'open', 'quantity_needed', 'takeoff', 'Need quantity', "
            "?, ?, 'tenant_b', 'company_b')",
            (str(uuid4()), str(project_id), str(scope_item_id), "t", "t"),
        )
        conn.commit()

    with pytest.raises(QuantityRequirementError, match="tenant/company identity does not match"):
        list_quantity_requirements(project_id)


def test_draft_quantity_requirements_denies_mismatched_existing_requirement_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "quantity-requirement-draft-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_payload = _base_scope_item(project_id, run["id"])
    scope_payload.update(
        quantity=None,
        unit=None,
        quantity_basis="quantity_required",
        blocking_issues=[{"code": "missing_quantity"}],
        review_status="blocked",
        conflict_status="blocking",
    )
    scope_item = insert_scope_item(scope_payload)
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO quantity_requirements (id, project_id, scope_item_id, trade_code, "
            "status, requirement_type, suggested_method, basis_note, created_at, updated_at, "
            "tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'open', 'quantity_needed', 'takeoff', 'Need quantity', "
            "?, ?, 'tenant_b', 'company_b')",
            (str(uuid4()), str(project_id), scope_item["id"], "t", "t"),
        )
        conn.commit()

    with pytest.raises(QuantityRequirementError, match="tenant/company identity does not match"):
        draft_quantity_requirements(project_id)


def test_insert_scope_item_denies_mismatched_run_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "scope-mismatch-run.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    run_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'completed', 'test', 1, ?, ?, ?, ?)",
            (str(run_id), str(project_id), "t", "t", "tenant_b", "company_a"),
        )
        conn.commit()

    with pytest.raises(ValueError, match="extraction run identity must match"):
        insert_scope_item(_base_scope_item(project_id, str(run_id)))

    with database.get_connection() as conn:
        scope_count = conn.execute(
            "SELECT COUNT(*) FROM scope_items WHERE project_id = ?",
            (str(project_id),),
        ).fetchone()[0]
    assert scope_count == 0


def test_update_scope_item_rejects_identity_field_mutation(tmp_path, monkeypatch):
    db_path = tmp_path / "scope-identity-immutable.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))

    with pytest.raises(ValueError, match="identity fields are immutable"):
        update_scope_item(UUID(scope_item["id"]), tenant_id="tenant_b")

    unchanged = update_scope_item(UUID(scope_item["id"]))
    assert unchanged is not None
    assert unchanged["tenant_id"] == "tenant_a"


def test_update_scope_item_rejects_crafted_sql_field_identity_bypass(tmp_path, monkeypatch):
    db_path = tmp_path / "scope-identity-crafted-field.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))

    with pytest.raises(ValueError, match="unsupported fields"):
        update_scope_item(
            UUID(scope_item["id"]),
            **{"review_status = review_status, tenant_id": "tenant_b"},
        )

    unchanged = update_scope_item(UUID(scope_item["id"]))
    assert unchanged is not None
    assert unchanged["tenant_id"] == "tenant_a"
    assert unchanged["review_status"] == "pending"


@pytest.mark.parametrize(
    ("scope_tenant_id", "scope_company_id"),
    [(None, None), ("tenant_b", "company_a"), ("tenant_a", "company_b"), ("null", "company_a")],
)
def test_update_scope_item_denies_missing_or_mismatched_row_identity(
    tmp_path, monkeypatch, scope_tenant_id, scope_company_id
):
    db_path = tmp_path / "scope-update-row-identity.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))
    with database.get_connection() as conn:
        conn.execute(
            "UPDATE scope_items SET tenant_id=?, company_id=? WHERE id=?",
            (scope_tenant_id, scope_company_id, scope_item["id"]),
        )
        conn.commit()

    with pytest.raises(PermissionError):
        update_scope_item(UUID(scope_item["id"]), review_status="approved")

    with database.get_connection() as conn:
        unchanged = conn.execute(
            "SELECT review_status, tenant_id, company_id FROM scope_items WHERE id=?",
            (scope_item["id"],),
        ).fetchone()
    assert unchanged["review_status"] == "pending"
    assert unchanged["tenant_id"] == scope_tenant_id
    assert unchanged["company_id"] == scope_company_id


def test_update_scope_item_scopes_mutation_by_project_tenant_and_company(tmp_path, monkeypatch):
    db_path = tmp_path / "scope-update-tenant-scoped.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))

    updated = update_scope_item(UUID(scope_item["id"]), review_status="approved")

    assert updated is not None
    assert updated["review_status"] == "approved"
    assert updated["tenant_id"] == "tenant_a"
    assert updated["company_id"] == "company_a"


def test_child_row_reads_fail_closed_on_mismatched_job_and_sheet_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "child-row-read-identity.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    job_id = uuid4()
    sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO processing_jobs (id, project_id, status, attempt, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'processing', 1, ?, ?, ?, ?)",
            (str(job_id), str(project_id), "t", "t", "tenant_b", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, job_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 1, 0, 'sha', ?, ?, ?, ?)",
            (str(sheet_id), str(project_id), str(job_id), "t", "t", "tenant_b", "company_a"),
        )
        conn.commit()

    assert database.get_latest_job(project_id) is None
    assert database.get_sheet(project_id, sheet_id) is None
    sheets, total = database.list_sheets(project_id, limit=10, offset=0)
    assert sheets == []
    assert total == 0


def test_child_row_reads_fail_closed_on_mismatched_run_and_scope_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "run-scope-read-identity.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    run_id = uuid4()
    scope_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'completed', 'test', 1, ?, ?, ?, ?)",
            (str(run_id), str(project_id), "t", "t", "tenant_b", "company_a"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "review_status, conflict_status, quantity_basis, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'test', 'test', 'walls', 'Paint walls', "
            "'pending', 'none', 'test_fixture', ?, ?, ?, ?)",
            (str(scope_id), str(project_id), str(run_id), "t", "t", "tenant_b", "company_a"),
        )
        conn.commit()

    assert get_run(project_id, run_id) is None
    runs, run_total = list_runs(project_id, "painting", limit=10, offset=0)
    assert runs == []
    assert run_total == 0
    assert get_scope_item(project_id, scope_id) is None
    scope_items, scope_total = list_scope_items(project_id, filters={}, limit=10, offset=0)
    assert scope_items == []
    assert scope_total == 0


def test_evidence_reference_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "evidence-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    run_id = uuid4()
    scope_item_id = uuid4()
    sheet_id = uuid4()
    evidence_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant Project", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, "
            "provider, attempt, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'completed', 'test', 1, ?, ?, ?, ?)",
            (str(run_id), str(project_id), "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "quantity_basis, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'test', 'test', 'walls', 'Paint walls', "
            "'takeoff', ?, ?, 'tenant_a', 'company_a')",
            (str(scope_item_id), str(project_id), str(run_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'sha', ?, ?, 'tenant_a', 'company_a')",
            (str(sheet_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO evidence_references (id, scope_item_id, project_id, sheet_id, "
            "pdf_page_number, verified_sheet_number, evidence_type, description, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, ?, 1, 'A-101', 'note', 'Plan note', ?, ?, NULL, NULL)",
            (str(evidence_id), str(scope_item_id), str(project_id), str(sheet_id), "t", "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 28")
        conn.commit()
        apply_migrations(conn)
        row = conn.execute(
            "SELECT tenant_id, company_id FROM evidence_references WHERE id = ?",
            (str(evidence_id),),
        ).fetchone()

    assert tuple(row) == ("tenant_a", "company_a")


def test_insert_evidence_copies_project_scope_and_sheet_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "evidence-insert-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'sha', ?, ?, 'tenant_a', 'company_a')",
            (str(sheet_id), str(project_id), "t", "t"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))

    evidence = insert_evidence(
        {
            "id": str(uuid4()),
            "scope_item_id": scope_item["id"],
            "project_id": str(project_id),
            "sheet_id": str(sheet_id),
            "pdf_page_number": 1,
            "verified_sheet_number": "A-101",
            "evidence_type": "note",
            "description": "Plan note",
        }
    )

    assert evidence["tenant_id"] == "tenant_a"
    assert evidence["company_id"] == "company_a"
    listed = list_evidence(project_id, UUID(scope_item["id"]))
    assert len(listed) == 1
    assert listed[0]["tenant_id"] == "tenant_a"
    assert listed[0]["company_id"] == "company_a"


def test_list_evidence_denies_cross_project_scope_item_uuid_substitution(tmp_path, monkeypatch):
    db_path = tmp_path / "evidence-cross-project-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    tenant_a_project_id = uuid4()
    tenant_b_project_id = uuid4()
    sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(tenant_a_project_id), "Tenant A", "/tenant-a.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(tenant_b_project_id), "Tenant B", "/tenant-b.pdf", "t", "t", "tenant_b", "company_b"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'sha', ?, ?, 'tenant_a', 'company_a')",
            (str(sheet_id), str(tenant_a_project_id), "t", "t"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=tenant_a_project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(tenant_a_project_id, run["id"]))
    insert_evidence(
        {
            "id": str(uuid4()),
            "scope_item_id": scope_item["id"],
            "project_id": str(tenant_a_project_id),
            "sheet_id": str(sheet_id),
            "pdf_page_number": 1,
            "verified_sheet_number": "A-101",
            "evidence_type": "note",
            "description": "Plan note",
        }
    )

    assert len(list_evidence(tenant_a_project_id, UUID(scope_item["id"]))) == 1
    assert list_evidence(tenant_b_project_id, UUID(scope_item["id"])) == []


def test_insert_evidence_denies_mismatched_sheet_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "evidence-sheet-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'sha', ?, ?, 'tenant_b', 'company_a')",
            (str(sheet_id), str(project_id), "t", "t"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))

    with pytest.raises(ValueError, match="evidence sheet identity must match project tenant"):
        insert_evidence(
            {
                "id": str(uuid4()),
                "scope_item_id": scope_item["id"],
                "project_id": str(project_id),
                "sheet_id": str(sheet_id),
                "pdf_page_number": 1,
                "verified_sheet_number": "A-101",
                "evidence_type": "note",
                "description": "Plan note",
            }
        )

    assert list_evidence(project_id, UUID(scope_item["id"])) == []


def test_list_evidence_filters_mismatched_evidence_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "evidence-list-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'sha', ?, ?, 'tenant_a', 'company_a')",
            (str(sheet_id), str(project_id), "t", "t"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO evidence_references (id, scope_item_id, project_id, sheet_id, "
            "pdf_page_number, verified_sheet_number, evidence_type, description, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, ?, 1, 'A-101', 'note', 'Plan note', ?, ?, 'tenant_b', 'company_b')",
            (str(uuid4()), scope_item["id"], str(project_id), str(sheet_id), "t", "t"),
        )
        conn.commit()

    assert list_evidence(project_id, UUID(scope_item["id"])) == []


def test_list_evidence_filters_mismatched_sheet_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "evidence-list-sheet-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'sha', ?, ?, 'tenant_b', 'company_a')",
            (str(sheet_id), str(project_id), "t", "t"),
        )
        conn.commit()
    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"
    scope_item = insert_scope_item(_base_scope_item(project_id, run["id"]))
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO evidence_references (id, scope_item_id, project_id, sheet_id, "
            "pdf_page_number, verified_sheet_number, evidence_type, description, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, ?, 1, 'A-101', 'note', 'Plan note', ?, ?, 'tenant_a', 'company_a')",
            (str(uuid4()), scope_item["id"], str(project_id), str(sheet_id), "t", "t"),
        )
        conn.commit()

    assert list_evidence(project_id, UUID(scope_item["id"])) == []


def test_routing_decision_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "routing-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    sheet_id = uuid4()
    routing_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant Project", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'sha', ?, ?, 'tenant_a', 'company_a')",
            (str(sheet_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO sheet_routing_decisions (id, project_id, sheet_id, "
            "trade_code, eligibility, reason, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'eligible', 'test', ?, ?, NULL, NULL)",
            (str(routing_id), str(project_id), str(sheet_id), "t", "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 29")
        conn.commit()
        apply_migrations(conn)
        row = conn.execute(
            "SELECT tenant_id, company_id FROM sheet_routing_decisions WHERE id = ?",
            (str(routing_id),),
        ).fetchone()

    assert tuple(row) == ("tenant_a", "company_a")


def test_upsert_routing_decision_copies_and_enforces_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "routing-upsert-tenant.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'sha', ?, ?, 'tenant_a', 'company_a')",
            (str(sheet_id), str(project_id), "t", "t"),
        )
        conn.commit()

    outcome, run = claim_extraction_run(
        project_id=project_id,
        trade_code="painting",
        provider="test",
        model=None,
        prompt_version=None,
        provider_schema_version=None,
        trade_schema_version=None,
        force=False,
        dry_run=False,
    )
    assert outcome == "created"

    routing = upsert_routing_decision(
        project_id=project_id,
        sheet_id=sheet_id,
        trade_code="painting",
        extraction_run_id=UUID(run["id"]),
        eligibility="eligible",
        reason="test",
        automatic=True,
    )

    assert routing["tenant_id"] == "tenant_a"
    assert routing["company_id"] == "company_a"
    listed = list_routing(project_id, "painting")
    assert len(listed) == 1
    assert listed[0]["tenant_id"] == "tenant_a"
    override = set_manual_override(
        project_id,
        "painting",
        sheet_id,
        manual_override="exclude",
        reviewer_notes="wrong trade",
    )
    assert override is not None
    assert override["manual_override"] == "exclude"


def test_upsert_routing_decision_denies_mismatched_sheet_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "routing-sheet-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'sha', ?, ?, 'tenant_b', 'company_a')",
            (str(sheet_id), str(project_id), "t", "t"),
        )
        conn.commit()

    with pytest.raises(ValueError, match="routing decision sheet identity must match project tenant"):
        upsert_routing_decision(
            project_id=project_id,
            sheet_id=sheet_id,
            trade_code="painting",
            extraction_run_id=None,
            eligibility="eligible",
            reason="test",
            automatic=True,
        )

    assert list_routing(project_id, "painting") == []


def test_list_routing_filters_mismatched_routing_and_sheet_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "routing-list-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    good_sheet_id = uuid4()
    mismatched_sheet_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 1, 0, 'good', ?, ?, 'tenant_a', 'company_a')",
            (str(good_sheet_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO sheets (id, project_id, pdf_page_number, page_index, "
            "page_sha256, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 2, 1, 'bad', ?, ?, 'tenant_b', 'company_a')",
            (str(mismatched_sheet_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO sheet_routing_decisions (id, project_id, tenant_id, company_id, "
            "sheet_id, trade_code, eligibility, reason, created_at, updated_at) "
            "VALUES (?, ?, 'tenant_b', 'company_a', ?, 'painting', 'eligible', 'bad row', ?, ?)",
            (str(uuid4()), str(project_id), str(good_sheet_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO sheet_routing_decisions (id, project_id, tenant_id, company_id, "
            "sheet_id, trade_code, eligibility, reason, created_at, updated_at) "
            "VALUES (?, ?, 'tenant_a', 'company_a', ?, 'painting', 'eligible', 'bad sheet', ?, ?)",
            (str(uuid4()), str(project_id), str(mismatched_sheet_id), "t", "t"),
        )
        conn.commit()

    assert list_routing(project_id, "painting") == []


def test_qa_finding_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "qa-finding-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    finding_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO qa_findings (id, project_id, source, code, severity, message, status, "
            "created_at, updated_at) VALUES (?, ?, 'legacy', 'missing_quantity', 'critical', "
            "'Needs quantity', 'open', ?, ?)",
            (str(finding_id), str(project_id), "t", "t"),
        )
        conn.commit()
        # Simulate upgrading a v29 database where qa_findings exists but tenant columns do not.
        conn.execute("DELETE FROM schema_migrations WHERE version >= 30")
        conn.execute("DROP INDEX idx_qa_findings_tenant_company_project")
        conn.execute("ALTER TABLE qa_findings DROP COLUMN tenant_id")
        conn.execute("ALTER TABLE qa_findings DROP COLUMN company_id")
        conn.commit()
        apply_migrations(conn)
        row = conn.execute(
            "SELECT tenant_id, company_id FROM qa_findings WHERE id=?",
            (str(finding_id),),
        ).fetchone()

    assert row["tenant_id"] == "tenant_a"
    assert row["company_id"] == "company_a"


def test_list_qa_findings_filters_mismatched_finding_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "qa-finding-list-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'processing', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO qa_findings (id, project_id, tenant_id, company_id, source, code, severity, "
            "message, status, created_at, updated_at) "
            "VALUES (?, ?, 'tenant_a', 'company_a', 'manual', 'ok', 'major', 'visible', 'open', ?, ?)",
            (str(uuid4()), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO qa_findings (id, project_id, tenant_id, company_id, source, code, severity, "
            "message, status, created_at, updated_at) "
            "VALUES (?, ?, 'tenant_b', 'company_a', 'manual', 'leak', 'critical', 'hidden', 'open', ?, ?)",
            (str(uuid4()), str(project_id), "t", "t"),
        )
        conn.commit()

    rows = list_qa_findings(project_id)

    assert [row["code"] for row in rows] == ["ok"]
    assert rows[0]["tenant_id"] == "tenant_a"
    assert rows[0]["company_id"] == "company_a"


def test_estimate_artifact_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "estimate-artifact-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    estimate_id = uuid4()
    version_id = uuid4()
    line_item_id = uuid4()
    indirect_id = uuid4()
    adjustment_id = uuid4()
    snapshot_id = uuid4()
    review_event_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'review_ready', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO estimates (id, project_id, name, created_at, updated_at) "
            "VALUES (?, ?, 'Estimate', ?, ?)",
            (str(estimate_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO estimate_versions (id, estimate_id, project_id, version_number, "
            "cost_book_version_id, created_at) VALUES (?, ?, ?, 1, ?, ?)",
            (str(version_id), str(estimate_id), str(project_id), str(uuid4()), "t"),
        )
        conn.execute(
            "INSERT INTO estimate_line_items (id, version_id, project_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (str(line_item_id), str(version_id), str(project_id), "t"),
        )
        conn.execute(
            "INSERT INTO estimate_indirects (id, version_id, payload) VALUES (?, ?, '{}')",
            (str(indirect_id), str(version_id)),
        )
        conn.execute(
            "INSERT INTO estimate_adjustments (id, version_id, payload) VALUES (?, ?, '{}')",
            (str(adjustment_id), str(version_id)),
        )
        conn.execute(
            "INSERT INTO estimate_snapshots (id, version_id, snapshot_json, snapshot_hash, created_at) "
            "VALUES (?, ?, '{}', 'hash', ?)",
            (str(snapshot_id), str(version_id), "t"),
        )
        conn.execute(
            "INSERT INTO estimate_review_events (id, version_id, project_id, action, created_at) "
            "VALUES (?, ?, ?, 'approved', ?)",
            (str(review_event_id), str(version_id), str(project_id), "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 31")
        conn.commit()
        apply_migrations(conn)
        tables_and_ids = {
            "estimates": estimate_id,
            "estimate_versions": version_id,
            "estimate_line_items": line_item_id,
            "estimate_indirects": indirect_id,
            "estimate_adjustments": adjustment_id,
            "estimate_snapshots": snapshot_id,
            "estimate_review_events": review_event_id,
        }
        rows = {
            table: conn.execute(
                f"SELECT tenant_id, company_id FROM {table} WHERE id=?",
                (str(row_id),),
            ).fetchone()
            for table, row_id in tables_and_ids.items()
        }

    assert {tuple(row) for row in rows.values()} == {("tenant_a", "company_a")}


def test_estimate_artifact_writes_copy_project_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "estimate-artifact-tenant-writes.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    scope_item_id = uuid4()
    extraction_run_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'review_ready', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, provider, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'completed', 'test', ?, ?, 'tenant_a', 'company_a')",
            (str(extraction_run_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "quantity_basis, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'test', 'test', 'painting', 'Paint walls', "
            "'measured', ?, ?, 'tenant_a', 'company_a')",
            (str(scope_item_id), str(project_id), str(extraction_run_id), "t", "t"),
        )
        conn.commit()

    cost_book = pricing_db.create_cost_book({"name": "Tenant Cost Book"})
    cost_version = pricing_db.create_version(
        UUID(cost_book["id"]), {"version_label": "tenant-v1", "effective_date": "2026-01-01"}
    )
    estimate = pricing_db.create_estimate(project_id, {"name": "Tenant Estimate"})
    version = pricing_db.create_estimate_version(
        UUID(estimate["id"]),
        project_id,
        {
            "version_number": 1,
            "cost_book_version_id": UUID(cost_version["id"]),
            "indirects": [{"type": "overhead"}],
            "adjustments": [{"type": "rounding"}],
        },
    )
    pricing_db.replace_line_items(
        version["id"],
        project_id,
        [{"trade_code": "painting", "scope_item_id": str(scope_item_id), "description": "Paint walls"}],
    )
    pricing_db.save_snapshot(version["id"], "{}", "hash")
    pricing_db.append_estimate_review(version["id"], project_id, {"action": "owner_review_required"})

    with database.get_connection() as conn:
        checks = [
            conn.execute("SELECT tenant_id, company_id FROM estimates WHERE id=?", (estimate["id"],)).fetchone(),
            conn.execute("SELECT tenant_id, company_id FROM estimate_versions WHERE id=?", (version["id"],)).fetchone(),
            conn.execute("SELECT tenant_id, company_id FROM estimate_line_items WHERE version_id=?", (version["id"],)).fetchone(),
            conn.execute("SELECT tenant_id, company_id FROM estimate_indirects WHERE version_id=?", (version["id"],)).fetchone(),
            conn.execute("SELECT tenant_id, company_id FROM estimate_adjustments WHERE version_id=?", (version["id"],)).fetchone(),
            conn.execute("SELECT tenant_id, company_id FROM estimate_snapshots WHERE version_id=?", (version["id"],)).fetchone(),
            conn.execute("SELECT tenant_id, company_id FROM estimate_review_events WHERE version_id=?", (version["id"],)).fetchone(),
        ]

    assert {tuple(row) for row in checks} == {("tenant_a", "company_a")}


def test_estimate_artifact_writes_reject_mismatched_project_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "estimate-artifact-tenant-mismatch.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_a = uuid4()
    project_b = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'review_ready', ?, ?, ?, ?)",
            (str(project_a), "Tenant A", "/a.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'review_ready', ?, ?, ?, ?)",
            (str(project_b), "Tenant B", "/b.pdf", "t", "t", "tenant_b", "company_b"),
        )
        conn.commit()

    cost_book = pricing_db.create_cost_book({"name": "Tenant Cost Book"})
    cost_version = pricing_db.create_version(
        UUID(cost_book["id"]), {"version_label": "tenant-v1", "effective_date": "2026-01-01"}
    )
    estimate = pricing_db.create_estimate(project_a, {"name": "Tenant Estimate"})
    with pytest.raises(PermissionError, match="cross_tenant_project_access_denied"):
        pricing_db.create_estimate_version(
            UUID(estimate["id"]),
            project_b,
            {"version_number": 1, "cost_book_version_id": UUID(cost_version["id"])},
        )
    with database.get_connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM estimate_versions WHERE estimate_id=?", (estimate["id"],)
        ).fetchone()[0] == 0

    version = pricing_db.create_estimate_version(
        UUID(estimate["id"]),
        project_a,
        {"version_number": 1, "cost_book_version_id": UUID(cost_version["id"])},
    )

    with pytest.raises(PermissionError, match="cross_tenant_project_access_denied"):
        pricing_db.replace_line_items(
            version["id"],
            project_b,
            [{"trade_code": "painting", "scope_item_id": str(uuid4())}],
        )
    with pytest.raises(PermissionError, match="cross_tenant_project_access_denied"):
        pricing_db.append_estimate_review(version["id"], project_b, {"action": "approve"})

    with database.get_connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM estimate_line_items WHERE version_id=?", (version["id"],)
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM estimate_review_events WHERE version_id=?", (version["id"],)
        ).fetchone()[0] == 0



def test_estimate_artifact_reads_fail_closed_on_stale_tenant_identity(tmp_path, monkeypatch):
    db_path = tmp_path / "estimate-artifact-tenant-read-scope.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    scope_item_id = uuid4()
    extraction_run_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'review_ready', ?, ?, ?, ?)",
            (str(project_id), "Tenant A", "/tenant-a.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, provider, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, 'painting', 'completed', 'test', ?, ?, 'tenant_a', 'company_a')",
            (str(extraction_run_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, "
            "quantity_basis, created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'painting', 'test', 'test', 'painting', 'Paint walls', "
            "'measured', ?, ?, 'tenant_a', 'company_a')",
            (str(scope_item_id), str(project_id), str(extraction_run_id), "t", "t"),
        )
        conn.commit()

    cost_book = pricing_db.create_cost_book({"name": "Tenant Cost Book"})
    cost_version = pricing_db.create_version(
        UUID(cost_book["id"]), {"version_label": "tenant-v1", "effective_date": "2026-01-01"}
    )
    estimate = pricing_db.create_estimate(project_id, {"name": "Tenant Estimate"})
    version = pricing_db.create_estimate_version(
        UUID(estimate["id"]),
        project_id,
        {
            "version_number": 1,
            "cost_book_version_id": UUID(cost_version["id"]),
            "indirects": [{"type": "overhead"}],
            "adjustments": [{"type": "rounding"}],
        },
    )
    pricing_db.replace_line_items(
        version["id"],
        project_id,
        [{"trade_code": "painting", "scope_item_id": str(scope_item_id), "description": "Paint walls"}],
    )
    pricing_db.save_snapshot(version["id"], "{}", "hash")

    with database.get_connection() as conn:
        stale_version_id = str(uuid4())
        conn.execute(
            "INSERT INTO estimate_versions (id, estimate_id, project_id, version_number, "
            "cost_book_version_id, created_at, tenant_id, company_id) VALUES (?, ?, ?, 99, ?, ?, ?, ?)",
            (
                stale_version_id,
                estimate["id"],
                str(project_id),
                str(cost_version["id"]),
                "t",
                "tenant_b",
                "company_b",
            ),
        )
        conn.commit()

    assert pricing_db.next_version_number(UUID(estimate["id"])) == 2

    with database.get_connection() as conn:
        line_item_id = conn.execute(
            "SELECT id FROM estimate_line_items WHERE version_id=?", (version["id"],)
        ).fetchone()[0]
        for table, where_col, where_val in (
            ("estimates", "id", estimate["id"]),
            ("estimate_versions", "id", version["id"]),
            ("estimate_line_items", "version_id", version["id"]),
            ("estimate_indirects", "version_id", version["id"]),
            ("estimate_adjustments", "version_id", version["id"]),
            ("estimate_snapshots", "version_id", version["id"]),
        ):
            conn.execute(
                f"UPDATE {table} SET tenant_id='tenant_b', company_id='company_b' WHERE {where_col}=?",
                (where_val,),
            )
        conn.commit()

    assert pricing_db.get_estimate(project_id, UUID(estimate["id"])) is None
    assert pricing_db.list_estimates(project_id) == []
    assert pricing_db.get_estimate_version(version["id"]) is None
    assert pricing_db.list_estimate_versions(UUID(estimate["id"])) == []
    assert pricing_db.get_indirects(version["id"]) == []
    assert pricing_db.get_adjustments(version["id"]) == []
    assert pricing_db.get_line_items(version["id"]) == []
    assert pricing_db.get_line_item(version["id"], UUID(line_item_id)) is None
    assert pricing_db.get_snapshot(version["id"]) is None



def test_customer_revision_tenant_identity_migration_backfills_from_project(tmp_path, monkeypatch):
    db_path = tmp_path / "customer-revision-tenant-migration.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    request_id = uuid4()
    version_id = uuid4()
    blocker_id = uuid4()
    run_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'review_ready', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.execute(
            "INSERT INTO customer_revision_requests (id, project_id, source, actor, action, "
            "status, summary, confidence, payload, created_at, updated_at) "
            "VALUES (?, ?, 'customer_email', 'customer', 'include', 'open', 'Add item', 0.8, '{}', ?, ?)",
            (str(request_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, trade_code, status, provider, created_at, updated_at) "
            "VALUES (?, ?, 'plumbing', 'completed', 'test', ?, ?)",
            (str(run_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, quantity_basis, "
            "created_at, updated_at) VALUES (?, ?, ?, 'plumbing', 'test', 'test', 'revision', 'Blocker', 'manual', ?, ?)",
            (str(blocker_id), str(project_id), str(run_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO customer_revision_rescope_versions (id, project_id, customer_revision_request_id, "
            "blocker_scope_item_id, version_number, status, actor, before_snapshot, after_snapshot, "
            "changed_items, readiness_snapshot, created_at) "
            "VALUES (?, ?, ?, ?, 1, 'resolved', 'staff', '{}', '{}', '[]', '{}', ?)",
            (str(version_id), str(project_id), str(request_id), str(blocker_id), "t"),
        )
        conn.execute("DELETE FROM schema_migrations WHERE version >= 32")
        conn.commit()
        apply_migrations(conn)
        request_row = conn.execute(
            "SELECT tenant_id, company_id FROM customer_revision_requests WHERE id=?",
            (str(request_id),),
        ).fetchone()
        version_row = conn.execute(
            "SELECT tenant_id, company_id FROM customer_revision_rescope_versions WHERE id=?",
            (str(version_id),),
        ).fetchone()

    assert tuple(request_row) == ("tenant_a", "company_a")
    assert tuple(version_row) == ("tenant_a", "company_a")


def test_customer_revision_writes_and_reads_are_tenant_scoped(tmp_path, monkeypatch):
    db_path = tmp_path / "customer-revision-tenant-scope.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    leaked_request_id = uuid4()
    leaked_version_id = uuid4()
    hidden_same_request_version_id = uuid4()
    visible_same_request_version_id = uuid4()
    leaked_blocker_id = uuid4()
    leaked_run_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at, tenant_id, company_id) "
            "VALUES (?, ?, ?, 'review_ready', ?, ?, ?, ?)",
            (str(project_id), "Tenant P", "/tenant.pdf", "t", "t", "tenant_a", "company_a"),
        )
        conn.commit()

    created = create_revision_requests(
        project_id,
        source="customer_email",
        actor="customer",
        raw_text="Please add plumbing fixture rough-ins shown on P-201.",
    )
    request_id = created["items"][0]["id"]

    with database.get_connection() as conn:
        stored = conn.execute(
            "SELECT tenant_id, company_id FROM customer_revision_requests WHERE id=?",
            (request_id,),
        ).fetchone()
        conn.execute(
            "INSERT INTO customer_revision_requests (id, project_id, tenant_id, company_id, source, actor, action, "
            "status, summary, confidence, payload, created_at, updated_at) "
            "VALUES (?, ?, 'tenant_b', 'company_a', 'customer_email', 'customer', 'include', 'open', 'Leaked', 0.8, '{}', ?, ?)",
            (str(leaked_request_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO extraction_runs (id, project_id, tenant_id, company_id, trade_code, status, provider, created_at, updated_at) "
            "VALUES (?, ?, 'tenant_b', 'company_a', 'plumbing', 'completed', 'test', ?, ?)",
            (str(leaked_run_id), str(project_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO scope_items (id, project_id, tenant_id, company_id, extraction_run_id, trade_code, "
            "trade_module_version, trade_schema_version, category_code, description, quantity_basis, "
            "created_at, updated_at) VALUES (?, ?, 'tenant_b', 'company_a', ?, 'plumbing', 'test', 'test', 'revision', 'Blocker', 'manual', ?, ?)",
            (str(leaked_blocker_id), str(project_id), str(leaked_run_id), "t", "t"),
        )
        conn.execute(
            "INSERT INTO customer_revision_rescope_versions (id, project_id, tenant_id, company_id, customer_revision_request_id, "
            "blocker_scope_item_id, version_number, status, actor, before_snapshot, after_snapshot, changed_items, readiness_snapshot, created_at) "
            "VALUES (?, ?, 'tenant_b', 'company_a', ?, ?, 1, 'resolved', 'staff', '{}', '{}', '[]', '{}', ?)",
            (str(leaked_version_id), str(project_id), str(leaked_request_id), str(leaked_blocker_id), "t"),
        )
        conn.execute(
            "INSERT INTO customer_revision_rescope_versions (id, project_id, tenant_id, company_id, customer_revision_request_id, "
            "blocker_scope_item_id, version_number, status, actor, before_snapshot, after_snapshot, changed_items, readiness_snapshot, created_at) "
            "VALUES (?, ?, 'tenant_b', 'company_a', ?, ?, 1, 'resolved', 'staff', '{}', '{}', '[]', '{}', ?)",
            (str(hidden_same_request_version_id), str(project_id), request_id, str(leaked_blocker_id), "t"),
        )
        conn.execute(
            "INSERT INTO customer_revision_rescope_versions (id, project_id, tenant_id, company_id, customer_revision_request_id, "
            "blocker_scope_item_id, version_number, status, actor, before_snapshot, after_snapshot, changed_items, readiness_snapshot, created_at) "
            "VALUES (?, ?, 'tenant_a', 'company_a', ?, ?, 1, 'resolved', 'staff', '{}', '{}', '[]', '{}', ?)",
            (str(visible_same_request_version_id), str(project_id), request_id, str(leaked_blocker_id), "t"),
        )
        conn.commit()

    rows = list_revision_requests(project_id)
    leaked_versions = list_revision_rescope_versions(project_id, leaked_request_id)
    visible_versions = list_revision_rescope_versions(project_id, request_id)

    assert tuple(stored) == ("tenant_a", "company_a")
    assert [row["id"] for row in rows] == [request_id]
    assert leaked_versions == []
    assert [row["id"] for row in visible_versions] == [str(visible_same_request_version_id)]


# ---------------------------------------------------------------------------
# Canonical takeoff evidence provider fields (migration 38)
# ---------------------------------------------------------------------------
def _build_v37_evidence_row() -> dict:
    """Serialize a canonical evidence row shaped like the pre-v38 (v37) schema.

    The v37 table had no ``condition``/``scale`` columns and its ``raw_payload``
    predates those keys, so we drop both from the flattened columns and from the
    normalized JSON to reproduce an authentically old row.
    """
    from app.takeoff import (
        CanonicalEvidence,
        EvidenceClass,
        MeasurementMethod,
        TakeoffProviderKind,
    )
    from app.takeoff.store import serialize_canonical_evidence

    evidence = CanonicalEvidence(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        document_id=uuid4(),
        sheet_id=uuid4(),
        page_number=1,
        takeoff_provider=TakeoffProviderKind.MOBI_NATIVE,
        provider_record_id="legacy-1",
        evidence_class=EvidenceClass.MEASURED,
        measurement_method=MeasurementMethod.MODEL_INFERENCE,
        trade="painting",
        scope_category="interior_walls",
        description="Paint walls",
        quantity=__import__("decimal").Decimal("100"),
        unit="SF",
        extractor_version="1.0.0",
    )
    row = serialize_canonical_evidence(evidence)
    raw = __import__("json").loads(row["raw_payload"])
    raw.pop("condition", None)
    raw.pop("scale", None)
    row["raw_payload"] = __import__("json").dumps(raw, sort_keys=True)
    row.pop("condition", None)
    row.pop("scale", None)
    return row


def test_migration_38_evolves_applied_v37_table_preserving_rows(tmp_path):
    from app import migrations

    db_path = tmp_path / "evidence-v38.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Reconstruct an authentic v37 database: migrations ledger recorded up to
        # 37 and the original (pre-provider-fields) evidence table.
        migrations._ensure_migrations_table(conn)
        migrations._0037_canonical_takeoff_evidence(conn)
        for migration in migrations.MIGRATIONS:
            if migration.version <= 37:
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) "
                    "VALUES (?, ?, ?)",
                    (migration.version, migration.name, "2026-01-01T00:00:00+00:00"),
                )

        v37_columns = {
            r[1] for r in conn.execute("PRAGMA table_info(canonical_takeoff_evidence)")
        }
        assert "condition" not in v37_columns
        assert "scale" not in v37_columns

        row = _build_v37_evidence_row()
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        conn.execute(
            f"INSERT INTO canonical_takeoff_evidence ({columns}) VALUES ({placeholders})",
            list(row.values()),
        )
        # A pre-v38 database cannot store the new provider lanes yet.
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE canonical_takeoff_evidence SET takeoff_provider = 'open_takeoff' "
                "WHERE evidence_id = ?",
                (row["evidence_id"],),
            )
        conn.commit()

        applied = migrations.apply_migrations(conn)
        assert 38 in applied
        assert migrations.current_version(conn) == 38

        # New columns exist, indexes were recreated, and the legacy row survived
        # with NULL provenance (its raw_payload predated condition/scale).
        v38_columns = {
            r[1] for r in conn.execute("PRAGMA table_info(canonical_takeoff_evidence)")
        }
        assert {"condition", "scale"} <= v38_columns
        indexes = {
            r[1] for r in conn.execute("PRAGMA index_list(canonical_takeoff_evidence)")
        }
        assert {
            "idx_canonical_evidence_tenant_company_project",
            "idx_canonical_evidence_project",
            "idx_canonical_evidence_document",
            "idx_canonical_evidence_sheet",
        } <= indexes

        preserved = conn.execute(
            "SELECT * FROM canonical_takeoff_evidence WHERE evidence_id = ?",
            (row["evidence_id"],),
        ).fetchone()
        assert preserved is not None
        assert preserved["provider_record_id"] == "legacy-1"
        assert preserved["condition"] is None
        assert preserved["scale"] is None

        # The expanded provider CHECK now admits the new lanes.
        conn.execute(
            "UPDATE canonical_takeoff_evidence SET takeoff_provider = 'open_takeoff' "
            "WHERE evidence_id = ?",
            (row["evidence_id"],),
        )
        conn.commit()
        assert (
            conn.execute(
                "SELECT takeoff_provider FROM canonical_takeoff_evidence WHERE evidence_id = ?",
                (row["evidence_id"],),
            ).fetchone()[0]
            == "open_takeoff"
        )
    finally:
        conn.close()


def test_migration_38_is_idempotent_on_v38_shape(tmp_path):
    """Re-running the forward migration over an already-evolved table is a no-op."""
    from app import migrations

    db_path = tmp_path / "evidence-v38-idempotent.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        migrations._ensure_migrations_table(conn)
        migrations._0037_canonical_takeoff_evidence(conn)
        migrations._0038_canonical_takeoff_evidence_provider_fields(conn)
        columns_before = {
            r[1] for r in conn.execute("PRAGMA table_info(canonical_takeoff_evidence)")
        }
        assert {"condition", "scale"} <= columns_before
        # Running it again must not raise or drop the (now v38-shaped) table.
        migrations._0038_canonical_takeoff_evidence_provider_fields(conn)
        columns_after = {
            r[1] for r in conn.execute("PRAGMA table_info(canonical_takeoff_evidence)")
        }
        assert columns_after == columns_before
    finally:
        conn.close()
