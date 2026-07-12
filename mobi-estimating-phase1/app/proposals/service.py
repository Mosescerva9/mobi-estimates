"""Proposal orchestration: build from an APPROVED estimate, issue, accept/decline,
regenerate. Client-facing content shows sell prices + scope only — never internal
cost buildup, margins, rates, or labor hours.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app import pricing_db, proposals_db
from app.capability_registry import (
    classify_supported_scope,
    evaluate_delivery_lock,
    has_test_only_metadata,
    is_test_only_source,
)
from app.pricing.service import compute_estimate_rollup
from app.proposals.allocation import allocate_proportionally
from app.proposals.schemas import ProposalVersionStatus
from app.trades.registry import trade_registry

_TEST_ONLY_METADATA_KEYS = (
    "internal_testing_only",
    "test_only",
    "testing_only",
    "fixture_only",
    "synthetic_only",
)

_IMMUTABLE_STATES = {
    ProposalVersionStatus.ISSUED.value, ProposalVersionStatus.ACCEPTED.value,
    ProposalVersionStatus.DECLINED.value, ProposalVersionStatus.SUPERSEDED.value,
    ProposalVersionStatus.EXPIRED.value,
}


class ProposalError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _d(value: Any) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else Decimal("0")


def _trade_name(code: str) -> str:
    if trade_registry.is_registered(code):
        return trade_registry.get(code).trade_name
    return code


def _resolve_approved_version(project_id: UUID, estimate_id: UUID,
                              estimate_version_id: UUID | None) -> dict:
    if pricing_db.get_estimate(project_id, estimate_id) is None:
        raise ProposalError("estimate_not_found", "Estimate not found")
    versions = pricing_db.list_estimate_versions(estimate_id)
    if estimate_version_id is not None:
        match = next((v for v in versions if v["id"] == str(estimate_version_id)), None)
        if match is None:
            raise ProposalError("estimate_version_not_found", "Estimate version not found")
        if match["status"] != "approved":
            raise ProposalError("estimate_not_approved",
                                "A proposal can only be built from an approved estimate version")
        chosen = match
    else:
        approved = [v for v in versions if v["status"] == "approved"]
        if not approved:
            raise ProposalError("no_approved_version",
                                "The estimate has no approved version to build a proposal from")
        chosen = sorted(approved, key=lambda v: v["version_number"])[-1]
    # Return the fully-decoded version (JSON list columns parsed).
    return pricing_db.get_estimate_version(chosen["id"])


def _delivery_lock_for_estimate_version(estimate_version: dict) -> dict[str, Any]:
    """Evaluate the final-customer-delivery lock for a proposal source version.

    Proposals and proposal exports are customer-facing estimate delivery surfaces,
    so they must use the same fail-closed lock as the readiness endpoint. There is
    intentionally no owner-approval persistence path in this P0 slice; therefore
    even an internally approved/priced estimate remains locked until a future,
    explicit owner-approval workflow is added.
    """
    line_items = pricing_db.get_line_items(estimate_version["id"])
    scope_items = [
        {
            "id": line.get("scope_item_id"),
            "trade_code": line.get("trade_code"),
            "category_code": line.get("category_code"),
        }
        for line in line_items
    ]
    supported_scope = classify_supported_scope(scope_items)
    delivery_sources: list[dict[str, Any]] = []
    for line in line_items:
        for component in line.get("components") or []:
            if not isinstance(component, dict):
                delivery_sources.append({
                    "scope_item_id": line.get("scope_item_id"),
                    "kind": "estimate_line_component_source",
                    "source": None,
                })
                continue
            delivery_sources.append({
                "scope_item_id": line.get("scope_item_id"),
                "kind": "estimate_line_component_source",
                "source": component.get("source") or component.get("component_source"),
                "metadata": component.get("metadata"),
                "source_metadata": component.get("source_metadata"),
                "provenance_metadata": component.get("provenance_metadata"),
                "audit_metadata": component.get("audit_metadata"),
                **{key: component.get(key) for key in _TEST_ONLY_METADATA_KEYS},
            })
        if line.get("quantity") not in (None, ""):
            delivery_sources.append({
                "scope_item_id": line.get("scope_item_id"),
                "kind": "estimate_line_quantity_source",
                "source": line.get("quantity_source") or line.get("quantity_basis"),
                "metadata": line.get("metadata"),
                "source_metadata": line.get("source_metadata"),
                "provenance_metadata": line.get("provenance_metadata"),
                "audit_metadata": line.get("audit_metadata"),
                **{key: line.get(key) for key in _TEST_ONLY_METADATA_KEYS},
            })

    evidence_complete = _line_items_have_complete_delivery_evidence(line_items)
    expected_scope_item_ids = [line.get("scope_item_id") for line in line_items]
    return evaluate_delivery_lock(
        evidence_complete=evidence_complete,
        required_reviews_complete=estimate_version.get("status") == "approved",
        owner_approval=None,
        delivery_sources=delivery_sources,
        supported_scope=supported_scope["supported_scope"],
        unsupported_scope=supported_scope,
        expected_scope_item_count=len(line_items),
        expected_scope_item_ids=expected_scope_item_ids,
    )


def _line_items_have_complete_delivery_evidence(line_items: list[dict[str, Any]]) -> bool:
    """Return True only when every line has real, structured evidence.

    A non-empty evidence list is not enough for final customer delivery: fixture
    evidence, malformed evidence rows, or rows whose provenance source is a test
    harness must fail the delivery lock before a proposal/export can expose final
    priced content.
    """
    if not line_items:
        return False
    for line in line_items:
        evidence_rows = line.get("evidence")
        if not isinstance(evidence_rows, list) or not evidence_rows:
            return False
        for row in evidence_rows:
            if not isinstance(row, dict):
                return False
            if has_test_only_metadata(row):
                return False
            if is_test_only_source(row.get("source")):
                return False
    return True


def _enforce_customer_delivery_lock(estimate_version: dict, *, action: str) -> None:
    delivery_lock = _delivery_lock_for_estimate_version(estimate_version)
    if delivery_lock["delivery_unlocked"]:
        return
    reasons = "; ".join(delivery_lock.get("reasons") or ["Customer delivery lock is closed."])
    raise ProposalError(
        "delivery_locked",
        f"Customer-facing proposal {action} is locked by the final delivery gate: {reasons}",
    )


def assert_proposal_version_exportable(
    project_id: UUID,
    proposal_id: UUID | str,
    version_id: str,
    *,
    action: str,
) -> None:
    """Fail closed before returning or exporting customer-visible proposal lines."""
    version = _require_version(project_id, proposal_id, version_id)
    estimate_version = pricing_db.get_estimate_version(version["estimate_version_id"])
    if estimate_version is None:
        raise ProposalError("estimate_version_not_found", "Estimate version not found")
    _enforce_customer_delivery_lock(estimate_version, action=action)


def _build_content(estimate_version: dict, *, detail_level: str) -> tuple[list[dict], Decimal]:
    """Return (proposal_line_items, total_sell_price). Sell prices are allocated from
    the estimate's final sell price in proportion to direct cost (largest-remainder)."""
    version_id = estimate_version["id"]
    rollup = compute_estimate_rollup(version_id)
    total_sell = _d(rollup["totals"]["final_sell_price"])
    est_lines = pricing_db.get_line_items(version_id)

    if detail_level == "summary":
        return ([{"section": "Project", "description": "Total project scope",
                  "sell_price": total_sell}], total_sell)

    if detail_level == "trade":
        by_trade: dict[str, Decimal] = {}
        order: list[str] = []
        for li in est_lines:
            code = li.get("trade_code") or "other"
            if code not in by_trade:
                by_trade[code] = Decimal("0")
                order.append(code)
            by_trade[code] += _d(li.get("direct_cost_total"))
        weights = [by_trade[c] for c in order]
        sells = allocate_proportionally(total_sell, weights)
        lines = [{"section": _trade_name(code), "trade_code": code,
                  "description": f"{_trade_name(code)} scope", "sell_price": sell}
                 for code, sell in zip(order, sells)]
        return lines, total_sell

    # line-level
    weights = [_d(li.get("direct_cost_total")) for li in est_lines]
    sells = allocate_proportionally(total_sell, weights)
    lines = [{"section": _trade_name(li.get("trade_code") or "other"),
              "trade_code": li.get("trade_code"), "category_code": li.get("category_code"),
              "description": li.get("description"), "location": li.get("location"),
              "quantity": li.get("quantity"), "unit": li.get("unit"), "sell_price": sell}
             for li, sell in zip(est_lines, sells)]
    return lines, total_sell


