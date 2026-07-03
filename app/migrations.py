"""Forward-only SQLite migrations for the lean Mobi MVP.

A tiny, dependency-free migration runner. Each migration has an integer version
and a callable that receives an open ``sqlite3.Connection``. Applied versions are
recorded in a ``schema_migrations`` table, so migrations run exactly once and in
order. Migrations are written defensively (``IF NOT EXISTS`` / guarded
``ALTER TABLE``) so they are safe to run against:

* a brand-new empty database, and
* an existing Phase 1 database that already contains the ``projects`` table.

Nothing here ever drops or recreates existing data.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable, NamedTuple


class Migration(NamedTuple):
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


# --- Individual migrations -------------------------------------------------
def _0001_projects(conn: sqlite3.Connection) -> None:
    """Phase 1 baseline: the projects table (no-op on existing Phase 1 DBs)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
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
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_file_sha256 "
        "ON projects (file_sha256)"
    )


def _0002_processing_jobs(conn: sqlite3.Connection) -> None:
    """Phase 2: processing jobs table."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processing_jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 1,
            force INTEGER NOT NULL DEFAULT 0,
            pages_discovered INTEGER NOT NULL DEFAULT 0,
            pages_completed INTEGER NOT NULL DEFAULT 0,
            pages_failed INTEGER NOT NULL DEFAULT 0,
            pages_requiring_ocr INTEGER NOT NULL DEFAULT 0,
            pages_requiring_review INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER,
            error_code TEXT,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_project ON processing_jobs (project_id)"
    )
    # At most one active (queued/processing) job per project. This partial unique
    # index is the database-level guard against concurrent duplicate processing.
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_active_per_project
        ON processing_jobs (project_id)
        WHERE status IN ('queued', 'processing')
        """
    )


def _0003_sheets(conn: sqlite3.Connection) -> None:
    """Phase 2: per-page sheet records."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sheets (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            job_id TEXT,
            pdf_page_number INTEGER NOT NULL,
            page_index INTEGER NOT NULL,
            detected_sheet_number TEXT,
            verified_sheet_number TEXT,
            detected_sheet_title TEXT,
            verified_sheet_title TEXT,
            detection_confidence REAL,
            requires_review INTEGER NOT NULL DEFAULT 1,
            requires_ocr INTEGER NOT NULL DEFAULT 0,
            text_char_count INTEGER NOT NULL DEFAULT 0,
            page_width_points REAL,
            page_height_points REAL,
            rotation INTEGER NOT NULL DEFAULT 0,
            page_sha256 TEXT,
            duplicate_of_sheet_id TEXT,
            full_image_path TEXT,
            thumbnail_path TEXT,
            text_path TEXT,
            processing_status TEXT NOT NULL DEFAULT 'pending',
            processing_error TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending',
            review_notes TEXT,
            verified_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (job_id) REFERENCES processing_jobs (id),
            FOREIGN KEY (duplicate_of_sheet_id) REFERENCES sheets (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sheets_project ON sheets (project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sheets_project_page "
        "ON sheets (project_id, pdf_page_number)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sheets_page_sha256 ON sheets (page_sha256)"
    )
    # Each PDF page maps to exactly one sheet row per project.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sheets_project_page "
        "ON sheets (project_id, pdf_page_number)"
    )


def _0004_trade_definitions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_definitions (
            trade_code TEXT PRIMARY KEY,
            trade_name TEXT NOT NULL,
            module_version TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            metadata TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _0005_extraction_runs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extraction_runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            status TEXT NOT NULL,
            provider TEXT NOT NULL,
            model_identifier TEXT,
            prompt_version TEXT,
            provider_schema_version TEXT,
            trade_schema_version TEXT,
            attempt INTEGER NOT NULL DEFAULT 1,
            started_at TEXT,
            completed_at TEXT,
            error_code TEXT,
            error_message TEXT,
            input_sheet_count INTEGER NOT NULL DEFAULT 0,
            processed_sheet_count INTEGER NOT NULL DEFAULT 0,
            blocked_sheet_count INTEGER NOT NULL DEFAULT 0,
            failed_sheet_count INTEGER NOT NULL DEFAULT 0,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            usage TEXT,
            estimated_cost TEXT,
            dry_run INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_project_trade "
        "ON extraction_runs (project_id, trade_code)"
    )
    # At most one active run per (project, trade) when not a dry run.
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_runs_active_per_project_trade
        ON extraction_runs (project_id, trade_code)
        WHERE status IN ('queued', 'running') AND dry_run = 0
        """
    )


