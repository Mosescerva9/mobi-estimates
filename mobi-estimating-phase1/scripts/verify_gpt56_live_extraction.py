"""Opt-in live verification for the staff GPT-5.6 scope-extraction activation path.

This exercises ONE real, paid live scope extraction end-to-end through the SAME
tenant/company-guarded extraction endpoint the staff admin action uses — proving
the activated path works — but against a throwaway, isolated database and a
purely SYNTHETIC public project. It is a sibling of ``verify_gpt56_live.py``
(which probes the raw Responses client); this one proves the extraction pipeline.

Safety envelope (do not weaken):

* refuses to run without ALL of: ``MOBI_GPT56_LIVE_EXTRACTION_VERIFY=1``, a
  configured API key, and ``MOBI_ENABLE_LIVE_EXTRACTION=true``;
* runs in an isolated :class:`tempfile.TemporaryDirectory` DB/upload root, set
  BEFORE app/settings import, and asserts the resolved DB/upload paths are under
  that owned temp root — so a stray production ``MOBI_DB_PATH`` in the ambient
  environment can never be touched even if present;
* builds a tiny SYNTHETIC, non-customer painting spec (no real project/tenant);
* re-checks the exact ``gpt-5.6`` / ``medium`` lock in a preflight that costs
  zero paid requests on mismatch;
* bounds the provider to exactly ONE request (retries forced to 0, one trade)
  and *counts actual provider dispatches* by wrapping the provider method — the
  count is measured, never asserted as a constant;
* checks every HTTP status before reading a body, verifies every persisted scope
  item is review-pending/blocked with a null quantity, no approval, and a
  same-page LITERAL grounded quote, asserts exactly one extraction run total
  (its one trade painting), and snapshots the throwaway DB to prove zero
  proposal/estimate/approval/pricing side effects;
* writes SANITIZED, machine-readable evidence (statuses, counts, booleans) that
  contains no source text, quotes, raw provider output, key material, filesystem
  paths, or customer IDs;
* the scratch DB/uploads are always cleaned up (even on failure) and the cleanup
  is explicitly verified (``scratch_cleanup_verified``, failing the contract if
  the temp root still exists); only the sanitized evidence file, written outside
  the temp root, is retained;
* does NOT approve, deliver, price, message, pay, or mutate any production data.

Usage (never paste secrets into chat/commits/logs — export them in your shell)::

    export OPENAI_API_KEY=...
    export MOBI_OPENAI_API_KEY=$OPENAI_API_KEY
    export MOBI_ENABLE_LIVE_EXTRACTION=true
    export MOBI_GPT56_LIVE_EXTRACTION_VERIFY=1
    python -m scripts.verify_gpt56_live_extraction --out evidence/gpt56_live_extraction.json

Do NOT run this as part of ordinary CI/tests; it makes a real paid call.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# A synthetic, non-customer painting spec. Contains no real project/tenant data.
_SYNTHETIC_SPEC_LINES = [
    "SECTION 099000 PAINTING",
    "This is a synthetic connectivity probe, not a real project.",
    "Interior gypsum board walls: apply primer and two finish coats.",
    "No quantities, dimensions, or prices are stated in this synthetic source.",
]

_TENANT_HEADERS = {
    "X-Mobi-Tenant-Id": "synthetic_probe_tenant",
    "X-Mobi-Company-Id": "synthetic_probe_company",
}


class ContractError(RuntimeError):
    """A violated safety/behavior contract. Message is safe/sanitized."""


def _gate_or_exit() -> None:
    problems: list[str] = []
    if os.environ.get("MOBI_GPT56_LIVE_EXTRACTION_VERIFY") != "1":
        problems.append("MOBI_GPT56_LIVE_EXTRACTION_VERIFY must equal '1'")
    if not os.environ.get("MOBI_OPENAI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        problems.append("an OpenAI API key must be configured via env")
    if os.environ.get("MOBI_ENABLE_LIVE_EXTRACTION", "").lower() not in {"true", "1", "yes"}:
        problems.append("MOBI_ENABLE_LIVE_EXTRACTION must be enabled")
    if problems:
        sys.stderr.write(
            "Refusing to run live extraction verification. Unmet gate(s):\n  - "
            + "\n  - ".join(problems)
            + "\n"
        )
        raise SystemExit(2)


def _synthetic_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Repeat the spec so the page clears the low-information text-layer gate.
    lines = _SYNTHETIC_SPEC_LINES * 8
    for index, line in enumerate(lines):
        page.insert_text((40, 50 + index * 18), line, fontsize=9)
    # Title block sheet number for a clean verified identity.
    page.insert_text((612 * 0.78, 792 * 0.94), "A-101", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data



def _preflight_exact_model_effort() -> list[str]:
    from app.config import ENFORCED_MODEL_ALIAS, ENFORCED_REASONING_EFFORT, settings

    problems: list[str] = []
    if settings.openai_model != ENFORCED_MODEL_ALIAS:
        problems.append(
            f"configured model {settings.openai_model!r} is not the enforced "
            f"alias {ENFORCED_MODEL_ALIAS!r}"
        )
    if settings.openai_reasoning_effort != ENFORCED_REASONING_EFFORT:
        problems.append(
            f"configured reasoning effort {settings.openai_reasoning_effort!r} is "
            f"not the enforced {ENFORCED_REASONING_EFFORT!r}"
        )
    return problems


def _require_status(resp, expected: int, label: str) -> None:
    """Fail closed if an HTTP status is not exactly ``expected`` — before JSON."""

    if resp.status_code != expected:
        raise ContractError(f"{label} returned HTTP {resp.status_code}, expected {expected}")


# Engine tables that a live *scope extraction* run must never write into. These
# are the estimate/proposal/pricing/delivery side-effect surfaces; the run only
# ever produces review-pending scope items + evidence. Delivery/payment/messaging
# live in the portal (Supabase), which this harness never touches.
_MUST_BE_EMPTY_TABLES = (
    "proposals",
    "proposal_versions",
    "proposal_line_items",
    "proposal_snapshots",
    "proposal_review_events",
    "estimates",
    "estimate_versions",
    "estimate_line_items",
    "estimate_indirects",
    "estimate_adjustments",
    "estimate_snapshots",
    "estimate_review_events",
    "qa_findings",
    "customer_revision_requests",
    "customer_revision_rescope_versions",
)


def _snapshot_side_effects(db_path: Path, problems: list[str]) -> dict[str, object]:
    """Query the throwaway DB directly and prove zero delivery/pricing/approval
    side effects. Records only measured counts (facts), never row contents."""

    facts: dict[str, object] = {}
    # Plain connection (SELECT-only below). The app's per-request WAL connections
    # are all closed by now; a plain handle reliably reads committed WAL data on
    # this throwaway file that is deleted immediately afterwards.
    conn = sqlite3.connect(str(db_path))
    try:
        existing = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

        def _count(sql: str) -> int:
            return int(conn.execute(sql).fetchone()[0])

        empty_counts: dict[str, int] = {}
        for table in _MUST_BE_EMPTY_TABLES:
            if table not in existing:
                empty_counts[table] = -1  # -1 == table absent (not applicable)
                continue
            count = _count(f"SELECT COUNT(*) FROM {table}")
            empty_counts[table] = count
            if count != 0:
                problems.append(f"side-effect table '{table}' had {count} row(s); expected 0")
        facts["side_effect_table_counts"] = empty_counts

        # Approval side effects on the tables that DO get scope rows.
        approved_reviews = (
            _count(
                "SELECT COUNT(*) FROM review_events "
                "WHERE action='approve' OR new_state='approved'"
            )
            if "review_events" in existing
            else 0
        )
        total_reviews = (
            _count("SELECT COUNT(*) FROM review_events")
            if "review_events" in existing
            else 0
        )
        approved_items = (
            _count(
                "SELECT COUNT(*) FROM scope_items "
                "WHERE review_status='approved' OR approved_at IS NOT NULL"
            )
            if "scope_items" in existing
            else 0
        )
        facts["approved_review_events"] = approved_reviews
        facts["total_review_events"] = total_reviews
        facts["approved_scope_items"] = approved_items
        if approved_reviews != 0:
            problems.append(f"found {approved_reviews} approved review event(s); expected 0")
        if approved_items != 0:
            problems.append(f"found {approved_items} approved scope item(s); expected 0")

        # Measured (not asserted) run status facts for the record.
        if "extraction_runs" in existing:
            run_statuses: dict[str, int] = {}
            for status, count in conn.execute(
                "SELECT status, COUNT(*) FROM extraction_runs GROUP BY status"
            ):
                run_statuses[str(status)] = int(count)
            facts["extraction_run_status_counts"] = run_statuses

        # Measured single-project / single-trade scope contract. This probe uploads
        # exactly one synthetic project and runs exactly one painting extraction, so
        # the throwaway DB must hold exactly one project and exactly one distinct
        # extraction-run trade, coded 'painting'. Anything else means the harness
        # produced an unexpected side effect; fail closed on any mismatch. Only the
        # measured counts/codes (never row contents) are retained as evidence.
        if "projects" in existing:
            project_count = _count("SELECT COUNT(*) FROM projects")
            facts["project_count"] = project_count
            if project_count != 1:
                problems.append(f"found {project_count} project(s); expected exactly 1")
        else:
            facts["project_count"] = -1
            problems.append("projects table absent; expected exactly 1 project")

        if "extraction_runs" in existing:
            # Exactly ONE extraction run total (one activation click = one run),
            # and its single trade is 'painting'. Assert both the row count and the
            # distinct-trade set so an unexpected extra run of any trade fails.
            run_count = _count("SELECT COUNT(*) FROM extraction_runs")
            facts["extraction_run_count"] = run_count
            if run_count != 1:
                problems.append(
                    f"found {run_count} extraction run(s); expected exactly 1"
                )
            run_trade_codes = sorted(
                str(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT trade_code FROM extraction_runs"
                )
            )
            facts["extraction_run_trade_codes"] = run_trade_codes
            if run_trade_codes != ["painting"]:
                problems.append(
                    f"extraction runs spanned {len(run_trade_codes)} distinct trade(s); "
                    "expected exactly 1 coded 'painting'"
                )
        else:
            facts["extraction_run_count"] = -1
            facts["extraction_run_trade_codes"] = []
            problems.append("extraction_runs table absent; expected exactly 1 painting run")
        # Portal-only effect classes have no engine table; record as not applicable.
        facts["engine_payment_tables"] = "none"
        facts["engine_delivery_tables"] = "none"
        facts["engine_message_tables"] = "none"
    finally:
        conn.close()
    return facts


def _check_scope_item_detail(
    item_detail: dict,
    problems: list[str],
    index: int,
    source_text_by_page: dict[int, str],
    category_allowlist: frozenset[str],
) -> dict:
    """Return sanitized per-item facts and record any contract violations."""

    scope_item = item_detail.get("scope_item") or {}
    evidence = item_detail.get("evidence") or []

    review_status = scope_item.get("review_status")
    quantity = scope_item.get("quantity")
    approved_at = scope_item.get("approved_at")
    category_code = scope_item.get("category_code")
    item_description = scope_item.get("description")

    review_ok = review_status in {"pending", "blocked"}
    quantity_null = quantity is None
    approved_null = approved_at is None
    evidence_nonempty = len(evidence) > 0

    # The persisted category must belong to the trade's authoritative allowlist,
    # derived at runtime from the trade module definition (never hardcoded here).
    category_valid = isinstance(category_code, str) and category_code in category_allowlist

    if not review_ok:
        problems.append(f"item[{index}] review_status not pending/blocked")
    if not quantity_null:
        problems.append(f"item[{index}] authored a non-null quantity")
    if not approved_null:
        problems.append(f"item[{index}] has a non-null approved_at")
    if not evidence_nonempty:
        problems.append(f"item[{index}] has no evidence")
    if not category_valid:
        problems.append(f"item[{index}] category_code not in authoritative allowlist")

    # The item description must equal the FIRST retained exact evidence quote,
    # bounded to 1000 characters — proving it is server-derived from a sourced
    # quote, not model-authored prose.
    description_source_derived = False
    if evidence_nonempty:
        first_quote = evidence[0].get("extracted_text_quote")
        if isinstance(first_quote, str) and item_description == first_quote[:1000]:
            description_source_derived = True
    if not description_source_derived:
        problems.append(
            f"item[{index}] description is not the first retained exact evidence "
            f"quote bounded to 1000"
        )

    all_evidence_grounded = evidence_nonempty
    all_verified_identity = evidence_nonempty
    all_require_human = evidence_nonempty
    all_evidence_desc_derived = evidence_nonempty
    for ev in evidence:
        page = ev.get("pdf_page_number")
        sheet_id = ev.get("sheet_id")
        sheet_number = ev.get("verified_sheet_number")
        quote = ev.get("extracted_text_quote")
        ev_description = ev.get("description")
        requires_human = ev.get("requires_human_verification")

        if not (sheet_id and sheet_number and isinstance(page, int)):
            all_verified_identity = False
        if not requires_human:
            all_require_human = False
        # Each evidence description must equal its OWN exact retained quote,
        # bounded to 1000 characters — never the candidate's first quote.
        if not (isinstance(quote, str) and ev_description == quote[:1000]):
            all_evidence_desc_derived = False
        source = source_text_by_page.get(page) if isinstance(page, int) else None
        # Literal exact substring — mirrors the provider's raw-text anchoring, and
        # is compared against the ACTUAL processed source text for that page.
        if not quote or source is None or quote not in source:
            all_evidence_grounded = False

    if not all_verified_identity:
        problems.append(f"item[{index}] evidence missing verified sheet id/number/page")
    if not all_require_human:
        problems.append(f"item[{index}] evidence not flagged requires_human_verification")
    if not all_evidence_grounded:
        problems.append(f"item[{index}] evidence quote not grounded on the same page")
    if not all_evidence_desc_derived:
        problems.append(
            f"item[{index}] evidence description not its own exact quote bounded to 1000"
        )

    # Sanitized facts only — booleans/counts. No quote text, description text, or
    # category text is retained (the category code is reduced to a validity boolean).
    return {
        "review_status_is_pending_or_blocked": review_ok,
        "quantity_is_null": quantity_null,
        "approved_at_is_null": approved_null,
        "evidence_count": len(evidence),
        "evidence_verified_identity": all_verified_identity,
        "evidence_requires_human_verification": all_require_human,
        "evidence_quote_grounded_same_page": all_evidence_grounded,
        "category_valid": category_valid,
        "description_source_derived": description_source_derived,
        "evidence_description_source_derived": all_evidence_desc_derived,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GPT-5.6 live scope-extraction probe")
    parser.add_argument(
        "--out",
        default="evidence/gpt56_live_extraction.json",
        help="Path to write sanitized machine-readable evidence.",
    )
    args = parser.parse_args(argv)

    _gate_or_exit()

    # Resolve the retained evidence path up front, OUTSIDE the scratch temp root.
    out_path = Path(args.out).resolve()

    problems: list[str] = []
    evidence: dict[str, object] = {"contains_customer_data": False}

    # Isolated, throwaway data root so no production DB/uploads are ever touched.
    # The context manager guarantees cleanup even if the probe raises.
    with tempfile.TemporaryDirectory(prefix="mobi-live-extract-verify-") as boot_str:
        boot = Path(boot_str).resolve()
        try:
            _run_probe(boot, evidence, problems)
        except ContractError as exc:
            problems.append(str(exc))
        except SystemExit:
            raise
        except Exception as exc:  # pragma: no cover - defensive, sanitized
            problems.append(f"unexpected failure: {type(exc).__name__}")

    # Temp root (and all scratch DB/uploads) is now removed. Explicitly VERIFY the
    # cleanup happened: ``boot`` still names the (now-deleted) scratch root, so it
    # must no longer exist. Record only the sanitized boolean (never the path) and
    # fail the contract if cleanup was not observed.
    scratch_cleanup_verified = not boot.exists()
    evidence["scratch_cleanup_verified"] = scratch_cleanup_verified
    if not scratch_cleanup_verified:
        problems.append("scratch temp root was not cleaned up after the probe")

    # Record the outcome and write the sanitized evidence to the retained path.
    evidence["contract_ok"] = not problems
    evidence["problems"] = problems
    _write(out_path, evidence)

    if problems:
        sys.stderr.write(
            f"Live extraction verification FAILED the safety contract "
            f"({len(problems)} problem(s)). Evidence: {out_path}\n"
        )
        return 1
    sys.stdout.write(
        f"Live extraction verification succeeded. Evidence written to {out_path}\n"
    )
    return 0


def _run_probe(boot: Path, evidence: dict[str, object], problems: list[str]) -> None:
    # Set the scratch DB/upload roots BEFORE importing app/settings so the cached
    # settings singleton binds to the temp root — never an ambient production path.
    db_path = boot / "mobi.db"
    upload_dir = boot / "uploads"
    os.environ["MOBI_DB_PATH"] = str(db_path)
    os.environ["MOBI_UPLOAD_DIR"] = str(upload_dir)
    os.environ.setdefault("MOBI_DEPLOYMENT_ENVIRONMENT", "local")
    os.environ.setdefault("MOBI_ENGINE_AUTH_MODE", "local_dev_open")
    os.environ["MOBI_ENABLED_TRADES"] = "painting"

    from fastapi.testclient import TestClient

    from app.config import settings

    # Prove the harness is bound to the owned temp root, not a production path.
    resolved_db = Path(settings.db_path).resolve()
    resolved_uploads = Path(settings.upload_dir).resolve()
    if not resolved_db.is_relative_to(boot) or not resolved_uploads.is_relative_to(boot):
        raise ContractError("resolved DB/upload paths are not under the owned temp root")
    evidence["scratch_paths_under_temp_root"] = True

    preflight = _preflight_exact_model_effort()
    if preflight:
        # Zero paid requests on a model/effort mismatch — refuse before any call.
        raise ContractError("preflight model/effort mismatch: " + "; ".join(preflight))

    if not settings.enable_live_extraction or not settings.openai_api_key:
        raise ContractError("live extraction is not fully armed (needs enable flag + key)")

    # Bound the provider to exactly one request: no retries, one trade, no cache.
    settings.extraction_max_retries = 0
    settings.extraction_inline = True
    settings.extraction_cache_enabled = False

    # Instrument ACTUAL provider dispatches by wrapping the method the retry loop
    # calls. The count is measured from real invocations, never a constant.
    from app.extraction import openai_provider as op

    dispatch = {"count": 0}
    _orig_extract = op.OpenAIExtractionProvider.extract_scope

    def _counting_extract(self, request):
        dispatch["count"] += 1
        return _orig_extract(self, request)

    op.OpenAIExtractionProvider.extract_scope = _counting_extract  # type: ignore[assignment]

    from app.main import app

    try:
        with TestClient(app) as client:
            upload = client.post(
                "/api/v1/projects/upload",
                data={"project_name": "SYNTHETIC-LIVE-EXTRACTION-PROBE"},
                files={"plan": ("synthetic.pdf", _synthetic_pdf(), "application/pdf")},
                headers=_TENANT_HEADERS,
            )
            _require_status(upload, 201, "upload")
            pid = upload.json()["project_id"]

            process = client.post(f"/api/v1/projects/{pid}/process", headers=_TENANT_HEADERS)
            _require_status(process, 200, "process")

            sheets_resp = client.get(f"/api/v1/projects/{pid}/sheets", headers=_TENANT_HEADERS)
            _require_status(sheets_resp, 200, "sheet list")
            for sheet in sheets_resp.json()["items"]:
                verify = client.patch(
                    f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}/verification",
                    json={"verified_sheet_number": "A-101", "review_status": "verified"},
                    headers=_TENANT_HEADERS,
                )
                _require_status(verify, 200, "sheet verification")

            # Read the ACTUAL processed source text used by the provider from the
            # throwaway project records. This avoids relying on a reconstructed PDF
            # text layer when proving literal same-page quote grounding.
            from uuid import UUID
            from app.database import list_sheets
            from app.extraction.service import _read_sheet_text

            sheet_rows, _ = list_sheets(UUID(pid), limit=200, offset=0)
            source_text_by_page = {
                int(sheet["pdf_page_number"]): _read_sheet_text(sheet)
                for sheet in sheet_rows
            }
            if not source_text_by_page or any(not text for text in source_text_by_page.values()):
                raise ContractError("processed sheet source text was unavailable")

            # Derive the painting authoritative scope-category allowlist at RUNTIME
            # from the trade registry / module definition — never hardcoded here —
            # so every persisted item's category_code is checked against the same
            # authoritative set the extraction service enforces.
            from app.trades.registry import trade_registry

            painting_module = trade_registry.get("painting", require_enabled=True)
            category_allowlist = frozenset(
                painting_module.get_definition().scope_categories
            )
            if not category_allowlist:
                raise ContractError("painting authoritative category allowlist was empty")

            # The one and only live call: exactly the staff activation payload.
            run_resp = client.post(
                f"/api/v1/projects/{pid}/trades/painting/extractions",
                json={"use_live_provider": True, "force": False, "dry_run": False},
                headers=_TENANT_HEADERS,
            )
            _require_status(run_resp, 202, "start extraction")
            run = run_resp.json()

            list_resp = client.get(
                f"/api/v1/projects/{pid}/scope-items?trade_code=painting&limit=200",
                headers=_TENANT_HEADERS,
            )
            _require_status(list_resp, 200, "scope list")
            items = list_resp.json().get("items", [])

            sanitized_items = []
            for index, summary in enumerate(items):
                detail_resp = client.get(
                    f"/api/v1/projects/{pid}/scope-items/{summary['id']}",
                    headers=_TENANT_HEADERS,
                )
                _require_status(detail_resp, 200, f"scope detail[{index}]")
                sanitized_items.append(
                    _check_scope_item_detail(
                        detail_resp.json(),
                        problems,
                        index,
                        source_text_by_page,
                        category_allowlist,
                    )
                )
    finally:
        op.OpenAIExtractionProvider.extract_scope = _orig_extract  # type: ignore[assignment]

    # --- Run-level contract ------------------------------------------------
    run_status = run.get("status")
    run_provider = run.get("provider")
    run_model = run.get("model_identifier")
    candidate_count = run.get("candidate_count")

    if run_status != "needs_review":
        problems.append(f"run status {run_status!r}, expected 'needs_review'")
    if run_provider != "openai":
        problems.append(f"run provider {run_provider!r}, expected 'openai'")
    if run_model != "gpt-5.6":
        problems.append(f"run model {run_model!r}, expected 'gpt-5.6'")
    if not isinstance(candidate_count, int) or candidate_count <= 0:
        problems.append("candidate_count is not > 0")
    if not sanitized_items:
        problems.append("no scope items were produced")

    if dispatch["count"] != 1:
        problems.append(f"provider dispatched {dispatch['count']} time(s), expected exactly 1")

    # --- DB side-effect snapshot ------------------------------------------
    side_effects = _snapshot_side_effects(db_path, problems)

    # --- Sanitized evidence (no source text, quotes, keys, paths, cust ids) --
    evidence.update(
        {
            "configured_model": settings.openai_model,
            "configured_reasoning_effort": settings.openai_reasoning_effort,
            "run_status": run_status,
            "run_provider": run_provider,
            "run_model_identifier": run_model,
            "candidate_count": candidate_count,
            "scope_item_count": len(sanitized_items),
            "scope_items": sanitized_items,
            "provider_dispatch_count": dispatch["count"],
            "retries_configured": settings.extraction_max_retries,
            "cache_enabled": settings.extraction_cache_enabled,
            "side_effects": side_effects,
            "all_items_review_pending_or_blocked": all(
                i["review_status_is_pending_or_blocked"] for i in sanitized_items
            )
            if sanitized_items
            else False,
            "no_model_authored_quantity": all(i["quantity_is_null"] for i in sanitized_items)
            if sanitized_items
            else False,
            "all_items_category_valid": all(i["category_valid"] for i in sanitized_items)
            if sanitized_items
            else False,
            "all_items_description_source_derived": all(
                i["description_source_derived"] for i in sanitized_items
            )
            if sanitized_items
            else False,
            "all_evidence_description_source_derived": all(
                i["evidence_description_source_derived"] for i in sanitized_items
            )
            if sanitized_items
            else False,
        }
    )


def _write(out_path: Path, evidence: dict[str, object]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover - manual, gated entry point
    raise SystemExit(main())