def create_proposal(project_id: UUID, data: dict[str, Any]) -> dict[str, Any]:
    est_version = _resolve_approved_version(
        project_id, UUID(str(data["estimate_id"])),
        UUID(str(data["estimate_version_id"])) if data.get("estimate_version_id") else None)
    _enforce_customer_delivery_lock(est_version, action="creation")

    proposal = proposals_db.create_proposal(project_id, {
        "estimate_id": data["estimate_id"], "name": data["name"],
        "client_name": data["client_name"]})

    lines, total = _build_content(est_version, detail_level=data.get("detail_level", "trade"))
    version = proposals_db.create_version(
        UUID(proposal["id"]), project_id, {
            "estimate_version_id": est_version["id"], "version_number": 1,
            "prepared_by": data.get("prepared_by"), "client_name": data["client_name"],
            "client_contact": data.get("client_contact"),
            "valid_until": data.get("valid_until"),
            "detail_level": data.get("detail_level", "trade"),
            "currency": est_version.get("currency", "USD"), "total_sell_price": total,
            "cover_notes": data.get("cover_notes", ""), "terms": data.get("terms", ""),
            "inclusions": (est_version.get("inclusions") or []) + data.get("extra_inclusions", []),
            "exclusions": (est_version.get("exclusions") or []) + data.get("extra_exclusions", []),
            "assumptions": (est_version.get("assumptions") or []) + data.get("extra_assumptions", []),
            "clarifications": (est_version.get("clarifications") or []) + data.get("extra_clarifications", []),
        }, lines)
    return {"proposal": proposal, "version": version}


