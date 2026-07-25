"""Apply one canonical takeoff evidence record to one scope item.

This closes the gap between the OpenTakeoff worker (which persists
``canonical_takeoff_evidence`` rows with ``review_status=pending``) and scope
approval (which only trusts ``evidence_references`` linked to scope items).
There was previously no supported API to bridge the two.

This module never trusts client-supplied quantity/unit/project/sheet/path: the
canonical evidence, the scope item, and the source sheet are all re-resolved
and re-verified server-side, tenant/company/project-scoped, immediately before
any write. All mutation happens inside a single SQLite transaction so a
rejection at any check leaves the database exactly as it was.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app import database
from app.estimating.quantities import QuantityBasis
from app.estimating.units import is_unit
from app.takeoff.evidence import (
    CanonicalEvidence,
    EvidenceClass,
    EvidenceReviewStatus,
    MeasurementMethod,
    TakeoffProviderKind,
)
from app.takeoff.store import (
    CANONICAL_EVIDENCE_TABLE,
    deserialize_canonical_evidence,
    serialize_canonical_evidence,
)
from app.takeoff.worker_api import WorkerActor, WorkerApiError
from app.tenant_boundary import assert_same_tenant_project_access, build_tenant_project_context
from app.trades.base import CandidateContext
from app.trades.registry import UnknownTradeError, trade_registry

# Measurement methods this endpoint accepts, mapped to the QuantityBasis the
# applied scope item quantity is stamped with. A staff marker tally (count) is
# a deterministic tally of placed markers -> drawing_count; a native digital
# line/polygon measurement is a value read directly off the verified drawing
# -> explicit_plan_quantity. No other measurement method is supported here.
MEASUREMENT_METHOD_QUANTITY_BASIS: dict[str, str] = {
    MeasurementMethod.STAFF_MARKER_TALLY.value: QuantityBasis.DRAWING_COUNT.value,
    MeasurementMethod.DIGITAL_MEASUREMENT.value: QuantityBasis.EXPLICIT_PLAN_QUANTITY.value,
}

ALLOWED_TAKEOFF_PROVIDERS: frozenset[str] = frozenset(
    {
        TakeoffProviderKind.MOBI_NATIVE.value,
        TakeoffProviderKind.OPEN_TAKEOFF.value,
        TakeoffProviderKind.MANUAL_IMPORT.value,
        TakeoffProviderKind.HUMAN_VERIFIED.value,
        TakeoffProviderKind.AUTHORIZED_THIRD_PARTY.value,
    }
)

ALLOWED_EVIDENCE_REVIEW_STATUSES: frozenset[str] = frozenset(
    {EvidenceReviewStatus.PENDING.value, EvidenceReviewStatus.APPROVED.value}
)

REQUIRED_EVIDENCE_CLASS = EvidenceClass.MEASURED.value

# Workflow-level blocker codes that a trade module's candidate validation does
# not know about and so cannot reconstruct on its own. Applying evidence must
# never silently clear these (mirrors app.review.service._WORKFLOW_BLOCKER_CODES).
_WORKFLOW_BLOCKER_CODES = frozenset({"customer_revision_rescope_required"})

_EVIDENCE_TYPE = "drawing_dimension"

# Flattened row columns whose value MUST reproduce the canonical ``raw_payload``
# before any of them is used to authorize an application or to map a quantity.
# Grouped by the security family each one decides, because a divergence in any
# family is independently exploitable:
#   * review/authorization: a REJECTED raw status behind an APPROVED column would
#     let unreviewed evidence through the reviewable gate;
#   * class/method: a non-measurement raw class or method behind ``measured`` /
#     ``staff_marker_tally`` would apply evidence the canonical record does not
#     support AND pick the wrong QuantityBasis;
#   * provider identity: an unsupported raw provider behind an allowed column
#     would bypass ALLOWED_TAKEOFF_PROVIDERS;
#   * quantity mapping: a divergent quantity/unit would stamp a scope item with a
#     measurement the canonical evidence never recorded;
#   * page/record identity: a divergent page or provider record id would break
#     the verified-sheet binding and the provenance trail;
#   * measurement provenance: condition/scale describe how the value was measured.
_CANONICAL_ROW_FIELD_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("review", ("review_status", "reviewed_by")),
    ("class_and_method", ("evidence_class", "measurement_method")),
    ("provider", ("takeoff_provider", "provider_record_id")),
    ("quantity", ("quantity", "unit", "confidence")),
    ("page_identity", ("page_number", "sheet_id", "document_id")),
    ("scope", ("trade", "scope_category")),
    ("measurement_provenance", ("condition", "scale")),
)


def _canonical_row_divergences(
    row: dict[str, Any], payload: dict[str, Any]
) -> list[str]:
    """Return every flattened column that diverges from the canonical payload.

    Null-safe and type-strict on purpose: ``None`` on one side only is a
    divergence, and a value whose Python type differs (a text ``"5"`` standing in
    for an integer ``5``) is a divergence too. Nothing here relies on truthiness
    or on ``str()`` coercion, so a missing key, a null, a ``0``/``""`` value, and
    a type-punned value all fail closed instead of comparing equal.
    """

    divergent: list[str] = []
    for family, columns in _CANONICAL_ROW_FIELD_FAMILIES:
        for column in columns:
            row_value = row.get(column)
            payload_value = payload.get(column)
            if row_value is None or payload_value is None:
                if row_value is None and payload_value is None:
                    continue
                divergent.append(f"{family}.{column}")
                continue
            if type(row_value) is not type(payload_value) or row_value != payload_value:
                divergent.append(f"{family}.{column}")
    return divergent


def _require_row_matches_canonical(
    evidence_row: dict[str, Any], evidence: CanonicalEvidence
) -> None:
    """Fail closed when an indexed column disagrees with the canonical payload.

    ``deserialize_canonical_evidence`` already enforces this at the store
    boundary; repeating it here keeps the guarantee local to the code that acts
    on these fields, so a future reader/loader change cannot quietly re-open the
    divergence for the authorization and quantity-mapping decisions below.
    """

    divergent = _canonical_row_divergences(evidence_row, evidence.model_dump(mode="json"))
    if divergent:
        raise WorkerApiError(
            "evidence_corrupt",
            500,
            "Canonical evidence failed integrity checks",
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, default=str, sort_keys=True)


def _loads(value: str | None) -> Any:
    if value in (None, ""):
        return None
    return json.loads(value)


def _module(trade_code: str):
    try:
        return trade_registry.get(trade_code)
    except UnknownTradeError as exc:
        raise WorkerApiError(
            "unknown_trade", 404, f"Trade '{trade_code}' is not registered"
        ) from exc


def _resolve_quantity_basis(raw: Any) -> QuantityBasis:
    try:
        return QuantityBasis(raw)
    except ValueError:
        return QuantityBasis.UNKNOWN


def _require_same_identity(
    actor_identity: dict[str, str], row: sqlite3.Row | dict[str, Any], *, what: str, project_id_column: str = "project_id"
) -> None:
    try:
        target = {
            "tenant_id": row["tenant_id"],
            "company_id": row["company_id"],
            "project_id": row[project_id_column],
        }
        assert_same_tenant_project_access(actor_identity, target)
    except (KeyError, PermissionError) as exc:
        raise WorkerApiError(
            "forbidden", 403, f"{what} is not accessible in this tenant/company/project scope"
        ) from exc


def _public_scope_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "quantity": row.get("quantity"),
        "unit": row.get("unit"),
        "quantity_basis": row.get("quantity_basis"),
        "review_status": row.get("review_status"),
        "conflict_status": row.get("conflict_status"),
        "blocking_issues": _loads(row.get("blocking_issues")) or [],
    }


def _revalidate_preserving_workflow_blockers(
    conn: sqlite3.Connection,
    module: Any,
    item: dict[str, Any],
    ctx: CandidateContext,
    *,
    identity: dict[str, str],
) -> tuple[list[dict[str, Any]], str]:
    """Rerun trade validation + conflict detection without clearing workflow blockers.

    Mirrors ``app.review.service._revalidate`` but operates on the caller's open
    transaction ``conn`` instead of opening a fresh connection, so it can see the
    evidence reference just inserted in this same transaction.
    """

    validation = module.validate_candidate(ctx)
    blocking_issues = [bi.model_dump() for bi in validation.blocking_issues]

    existing_codes = {issue.get("code") for issue in blocking_issues}
    for issue in item.get("blocking_issues") or []:
        if isinstance(issue, dict) and issue.get("code") in _WORKFLOW_BLOCKER_CODES and issue.get("code") not in existing_codes:
            blocking_issues.append(issue)
            existing_codes.add(issue.get("code"))

    conn.execute(
        "DELETE FROM conflicts WHERE scope_item_id=? AND tenant_id=? AND company_id=?",
        (item["id"], identity["tenant_id"], identity["company_id"]),
    )
    conflicts = module.detect_conflicts(ctx, [])
    has_blocking_conflict = False
    now = _now()
    for conflict in conflicts:
        row = conflict.model_dump(mode="json")
        conn.execute(
            """
            INSERT INTO conflicts (id, scope_item_id, tenant_id, company_id, code,
                severity, description, competing_evidence, resolution_status,
                created_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, NULL)
            """,
            (
                str(uuid4()), item["id"], identity["tenant_id"], identity["company_id"],
                row["code"], row["severity"], row["description"],
                _dumps(row.get("competing_evidence", [])), now,
            ),
        )
        if row["severity"] == "blocking":
            has_blocking_conflict = True

    has_blocking = bool(blocking_issues) or has_blocking_conflict
    status = "blocking" if has_blocking else ("warning" if conflicts else "none")
    return blocking_issues, status


def apply_canonical_evidence_to_scope_item(
    *,
    tenant_id: str,
    company_id: str,
    project_id: UUID,
    scope_item_id: UUID,
    evidence_id: UUID,
    actor: WorkerActor,
    reviewer_id: str,
    reviewer_notes: str | None,
) -> dict[str, Any]:
    # The persisted reviewer/applier identity is the authenticated actor and
    # nothing else. The router already rejects a mismatching body ``reviewer_id``;
    # re-asserting it here means no future caller can pass an arbitrary reviewer
    # string into ``reviewed_by`` / ``applied_by`` / the review event.
    if not reviewer_id or reviewer_id != actor.actor_id:
        raise WorkerApiError(
            "reviewer_identity_mismatch",
            403,
            "reviewer_id must match the authenticated actor",
        )

    identity = build_tenant_project_context(
        tenant_id=tenant_id, company_id=company_id, project_id=str(project_id)
    )

    with database.get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            project = conn.execute(
                "SELECT * FROM projects WHERE id=?", (str(project_id),)
            ).fetchone()
            if project is None:
                raise WorkerApiError("project_not_found", 404, "Project not found")
            _require_same_identity(identity, project, what="Project", project_id_column="id")

            scope_row = conn.execute(
                "SELECT * FROM scope_items WHERE id=? AND project_id=?",
                (str(scope_item_id), str(project_id)),
            ).fetchone()
            if scope_row is None:
                raise WorkerApiError("scope_item_not_found", 404, "Scope item not found")
            _require_same_identity(identity, scope_row, what="Scope item")
            scope_item = dict(scope_row)
            for key in ("raw_quantity_inputs", "blocking_issues", "assumptions", "exclusions",
                        "trade_data", "original_provider_candidate"):
                scope_item[key] = _loads(scope_item.get(key))

            evidence_row = conn.execute(
                f"SELECT * FROM {CANONICAL_EVIDENCE_TABLE} WHERE evidence_id=?",
                (str(evidence_id),),
            ).fetchone()
            if evidence_row is None:
                raise WorkerApiError("evidence_not_found", 404, "Canonical evidence not found")
            evidence_row = dict(evidence_row)
            # Requirement: canonical evidence tenant/company/project must match
            # BOTH the scope item and the request project -- a mismatch on any
            # of the three is denied before any other evidence field is trusted.
            _require_same_identity(identity, evidence_row, what="Canonical evidence")
            if str(evidence_row["project_id"]) != str(scope_item["project_id"]):
                raise WorkerApiError(
                    "forbidden", 403, "Canonical evidence project does not match the scope item's project"
                )

            try:
                evidence: CanonicalEvidence = deserialize_canonical_evidence(evidence_row)
            except ValueError as exc:
                raise WorkerApiError("evidence_corrupt", 500, "Canonical evidence failed integrity checks") from exc

            # Nothing below may read a flattened column until it has been proven
            # to reproduce the canonical payload exactly. Authorization and
            # quantity mapping then read the CANONICAL record, so the raw payload
            # is the single source of truth for both.
            _require_row_matches_canonical(evidence_row, evidence)

            if evidence.review_status not in ALLOWED_EVIDENCE_REVIEW_STATUSES:
                raise WorkerApiError(
                    "evidence_not_reviewable",
                    422,
                    "Canonical evidence must be pending or approved to be applied",
                )
            if evidence.evidence_class != REQUIRED_EVIDENCE_CLASS:
                raise WorkerApiError(
                    "unsupported_evidence_class",
                    422,
                    "Only measured canonical evidence can be applied to a scope item",
                )
            if evidence.measurement_method not in MEASUREMENT_METHOD_QUANTITY_BASIS:
                raise WorkerApiError(
                    "unsupported_measurement_method",
                    422,
                    "Unsupported takeoff measurement method for scope-item application",
                )
            if evidence.takeoff_provider not in ALLOWED_TAKEOFF_PROVIDERS:
                raise WorkerApiError(
                    "unsupported_provider", 422, "Unsupported takeoff provider for scope-item application"
                )

            quantity = evidence.quantity
            if quantity is None or not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity <= 0:
                raise WorkerApiError("invalid_quantity", 422, "Canonical evidence quantity must be positive and finite")
            unit_value = evidence.unit
            if not unit_value or not is_unit(unit_value):
                raise WorkerApiError("invalid_unit", 422, "Canonical evidence unit is missing or unrecognized")

            sheet_row = conn.execute(
                "SELECT * FROM sheets WHERE id=? AND project_id=?",
                (str(evidence.sheet_id), str(project_id)),
            ).fetchone()
            if sheet_row is None:
                raise WorkerApiError("sheet_not_found", 422, "Evidence sheet_id does not reference a project sheet")
            _require_same_identity(identity, sheet_row, what="Sheet")
            sheet = dict(sheet_row)
            if str(sheet.get("review_status") or "").lower() != "verified" or not sheet.get("verified_sheet_number"):
                raise WorkerApiError("sheet_not_verified", 422, "Evidence sheet is not staff-verified")
            if int(sheet.get("pdf_page_number") or 0) != int(evidence.page_number):
                raise WorkerApiError(
                    "sheet_page_mismatch", 422, "Evidence page_number does not match the verified sheet's page"
                )

            existing_link = conn.execute(
                "SELECT * FROM canonical_evidence_scope_links WHERE evidence_id=?",
                (str(evidence_id),),
            ).fetchone()
            if existing_link is not None:
                if str(existing_link["scope_item_id"]) != str(scope_item_id):
                    raise WorkerApiError(
                        "evidence_already_linked",
                        409,
                        "Canonical evidence is already linked to a different scope item",
                    )
                # Idempotent retry: everything above still validated cleanly, but
                # this (evidence, scope item) pair was already applied. Read the
                # current committed state and make no further writes.
                current_scope = conn.execute(
                    "SELECT * FROM scope_items WHERE id=?", (str(scope_item_id),)
                ).fetchone()
                conn.rollback()
                # Reported provenance comes from the canonical record verified
                # above -- never re-read from the flattened columns, which have
                # no independent authority.
                return {
                    "applied": True,
                    "idempotent": True,
                    "project_id": str(project_id),
                    "scope_item_id": str(scope_item_id),
                    "evidence_id": str(evidence_id),
                    "evidence_reference_id": existing_link["evidence_reference_id"],
                    "evidence_review_status": evidence.review_status,
                    "scope_item": _public_scope_item(dict(current_scope)),
                    "provenance": {
                        "takeoff_provider": evidence.takeoff_provider,
                        "measurement_method": evidence.measurement_method,
                        "verified_sheet_number": sheet.get("verified_sheet_number"),
                        "page_number": evidence.page_number,
                        "provider_record_id": evidence.provider_record_id,
                    },
                }

            # -- Fresh application: mutate everything in this one transaction. --
            now = _now()
            new_quantity_basis = MEASUREMENT_METHOD_QUANTITY_BASIS[evidence.measurement_method]
            evidence_reference_id = str(uuid4())

            conn.execute(
                """
                INSERT INTO evidence_references (id, scope_item_id, project_id, tenant_id,
                    company_id, sheet_id, pdf_page_number, verified_sheet_number,
                    evidence_type, description, extracted_text_quote, text_block_coords,
                    page_region_coords, source_artifact_ref, provider_confidence,
                    requires_human_verification, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, 0, ?, ?)
                """,
                (
                    evidence_reference_id, str(scope_item_id), str(project_id),
                    identity["tenant_id"], identity["company_id"], str(evidence.sheet_id),
                    int(sheet["pdf_page_number"]), sheet["verified_sheet_number"],
                    _EVIDENCE_TYPE, evidence.description,
                    _dumps(list(evidence.region_coordinates)) if evidence.region_coordinates else None,
                    f"canonical_takeoff_evidence:{evidence_id}",
                    float(evidence.confidence) if evidence.confidence is not None else None,
                    now, now,
                ),
            )

            approved_evidence = evidence.model_copy(
                update={
                    "review_status": EvidenceReviewStatus.APPROVED.value,
                    "reviewed_by": reviewer_id,
                }
            )
            approved_row = serialize_canonical_evidence(approved_evidence)
            approved_row["updated_at"] = now
            conn.execute(
                f"""
                UPDATE {CANONICAL_EVIDENCE_TABLE}
                SET review_status=?, reviewed_by=?, raw_payload=?, updated_at=?
                WHERE evidence_id=? AND tenant_id=? AND company_id=? AND project_id=?
                """,
                (
                    approved_row["review_status"], approved_row["reviewed_by"], approved_row["raw_payload"],
                    approved_row["updated_at"], str(evidence_id), identity["tenant_id"],
                    identity["company_id"], str(project_id),
                ),
            )

            raw_quantity_inputs = {
                "source": "canonical_takeoff_evidence",
                "evidence_id": str(evidence_id),
                "sheet_id": str(evidence.sheet_id),
                "verified_sheet_number": sheet["verified_sheet_number"],
                "page_number": evidence.page_number,
                "takeoff_provider": evidence.takeoff_provider,
                "measurement_method": evidence.measurement_method,
                "provider_record_id": evidence.provider_record_id,
                "applied_by": reviewer_id,
                "applied_at": now,
            }

            evidence_count_row = conn.execute(
                "SELECT COUNT(*) FROM evidence_references WHERE scope_item_id=? AND tenant_id=? AND company_id=? AND project_id=?",
                (str(scope_item_id), identity["tenant_id"], identity["company_id"], str(project_id)),
            ).fetchone()
            module = _module(scope_item["trade_code"])
            ctx = CandidateContext(
                category_code=scope_item["category_code"],
                description=scope_item["description"],
                location=scope_item.get("location"),
                quantity_basis=_resolve_quantity_basis(new_quantity_basis),
                quantity_value=quantity,
                unit=unit_value,
                raw_quantity_inputs=raw_quantity_inputs,
                trade_data=scope_item.get("trade_data") or {},
                evidence_count=int(evidence_count_row[0]),
                confidence=scope_item.get("extraction_confidence"),
            )
            blocking_issues, conflict_status = _revalidate_preserving_workflow_blockers(
                conn, module, scope_item, ctx, identity=identity
            )
            # Never approve/correct the scope item here -- only ever move it TO
            # blocked when validation demands it. Otherwise its review_status is
            # left exactly as it was (e.g. still "blocked" on a workflow blocker).
            new_review_status = "blocked" if blocking_issues else scope_item["review_status"]

            conn.execute(
                """
                UPDATE scope_items
                SET quantity=?, unit=?, quantity_basis=?, raw_quantity_inputs=?,
                    blocking_issues=?, conflict_status=?, review_status=?, updated_at=?
                WHERE id=? AND project_id=? AND tenant_id=? AND company_id=?
                """,
                (
                    str(quantity), unit_value, new_quantity_basis, _dumps(raw_quantity_inputs),
                    _dumps(blocking_issues), conflict_status, new_review_status, now,
                    str(scope_item_id), str(project_id), identity["tenant_id"], identity["company_id"],
                ),
            )

            conn.execute(
                """
                INSERT INTO review_events (id, project_id, scope_item_id, tenant_id,
                    company_id, trade_code, action, previous_state, new_state,
                    reviewer_id, reviewer_notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()), str(project_id), str(scope_item_id), identity["tenant_id"],
                    identity["company_id"], scope_item["trade_code"], "takeoff_evidence_applied",
                    scope_item["review_status"], new_review_status, reviewer_id, reviewer_notes, now,
                ),
            )

            conn.execute(
                """
                INSERT INTO canonical_evidence_scope_links (id, evidence_id, scope_item_id,
                    project_id, tenant_id, company_id, evidence_reference_id, applied_by,
                    applied_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()), str(evidence_id), str(scope_item_id), str(project_id),
                    identity["tenant_id"], identity["company_id"], evidence_reference_id,
                    reviewer_id, now, now, now,
                ),
            )

            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            # Only the uq_canonical_evidence_scope_links_evidence unique index --
            # a concurrent apply that won the race for this evidence id -- is a
            # 409. Any OTHER integrity failure (NOT NULL, foreign key, a
            # different unique index) is a real defect and must NOT be
            # mislabelled as "already linked"; it propagates as a 500 so the
            # failure stays visible instead of looking like benign contention.
            if "UNIQUE constraint failed: canonical_evidence_scope_links.evidence_id" not in str(exc):
                raise
            raise WorkerApiError(
                "evidence_already_linked",
                409,
                "Canonical evidence is already linked to a different scope item",
            ) from exc
        except WorkerApiError:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise

    return {
        "applied": True,
        "idempotent": False,
        "project_id": str(project_id),
        "scope_item_id": str(scope_item_id),
        "evidence_id": str(evidence_id),
        "evidence_reference_id": evidence_reference_id,
        "evidence_review_status": EvidenceReviewStatus.APPROVED.value,
        "scope_item": {
            "id": str(scope_item_id),
            "quantity": str(quantity),
            "unit": unit_value,
            "quantity_basis": new_quantity_basis,
            "review_status": new_review_status,
            "conflict_status": conflict_status,
            "blocking_issues": blocking_issues,
        },
        "provenance": {
            "takeoff_provider": evidence.takeoff_provider,
            "measurement_method": evidence.measurement_method,
            "verified_sheet_number": sheet["verified_sheet_number"],
            "page_number": evidence.page_number,
            "provider_record_id": evidence.provider_record_id,
        },
    }
