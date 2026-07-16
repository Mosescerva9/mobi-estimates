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


def _0017_trade_coverage_matrix(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_coverage_rows (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            trade_name TEXT NOT NULL,
            csi_divisions TEXT NOT NULL DEFAULT '[]',
            detected_from TEXT NOT NULL DEFAULT '[]',
            disposition TEXT NOT NULL DEFAULT 'undispositioned',
            basis_note TEXT,
            confidence REAL,
            status TEXT NOT NULL DEFAULT 'draft',
            blockers TEXT NOT NULL DEFAULT '[]',
            evidence_refs TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_coverage_project "
        "ON trade_coverage_rows (project_id)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_trade_coverage_project_trade "
        "ON trade_coverage_rows (project_id, trade_code)"
    )


def _0018_qa_findings(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS qa_findings (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            source TEXT NOT NULL,
            code TEXT NOT NULL,
            severity TEXT NOT NULL,
            trade_code TEXT,
            coverage_row_id TEXT,
            scope_item_id TEXT,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qa_findings_project "
        "ON qa_findings (project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qa_findings_project_status "
        "ON qa_findings (project_id, status)"
    )


def _0019_customer_revision_requests(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_revision_requests (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            source TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            trade_code TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            summary TEXT NOT NULL,
            confidence REAL NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_revision_requests_project "
        "ON customer_revision_requests (project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_revision_requests_project_status "
        "ON customer_revision_requests (project_id, status)"
    )


def _0020_quantity_requirements(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quantity_requirements (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            scope_item_id TEXT NOT NULL,
            trade_code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            requirement_type TEXT NOT NULL,
            suggested_method TEXT NOT NULL,
            suggested_unit TEXT,
            basis_note TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            resolved_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (scope_item_id) REFERENCES scope_items (id)
        )
        """
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_quantity_requirements_project_scope "
        "ON quantity_requirements (project_id, scope_item_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quantity_requirements_project_status "
        "ON quantity_requirements (project_id, status)"
    )


def _0021_customer_revision_rescope_versions(conn: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(customer_revision_requests)").fetchall()
    }
    if "resolved_at" not in existing_columns:
        conn.execute("ALTER TABLE customer_revision_requests ADD COLUMN resolved_at TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_revision_rescope_versions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            customer_revision_request_id TEXT NOT NULL,
            blocker_scope_item_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'resolved',
            actor TEXT NOT NULL DEFAULT 'staff',
            notes TEXT,
            before_snapshot TEXT NOT NULL,
            after_snapshot TEXT NOT NULL,
            changed_items TEXT NOT NULL DEFAULT '[]',
            readiness_snapshot TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (customer_revision_request_id) REFERENCES customer_revision_requests (id),
            FOREIGN KEY (blocker_scope_item_id) REFERENCES scope_items (id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_revision_rescope_project "
        "ON customer_revision_rescope_versions (project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_revision_rescope_request "
        "ON customer_revision_rescope_versions (customer_revision_request_id)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_revision_rescope_request_version "
        "ON customer_revision_rescope_versions (customer_revision_request_id, version_number)"
    )


def _0022_project_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: persist project tenant/company identity.

    Existing local/dev rows may remain NULL so this migration is non-destructive.
    New API writes can populate both columns, and project-read paths can deny
    mismatched tenant headers whenever a row is tenant-scoped.
    """

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()
    }
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE projects ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE projects ADD COLUMN company_id TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_tenant_company "
        "ON projects (tenant_id, company_id, id)"
    )


def _0023_processing_job_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on processing jobs.

    Existing local/dev rows are backfilled from their project when possible and
    otherwise remain NULL so the migration is non-destructive. New job claims
    populate both columns from the tenant-scoped project row, preventing the
    workflow/job layer from being purely UUID/project keyed.
    """

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(processing_jobs)").fetchall()
    }
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE processing_jobs ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE processing_jobs ADD COLUMN company_id TEXT")
    conn.execute(
        """
        UPDATE processing_jobs
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = processing_jobs.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = processing_jobs.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_tenant_company_project "
        "ON processing_jobs (tenant_id, company_id, project_id)"
    )


def _0024_sheet_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on processed sheets.

    Sheet rows are evidence-bearing artifacts for extraction and review. Backfill
    existing rows from their owning project when possible, then index tenant and
    company with project/sheet IDs so subsequent read paths can be narrowed from
    project UUID-only access to tenant-scoped evidence access.
    """

    columns = {row[1] for row in conn.execute("PRAGMA table_info(sheets)").fetchall()}
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE sheets ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE sheets ADD COLUMN company_id TEXT")
    conn.execute(
        """
        UPDATE sheets
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = sheets.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = sheets.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sheets_tenant_company_project "
        "ON sheets (tenant_id, company_id, project_id, id)"
    )


