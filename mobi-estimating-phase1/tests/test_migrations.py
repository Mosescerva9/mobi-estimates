"""Migration and database-concurrency-guard tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from app import database
from app.config import settings
from app.migrations import apply_migrations, current_version


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
    # + processing job tenant identity (→v23) = 23.
    assert first_version == 23


def test_only_one_active_job_per_project(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs.db"
    monkeypatch.setattr(settings, "db_path", db_path)
    database.init_db()

    project_id = uuid4()
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, stored_file_path, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(project_id), "P", "/x.pdf", "uploaded",
             "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
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
            "created_at, updated_at) VALUES (?, ?, ?, 'uploaded', ?, ?)",
            (str(project_id), "P", "/x.pdf", "t", "t"),
        )
        conn.execute(
            "INSERT INTO processing_jobs (id, project_id, status, attempt, "
            "created_at, updated_at) VALUES (?, ?, 'processing', 1, ?, ?)",
            (str(uuid4()), str(project_id), "t", "t"),
        )
        conn.commit()

    outcome, job, _ = database.claim_processing_slot(project_id, force=False)
    assert outcome == "active"
    assert job is not None


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
        conn.execute("DELETE FROM schema_migrations WHERE version = 23")
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