def _snapshot(version: dict, lines: list[dict]) -> tuple[str, str]:
    payload = {
        "proposal_version": {k: version.get(k) for k in (
            "id", "proposal_id", "version_number", "estimate_version_id",
            "detail_level", "currency", "total_sell_price", "client_name",
            "client_contact", "prepared_by", "valid_until", "cover_notes", "terms",
            "inclusions", "exclusions", "assumptions", "clarifications")},
        "line_items": [{k: li.get(k) for k in (
            "section", "trade_code", "category_code", "description", "location",
            "quantity", "unit", "sell_price")} for li in lines],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def issue(
    project_id: UUID,
    proposal_id: UUID | str,
    version_id: str,
    *,
    proposal_number: str | None,
    actor: str,
) -> dict[str, Any]:
    version = _require_version(project_id, proposal_id, version_id)
    estimate_version = pricing_db.get_estimate_version(version["estimate_version_id"])
    if estimate_version is None:
        raise ProposalError("estimate_version_not_found", "Estimate version not found")
    _enforce_customer_delivery_lock(estimate_version, action="issue")
    if version["status"] != ProposalVersionStatus.DRAFT.value:
        raise ProposalError("not_draft", "Only a draft proposal version can be issued")
    number = proposal_number or _auto_number(version)
    lines = proposals_db.get_line_items(project_id, proposal_id, version_id)
    updated = proposals_db.update_version(project_id, proposal_id, version_id, {
        "status": ProposalVersionStatus.ISSUED.value, "proposal_number": number,
        "issued_at": _now()})
    if updated is None:
        raise ProposalError("not_found", "Proposal version not found")
    snap_text, snap_hash = _snapshot(updated, lines)
    proposals_db.save_snapshot(project_id, proposal_id, version_id, snap_text, snap_hash)
    proposals_db.update_version(project_id, proposal_id, version_id, {"snapshot_hash": snap_hash})
    proposals_db.append_review_event(project_id, proposal_id, version_id, {
        "action": "issue", "previous_state": "draft",
        "new_state": ProposalVersionStatus.ISSUED.value, "actor": actor})
    issued = proposals_db.get_version(project_id, proposal_id, version_id)
    if issued is None:
        raise ProposalError("not_found", "Proposal version not found")
    return issued


def _auto_number(version: dict) -> str:
    return f"P-{version['proposal_id'][:8].upper()}-{version['version_number']:02d}"


def _client_response(project_id: UUID, proposal_id: UUID | str, version_id: str, *, new_state: str,
                     actor: str, notes: str | None, reason: str | None) -> dict[str, Any]:
    version = _require_version(project_id, proposal_id, version_id)
    assert_proposal_version_exportable(project_id, proposal_id, version_id, action=new_state)
    if version["status"] != ProposalVersionStatus.ISSUED.value:
        raise ProposalError("not_issued",
                            "Only an issued proposal can be accepted or declined")
    fields = {"status": new_state}
    if new_state == ProposalVersionStatus.ACCEPTED.value:
        fields["accepted_at"] = _now()
    else:
        fields["declined_at"] = _now()
        fields["decline_reason"] = reason
    proposals_db.update_version(project_id, proposal_id, version_id, fields)
    proposals_db.append_review_event(project_id, proposal_id, version_id, {
        "action": new_state, "previous_state": "issued", "new_state": new_state,
        "actor": actor, "notes": notes or reason})
    updated = proposals_db.get_version(project_id, proposal_id, version_id)
    if updated is None:
        raise ProposalError("not_found", "Proposal version not found")
    return updated


def accept(project_id: UUID, proposal_id: UUID | str, version_id: str, *, actor: str, notes: str) -> dict:
    return _client_response(project_id, proposal_id, version_id,
                            new_state=ProposalVersionStatus.ACCEPTED.value,
                            actor=actor, notes=notes, reason=None)


def decline(project_id: UUID, proposal_id: UUID | str, version_id: str, *, actor: str, reason: str) -> dict:
    if not reason or not reason.strip():
        raise ProposalError("reason_required", "A decline reason is required")
    return _client_response(project_id, proposal_id, version_id,
                            new_state=ProposalVersionStatus.DECLINED.value,
                            actor=actor, notes=None, reason=reason)


def regenerate(project_id: UUID, proposal_id: UUID, *, estimate_version_id: UUID | None,
               actor: str) -> dict[str, Any]:
    proposal = proposals_db.get_proposal(project_id, proposal_id)
    if proposal is None:
        raise ProposalError("not_found", "Proposal not found")
    versions = proposals_db.list_versions(proposal_id)
    if not versions:
        raise ProposalError("no_version", "Proposal has no version to regenerate")
    latest = versions[-1]
    est_version = _resolve_approved_version(
        project_id, UUID(proposal["estimate_id"]), estimate_version_id)
    _enforce_customer_delivery_lock(est_version, action="regeneration")
    lines, total = _build_content(est_version, detail_level=latest["detail_level"])
    prior = proposals_db.get_version(project_id, proposal_id, latest["id"])
    if prior is None:
        raise ProposalError("not_found", "Proposal version not found")
    new_version = proposals_db.create_version(
        proposal_id, project_id, {
            "estimate_version_id": est_version["id"],
            "version_number": proposals_db.next_version_number(proposal_id),
            "prepared_by": prior.get("prepared_by"), "client_name": prior.get("client_name"),
            "client_contact": prior.get("client_contact"), "valid_until": prior.get("valid_until"),
            "detail_level": prior["detail_level"], "currency": prior.get("currency", "USD"),
            "total_sell_price": total, "cover_notes": prior.get("cover_notes", ""),
            "terms": prior.get("terms", ""), "inclusions": prior.get("inclusions", []),
            "exclusions": prior.get("exclusions", []), "assumptions": prior.get("assumptions", []),
            "clarifications": prior.get("clarifications", []),
        }, lines)
    # Supersede the prior version unless a client already accepted it.
    if prior["status"] not in (ProposalVersionStatus.ACCEPTED.value,):
        proposals_db.update_version(project_id, proposal_id, latest["id"], {
            "status": ProposalVersionStatus.SUPERSEDED.value, "superseded_at": _now()})
        proposals_db.append_review_event(project_id, proposal_id, latest["id"], {
            "action": "supersede", "previous_state": prior["status"],
            "new_state": ProposalVersionStatus.SUPERSEDED.value, "actor": actor})
    return {"proposal": proposal, "version": new_version}


def get_version_public(project_id: UUID, proposal_id: UUID | str, version_id: str) -> dict[str, Any]:
    version = _require_version(project_id, proposal_id, version_id)
    # Lazily expire an issued proposal past its validity date.
    if (version["status"] == ProposalVersionStatus.ISSUED.value
            and version.get("valid_until")):
        try:
            if date.fromisoformat(str(version["valid_until"])[:10]) < date.today():
                version = proposals_db.update_version(project_id, proposal_id, version_id, {
                    "status": ProposalVersionStatus.EXPIRED.value})
                proposals_db.append_review_event(project_id, proposal_id, version_id, {
                    "action": "expire", "previous_state": "issued",
                    "new_state": ProposalVersionStatus.EXPIRED.value, "actor": "system"})
        except ValueError:
            pass
    if version is None:
        raise ProposalError("not_found", "Proposal version not found")
    return version


def _require_version(project_id: UUID, proposal_id: UUID | str, version_id: str) -> dict[str, Any]:
    version = proposals_db.get_version(project_id, proposal_id, version_id)
    if version is None:
        raise ProposalError("not_found", "Proposal version not found")
    return version