def _0025_extraction_run_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on extraction runs.

    Extraction runs are the first evidence-producing workflow rows after sheets.
    Backfill existing local/dev rows from their project when possible and index
    tenant/company/project/trade so run claims can fail closed instead of using
    only a project UUID and trade code as the workflow boundary.
    """

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(extraction_runs)").fetchall()
    }
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE extraction_runs ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE extraction_runs ADD COLUMN company_id TEXT")
    conn.execute(
        """
        UPDATE extraction_runs
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = extraction_runs.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = extraction_runs.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_tenant_company_project_trade "
        "ON extraction_runs (tenant_id, company_id, project_id, trade_code)"
    )


def _0026_scope_item_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on scope items.

    Scope items are estimate-bearing extraction outputs. Existing local/dev rows
    are backfilled from their project when possible; new DAL writes copy the
    tenant/company identity from the owning project and extraction run so scope
    outputs are not trusted from project UUID alone.
    """

    columns = {row[1] for row in conn.execute("PRAGMA table_info(scope_items)").fetchall()}
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE scope_items ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE scope_items ADD COLUMN company_id TEXT")
    conn.execute(
        """
        UPDATE scope_items
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = scope_items.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = scope_items.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scope_items_tenant_company_project "
        "ON scope_items (tenant_id, company_id, project_id, id)"
    )


def _0027_quantity_requirement_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on quantity requirements.

    Quantity requirements are reviewer-facing blockers that can later write real
    quantity evidence onto scope items. They must therefore be tenant/company
    scoped instead of relying only on a project UUID and scope-item UUID.
    Existing local/dev rows are backfilled from their owning project when
    possible so the migration remains non-destructive.
    """

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(quantity_requirements)").fetchall()
    }
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE quantity_requirements ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE quantity_requirements ADD COLUMN company_id TEXT")
    conn.execute(
        """
        UPDATE quantity_requirements
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = quantity_requirements.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = quantity_requirements.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quantity_requirements_tenant_company_project "
        "ON quantity_requirements (tenant_id, company_id, project_id, id)"
    )


def _0028_evidence_reference_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on evidence references.

    Evidence references are the document lineage used to justify scope and final
    estimate readiness. Existing local/dev rows are backfilled from their owning
    project when possible; new DAL writes copy tenant/company identity only after
    validating the referenced scope item and sheet are in the same tenant scope.
    """

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(evidence_references)").fetchall()
    }
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE evidence_references ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE evidence_references ADD COLUMN company_id TEXT")
    conn.execute(
        """
        UPDATE evidence_references
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = evidence_references.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = evidence_references.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_tenant_company_project_scope "
        "ON evidence_references (tenant_id, company_id, project_id, scope_item_id)"
    )


def _0029_sheet_routing_decision_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on routing decisions.

    Routing decisions decide which sheets are eligible for extraction by trade.
    They reference sheets and, optionally, extraction runs, so each row must be
    tenant/company scoped before it can safely participate in downstream evidence
    generation. Existing local/dev rows are backfilled from their owning project
    when possible so the migration remains non-destructive.
    """

    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(sheet_routing_decisions)").fetchall()
    }
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE sheet_routing_decisions ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE sheet_routing_decisions ADD COLUMN company_id TEXT")
    conn.execute(
        """
        UPDATE sheet_routing_decisions
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = sheet_routing_decisions.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = sheet_routing_decisions.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_routing_tenant_company_project_trade "
        "ON sheet_routing_decisions (tenant_id, company_id, project_id, trade_code)"
    )


