"""Migration and database-concurrency-guard tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app import database
from app.config import settings
from app.extraction_db import (
    claim_extraction_run,
    get_run,
    get_scope_item,
    insert_evidence,
    insert_scope_item,
    list_evidence,
    list_routing,
    list_runs,
    list_scope_items,
    set_manual_override,
    update_run,
    update_scope_item,
    upsert_routing_decision,
)
from app.migrations import apply_migrations, current_version
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
    # + sheet routing decision tenant identity (→v29) = 29.
    assert first_version == 29


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
    listed = list_evidence(UUID(scope_item["id"]))
    assert len(listed) == 1
    assert listed[0]["tenant_id"] == "tenant_a"
    assert listed[0]["company_id"] == "company_a"


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

    assert list_evidence(UUID(scope_item["id"])) == []


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

    assert list_evidence(UUID(scope_item["id"])) == []


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

    assert list_evidence(UUID(scope_item["id"])) == []


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
        conn.execute("DELETE FROM schema_migrations WHERE version = 29")
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