def _0006_sheet_routing_decisions(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sheet_routing_decisions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            sheet_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            extraction_run_id TEXT,
            eligibility TEXT NOT NULL,
            reason TEXT NOT NULL,
            automatic INTEGER NOT NULL DEFAULT 1,
            manual_override TEXT,
            reviewer_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (sheet_id) REFERENCES sheets (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_routing_project_trade "
        "ON sheet_routing_decisions (project_id, trade_code)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_routing_project_trade_sheet "
        "ON sheet_routing_decisions (project_id, trade_code, sheet_id)"
    )


def _0007_scope_items(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scope_items (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            extraction_run_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            trade_module_version TEXT NOT NULL,
            trade_schema_version TEXT NOT NULL,
            category_code TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT,
            specification_section TEXT,
            assembly_designation TEXT,
            material_or_substrate TEXT,
            existing_condition TEXT,
            proposed_work TEXT,
            quantity TEXT,
            unit TEXT,
            quantity_basis TEXT NOT NULL,
            raw_quantity_inputs TEXT,
            extraction_confidence REAL,
            conflict_status TEXT NOT NULL DEFAULT 'none',
            review_status TEXT NOT NULL DEFAULT 'pending',
            blocking_issues TEXT,
            assumptions TEXT,
            exclusions TEXT,
            trade_data TEXT,
            original_provider_candidate TEXT,
            calculation_id TEXT,
            calculation_version TEXT,
            reviewer_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            approved_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (extraction_run_id) REFERENCES extraction_runs (id)
        )
        """
    )
    for column in ("project_id", "extraction_run_id"):
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_scope_items_{column} "
            f"ON scope_items ({column})"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scope_items_project_trade "
        "ON scope_items (project_id, trade_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scope_items_review "
        "ON scope_items (project_id, review_status)"
    )


def _0008_evidence_references(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_references (
            id TEXT PRIMARY KEY,
            scope_item_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            sheet_id TEXT NOT NULL,
            pdf_page_number INTEGER NOT NULL,
            verified_sheet_number TEXT NOT NULL,
            evidence_type TEXT NOT NULL,
            description TEXT NOT NULL,
            extracted_text_quote TEXT,
            text_block_coords TEXT,
            page_region_coords TEXT,
            source_artifact_ref TEXT,
            provider_confidence REAL,
            requires_human_verification INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id),
            FOREIGN KEY (sheet_id) REFERENCES sheets (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_scope_item "
        "ON evidence_references (scope_item_id)"
    )


def _0009_quantity_derivations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quantity_derivations (
            id TEXT PRIMARY KEY,
            scope_item_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            formula_id TEXT NOT NULL,
            formula_version TEXT NOT NULL,
            inputs TEXT NOT NULL,
            output_value TEXT NOT NULL,
            output_unit TEXT NOT NULL,
            calculated_at TEXT NOT NULL,
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_derivations_scope_item "
        "ON quantity_derivations (scope_item_id)"
    )


def _0010_conflicts(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conflicts (
            id TEXT PRIMARY KEY,
            scope_item_id TEXT NOT NULL,
            code TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT NOT NULL,
            competing_evidence TEXT,
            resolution_status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conflicts_scope_item "
        "ON conflicts (scope_item_id)"
    )


def _0011_review_events(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_events (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            scope_item_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            action TEXT NOT NULL,
            previous_state TEXT,
            new_state TEXT,
            reviewer_id TEXT NOT NULL DEFAULT 'system',
            reviewer_notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_events_scope_item "
        "ON review_events (scope_item_id)"
    )


def _0012_cost_books(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cost_books (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
            currency TEXT NOT NULL DEFAULT 'USD', region TEXT, market TEXT,
            organization TEXT, status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cost_book_versions (
            id TEXT PRIMARY KEY, cost_book_id TEXT NOT NULL,
            version_label TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
            effective_date TEXT, expiration_date TEXT, pricing_date TEXT,
            description TEXT, source_notes TEXT, created_at TEXT NOT NULL,
            published_at TEXT, archived_at TEXT,
            FOREIGN KEY (cost_book_id) REFERENCES cost_books (id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cbv_book ON cost_book_versions (cost_book_id)")


def _0013_cost_inputs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cost_sources (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, source_type TEXT NOT NULL,
            source_name TEXT NOT NULL, effective_date TEXT, expiration_date TEXT,
            verified INTEGER NOT NULL DEFAULT 0, payload TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES cost_book_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS labor_rates (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, classification TEXT NOT NULL,
            trade_code TEXT NOT NULL, rate_type TEXT NOT NULL, loaded_rate TEXT,
            base_wage TEXT, burden TEXT, effective_date TEXT, expiration_date TEXT,
            source_id TEXT, payload TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES cost_book_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crews (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, crew_code TEXT NOT NULL,
            trade_code TEXT NOT NULL, name TEXT, members TEXT,
            loaded_crew_hour_rate TEXT, payload TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES cost_book_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS production_rates (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, production_code TEXT NOT NULL,
            trade_code TEXT NOT NULL, scope_category TEXT, assembly_code TEXT,
            quantity_unit TEXT, basis TEXT NOT NULL, value TEXT NOT NULL,
            crew_code TEXT, source_id TEXT, effective_date TEXT, expiration_date TEXT,
            verified INTEGER NOT NULL DEFAULT 0, payload TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES cost_book_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS material_rates (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, material_code TEXT NOT NULL,
            description TEXT, trade_code TEXT, purchase_unit TEXT, unit_cost TEXT NOT NULL,
            coverage_per_unit TEXT, coverage_unit TEXT, taxable INTEGER DEFAULT 1,
            freight_included INTEGER DEFAULT 0, waste_included INTEGER DEFAULT 0,
            source_id TEXT, effective_date TEXT, expiration_date TEXT, payload TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES cost_book_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment_rates (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, equipment_code TEXT NOT NULL,
            description TEXT, trade_code TEXT, basis TEXT NOT NULL, base_rate TEXT NOT NULL,
            delivery TEXT, pickup TEXT, fuel TEXT, operator_included INTEGER DEFAULT 0,
            mobilization_included INTEGER DEFAULT 0, minimum_charge TEXT, source_id TEXT,
            effective_date TEXT, expiration_date TEXT, payload TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES cost_book_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subcontract_quotes (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, sub_code TEXT NOT NULL,
            project_id TEXT, trade_code TEXT, vendor_label TEXT, base_amount TEXT NOT NULL,
            leveling_adjustment TEXT, verified INTEGER NOT NULL DEFAULT 0, source_id TEXT,
            payload TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES cost_book_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS other_direct_costs (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, odc_code TEXT NOT NULL,
            cost_type TEXT, description TEXT, unit TEXT, unit_rate TEXT NOT NULL,
            taxable INTEGER DEFAULT 0, source_id TEXT, payload TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES cost_book_versions (id)
        )
        """
    )
    for tbl in ("cost_sources", "labor_rates", "crews", "production_rates",
                "material_rates", "equipment_rates", "subcontract_quotes",
                "other_direct_costs"):
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{tbl}_version ON {tbl} (version_id)")


def _0014_assemblies(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assemblies (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, trade_code TEXT NOT NULL,
            assembly_code TEXT NOT NULL, name TEXT, description TEXT,
            scope_category TEXT, input_unit TEXT, output_basis TEXT,
            required_trade_data TEXT, required_evidence_types TEXT,
            required_quantity_basis TEXT, assembly_version TEXT DEFAULT '1.0',
            active INTEGER NOT NULL DEFAULT 1, notes TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES cost_book_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assembly_components (
            id TEXT PRIMARY KEY, assembly_id TEXT NOT NULL, component_type TEXT NOT NULL,
            cost_item_ref TEXT NOT NULL, quantity_factor TEXT, waste_factor TEXT,
            production_ref TEXT, crew_ref TEXT, conversion_id TEXT, minimum_charge TEXT,
            conditions TEXT, sequence INTEGER NOT NULL DEFAULT 0, version TEXT DEFAULT '1.0',
            FOREIGN KEY (assembly_id) REFERENCES assemblies (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scope_assembly_mappings (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, scope_item_id TEXT NOT NULL,
            trade_code TEXT, scope_category TEXT, trade_schema_version TEXT,
            assembly_code TEXT, priority INTEGER DEFAULT 0, confirmed_by TEXT,
            confirmed_at TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asm_version ON assemblies (version_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asmc_assembly ON assembly_components (assembly_id)")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mapping_active "
        "ON scope_assembly_mappings (scope_item_id)"
    )


def _0015_estimates(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS estimates (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL,
            description TEXT, currency TEXT NOT NULL DEFAULT 'USD',
            status TEXT NOT NULL DEFAULT 'active', current_version_id TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS estimate_versions (
            id TEXT PRIMARY KEY, estimate_id TEXT NOT NULL, project_id TEXT NOT NULL,
            version_number INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
            cost_book_version_id TEXT NOT NULL, snapshot_id TEXT,
            pricing_engine_version TEXT, rounding_policy TEXT, snapshot_hash TEXT,
            calculation_at TEXT, pricing_date TEXT, effective_date TEXT,
            expiration_date TEXT, currency TEXT DEFAULT 'USD', markup_method TEXT,
            inclusions TEXT, exclusions TEXT, assumptions TEXT, clarifications TEXT,
            config TEXT, exceptions TEXT, created_at TEXT NOT NULL, approved_at TEXT,
            superseded_at TEXT,
            FOREIGN KEY (estimate_id) REFERENCES estimates (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS estimate_line_items (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, project_id TEXT NOT NULL,
            trade_code TEXT, category_code TEXT, scope_item_id TEXT, assembly_code TEXT,
            description TEXT,
            location TEXT, quantity TEXT, unit TEXT, labor_hours TEXT, crew_hours TEXT,
            labor_cost TEXT, material_cost TEXT, equipment_cost TEXT,
            subcontract_cost TEXT, other_direct_cost TEXT, direct_cost_total TEXT,
            status TEXT, components TEXT, exceptions TEXT, evidence TEXT, overrides TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES estimate_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS estimate_indirects (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, payload TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES estimate_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS estimate_adjustments (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, payload TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES estimate_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS estimate_snapshots (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES estimate_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS estimate_review_events (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, project_id TEXT NOT NULL,
            action TEXT NOT NULL, previous_state TEXT, new_state TEXT,
            reviewer_id TEXT NOT NULL DEFAULT 'system', notes TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES estimate_versions (id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_estimate ON estimate_versions (estimate_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_eli_version ON estimate_line_items (version_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_estimates_project ON estimates (project_id)")


def _0016_proposals(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, estimate_id TEXT NOT NULL,
            name TEXT NOT NULL, client_name TEXT, status TEXT NOT NULL DEFAULT 'active',
            current_version_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (estimate_id) REFERENCES estimates (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposal_versions (
            id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, project_id TEXT NOT NULL,
            estimate_version_id TEXT NOT NULL, version_number INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft', proposal_number TEXT,
            prepared_by TEXT, client_name TEXT, client_contact TEXT, valid_until TEXT,
            detail_level TEXT NOT NULL DEFAULT 'trade', currency TEXT DEFAULT 'USD',
            total_sell_price TEXT, cover_notes TEXT, terms TEXT,
            inclusions TEXT, exclusions TEXT, assumptions TEXT, clarifications TEXT,
            snapshot_hash TEXT, issued_at TEXT, accepted_at TEXT, declined_at TEXT,
            decline_reason TEXT, superseded_at TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (proposal_id) REFERENCES proposals (id),
            FOREIGN KEY (estimate_version_id) REFERENCES estimate_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposal_line_items (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, section TEXT,
            trade_code TEXT, category_code TEXT, description TEXT, location TEXT,
            quantity TEXT, unit TEXT, sell_price TEXT NOT NULL, sort_order INTEGER,
            FOREIGN KEY (version_id) REFERENCES proposal_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposal_snapshots (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, snapshot_json TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES proposal_versions (id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposal_review_events (
            id TEXT PRIMARY KEY, version_id TEXT NOT NULL, project_id TEXT NOT NULL,
            action TEXT NOT NULL, previous_state TEXT, new_state TEXT,
            actor TEXT NOT NULL DEFAULT 'system', notes TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES proposal_versions (id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pv_proposal ON proposal_versions (proposal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pli_version ON proposal_line_items (version_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_project ON proposals (project_id)")


MIGRATIONS: list[Migration] = [
    Migration(1, "projects", _0001_projects),
    Migration(2, "processing_jobs", _0002_processing_jobs),
    Migration(3, "sheets", _0003_sheets),
    Migration(4, "trade_definitions", _0004_trade_definitions),
    Migration(5, "extraction_runs", _0005_extraction_runs),
    Migration(6, "sheet_routing_decisions", _0006_sheet_routing_decisions),
    Migration(7, "scope_items", _0007_scope_items),
    Migration(8, "evidence_references", _0008_evidence_references),
    Migration(9, "quantity_derivations", _0009_quantity_derivations),
    Migration(10, "conflicts", _0010_conflicts),
    Migration(11, "review_events", _0011_review_events),
    Migration(12, "cost_books", _0012_cost_books),
    Migration(13, "cost_inputs", _0013_cost_inputs),
    Migration(14, "assemblies", _0014_assemblies),
    Migration(15, "estimates", _0015_estimates),
    Migration(16, "proposals", _0016_proposals),
]


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def current_version(conn: sqlite3.Connection) -> int:
    _ensure_migrations_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def apply_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply all pending migrations in order. Returns the versions applied."""
    _ensure_migrations_table(conn)
    applied: list[int] = []
    version = current_version(conn)
    for migration in sorted(MIGRATIONS, key=lambda m: m.version):
        if migration.version <= version:
            continue
        migration.apply(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) "
            "VALUES (?, ?, ?)",
            (
                migration.version,
                migration.name,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        applied.append(migration.version)
    return applied