def _0030_qa_finding_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on QA findings.

    QA findings are readiness blockers that can prevent owner review and final
    customer delivery. They must therefore be tenant/company scoped instead of
    trusting project UUID alone. Existing local/dev rows are backfilled from the
    owning project when possible so the migration remains non-destructive.
    """

    columns = {row[1] for row in conn.execute("PRAGMA table_info(qa_findings)").fetchall()}
    if "tenant_id" not in columns:
        conn.execute("ALTER TABLE qa_findings ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute("ALTER TABLE qa_findings ADD COLUMN company_id TEXT")
    conn.execute(
        """
        UPDATE qa_findings
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = qa_findings.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = qa_findings.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qa_findings_tenant_company_project "
        "ON qa_findings (tenant_id, company_id, project_id, id)"
    )


def _add_identity_columns(conn: sqlite3.Connection, table: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if "tenant_id" not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT")
    if "company_id" not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN company_id TEXT")


def _0031_estimate_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on estimate artifacts.

    Estimate rows, versions, line items, snapshots, indirects, adjustments, and
    review events are customer-facing delivery artifacts. Backfill existing
    local/dev data from the owning project/version graph and index tenant scope
    so final-estimate surfaces do not rely on UUID selectors alone.
    """

    for table in (
        "estimates",
        "estimate_versions",
        "estimate_line_items",
        "estimate_indirects",
        "estimate_adjustments",
        "estimate_snapshots",
        "estimate_review_events",
    ):
        _add_identity_columns(conn, table)

    conn.execute(
        """
        UPDATE estimates
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = estimates.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = estimates.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        """
        UPDATE estimate_versions
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = estimate_versions.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = estimate_versions.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        """
        UPDATE estimate_line_items
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = estimate_line_items.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = estimate_line_items.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute(
        """
        UPDATE estimate_review_events
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = estimate_review_events.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = estimate_review_events.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    for table in ("estimate_indirects", "estimate_adjustments", "estimate_snapshots"):
        conn.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (
                    SELECT estimate_versions.tenant_id FROM estimate_versions
                    WHERE estimate_versions.id = {table}.version_id
                ),
                company_id = (
                    SELECT estimate_versions.company_id FROM estimate_versions
                    WHERE estimate_versions.id = {table}.version_id
                )
            WHERE tenant_id IS NULL OR company_id IS NULL
            """
        )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_estimates_tenant_company_project "
        "ON estimates (tenant_id, company_id, project_id, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_estimate_versions_tenant_company_project "
        "ON estimate_versions (tenant_id, company_id, project_id, estimate_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_estimate_line_items_tenant_company_project "
        "ON estimate_line_items (tenant_id, company_id, project_id, version_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_estimate_review_events_tenant_company_project "
        "ON estimate_review_events (tenant_id, company_id, project_id, version_id)"
    )


def _0032_customer_revision_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on customer revision rows.

    Customer revision requests and rescope-version snapshots can block or mutate
    estimate readiness. Backfill existing local/dev rows from their owning project
    and index tenant scope so revision workflows cannot rely on project/request
    UUID selectors alone.
    """

    for table in ("customer_revision_requests", "customer_revision_rescope_versions"):
        _add_identity_columns(conn, table)

    for table in ("customer_revision_requests", "customer_revision_rescope_versions"):
        conn.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (
                    SELECT projects.tenant_id FROM projects
                    WHERE projects.id = {table}.project_id
                ),
                company_id = (
                    SELECT projects.company_id FROM projects
                    WHERE projects.id = {table}.project_id
                )
            WHERE tenant_id IS NULL OR company_id IS NULL
            """
        )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_revision_requests_tenant_company_project "
        "ON customer_revision_requests (tenant_id, company_id, project_id, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_customer_revision_rescope_tenant_company_project "
        "ON customer_revision_rescope_versions (tenant_id, company_id, project_id, customer_revision_request_id)"
    )
    conn.execute("DROP INDEX IF EXISTS uq_customer_revision_rescope_request_version")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_revision_rescope_tenant_request_version "
        "ON customer_revision_rescope_versions (tenant_id, company_id, project_id, customer_revision_request_id, version_number)"
    )


