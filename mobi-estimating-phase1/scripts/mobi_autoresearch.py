#!/usr/bin/env python3
"""Mobi AutoResearch v1: safe scoring, guardrails, and ledger helpers.

This is a local/internal tool for Karpathy-style experiment loops on top of the
Golden Set evaluator. It deliberately keeps the ground truth/evaluator locked
and makes the first loop measurable before any autonomous agent is allowed to
keep or revert changes.

V1 does **not** send customer messages, deliver estimates, process payments,
change pricing, or deploy anything. It only scores local reports, runs the local
Golden Set evaluator when requested, checks git diffs against an allowlist, and
writes JSONL experiment ledger records.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent

DEFAULT_GOLDEN_SET_V2_MANIFEST = ENGINE_ROOT / "data/golden_set_v2/manifest.real-v2.json"
DEFAULT_GOLDEN_SET_V2_REPORT = ENGINE_ROOT / "data/golden_set_v2/reports/golden_set_real_v2_report.json"

# These are the evaluator / ground-truth artifacts. In guard mode, experiments
# are rejected if any of these paths change, even if a caller accidentally puts
# them in --allowed.
LOCKED_PATHS = (
    "mobi-estimating-phase1/data/golden_set_v2/documents/",
    "mobi-estimating-phase1/data/golden_set_v2/manifest.real-v2.json",
    "mobi-estimating-phase1/data/golden_set_v2/sources.v2.json",
    "mobi-estimating-phase1/scripts/golden_set_extraction_eval.py",
)

DEFAULT_EVAL_SCRIPT = ENGINE_ROOT / "scripts/golden_set_extraction_eval.py"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON file is invalid: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _safe_number(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_rate(numerator: Any, denominator: Any, *, zero_default: float = 1.0) -> float:
    denom = _safe_number(denominator)
    if denom <= 0:
        return zero_default
    return _safe_number(numerator) / denom


def _nonnegative_int_count(value: Any) -> int | None:
    """Parse strict release-gate count evidence.

    Release promotion evidence must not coerce booleans, fractional floats,
    negative values, or missing fields into plausible counts. Numeric strings are
    allowed only when they are whole non-negative integers because reports may be
    serialized through JSON/CLI boundaries.
    """
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdecimal():
            return int(normalized)
    return None


def _normalize_marker_text(raw: Any) -> str:
    """Normalize serialized flags/logs so spaced/camelCase CLI text cannot bypass gates."""
    camel_spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(raw).strip())
    return re.sub(r"[^a-z0-9]+", "_", camel_spaced.lower()).strip("_")


def _compact_marker_text(normalized: str) -> str:
    return normalized.replace("_", "")


def _marker_text_contains(normalized: str, markers: set[str] | tuple[str, ...]) -> bool:
    compact = _compact_marker_text(normalized)
    return any(marker in normalized or _compact_marker_text(marker) in compact for marker in markers)


def _marker_key_matches(normalized_key: str, keys: set[str] | tuple[str, ...]) -> bool:
    compact = _compact_marker_text(normalized_key)
    return normalized_key in keys or compact in {_compact_marker_text(key) for key in keys}


def _value_contains_marker_text(value: Any, markers: tuple[str, ...], *, depth: int = 0) -> bool:
    """Return True when a scalar/list/object value contains any normalized marker text."""
    if depth > 8:
        return True
    if isinstance(value, str):
        return _marker_text_contains(_normalize_marker_text(value), markers)
    if isinstance(value, dict):
        return any(
            _value_contains_marker_text(key, markers, depth=depth + 1)
            or _value_contains_marker_text(child, markers, depth=depth + 1)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_value_contains_marker_text(child, markers, depth=depth + 1) for child in value)
    return False


def _value_contains_marker_token(value: Any, tokens: tuple[str, ...], *, depth: int = 0) -> bool:
    """Return True when a scalar/list/object contains a normalized provider token.

    Drawing sheet numbers can look like provider tokens (for example ``AI-501``).
    Treat standalone provider names and short model-version forms as markers, but
    do not classify sheet-like provider+large-number labels as AI provenance.
    """
    if depth > 8:
        return True
    if isinstance(value, str):
        normalized = _normalize_marker_text(value)
        if normalized in tokens:
            return True
        parts = [part for part in normalized.split("_") if part]
        for index, part in enumerate(parts):
            if part not in tokens:
                continue
            next_part = parts[index + 1] if index + 1 < len(parts) else ""
            prev_part = parts[index - 1] if index > 0 else ""
            if (next_part.isdecimal() and len(next_part) >= 3) or (prev_part.isdecimal() and len(prev_part) >= 3):
                continue
            return True
        return False
    if isinstance(value, dict):
        return any(
            _value_contains_marker_token(key, tokens, depth=depth + 1)
            or _value_contains_marker_token(child, tokens, depth=depth + 1)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_value_contains_marker_token(child, tokens, depth=depth + 1) for child in value)
    return False


def _flag_value_is_true(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes", "y"}


def _report_marks_internal_testing_only(
    value: Any,
    *,
    depth: int = 0,
    path: tuple[str, ...] = (),
    allow_release_gate_internal_labels: bool = False,
) -> bool:
    """Return True when a Golden Set report is explicitly test-only evidence.

    Release evidence must fail closed not only on structured boolean bypass flags,
    but also on serialized command arrays/log snippets that contain report-only
    switches such as ``--no-fail-on-accuracy``. Otherwise a stale wrapper could
    strip the structured flag while leaving the actual bypass command in the
    report metadata and still pass promotion validation.
    """
    if depth > 8:
        return True
    release_gate_internal_label_paths = {
        ("internal_testing_only",),
        ("manifest_metadata", "internal_testing_only"),
    }
    bypass_markers = {
        "internal_testing_only",
        "is_internal_testing_only",
        "test_only",
        "is_test_only",
        "report_only_baseline",
        "no_fail_on_accuracy",
        "accuracy_bypass",
        "accuracy_bypass_enabled",
        "allow_accuracy_failure",
        "allow_accuracy_failures",
        "accuracy_failures_allowed",
        "accuracy_failure_allowance",
        "accuracy_failures_allowance",
        "missing_document_allowance",
        "missing_documents_allowance",
        "missing_documents_allowed",
        "allow_missing_documents",
        "allowed_missing_documents",
    }

    if isinstance(value, str):
        normalized_value = _normalize_marker_text(value)
        return any(marker in normalized_value for marker in bypass_markers)
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = _normalize_marker_text(key).lstrip("_")
            child_path = (*path, normalized_key)
            if normalized_key in bypass_markers:
                if (
                    allow_release_gate_internal_labels
                    and normalized_key == "internal_testing_only"
                    and child_path in release_gate_internal_label_paths
                ):
                    continue
                if child is not False and str(child).strip().lower() not in {"", "false", "0", "no", "n"}:
                    return True
            if _report_marks_internal_testing_only(
                child,
                depth=depth + 1,
                path=child_path,
                allow_release_gate_internal_labels=allow_release_gate_internal_labels,
            ):
                return True
    elif isinstance(value, list):
        return any(
            _report_marks_internal_testing_only(
                child,
                depth=depth + 1,
                path=(*path, "[]"),
                allow_release_gate_internal_labels=allow_release_gate_internal_labels,
            )
            for child in value
        )
    return False


def _report_has_test_only_evidence_counter(value: Any, *, depth: int = 0) -> bool:
    """Reject release evidence that reports any test-only/mock quantity rows.

    ``_report_marks_internal_testing_only`` catches explicit boolean/string
    markers such as ``test_only=True`` or ``source=harness_test_only_quantity``.
    Release-gate wrappers may instead preserve only aggregate counters like
    ``test_only_quantity_count=3`` or ``mock_quantity_count=3``. Those counters
    are still proof that the run is not release evidence, so positive or
    malformed counter/contains flags fail closed while explicit zero/false values
    remain acceptable.
    """
    if depth > 8:
        return True
    counter_keys = {
        "test_only_quantity_count",
        "test_only_quantities_count",
        "test_only_evidence_count",
        "test_only_source_count",
        "test_only_sources_count",
        "test_only_delivery_source_count",
        "synthetic_quantity_count",
        "synthetic_quantities_count",
        "synthetic_evidence_count",
        "synthetic_source_count",
        "synthetic_sources_count",
        "synthetic_fixture_quantity_count",
        "synthetic_fixture_quantities_count",
        "synthetic_fixture_source_count",
        "synthetic_fixture_sources_count",
        "synthetic_fixture_evidence_count",
        "mock_quantity_count",
        "mock_quantities_count",
        "mock_evidence_count",
        "mock_source_count",
        "mock_sources_count",
        "sample_quantity_count",
        "sample_quantities_count",
        "sample_evidence_count",
        "sample_source_count",
        "sample_sources_count",
        "demo_quantity_count",
        "demo_quantities_count",
        "demo_evidence_count",
        "demo_source_count",
        "demo_sources_count",
        "placeholder_quantity_count",
        "placeholder_quantities_count",
        "placeholder_evidence_count",
        "placeholder_source_count",
        "placeholder_sources_count",
        "fixture_quantity_count",
        "fixture_quantities_count",
        "fixture_source_count",
        "fixture_sources_count",
        "fixture_evidence_count",
        "harness_test_only_quantity_count",
        "harness_test_only_evidence_count",
        "model_quantity_count",
        "model_quantities_count",
        "llm_quantity_count",
        "llm_quantities_count",
        "ai_quantity_count",
        "ai_quantities_count",
        "gpt_quantity_count",
        "gpt_quantities_count",
        "model_generated_quantity_count",
        "model_generated_quantities_count",
        "model_generated_evidence_count",
        "model_generated_source_count",
        "ai_generated_quantity_count",
        "ai_generated_quantities_count",
        "ai_generated_evidence_count",
        "ai_generated_source_count",
        "llm_evidence_count",
        "llm_source_count",
        "gpt_evidence_count",
        "gpt_source_count",
        "machine_generated_quantity_count",
        "machine_generated_quantities_count",
        "automated_quantity_count",
        "automated_quantities_count",
        "automated_generated_quantity_count",
        "automated_generated_quantities_count",
        "autogenerated_quantity_count",
        "autogenerated_quantities_count",
        "computer_generated_quantity_count",
        "computer_generated_quantities_count",
    }
    contains_keys = {
        "test_only_evidence",
        "test_only_source",
        "test_only_sources",
        "synthetic_evidence",
        "synthetic_source",
        "synthetic_sources",
        "fixture_evidence",
        "fixture_quantity",
        "fixture_quantities",
        "fixture_source",
        "fixture_sources",
        "synthetic_fixture_evidence",
        "synthetic_fixture_quantity",
        "synthetic_fixture_quantities",
        "synthetic_fixture_source",
        "synthetic_fixture_sources",
        "contains_test_only_quantities",
        "contains_test_only_evidence",
        "contains_test_only_source",
        "contains_test_only_sources",
        "contains_synthetic_quantities",
        "contains_synthetic_evidence",
        "contains_synthetic_source",
        "contains_synthetic_sources",
        "contains_fixture_quantity",
        "contains_fixture_quantities",
        "contains_fixture_evidence",
        "contains_fixture_source",
        "contains_fixture_sources",
        "contains_synthetic_fixture_quantities",
        "contains_synthetic_fixture_evidence",
        "contains_synthetic_fixture_source",
        "contains_synthetic_fixture_sources",
        "contains_mock_quantities",
        "contains_mock_evidence",
        "contains_mock_source",
        "contains_mock_sources",
        "contains_sample_quantities",
        "contains_sample_evidence",
        "contains_sample_source",
        "contains_sample_sources",
        "contains_demo_quantities",
        "contains_demo_evidence",
        "contains_demo_source",
        "contains_demo_sources",
        "contains_placeholder_quantities",
        "contains_placeholder_evidence",
        "contains_placeholder_source",
        "contains_placeholder_sources",
        "contains_llm_quantities",
        "llm_quantity",
        "llm_quantities",
        "model_quantity",
        "model_quantities",
        "model_generated_quantity",
        "model_generated_quantities",
        "model_generated_evidence",
        "model_generated_source",
        "ai_generated_quantity",
        "ai_generated_quantities",
        "ai_generated_evidence",
        "ai_generated_source",
        "llm_evidence",
        "llm_source",
        "gpt_evidence",
        "gpt_source",
        "machine_generated_quantity",
        "machine_generated_quantities",
        "automated_quantity",
        "automated_quantities",
        "automated_generated_quantity",
        "automated_generated_quantities",
        "autogenerated_quantity",
        "autogenerated_quantities",
        "computer_generated_quantity",
        "computer_generated_quantities",
        "contains_model_quantity",
        "contains_model_quantities",
        "contains_model_generated_quantity",
        "contains_model_generated_quantities",
        "contains_model_generated_evidence",
        "contains_model_generated_source",
        "contains_ai_generated_quantity",
        "contains_ai_generated_quantities",
        "contains_ai_generated_evidence",
        "contains_ai_generated_source",
        "contains_llm_evidence",
        "contains_llm_source",
        "contains_gpt_evidence",
        "contains_gpt_source",
        "contains_machine_generated_quantity",
        "contains_machine_generated_quantities",
        "contains_automated_quantity",
        "contains_automated_quantities",
        "contains_automated_generated_quantity",
        "contains_automated_generated_quantities",
        "contains_autogenerated_quantity",
        "contains_autogenerated_quantities",
        "contains_computer_generated_quantity",
        "contains_computer_generated_quantities",
        "has_test_only_quantities",
        "has_test_only_evidence",
        "has_test_only_source",
        "has_test_only_sources",
        "has_synthetic_quantities",
        "has_synthetic_evidence",
        "has_synthetic_source",
        "has_synthetic_sources",
        "has_fixture_quantity",
        "has_fixture_quantities",
        "has_fixture_evidence",
        "has_fixture_source",
        "has_fixture_sources",
        "has_synthetic_fixture_quantities",
        "has_synthetic_fixture_evidence",
        "has_synthetic_fixture_source",
        "has_synthetic_fixture_sources",
        "has_mock_quantities",
        "has_mock_evidence",
        "has_mock_source",
        "has_mock_sources",
        "has_sample_quantities",
        "has_sample_evidence",
        "has_sample_source",
        "has_sample_sources",
        "has_demo_quantities",
        "has_demo_evidence",
        "has_demo_source",
        "has_demo_sources",
        "has_placeholder_quantities",
        "has_placeholder_evidence",
        "has_placeholder_source",
        "has_placeholder_sources",
        "has_llm_quantities",
        "has_llm_evidence",
        "has_llm_source",
        "has_gpt_evidence",
        "has_gpt_source",
        "has_model_quantity",
        "has_model_quantities",
        "has_model_generated_quantity",
        "has_model_generated_quantities",
        "has_model_generated_evidence",
        "has_model_generated_source",
        "has_ai_generated_quantity",
        "has_ai_generated_quantities",
        "has_ai_generated_evidence",
        "has_ai_generated_source",
        "has_machine_generated_quantity",
        "has_machine_generated_quantities",
        "has_automated_quantity",
        "has_automated_quantities",
        "has_automated_generated_quantity",
        "has_automated_generated_quantities",
        "has_autogenerated_quantity",
        "has_autogenerated_quantities",
        "has_computer_generated_quantity",
        "has_computer_generated_quantities",
    }
    evidence_markers = (
        "test_only",
        "synthetic",
        "mock",
        "sample",
        "demo",
        "placeholder",
        "fixture",
        "fixtures",
        "dummy",
        "fake",
        "stub",
        "toy",
    )
    model_quantity_markers = (
        "llm",
        "large_language_model",
        "model_generated",
        "ai_generated",
        "machine_generated",
        "automated_quantity",
        "automated_quantities",
        "automated_takeoff",
        "automated_measurement",
        "automated_generated",
        "autogenerated",
        "computer_generated",
    )
    provider_tokens = (
        "ai",
        "gpt",
        "chatgpt",
        "openai",
        "claude",
        "anthropic",
        "gemini",
        "llama",
        "mistral",
    )
    lineage_model_type_keys = {
        "type",
        "kind",
        "source_type",
        "provenance_type",
        "origin_type",
        "generator_type",
        "lineage_type",
        "provider",
        "provider_name",
        "model_provider",
        "created_by",
        "generated_by",
    }
    lineage_model_values = (
        "model",
        "language_model",
        "large_language_model",
        "llm",
        "ai",
        "gpt",
        "model_generated",
        "ai_generated",
        "machine_generated",
        "automated_generated",
        "autogenerated",
        "computer_generated",
    )
    provenance_profile_keys = (
        "dataset",
        "corpus",
        "profile",
        "report_profile",
        "benchmark_profile",
        "benchmark_corpus",
        "evidence_set",
        "source_set",
        "quantity_set",
    )

    def lineage_object_marks_model_quantity(child: Any, *, depth: int = 0) -> bool:
        """Detect nested source/provenance objects that identify generated quantity evidence."""
        if depth > 8:
            return True
        if isinstance(child, dict):
            for raw_key, raw_value in child.items():
                normalized_child_key = _normalize_marker_text(raw_key).lstrip("_")
                if normalized_child_key in lineage_model_type_keys and (
                    _normalize_marker_text(raw_value) in lineage_model_values
                    or _value_contains_marker_text(raw_value, model_quantity_markers)
                    or _value_contains_marker_token(raw_value, provider_tokens)
                ):
                    return True
                if lineage_object_marks_model_quantity(raw_value, depth=depth + 1):
                    return True
            return False
        if isinstance(child, list):
            return any(lineage_object_marks_model_quantity(item, depth=depth + 1) for item in child)
        return False

    def payload_has_explicit_model_metadata(child: Any, *, depth: int = 0) -> bool:
        """Fail closed on explicit model metadata anywhere inside a quantity row."""
        if depth > 8:
            return True
        if isinstance(child, dict):
            for raw_key, raw_value in child.items():
                normalized_child_key = _normalize_marker_text(raw_key).lstrip("_")
                if normalized_child_key in {
                    "model",
                    "model_name",
                    "model_id",
                    "model_provider",
                    "model_provider_name",
                    "model_version",
                    "model_family",
                    "model_slug",
                    "generated_by",
                    "created_by",
                }:
                    if raw_value is not False and str(raw_value).strip().lower() not in {
                        "",
                        "false",
                        "0",
                        "no",
                        "n",
                        "none",
                        "null",
                    }:
                        return True
                if payload_has_explicit_model_metadata(raw_value, depth=depth + 1):
                    return True
            return False
        if isinstance(child, list):
            return any(payload_has_explicit_model_metadata(item, depth=depth + 1) for item in child)
        return False

    if isinstance(value, dict):
        normalized_items = [(_normalize_marker_text(key).lstrip("_"), child) for key, child in value.items()]
        row_has_quantity_field = any(
            _marker_text_contains(normalized_key, ("quantity", "quantities", "takeoff", "measurement"))
            for normalized_key, _child in normalized_items
        )
        row_has_model_quantity_provenance = any(
            _marker_text_contains(
                normalized_key,
                (
                    "source",
                    "sources",
                    "evidence",
                    "provenance",
                    "origin",
                    "generator",
                    "generated_by",
                    "created_by",
                    "provider",
                    "provider_name",
                    "model",
                    "model_name",
                    "model_id",
                    "model_provider",
                    "lineage",
                    "document",
                    "documents",
                    "reference",
                    "references",
                ),
            )
            and (
                _value_contains_marker_text(child, model_quantity_markers)
                or _value_contains_marker_token(child, provider_tokens)
                or lineage_object_marks_model_quantity(child)
                or (
                    normalized_key
                    in {
                        "model",
                        "model_name",
                        "model_id",
                        "model_provider",
                        "model_provider_name",
                        "model_version",
                        "model_family",
                        "model_slug",
                    }
                    and child is not False
                    and str(child).strip().lower() not in {"", "false", "0", "no", "n", "none", "null"}
                )
                or (
                    normalized_key in {"provenance", "provenance_type", "source", "sources", "source_type", "origin", "generator"}
                    and _normalize_marker_text(child) == "model"
                )
            )
            for normalized_key, child in normalized_items
        )
        if row_has_quantity_field and (row_has_model_quantity_provenance or payload_has_explicit_model_metadata(value)):
            return True
        for normalized_key, child in normalized_items:
            marker_key = _marker_text_contains(normalized_key, evidence_markers)
            quantity_key = _marker_text_contains(normalized_key, ("quantity", "quantities"))
            evidence_key = _marker_text_contains(normalized_key, ("quantity", "quantities", "evidence", "source", "sources"))
            provenance_profile_key = _marker_text_contains(normalized_key, provenance_profile_keys)
            child_marker = _value_contains_marker_text(child, evidence_markers)
            model_quantity_marker = _value_contains_marker_text(child, model_quantity_markers)
            model_provider_marker = _value_contains_marker_token(child, provider_tokens)
            model_quantity_payload = model_quantity_marker and _value_contains_marker_text(
                child,
                ("quantity", "quantities", "takeoff", "measurement"),
            )
            if quantity_key and (model_quantity_marker or model_provider_marker):
                return True
            if (evidence_key or provenance_profile_key) and (model_quantity_payload or model_provider_marker):
                return True
            if (evidence_key or provenance_profile_key) and lineage_object_marks_model_quantity(child):
                return True
            if (
                (evidence_key or provenance_profile_key)
                and normalized_key in {"provenance", "provenance_type", "source", "sources", "source_type", "origin", "generator"}
                and _normalize_marker_text(child) == "model"
            ):
                return True
            if (evidence_key or provenance_profile_key) and child_marker:
                return True
            if marker_key and "count" in normalized_key:
                parsed = _nonnegative_int_count(child)
                if parsed is None or parsed > 0:
                    return True
            if marker_key and (evidence_key or provenance_profile_key):
                if "count" in normalized_key:
                    parsed = _nonnegative_int_count(child)
                    if parsed is None or parsed > 0:
                        return True
                elif child is not False and str(child).strip().lower() not in {"", "false", "0", "no", "n"}:
                    return True
            if _marker_key_matches(normalized_key, counter_keys):
                parsed = _nonnegative_int_count(child)
                if parsed is None or parsed > 0:
                    return True
                continue
            if _marker_key_matches(normalized_key, contains_keys):
                if child is not False and str(child).strip().lower() not in {"", "false", "0", "no", "n"}:
                    return True
                continue
            if _report_has_test_only_evidence_counter(child, depth=depth + 1):
                return True
    elif isinstance(value, list):
        return any(_report_has_test_only_evidence_counter(child, depth=depth + 1) for child in value)
    return False


def _report_marks_unsupported_scope(value: Any, *, depth: int = 0) -> bool:
    """Reject release evidence that contains explicit unsupported-scope markers.

    A release-gate report with clean aggregate counts is still not safe if a
    nested project/result row says the scope was unsupported, abstained, or not
    supported. Treat explicit unsupported/abstention markers as a hard release
    blocker so unsupported scopes cannot be promoted by a stale wrapper that only
    copies aggregate counts forward.
    """
    if depth > 8:
        return True
    unsupported_values = {
        "unsupported",
        "unsupported_scope",
        "not_supported",
        "abstain",
        "abstained",
        "abstention",
        "out_of_scope",
        "out_of_supported_scope",
        "scope_not_supported",
    }
    safe_false_values = {"", "false", "0", "no", "n", "none", "null", "supported"}
    unsupported_flag_keys = {
        "unsupported",
        "unsupported_scope",
        "not_supported",
        "contains_unsupported_scope",
        "has_unsupported_scope",
        "scope_unsupported",
        "scope_not_supported",
        "out_of_supported_scope",
        "abstain",
        "abstained",
        "abstention",
        "should_abstain",
    }
    unsupported_count_keys = {
        "unsupported_scope_count",
        "unsupported_scopes_count",
        "unsupported_scope_item_count",
        "unsupported_scope_items_count",
        "unsupported_customer_delivery_scope_count",
        "unsupported_trade_count",
        "unsupported_trades_count",
        "abstained_scope_count",
        "abstention_count",
    }
    unsupported_list_keys = {
        "unsupported_scope_items",
        "unsupported_scopes",
        "unsupported_customer_delivery_scope",
        "unsupported_customer_delivery_scope_items",
        "unsupported_trades",
        "abstained_scopes",
    }
    supported_scope_boolean_keys = {
        "supported_scope",
        "supported_customer_delivery_scope",
        "supported_delivery_scope",
        "customer_delivery_scope_supported",
    }
    scope_status_keys = {
        "status",
        "project_status",
        "delivery_status",
        "scope_status",
        "scope_classification",
        "classification",
        "supported_scope",
        "support_status",
        "release_scope_status",
    }

    if isinstance(value, str):
        normalized = _normalize_marker_text(value)
        return any(
            marker in normalized
            for marker in (
                "unsupported_scope_true",
                "unsupported_scope_yes",
                "unsupported",
                "unsupported_scope_found",
                "unsupported_scopes_found",
                "scope_status_unsupported",
                "scope_status_abstain",
                "scope_classification_unsupported",
                "scope_classification_abstain",
                "supported_scope_false",
                "supported_scope_0",
                "scope_not_supported",
                "project_not_supported",
                "not_supported",
                "project_abstained",
                "scope_abstained",
                "abstain",
                "abstained",
                "abstention",
                "should_abstain_true",
                "out_of_scope",
                "out_of_supported_scope",
                "out_of_supported_scope_true",
            )
        )
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = _normalize_marker_text(key).lstrip("_")
            normalized_child = _normalize_marker_text(child) if isinstance(child, str) else str(child).strip().lower()
            if _marker_key_matches(normalized_key, unsupported_flag_keys):
                if isinstance(child, (dict, list)):
                    return True
                elif child is not False and normalized_child not in safe_false_values:
                    return True
            if _marker_key_matches(normalized_key, unsupported_count_keys):
                parsed = _nonnegative_int_count(child)
                if parsed is None or parsed > 0:
                    return True
                continue
            if _marker_key_matches(normalized_key, unsupported_list_keys):
                if isinstance(child, list):
                    if len(child) > 0:
                        return True
                    continue
                if isinstance(child, dict):
                    if len(child) > 0:
                        return True
                    if _report_marks_unsupported_scope(child, depth=depth + 1):
                        return True
                    continue
                if child is not None and normalized_child not in safe_false_values:
                    return True
            if _marker_key_matches(normalized_key, supported_scope_boolean_keys) and child is not True:
                return True
            if _marker_key_matches(normalized_key, scope_status_keys) and normalized_child in unsupported_values:
                return True
            if _report_marks_unsupported_scope(child, depth=depth + 1):
                return True
    elif isinstance(value, list):
        # Inspect list entries individually. Joining stringified dictionaries can
        # turn safe keys such as ``unsupported_scope=False`` into substrings like
        # ``supported_scope_false`` and create false blockers.
        return any(_report_marks_unsupported_scope(child, depth=depth + 1) for child in value)
    return False


def _report_has_incomplete_document_evidence(value: Any, *, depth: int = 0) -> bool:
    """Reject release evidence with capped, partial, or missing document text.

    A release-gate aggregate can claim the eligible projects passed text
    extraction while nested project metadata still exposes page caps, truncated
    text, missing pages, or partial document extraction. Those conditions are not
    safe release evidence because complete document evidence is a P0 gate.
    """
    if depth > 8:
        return True
    safe_false_values = {"", "false", "0", "no", "n", "none", "null", "complete"}
    incomplete_flag_keys = {
        "document_text_truncated",
        "document_text_incomplete",
        "text_extraction_truncated",
        "text_extraction_incomplete",
        "source_text_truncated",
        "source_text_incomplete",
        "partial_document_text",
        "contains_partial_document_text",
        "has_partial_document_text",
        "page_cap_exceeded",
        "page_limit_exceeded",
        "extraction_cap_hit",
        "extraction_cap_exceeded",
        "document_cap_hit",
        "document_page_cap_hit",
        "has_missing_pages",
        "contains_missing_pages",
        "incomplete_document_set",
        "addenda_incomplete",
        "revision_incomplete",
    }
    incomplete_count_keys = {
        "document_text_truncated_count",
        "document_text_incomplete_count",
        "text_extraction_truncated_count",
        "text_extraction_incomplete_count",
        "source_text_truncated_count",
        "source_text_incomplete_count",
        "partial_document_text_count",
        "page_cap_exceeded_count",
        "page_limit_exceeded_count",
        "extraction_cap_hit_count",
        "extraction_cap_exceeded_count",
        "document_cap_hit_count",
        "document_page_cap_hit_count",
        "missing_page_count",
        "missing_pages_count",
        "skipped_page_count",
        "skipped_pages_count",
        "document_text_extraction_failure_count",
        "text_extraction_failure_count",
        "incomplete_document_set_count",
        "addenda_incomplete_count",
        "revision_incomplete_count",
    }
    incomplete_list_keys = {
        "missing_pages",
        "skipped_pages",
        "missing_documents",
        "skipped_documents",
        "incomplete_documents",
        "partial_document_text_items",
        "text_extraction_failures",
        "document_text_extraction_failures",
    }
    incomplete_status_keys = {
        "document_text_status",
        "text_extraction_status",
        "source_text_status",
        "document_status",
        "document_set_status",
        "addenda_status",
        "revision_status",
    }
    incomplete_status_values = {
        "truncated",
        "incomplete",
        "partial",
        "capped",
        "cap_hit",
        "cap_exceeded",
        "page_cap_exceeded",
        "missing_pages",
        "missing_documents",
        "source_text_unavailable",
    }
    document_text_object_keys = {
        "document_text_extraction",
        "text_extraction",
        "source_text_extraction",
    }

    if isinstance(value, str):
        normalized = _normalize_marker_text(value)
        return any(
            marker in normalized
            for marker in (
                "document_text_truncated",
                "document_text_incomplete",
                "text_extraction_truncated",
                "text_extraction_incomplete",
                "source_text_truncated",
                "source_text_incomplete",
                "partial_document_text",
                "page_cap_exceeded",
                "page_limit_exceeded",
                "extraction_cap_hit",
                "extraction_cap_exceeded",
                "document_page_cap_hit",
                "missing_pages",
                "skipped_pages",
                "incomplete_document_set",
                "addenda_incomplete",
                "revision_incomplete",
                "source_text_unavailable",
            )
        )
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = _normalize_marker_text(key).lstrip("_")
            normalized_child = _normalize_marker_text(child) if isinstance(child, str) else str(child).strip().lower()
            if _marker_key_matches(normalized_key, incomplete_flag_keys):
                if isinstance(child, (dict, list)):
                    return True
                if child is not False and normalized_child not in safe_false_values:
                    return True
                continue
            if _marker_key_matches(normalized_key, incomplete_count_keys):
                parsed = _nonnegative_int_count(child)
                if parsed is None or parsed > 0:
                    return True
                continue
            if _marker_key_matches(normalized_key, incomplete_list_keys):
                if isinstance(child, (list, dict)):
                    if len(child) > 0:
                        return True
                    continue
                if child is not None and normalized_child not in safe_false_values:
                    return True
            if _marker_key_matches(normalized_key, document_text_object_keys) and isinstance(child, dict):
                extraction_ok = child.get("ok")
                if extraction_ok is not None and extraction_ok is not True:
                    return True
                extraction_status = child.get("status")
                if extraction_status is not None and _normalize_marker_text(extraction_status) != "pass":
                    return True
            if _marker_key_matches(normalized_key, incomplete_status_keys) and normalized_child in incomplete_status_values:
                return True
            if _report_has_incomplete_document_evidence(child, depth=depth + 1):
                return True
    elif isinstance(value, list):
        return any(_report_has_incomplete_document_evidence(child, depth=depth + 1) for child in value)
    return False


def _report_has_customer_delivery_exposure_marker(value: Any, *, depth: int = 0) -> bool:
    """Reject release evidence that looks like customer/final estimate exposure.

    Release-gate reports are internal benchmark evidence. They must not double as
    proof that an estimate/proposal is ready for customer delivery, because final
    construction estimate exposure is separately locked behind complete evidence,
    supported scope, required reviews, and explicit owner approval.
    """
    if depth > 8:
        return True
    delivery_ready_keys = {
        "customer_delivery_ready",
        "customer_facing_ready",
        "customer_ready",
        "ready_for_customer",
        "ready_for_customer_delivery",
        "final_delivery_ready",
        "final_estimate_ready",
        "estimate_delivery_ready",
        "proposal_delivery_ready",
        "proposal_ready_for_customer",
        "customer_facing",
        "customer_facing_delivery",
        "customer_estimate_exported",
        "final_estimate_exported",
        "final_estimate_approved",
        "final_estimate_approval",
        "final_delivery_approval",
        "owner_approved_final_delivery",
        "owner_approval_scope",
        "customer_delivery_approved",
        "approved_for_customer_delivery",
        "customer_delivery",
        "estimate_exported_to_customer",
        "proposal_exported_to_customer",
        "sent_to_customer",
        "issued_to_customer",
        "delivered_to_customer",
        "delivery_unlocked",
        "customer_delivery_unlocked",
        "final_customer_delivery_enabled",
    }
    delivery_status_keys = {
        "delivery_status",
        "estimate_status",
        "proposal_status",
        "customer_delivery_status",
        "final_delivery_status",
        "customer_delivery_gate",
        "final_delivery_gate",
    }
    delivery_status_values = {
        "ready_for_customer",
        "ready_for_customer_delivery",
        "customer_delivery_ready",
        "customer_ready",
        "final_delivery_ready",
        "final_estimate_ready",
        "final_estimate_delivered",
        "delivered_to_customer",
        "customer_delivered",
        "customer_facing",
        "sent_to_customer",
        "issued_to_customer",
        "exported_to_customer",
        "estimate_sent_to_customer",
        "estimate_issued_to_customer",
        "estimate_exported_to_customer",
        "approved_for_customer_delivery",
        "customer_delivery_approved",
        "final_delivery_approval_recorded",
        "final_delivery_approved",
        "owner_approved_final_delivery",
        "unlocked",
        "delivery_unlocked",
        "enabled",
    }
    safe_false_values = {"", "false", "0", "no", "n", "none", "null", "not_ready", "internal_only", "locked", "disabled"}
    supported_scope_keys = {
        "supported_customer_delivery_scope",
        "customer_delivery_scope_supported",
        "supported_delivery_scope",
    }

    if isinstance(value, str):
        normalized = _normalize_marker_text(value)
        safe_markers = (
            "not_ready_for_customer_delivery",
            "not_ready_for_customer",
            "customer_delivery_not_ready",
            "final_estimate_not_ready",
        )
        normalized_to_scan = normalized
        for safe_marker in safe_markers:
            normalized_to_scan = normalized_to_scan.replace(safe_marker, "")
        parts = {part for part in normalized_to_scan.split("_") if part}
        if (
            {"estimate", "proposal"}.intersection(parts)
            and ({"customer", "final"}.intersection(parts))
            and {
                "delivered",
                "sent",
                "issued",
                "exported",
                "facing",
                "ready",
                "approved",
                "approval",
            }.intersection(parts)
        ):
            return True
        return any(
            marker in normalized_to_scan
            for marker in (
                "customer_delivery_ready",
                "ready_for_customer_delivery",
                "ready_for_delivery_to_customer",
                "final_delivery_ready",
                "final_delivery_approval_recorded",
                "final_delivery_approved",
                "final_estimate_ready",
                "final_estimate_approved",
                "final_estimate_approval",
                "final_estimate_delivered",
                "final_estimate_sent_to_customer",
                "final_estimate_issued_to_customer",
                "final_estimate_exported_to_customer",
                "delivered_to_customer",
                "sent_to_customer",
                "issued_to_customer",
                "exported_to_customer",
                "customer_delivered_estimate",
                "customer_estimate_exported",
                "customer_facing_delivery",
                "customer_facing_ready",
                "final_estimate_customer_facing",
                "final_estimate_is_customer_facing",
                "estimate_customer_facing",
                "owner_approved_final_delivery",
                "customer_delivery_approved",
                "approved_for_customer_delivery",
            )
        )
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = _normalize_marker_text(key).lstrip("_")
            normalized_child = _normalize_marker_text(child) if isinstance(child, str) else str(child).strip().lower()
            if _marker_key_matches(normalized_key, supported_scope_keys):
                if _report_has_customer_delivery_exposure_marker(child, depth=depth + 1):
                    return True
                continue
            delivery_ready_key = _marker_key_matches(normalized_key, delivery_ready_keys) or _marker_text_contains(
                normalized_key, delivery_ready_keys
            )
            if delivery_ready_key:
                if isinstance(child, (dict, list)):
                    if _marker_text_contains(normalized_key, ("approval", "approved", "unlocked", "enabled")) and len(child) > 0:
                        return True
                    if _report_has_customer_delivery_exposure_marker(child, depth=depth + 1):
                        return True
                    continue
                if "count" in normalized_key:
                    parsed = _nonnegative_int_count(child)
                    if parsed is None or parsed > 0:
                        return True
                    continue
                if child is not False and normalized_child not in safe_false_values:
                    return True
            if _marker_key_matches(normalized_key, delivery_status_keys) and normalized_child in delivery_status_values:
                return True
            if _report_has_customer_delivery_exposure_marker(child, depth=depth + 1):
                return True
    elif isinstance(value, list):
        return any(_report_has_customer_delivery_exposure_marker(child, depth=depth + 1) for child in value)
    return False


def _value_has_nonempty_lineage(value: Any, *, depth: int = 0) -> bool:
    """Return True when a value carries non-empty document/source lineage."""
    if depth > 8:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, dict):
        return any(_value_has_nonempty_lineage(child, depth=depth + 1) for child in value.values())
    if isinstance(value, list):
        return any(_value_has_nonempty_lineage(child, depth=depth + 1) for child in value)
    return False


def _value_has_keyed_lineage(value: Any, keys: set[str], *, depth: int = 0) -> bool:
    """Return True when nested evidence carries one of the required lineage keys."""
    if depth > 8:
        return False
    if isinstance(value, dict):
        for raw_key, child in value.items():
            normalized_key = _normalize_marker_text(raw_key).lstrip("_")
            if _marker_key_matches(normalized_key, keys) and _value_has_nonempty_lineage(child):
                return True
            if _value_has_keyed_lineage(child, keys, depth=depth + 1):
                return True
    if isinstance(value, list):
        return any(_value_has_keyed_lineage(child, keys, depth=depth + 1) for child in value)
    return False


def _report_has_quantity_without_source_lineage(value: Any, *, depth: int = 0, path: tuple[str, ...] = ()) -> bool:
    """Reject release evidence with quantity rows that lack source/document lineage.

    Aggregate counters can prove that the evaluator saw complete key-quantity
    evidence, but a stale wrapper could still attach row-level quantity payloads
    with no source document, sheet, page, region, reference, or evidence object.
    Those rows must not become promotion evidence because P0 requires every
    release quantity to remain traceable to complete evidence.
    """
    if depth > 8:
        return True
    # The top-level report aggregate contains count/rate fields such as
    # key_quantity_total; nested project aggregates may contain estimate payloads
    # and must still be scanned.
    if path == ("aggregate",):
        return False
    quantity_value_keys = {
        "quantity",
        "quantity_value",
        "measured_quantity",
        "measurement",
        "measurement_value",
        "takeoff",
        "takeoff_quantity",
        "takeoff_value",
    }
    lineage_keys = {
        "source",
        "sources",
        "source_document",
        "source_documents",
        "evidence",
        "evidence_ref",
        "evidence_refs",
        "evidence_reference",
        "evidence_references",
        "provenance",
        "lineage",
        "document",
        "document_id",
        "document_hash",
        "sheet",
        "sheet_number",
        "verified_sheet_number",
        "page",
        "page_number",
        "pdf_page_number",
        "region",
        "regions",
        "bbox",
        "bounding_box",
        "reference",
        "references",
    }
    document_lineage_keys = {
        "source_document",
        "source_documents",
        "document",
        "document_id",
        "document_hash",
        "sheet",
        "sheet_number",
        "verified_sheet_number",
        "page",
        "page_number",
        "pdf_page_number",
        "evidence",
        "evidence_ref",
        "evidence_refs",
        "evidence_reference",
        "evidence_references",
    }
    region_lineage_keys = {
        "region",
        "regions",
        "bbox",
        "bounding_box",
        "page",
        "page_number",
        "pdf_page_number",
        "reference",
        "references",
        "evidence",
        "evidence_ref",
        "evidence_refs",
        "evidence_reference",
        "evidence_references",
    }
    if isinstance(value, dict):
        normalized_items = [(_normalize_marker_text(key).lstrip("_"), child) for key, child in value.items()]
        row_has_quantity = any(
            _marker_key_matches(normalized_key, quantity_value_keys)
            and child not in (None, "")
            and not isinstance(child, bool)
            for normalized_key, child in normalized_items
        )
        if row_has_quantity:
            has_lineage = any(
                _marker_key_matches(normalized_key, lineage_keys) and _value_has_nonempty_lineage(child)
                for normalized_key, child in normalized_items
            )
            has_document_lineage = any(
                (
                    _marker_key_matches(normalized_key, document_lineage_keys)
                    and _value_has_nonempty_lineage(child)
                    and (
                        normalized_key not in {"evidence", "evidence_ref", "evidence_refs", "evidence_reference", "evidence_references"}
                        or _value_has_keyed_lineage(child, document_lineage_keys)
                    )
                )
                for normalized_key, child in normalized_items
            )
            has_region_lineage = any(
                (
                    _marker_key_matches(normalized_key, region_lineage_keys)
                    and _value_has_nonempty_lineage(child)
                    and (
                        normalized_key not in {"evidence", "evidence_ref", "evidence_refs", "evidence_reference", "evidence_references"}
                        or _value_has_keyed_lineage(child, region_lineage_keys)
                    )
                )
                for normalized_key, child in normalized_items
            )
            # P0 release evidence must be document-region traceable. A generic
            # source string or a sheet number alone can identify *where the row
            # came from* but still omit the page/detail/bbox/region needed to
            # audit the measured quantity before customer delivery.
            if not (has_lineage and has_document_lineage and has_region_lineage):
                return True
        return any(
            _report_has_quantity_without_source_lineage(child, depth=depth + 1, path=(*path, normalized_key))
            for normalized_key, child in normalized_items
        )
    if isinstance(value, list):
        return any(
            _report_has_quantity_without_source_lineage(child, depth=depth + 1, path=(*path, "[]"))
            for child in value
        )
    return False


def _report_has_non_strict_release_mode_alias(value: Any, *, depth: int = 0) -> bool:
    """Reject contradictory camelCase/nested strict-mode aliases in release evidence.

    The canonical evaluator emits ``run_mode.fail_on_accuracy=True`` and
    ``run_mode.release_gate=True``. A stale wrapper could still include a nested
    alias such as ``commandFlags.failOnAccuracy=False`` while the canonical fields
    look strict. Treat that as an accuracy-bypass marker instead of letting the
    report pass on the snake_case fields alone.
    """
    if depth > 8:
        return True
    if isinstance(value, str):
        normalized_value = _normalize_marker_text(value)
        return any(
            marker in normalized_value
            for marker in (
                "fail_on_accuracy_false",
                "fail_on_accuracy_0",
                "release_gate_false",
                "release_gate_0",
            )
        )
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = _normalize_marker_text(key).lstrip("_")
            if any(
                marker in normalized_key
                for marker in (
                    "fail_on_accuracy_false",
                    "fail_on_accuracy_0",
                    "release_gate_false",
                    "release_gate_0",
                )
            ):
                return True
            if normalized_key == "release_gate" and not _flag_value_is_true(child):
                return True
            if normalized_key == "fail_on_accuracy" and not _flag_value_is_true(child):
                return True
            if normalized_key in {"report_only_baseline", "allow_missing_documents", "no_fail_on_accuracy"} and _flag_value_is_true(child):
                return True
            if _report_has_non_strict_release_mode_alias(child, depth=depth + 1):
                return True
    elif isinstance(value, list):
        normalized_joined = _normalize_marker_text(" ".join(str(child) for child in value))
        if any(
            marker in normalized_joined
            for marker in (
                "fail_on_accuracy_false",
                "fail_on_accuracy_0",
                "release_gate_false",
                "release_gate_0",
            )
        ):
            return True
        return any(_report_has_non_strict_release_mode_alias(child, depth=depth + 1) for child in value)
    return False


def validate_release_gate_report(report: dict[str, Any]) -> dict[str, Any]:
    """Independently verify that a report can be accepted as release-gate evidence.

    The evaluator process exit code is the primary gate, but the wrapper must not
    blindly mark release evidence ok if a stale/mocked evaluator exits 0 while the
    report has zero eligible projects, missing quantity evidence, accuracy
    failures, internal test-only/report-only metadata, or inconsistent aggregate
    counts.
    """
    if not isinstance(report, dict):
        return {"ok": False, "reason": "release gate report is missing aggregate counts"}
    run_mode = report.get("run_mode")
    if not isinstance(run_mode, dict):
        return {
            "ok": False,
            "reason": "release gate report does not prove it came from a strict release-gate run",
        }
    if (
        run_mode.get("release_gate") is not True
        or run_mode.get("fail_on_accuracy") is not True
        or run_mode.get("report_only_baseline") is not False
        or run_mode.get("allow_missing_documents") is not False
    ):
        return {
            "ok": False,
            "reason": "release gate report was produced with accuracy-bypass or report-only flags",
        }
    if _report_marks_internal_testing_only(report, allow_release_gate_internal_labels=True):
        return {"ok": False, "reason": "release gate report is marked test-only or accuracy-bypass evidence"}
    if _report_has_test_only_evidence_counter(report):
        return {"ok": False, "reason": "release gate report contains test-only or synthetic quantity evidence"}
    if _report_marks_unsupported_scope(report):
        return {"ok": False, "reason": "release gate report contains unsupported-scope or abstention evidence"}
    if _report_has_incomplete_document_evidence(report):
        return {
            "ok": False,
            "reason": "release gate report contains incomplete or capped document extraction evidence",
        }
    if _report_has_customer_delivery_exposure_marker(report):
        return {
            "ok": False,
            "reason": "release gate report contains customer/final delivery exposure markers",
        }
    if _report_has_quantity_without_source_lineage(report):
        return {
            "ok": False,
            "reason": "release gate report contains quantity rows without source/document lineage",
        }
    if _report_has_non_strict_release_mode_alias(report):
        return {
            "ok": False,
            "reason": "release gate report was produced with accuracy-bypass or report-only flags",
        }
    aggregate = report.get("aggregate")
    if not isinstance(aggregate, dict):
        return {"ok": False, "reason": "release gate report is missing aggregate counts"}

    required_fields = (
        "project_count",
        "evaluated_count",
        "evaluation_passed_count",
        "skipped_count",
        "harness_failed_count",
        "safety_violation_count",
        "benchmark_eligible_count",
        "benchmark_ineligible_count",
        "evaluated_benchmark_eligible_count",
        "evaluated_benchmark_ineligible_count",
        "accuracy_failed_project_count",
        "missed_required_trade_project_count",
        "trade_unexpected_false_positive_total",
        "evaluated_benchmark_eligible_key_quantity_total",
        "evaluated_benchmark_eligible_key_quantity_pass_count",
        "evaluated_benchmark_eligible_key_quantity_evidence_pass_count",
        "evaluated_benchmark_eligible_document_text_extraction_pass_count",
        "evaluated_benchmark_eligible_document_text_extraction_fail_count",
    )
    counts: dict[str, int] = {}
    malformed = []
    for field in required_fields:
        parsed = _nonnegative_int_count(aggregate.get(field))
        if parsed is None:
            malformed.append(field)
        else:
            counts[field] = parsed
    if malformed:
        return {"ok": False, "reason": "release gate report has malformed/missing counts", "fields": malformed}

    if counts["skipped_count"]:
        return {"ok": False, "reason": "release gate has skipped project results"}
    if counts["harness_failed_count"]:
        return {"ok": False, "reason": "harness failures are present"}
    if counts["safety_violation_count"]:
        return {"ok": False, "reason": "safety-lock violations are present"}
    if counts["accuracy_failed_project_count"]:
        return {"ok": False, "reason": "accuracy failures are present"}
    if counts["missed_required_trade_project_count"]:
        return {"ok": False, "reason": "required trades were missed"}
    if counts["trade_unexpected_false_positive_total"]:
        return {"ok": False, "reason": "unexpected false-positive trades were detected"}

    project_count = counts["project_count"]
    evaluated_count = counts["evaluated_count"]
    evaluation_passed_count = counts["evaluation_passed_count"]
    evaluated_eligible_count = counts["evaluated_benchmark_eligible_count"]
    if evaluation_passed_count != evaluated_count:
        return {"ok": False, "reason": "release gate has unevaluated or failed project results"}
    if (
        evaluated_count + counts["skipped_count"] + counts["harness_failed_count"] != project_count
        or counts["benchmark_eligible_count"] + counts["benchmark_ineligible_count"] != project_count
        or evaluated_eligible_count + counts["evaluated_benchmark_ineligible_count"] != evaluated_count
        or evaluated_eligible_count > counts["benchmark_eligible_count"]
        or counts["evaluated_benchmark_ineligible_count"] > counts["benchmark_ineligible_count"]
    ):
        return {"ok": False, "reason": "release gate aggregate counts are inconsistent"}
    if evaluated_eligible_count <= 0:
        return {"ok": False, "reason": "release gate has zero evaluated benchmark-eligible projects"}

    key_quantity_total = counts["evaluated_benchmark_eligible_key_quantity_total"]
    key_quantity_pass = counts["evaluated_benchmark_eligible_key_quantity_pass_count"]
    key_quantity_evidence_pass = counts["evaluated_benchmark_eligible_key_quantity_evidence_pass_count"]
    if key_quantity_total <= 0 or key_quantity_pass != key_quantity_total or key_quantity_evidence_pass != key_quantity_total:
        return {"ok": False, "reason": "release gate lacks complete key-quantity evidence"}
    if (
        counts["evaluated_benchmark_eligible_document_text_extraction_fail_count"] != 0
        or counts["evaluated_benchmark_eligible_document_text_extraction_pass_count"] != evaluated_eligible_count
    ):
        return {"ok": False, "reason": "release gate document text extraction coverage is incomplete"}

    return {"ok": True, "reason": "release gate report passed wrapper validation"}


def compute_score(report: dict[str, Any]) -> dict[str, Any]:
    """Compute a deterministic scalar score from a Golden Set report.

    Formula v1:

        score =
          100 * scope_keyword_coverage_micro
        + 100 * trade_recall_micro
        +  50 * key_quantity_pass_rate
        +  25 * key_quantity_evidence_pass_rate
        -  20 * trade_unexpected_false_positive_total
        -1000 * safety_violation_count
        - 100 * harness_failed_count

    Quantity/evidence rates are denominator-safe. When no expected quantities are
    declared, the rate defaults to 1.0 so an early trade/scope-only corpus is not
    punished for lacking quantity rows. This is a scoring convention, not proof of
    quantity extraction quality.
    """
    raw_aggregate = report.get("aggregate")
    aggregate_present = isinstance(raw_aggregate, dict)
    aggregate = raw_aggregate if aggregate_present else {}

    scope_keyword_coverage_micro = _safe_number(aggregate.get("scope_keyword_coverage_micro"))
    trade_recall_micro = _safe_number(aggregate.get("trade_recall_micro"))
    key_quantity_pass_rate = _safe_rate(
        aggregate.get("key_quantity_pass_count"),
        aggregate.get("key_quantity_total"),
        zero_default=1.0,
    )
    key_quantity_evidence_pass_rate = _safe_rate(
        aggregate.get("key_quantity_evidence_pass_count"),
        aggregate.get("key_quantity_total"),
        zero_default=1.0,
    )
    unexpected_false_positive_trades = _safe_number(
        aggregate.get("trade_unexpected_false_positive_total")
    )
    safety_violation_count = _safe_number(aggregate.get("safety_violation_count"))
    harness_failed_count = _safe_number(aggregate.get("harness_failed_count"))

    components = {
        "scope_keyword_coverage_micro": round(100 * scope_keyword_coverage_micro, 6),
        "trade_recall_micro": round(100 * trade_recall_micro, 6),
        "key_quantity_pass_rate": round(50 * key_quantity_pass_rate, 6),
        "key_quantity_evidence_pass_rate": round(25 * key_quantity_evidence_pass_rate, 6),
        "unexpected_false_positive_penalty": round(-20 * unexpected_false_positive_trades, 6),
        "safety_violation_penalty": round(-1000 * safety_violation_count, 6),
        "harness_failed_penalty": round(-100 * harness_failed_count, 6),
    }
    score = round(sum(components.values()), 6)

    release_gate_validation = validate_release_gate_report(report)

    return {
        "schema_version": "mobi-autoresearch-score-v1",
        "generated_at": _utc_now(),
        "score": score,
        "components": components,
        "metrics": {
            "aggregate_present": aggregate_present,
            "scope_keyword_coverage_micro": scope_keyword_coverage_micro,
            "trade_recall_micro": trade_recall_micro,
            "key_quantity_pass_rate": round(key_quantity_pass_rate, 6),
            "key_quantity_evidence_pass_rate": round(key_quantity_evidence_pass_rate, 6),
            "trade_unexpected_false_positive_total": unexpected_false_positive_trades,
            "safety_violation_count": safety_violation_count,
            "harness_failed_count": harness_failed_count,
            "evaluation_passed_count": int(_safe_number(aggregate.get("evaluation_passed_count"))),
            "evaluated_count": int(_safe_number(aggregate.get("evaluated_count"))),
            "accuracy_failed_project_count": int(
                _safe_number(aggregate.get("accuracy_failed_project_count"))
            ),
        },
        "release_gate_validation": release_gate_validation,
        "formula": (
            "100*scope_keyword_coverage_micro + 100*trade_recall_micro + "
            "50*key_quantity_pass_rate + 25*key_quantity_evidence_pass_rate - "
            "20*trade_unexpected_false_positive_total - 1000*safety_violation_count - "
            "100*harness_failed_count"
        ),
    }


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _resolve_input_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def _run_eval_command(
    manifest: Path,
    output: Path,
    workdir: Path,
    *,
    python_executable: str,
    release_gate: bool,
) -> dict[str, Any]:
    manifest = _resolve_input_path(manifest)
    output = _resolve_input_path(output)
    workdir = _resolve_input_path(workdir)
    output.parent.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    command = [
        python_executable,
        str(DEFAULT_EVAL_SCRIPT),
        "--manifest",
        str(manifest),
        "--output",
        str(output),
        "--workdir",
        str(workdir),
    ]
    if release_gate:
        command.append("--release-gate")
    else:
        command.extend(["--no-fail-on-accuracy", "--report-only-baseline"])
    completed = _run(command, cwd=ENGINE_ROOT)
    if completed.returncode != 0:
        return {
            "ok": False,
            "exit_code": completed.returncode,
            "command": command,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "report_path": str(output),
            "release_gate": release_gate,
        }
    if not output.exists():
        missing_report_validation = {
            "ok": False,
            "reason": "evaluator exited 0 without writing a release gate report"
            if release_gate
            else "evaluator exited 0 without writing an evaluation report",
        }
        return {
            "ok": False,
            "exit_code": 1,
            "command": command,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "report_path": str(output),
            "workdir": str(workdir),
            "release_gate": release_gate,
            "release_gate_validation": missing_report_validation if release_gate else None,
        }
    report = load_json(output)
    release_gate_validation = validate_release_gate_report(report) if release_gate else None
    if release_gate_validation is not None and not release_gate_validation["ok"]:
        return {
            "ok": False,
            "exit_code": 1,
            "command": command,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "report_path": str(output),
            "workdir": str(workdir),
            "release_gate": release_gate,
            "release_gate_validation": release_gate_validation,
        }
    score = compute_score(report)
    return {
        "ok": True,
        "exit_code": completed.returncode,
        "command": command,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "report_path": str(output),
        "workdir": str(workdir),
        "score": score,
        "release_gate": release_gate,
        "release_gate_validation": release_gate_validation,
    }


def run_baseline(manifest: Path, output: Path, workdir: Path, *, python_executable: str) -> dict[str, Any]:
    """Run a report-only baseline eval; never use this as release evidence."""
    return _run_eval_command(
        manifest,
        output,
        workdir,
        python_executable=python_executable,
        release_gate=False,
    )


def run_release_gate(manifest: Path, output: Path, workdir: Path, *, python_executable: str) -> dict[str, Any]:
    """Run the strict Golden Set promotion gate.

    This path intentionally omits ``--no-fail-on-accuracy`` and
    ``--allow-missing-documents``. The underlying evaluator therefore fails on
    accuracy failures and requires at least one evaluated benchmark-eligible
    project, preventing schema-only or zero-eligible runs from passing release.
    """
    return _run_eval_command(
        manifest,
        output,
        workdir,
        python_executable=python_executable,
        release_gate=True,
    )


def _normalize_repo_path(path: str | Path, *, repo_root: Path = REPO_ROOT) -> str:
    raw = str(path).replace("\\", "/").strip()
    if not raw:
        return ""
    candidate = Path(raw)
    if candidate.is_absolute():
        try:
            raw = candidate.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            raw = candidate.as_posix().lstrip("/")
    if raw.startswith("./"):
        raw = raw[2:]
    elif raw.startswith("/"):
        raw = raw.lstrip("/")
    return raw.rstrip("/") + ("/" if raw.endswith("/") else "")


def _path_matches(candidate: str, rule: str) -> bool:
    candidate = _normalize_repo_path(candidate).rstrip("/")
    rule_norm = _normalize_repo_path(rule)
    if rule_norm.endswith("/"):
        return candidate == rule_norm.rstrip("/") or candidate.startswith(rule_norm)
    return candidate == rule_norm


def collect_changed_paths(base_ref: str, *, repo_root: Path = REPO_ROOT) -> list[str]:
    """Return committed/staged/unstaged/untracked paths changed vs base_ref."""
    paths: set[str] = set()
    commands = [
        ["git", "diff", "--name-only", base_ref, "HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    for command in commands:
        completed = _run(command, cwd=repo_root)
        if completed.returncode != 0:
            raise RuntimeError(
                f"git command failed ({' '.join(command)}): {completed.stderr.strip()}"
            )
        for line in completed.stdout.splitlines():
            normalized = _normalize_repo_path(line, repo_root=repo_root)
            if normalized:
                paths.add(normalized.rstrip("/"))
    return sorted(paths)


def evaluate_guard(changed_paths: list[str], allowed_paths: list[str]) -> dict[str, Any]:
    allowed = [_normalize_repo_path(path) for path in allowed_paths]
    locked = [path for path in changed_paths if any(_path_matches(path, rule) for rule in LOCKED_PATHS)]
    outside_allowed = [
        path for path in changed_paths if not any(_path_matches(path, rule) for rule in allowed)
    ]
    ok = not locked and not outside_allowed
    return {
        "ok": ok,
        "changed_paths": changed_paths,
        "allowed_paths": allowed,
        "locked_paths": list(LOCKED_PATHS),
        "locked_violations": locked,
        "outside_allowed_violations": outside_allowed,
    }


def _score_has_release_gate_evidence(score: dict[str, Any]) -> bool:
    validation = score.get("release_gate_validation")
    return isinstance(validation, dict) and validation.get("ok") is True


def append_ledger(
    ledger: Path,
    *,
    experiment_id: str,
    score_json: Path,
    status: str,
    notes: str,
) -> dict[str, Any]:
    if status not in {"accepted", "rejected", "baseline"}:
        raise ValueError("status must be one of accepted, rejected, baseline")
    score = load_json(score_json)
    if status == "accepted" and not _score_has_release_gate_evidence(score):
        raise ValueError("accepted ledger entries require strict release-gate validation evidence")
    record = {
        "schema_version": "mobi-autoresearch-ledger-v1",
        "timestamp": _utc_now(),
        "experiment_id": experiment_id,
        "status": status,
        "notes": notes,
        "score": score,
    }
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def cmd_score(args: argparse.Namespace) -> int:
    report = load_json(Path(args.report))
    result = compute_score(report)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print_json(result)
    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    result = run_baseline(
        Path(args.manifest),
        Path(args.output),
        Path(args.workdir),
        python_executable=args.python,
    )
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_release_gate(args: argparse.Namespace) -> int:
    result = run_release_gate(
        Path(args.manifest),
        Path(args.output),
        Path(args.workdir),
        python_executable=args.python,
    )
    _print_json(result)
    return 0 if result.get("ok") else 1


def cmd_guard(args: argparse.Namespace) -> int:
    changed = collect_changed_paths(args.base_ref)
    result = evaluate_guard(changed, args.allowed)
    _print_json(result)
    return 0 if result["ok"] else 1


def cmd_append_ledger(args: argparse.Namespace) -> int:
    record = append_ledger(
        Path(args.ledger),
        experiment_id=args.experiment_id,
        score_json=Path(args.score_json),
        status=args.status,
        notes=args.notes,
    )
    _print_json(record)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mobi AutoResearch v1 helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    score = subparsers.add_parser("score", help="Score an existing Golden Set report")
    score.add_argument("--report", required=True, help="Golden Set report JSON path")
    score.add_argument("--output", help="Optional path to write score JSON")
    score.set_defaults(func=cmd_score)

    baseline = subparsers.add_parser("baseline", help="Run Golden Set v2 eval and score it")
    baseline.add_argument("--manifest", default=str(DEFAULT_GOLDEN_SET_V2_MANIFEST))
    baseline.add_argument("--output", default=str(DEFAULT_GOLDEN_SET_V2_REPORT))
    baseline.add_argument("--workdir", required=True)
    baseline.add_argument("--python", default=sys.executable, help="Python executable for evaluator")
    baseline.set_defaults(func=cmd_baseline)

    release_gate = subparsers.add_parser(
        "release-gate",
        help="Run strict Golden Set release gate; no accuracy bypass or schema-only evidence.",
    )
    release_gate.add_argument("--manifest", default=str(DEFAULT_GOLDEN_SET_V2_MANIFEST))
    release_gate.add_argument("--output", default=str(DEFAULT_GOLDEN_SET_V2_REPORT))
    release_gate.add_argument("--workdir", required=True)
    release_gate.add_argument("--python", default=sys.executable, help="Python executable for evaluator")
    release_gate.set_defaults(func=cmd_release_gate)

    guard = subparsers.add_parser("guard", help="Reject forbidden or outside-allowlist changes")
    guard.add_argument("--base-ref", required=True, help="Base git ref to compare against")
    guard.add_argument(
        "--allowed",
        action="append",
        required=True,
        help="Allowed mutable path. May be repeated. Directories should end with /.",
    )
    guard.set_defaults(func=cmd_guard)

    ledger = subparsers.add_parser("append-ledger", help="Append an AutoResearch JSONL ledger row")
    ledger.add_argument("--ledger", required=True)
    ledger.add_argument("--experiment-id", required=True)
    ledger.add_argument("--score-json", required=True)
    ledger.add_argument("--status", required=True, choices=["accepted", "rejected", "baseline"])
    ledger.add_argument("--notes", default="")
    ledger.set_defaults(func=cmd_append_ledger)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # pragma: no cover - CLI defensive path
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