def _0033_scope_review_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on scope-review child rows.

    Quantity derivations, conflicts, and scope-item review events are evidence and
    review artifacts that influence estimate readiness. Backfill them through
    their owning scope item and index tenant scope so reads/writes do not rely on
    scope-item UUIDs alone.
    """

    for table in ("quantity_derivations", "conflicts", "review_events"):
        _add_identity_columns(conn, table)

    for table in ("quantity_derivations", "conflicts"):
        conn.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (
                    SELECT scope_items.tenant_id FROM scope_items
                    WHERE scope_items.id = {table}.scope_item_id
                ),
                company_id = (
                    SELECT scope_items.company_id FROM scope_items
                    WHERE scope_items.id = {table}.scope_item_id
                )
            WHERE tenant_id IS NULL OR company_id IS NULL
            """
        )

    conn.execute(
        """
        UPDATE review_events
        SET tenant_id = (
                SELECT scope_items.tenant_id FROM scope_items
                WHERE scope_items.id = review_events.scope_item_id
                  AND scope_items.project_id = review_events.project_id
            ),
            company_id = (
                SELECT scope_items.company_id FROM scope_items
                WHERE scope_items.id = review_events.scope_item_id
                  AND scope_items.project_id = review_events.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quantity_derivations_tenant_scope "
        "ON quantity_derivations (tenant_id, company_id, scope_item_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conflicts_tenant_scope "
        "ON conflicts (tenant_id, company_id, scope_item_id, resolution_status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_events_tenant_project_scope "
        "ON review_events (tenant_id, company_id, project_id, scope_item_id)"
    )


def _0034_proposal_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on proposal artifacts.

    Proposals, proposal versions, line items, immutable snapshots, and review
    events are customer-facing delivery artifacts. Backfill existing local/dev
    rows from their owning project or proposal version and index tenant scope so
    proposal delivery surfaces do not rely on UUID selectors alone.
    """

    for table in (
        "proposals",
        "proposal_versions",
        "proposal_line_items",
        "proposal_snapshots",
        "proposal_review_events",
    ):
        _add_identity_columns(conn, table)

    for table in ("proposals", "proposal_versions", "proposal_review_events"):
        conn.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (
                    SELECT projects.tenant_id FROM projects
                    WHERE projects.id = {table}.project_id
                ),
                company_id = (
                    SELECT projects.company_id FROM projects
                    WHERE projects.id = {table}.project_id
                )
            WHERE tenant_id IS NULL OR company_id IS NULL
            """
        )

    for table in ("proposal_line_items", "proposal_snapshots"):
        conn.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (
                    SELECT proposal_versions.tenant_id FROM proposal_versions
                    WHERE proposal_versions.id = {table}.version_id
                ),
                company_id = (
                    SELECT proposal_versions.company_id FROM proposal_versions
                    WHERE proposal_versions.id = {table}.version_id
                )
            WHERE tenant_id IS NULL OR company_id IS NULL
            """
        )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposals_tenant_company_project "
        "ON proposals (tenant_id, company_id, project_id, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposal_versions_tenant_company_project "
        "ON proposal_versions (tenant_id, company_id, project_id, proposal_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposal_line_items_tenant_company_version "
        "ON proposal_line_items (tenant_id, company_id, version_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposal_snapshots_tenant_company_version "
        "ON proposal_snapshots (tenant_id, company_id, version_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_proposal_review_events_tenant_company_project "
        "ON proposal_review_events (tenant_id, company_id, project_id, version_id)"
    )


def _0035_scope_assembly_mapping_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on scope→assembly mappings.

    Scope assembly mappings influence priced estimate line generation. Backfill
    existing rows from their owning project/scope item and replace the legacy
    scope-item-only unique index with tenant/company/project/scope scoping so a
    stale or corrupt row cannot be served across tenant boundaries.
    """

    _add_identity_columns(conn, "scope_assembly_mappings")
    conn.execute(
        """
        UPDATE scope_assembly_mappings
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = scope_assembly_mappings.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = scope_assembly_mappings.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute("DROP INDEX IF EXISTS uq_mapping_active")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mapping_tenant_project_scope "
        "ON scope_assembly_mappings (tenant_id, company_id, project_id, scope_item_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mapping_tenant_company_project "
        "ON scope_assembly_mappings (tenant_id, company_id, project_id, id)"
    )


def _0036_trade_coverage_tenant_identity(conn: sqlite3.Connection) -> None:
    """P0 tenant-boundary slice: carry tenant identity on trade coverage rows.

    Coverage rows are the all-trade control layer: their dispositions, blockers,
    and evidence refs decide what a project's estimate is allowed to claim. Backfill
    existing rows from their owning project and replace the legacy project/trade
    unique index with a tenant/company scoped one so a mismatched row cannot be
    read, updated, or used as a duplicate check from a project UUID alone.
    """

    _add_identity_columns(conn, "trade_coverage_rows")
    conn.execute(
        """
        UPDATE trade_coverage_rows
        SET tenant_id = (
                SELECT projects.tenant_id FROM projects
                WHERE projects.id = trade_coverage_rows.project_id
            ),
            company_id = (
                SELECT projects.company_id FROM projects
                WHERE projects.id = trade_coverage_rows.project_id
            )
        WHERE tenant_id IS NULL OR company_id IS NULL
        """
    )
    conn.execute("DROP INDEX IF EXISTS uq_trade_coverage_project_trade")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_trade_coverage_tenant_project_trade "
        "ON trade_coverage_rows (tenant_id, company_id, project_id, trade_code)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_coverage_tenant_company_project "
        "ON trade_coverage_rows (tenant_id, company_id, project_id, id)"
    )


def _0037_canonical_takeoff_evidence(conn: sqlite3.Connection) -> None:
    """Milestone 2: additive persistence for canonical takeoff evidence.

    A dedicated, tenant/company-scoped store for ``CanonicalEvidence`` rows
    (``app.takeoff.evidence``). It is purely additive: no existing table is
    touched. Only validated canonical evidence is ever written here — unknown or
    unmapped provider payloads are quarantined by the provider layer and never
    reach this table. ``raw_payload`` keeps the normalized canonical JSON so a
    row round-trips back into a ``CanonicalEvidence`` without lossy re-mapping.

    The controlled-vocabulary columns carry CHECK constraints mirroring the
    Pydantic enums so a malformed provenance/review value fails closed at the DB
    boundary too.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS canonical_takeoff_evidence (
            evidence_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            sheet_id TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            region_coordinates TEXT,
            takeoff_provider TEXT NOT NULL,
            provider_record_id TEXT NOT NULL,
            evidence_class TEXT NOT NULL,
            measurement_method TEXT NOT NULL,
            trade TEXT NOT NULL,
            scope_category TEXT NOT NULL,
            description TEXT NOT NULL,
            quantity TEXT,
            unit TEXT,
            confidence TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending',
            reviewed_by TEXT,
            extractor_version TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (evidence_class IN (
                'measured', 'formula_derived', 'schedule_extracted',
                'specification_extracted', 'customer_supplied', 'human_verified',
                'vendor_quote', 'cost_book', 'allowance', 'model_candidate',
                'test_fixture', 'unsupported'
            )),
            CHECK (takeoff_provider IN (
                'mobi_native', 'manual_import', 'human_verified',
                'authorized_third_party', 'future_cad_bim', 'unknown'
            )),
            CHECK (review_status IN (
                'pending', 'approved', 'corrected', 'rejected', 'blocked'
            )),
            CHECK ((json_valid(raw_payload)) IS TRUE),
            CHECK ((json_type(raw_payload) = 'object') IS TRUE),
            CHECK ((json_type(raw_payload, '$.evidence_id') = 'text' AND json_extract(raw_payload, '$.evidence_id') = evidence_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.schema_version') = 'text' AND json_extract(raw_payload, '$.schema_version') = schema_version) IS TRUE),
            CHECK ((json_type(raw_payload, '$.tenant_id') = 'text' AND json_extract(raw_payload, '$.tenant_id') = tenant_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.company_id') = 'text' AND json_extract(raw_payload, '$.company_id') = company_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.project_id') = 'text' AND json_extract(raw_payload, '$.project_id') = project_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.document_id') = 'text' AND json_extract(raw_payload, '$.document_id') = document_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.sheet_id') = 'text' AND json_extract(raw_payload, '$.sheet_id') = sheet_id) IS TRUE)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_evidence_tenant_company_project "
        "ON canonical_takeoff_evidence (tenant_id, company_id, project_id, evidence_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_evidence_project "
        "ON canonical_takeoff_evidence (project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_evidence_document "
        "ON canonical_takeoff_evidence (document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_evidence_sheet "
        "ON canonical_takeoff_evidence (sheet_id)"
    )


def _0038_canonical_takeoff_evidence_provider_fields(conn: sqlite3.Connection) -> None:
    """Forward migration for OpenTakeoff/customer-supplied takeoff provenance.

    Migration ``_0037`` shipped and was applied with a fixed provider vocabulary
    and no takeoff measurement provenance columns. This migration evolves that
    already-applied table in place, preserving every existing row:

    * adds optional ``condition`` and ``scale`` columns (digital-takeoff
      measurement provenance; omitted by providers that cannot express them);
    * expands the ``takeoff_provider`` CHECK to admit ``open_takeoff``,
      ``customer_supplied`` and ``future_third_party`` lanes;
    * adds fail-closed, null-safe raw-vs-flattened CHECKs so a stored
      ``condition``/``scale`` column can never diverge from the value inside the
      canonical ``raw_payload`` (mirrors the identity CHECKs on the other
      columns and the ``deserialize_canonical_evidence`` guard).

    SQLite cannot ALTER an existing CHECK constraint, so the table is rebuilt via
    the supported copy/rename dance (new table -> copy rows -> drop old ->
    rename). Existing rows carry no ``condition``/``scale`` (NULL) and their
    ``raw_payload`` predates those keys, so ``json_extract(...) IS <column>``
    holds (NULL IS NULL) and the rebuild is loss-free.
    """

    # Rebuild only if the pre-existing (v37) table is present without the new
    # columns; guard keeps the migration a no-op on a table already at v38 shape.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(canonical_takeoff_evidence)")}
    if not columns or {"condition", "scale"} <= columns:
        return

    conn.execute(
        """
        CREATE TABLE canonical_takeoff_evidence__v38 (
            evidence_id TEXT PRIMARY KEY,
            schema_version TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            sheet_id TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            region_coordinates TEXT,
            takeoff_provider TEXT NOT NULL,
            provider_record_id TEXT NOT NULL,
            evidence_class TEXT NOT NULL,
            measurement_method TEXT NOT NULL,
            trade TEXT NOT NULL,
            scope_category TEXT NOT NULL,
            description TEXT NOT NULL,
            quantity TEXT,
            unit TEXT,
            confidence TEXT,
            condition TEXT,
            scale TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending',
            reviewed_by TEXT,
            extractor_version TEXT NOT NULL,
            raw_payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (evidence_class IN (
                'measured', 'formula_derived', 'schedule_extracted',
                'specification_extracted', 'customer_supplied', 'human_verified',
                'vendor_quote', 'cost_book', 'allowance', 'model_candidate',
                'test_fixture', 'unsupported'
            )),
            CHECK (takeoff_provider IN (
                'mobi_native', 'open_takeoff', 'manual_import', 'human_verified',
                'customer_supplied', 'authorized_third_party', 'future_cad_bim',
                'future_third_party', 'unknown'
            )),
            CHECK (review_status IN (
                'pending', 'approved', 'corrected', 'rejected', 'blocked'
            )),
            CHECK ((json_valid(raw_payload)) IS TRUE),
            CHECK ((json_type(raw_payload) = 'object') IS TRUE),
            CHECK ((json_type(raw_payload, '$.evidence_id') = 'text' AND json_extract(raw_payload, '$.evidence_id') = evidence_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.schema_version') = 'text' AND json_extract(raw_payload, '$.schema_version') = schema_version) IS TRUE),
            CHECK ((json_type(raw_payload, '$.tenant_id') = 'text' AND json_extract(raw_payload, '$.tenant_id') = tenant_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.company_id') = 'text' AND json_extract(raw_payload, '$.company_id') = company_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.project_id') = 'text' AND json_extract(raw_payload, '$.project_id') = project_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.document_id') = 'text' AND json_extract(raw_payload, '$.document_id') = document_id) IS TRUE),
            CHECK ((json_type(raw_payload, '$.sheet_id') = 'text' AND json_extract(raw_payload, '$.sheet_id') = sheet_id) IS TRUE),
            CHECK ((json_extract(raw_payload, '$.condition') IS condition) IS TRUE),
            CHECK ((json_extract(raw_payload, '$.scale') IS scale) IS TRUE)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO canonical_takeoff_evidence__v38 (
            evidence_id, schema_version, tenant_id, company_id, project_id,
            document_id, sheet_id, page_number, region_coordinates,
            takeoff_provider, provider_record_id, evidence_class,
            measurement_method, trade, scope_category, description, quantity,
            unit, confidence, condition, scale, review_status, reviewed_by,
            extractor_version, raw_payload, created_at, updated_at
        )
        SELECT
            evidence_id, schema_version, tenant_id, company_id, project_id,
            document_id, sheet_id, page_number, region_coordinates,
            takeoff_provider, provider_record_id, evidence_class,
            measurement_method, trade, scope_category, description, quantity,
            unit, confidence,
            json_extract(raw_payload, '$.condition'),
            json_extract(raw_payload, '$.scale'),
            review_status, reviewed_by,
            extractor_version, raw_payload, created_at, updated_at
        FROM canonical_takeoff_evidence
        """
    )
    conn.execute("DROP TABLE canonical_takeoff_evidence")
    conn.execute(
        "ALTER TABLE canonical_takeoff_evidence__v38 RENAME TO canonical_takeoff_evidence"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_evidence_tenant_company_project "
        "ON canonical_takeoff_evidence (tenant_id, company_id, project_id, evidence_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_evidence_project "
        "ON canonical_takeoff_evidence (project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_evidence_document "
        "ON canonical_takeoff_evidence (document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_canonical_evidence_sheet "
        "ON canonical_takeoff_evidence (sheet_id)"
    )


def _0039_opentakeoff_worker_jobs(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS opentakeoff_worker_jobs (
            job_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            operation TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            requested_by TEXT,
            started_at TEXT,
            completed_at TEXT,
            cancelled_at TEXT,
            error_category TEXT,
            safe_error_message TEXT,
            artifact_ids TEXT NOT NULL DEFAULT '[]',
            evidence_ids TEXT NOT NULL DEFAULT '[]',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (status IN (
                'queued', 'running', 'awaiting_scale_confirmation',
                'awaiting_geometry_confirmation', 'completed', 'failed', 'cancelled'
            )),
            CHECK ((json_valid(artifact_ids)) IS TRUE),
            CHECK ((json_valid(evidence_ids)) IS TRUE)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_project "
        "ON opentakeoff_worker_jobs (tenant_id, company_id, project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_document "
        "ON opentakeoff_worker_jobs (tenant_id, company_id, document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_status "
        "ON opentakeoff_worker_jobs (status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_tenant_status "
        "ON opentakeoff_worker_jobs (tenant_id, company_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_idempotency "
        "ON opentakeoff_worker_jobs (idempotency_key)"
    )


def _0040_opentakeoff_worker_job_api_statuses(conn: sqlite3.Connection) -> None:
    """Relax the worker-job status CHECK for the deployable worker API lifecycle.

    Migration ``_0039`` shipped a status CHECK covering only the in-process
    values. The deployable worker API adds ``starting``, ``document_loaded``,
    ``awaiting_geometry``, ``running_measurement``, and ``awaiting_review`` while
    keeping the older values as a backward-compatible superset. SQLite cannot
    ALTER an existing CHECK, so the table is rebuilt via the supported
    copy/rename dance. Every existing row is preserved; the rebuild is a no-op
    once the expanded CHECK is already present.
    """

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='opentakeoff_worker_jobs'"
    ).fetchone()
    if row is None:
        return
    existing_sql = row[0] or ""
    # Idempotency guard: skip rebuild once the expanded status vocabulary is live.
    if "awaiting_review" in existing_sql:
        return

    conn.execute(
        """
        CREATE TABLE opentakeoff_worker_jobs__v40 (
            job_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            operation TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            requested_by TEXT,
            started_at TEXT,
            completed_at TEXT,
            cancelled_at TEXT,
            error_category TEXT,
            safe_error_message TEXT,
            artifact_ids TEXT NOT NULL DEFAULT '[]',
            evidence_ids TEXT NOT NULL DEFAULT '[]',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK (status IN (
                'queued', 'starting', 'document_loaded', 'running',
                'awaiting_scale_confirmation', 'awaiting_geometry',
                'awaiting_geometry_confirmation', 'running_measurement',
                'awaiting_review', 'completed', 'failed', 'cancelled'
            )),
            CHECK ((json_valid(artifact_ids)) IS TRUE),
            CHECK ((json_valid(evidence_ids)) IS TRUE)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO opentakeoff_worker_jobs__v40 (
            job_id, tenant_id, company_id, project_id, document_id, provider,
            engine_version, operation, idempotency_key, status, requested_by,
            started_at, completed_at, cancelled_at, error_category,
            safe_error_message, artifact_ids, evidence_ids, attempt_count,
            created_at, updated_at
        )
        SELECT
            job_id, tenant_id, company_id, project_id, document_id, provider,
            engine_version, operation, idempotency_key, status, requested_by,
            started_at, completed_at, cancelled_at, error_category,
            safe_error_message, artifact_ids, evidence_ids, attempt_count,
            created_at, updated_at
        FROM opentakeoff_worker_jobs
        """
    )
    conn.execute("DROP TABLE opentakeoff_worker_jobs")
    conn.execute(
        "ALTER TABLE opentakeoff_worker_jobs__v40 RENAME TO opentakeoff_worker_jobs"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_project "
        "ON opentakeoff_worker_jobs (tenant_id, company_id, project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_document "
        "ON opentakeoff_worker_jobs (tenant_id, company_id, document_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_status "
        "ON opentakeoff_worker_jobs (status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_tenant_status "
        "ON opentakeoff_worker_jobs (tenant_id, company_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_opentakeoff_jobs_idempotency "
        "ON opentakeoff_worker_jobs (idempotency_key)"
    )


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
    Migration(17, "trade_coverage_matrix", _0017_trade_coverage_matrix),
    Migration(18, "qa_findings", _0018_qa_findings),
    Migration(19, "customer_revision_requests", _0019_customer_revision_requests),
    Migration(20, "quantity_requirements", _0020_quantity_requirements),
    Migration(21, "customer_revision_rescope_versions", _0021_customer_revision_rescope_versions),
    Migration(22, "project_tenant_identity", _0022_project_tenant_identity),
    Migration(23, "processing_job_tenant_identity", _0023_processing_job_tenant_identity),
    Migration(24, "sheet_tenant_identity", _0024_sheet_tenant_identity),
    Migration(25, "extraction_run_tenant_identity", _0025_extraction_run_tenant_identity),
    Migration(26, "scope_item_tenant_identity", _0026_scope_item_tenant_identity),
    Migration(27, "quantity_requirement_tenant_identity", _0027_quantity_requirement_tenant_identity),
    Migration(28, "evidence_reference_tenant_identity", _0028_evidence_reference_tenant_identity),
    Migration(29, "sheet_routing_decision_tenant_identity", _0029_sheet_routing_decision_tenant_identity),
    Migration(30, "qa_finding_tenant_identity", _0030_qa_finding_tenant_identity),
    Migration(31, "estimate_tenant_identity", _0031_estimate_tenant_identity),
    Migration(32, "customer_revision_tenant_identity", _0032_customer_revision_tenant_identity),
    Migration(33, "scope_review_tenant_identity", _0033_scope_review_tenant_identity),
    Migration(34, "proposal_tenant_identity", _0034_proposal_tenant_identity),
    Migration(35, "scope_assembly_mapping_tenant_identity", _0035_scope_assembly_mapping_tenant_identity),
    Migration(36, "trade_coverage_tenant_identity", _0036_trade_coverage_tenant_identity),
    Migration(37, "canonical_takeoff_evidence", _0037_canonical_takeoff_evidence),
    Migration(
        38,
        "canonical_takeoff_evidence_provider_fields",
        _0038_canonical_takeoff_evidence_provider_fields,
    ),
    Migration(39, "opentakeoff_worker_jobs", _0039_opentakeoff_worker_jobs),
    Migration(
        40,
        "opentakeoff_worker_job_api_statuses",
        _0040_opentakeoff_worker_job_api_statuses,
    ),
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
