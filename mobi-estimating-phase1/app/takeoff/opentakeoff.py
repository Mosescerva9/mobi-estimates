"""OpenTakeoff export normalizer.

This module is the first adapter seam between OpenTakeoff's exported
``opentakeoff.takeoff_canvas.v1`` payload and Mobi's canonical evidence model.
It intentionally maps a small, explicit subset of the export shape. Unknown or
unsupported measurement roles are quarantined instead of guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from app.takeoff.evidence import EvidenceClass, MeasurementMethod
from app.takeoff.providers import (
    OpenTakeoffProvider,
    ProviderNormalizationResult,
    QuarantinedPayload,
    TakeoffContext,
)


@dataclass(frozen=True)
class OpenTakeoffNormalizeOptions:
    """Server-owned scope defaults for an OpenTakeoff export normalization."""

    trade: str
    scope_category: str
    default_description: str = "OpenTakeoff measurement"
    page_by_sheet: Mapping[str, int] | None = None


def _sheet_page(sheet_id: str, page_by_sheet: Mapping[str, int] | None) -> int:
    if page_by_sheet and sheet_id in page_by_sheet:
        return page_by_sheet[sheet_id]
    if "#" in sheet_id:
        suffix = sheet_id.rsplit("#", 1)[1]
        if suffix.isdigit() and int(suffix) >= 1:
            return int(suffix)
    return 1


def _region_from_verts(verts: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(verts, list) or not verts:
        return None
    points: list[tuple[float, float]] = []
    for point in verts:
        if (
            not isinstance(point, list | tuple)
            or len(point) != 2
            or not isinstance(point[0], int | float)
            or not isinstance(point[1], int | float)
        ):
            return None
        points.append((float(point[0]), float(point[1])))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _quantity_unit(shape: Mapping[str, Any]) -> tuple[Decimal, str] | None:
    role = shape.get("measure_role")
    computed = shape.get("computed")
    if not isinstance(computed, Mapping):
        return None

    if role in {"floor_area", "area", "deduct"}:
        area = computed.get("area_sf")
        if isinstance(area, int | float):
            quantity = Decimal(str(area))
            if role == "deduct":
                quantity = -abs(quantity)
            return quantity, "SF"
    if role in {"linear", "line"}:
        length = computed.get("length_lf", computed.get("perimeter_lf"))
        if isinstance(length, int | float):
            return Decimal(str(length)), "LF"
    if role in {"count", "each"}:
        count = computed.get("count", computed.get("quantity"))
        if isinstance(count, int | float):
            return Decimal(str(count)), "EA"
    return None


def normalize_opentakeoff_export(
    export: Mapping[str, Any],
    *,
    context: TakeoffContext,
    options: OpenTakeoffNormalizeOptions,
) -> ProviderNormalizationResult:
    """Normalize an OpenTakeoff export into canonical evidence rows.

    The export is not allowed to provide tenant/company/project/document/sheet
    identity. Those values come only from ``context``. Per-shape unsupported or
    malformed records are quarantined; valid rows are normalized by
    :class:`OpenTakeoffProvider`, preserving the same no-unknown-field boundary as
    every other provider.
    """

    provider = OpenTakeoffProvider()
    result = ProviderNormalizationResult(provider=provider.provider_kind)

    if export.get("schema") != "opentakeoff.takeoff_canvas.v1":
        result.quarantined.append(
            QuarantinedPayload(
                reason_code="unsupported_opentakeoff_schema",
                message="OpenTakeoff export schema is missing or unsupported.",
                payload=dict(export),
            )
        )
        return result

    conditions = {
        condition.get("id"): condition
        for condition in export.get("conditions", [])
        if isinstance(condition, Mapping) and condition.get("id")
    }
    sheet_scales = {
        sheet.get("sheet_id"): sheet.get("units_per_px")
        for sheet in export.get("sheets", [])
        if isinstance(sheet, Mapping) and sheet.get("sheet_id")
    }

    shapes = export.get("shapes")
    if not isinstance(shapes, list):
        result.quarantined.append(
            QuarantinedPayload(
                reason_code="malformed_shapes",
                message="OpenTakeoff export does not contain a shapes array.",
                payload=dict(export),
            )
        )
        return result

    for shape in shapes:
        if not isinstance(shape, Mapping):
            result.quarantined.append(
                QuarantinedPayload(
                    reason_code="malformed_shape",
                    message="OpenTakeoff shape is not an object.",
                    payload={"shape": shape},
                )
            )
            continue

        shape_id = shape.get("id")
        sheet_id = shape.get("sheet_id")
        if not isinstance(shape_id, str) or not shape_id.strip() or not isinstance(sheet_id, str):
            result.quarantined.append(
                QuarantinedPayload(
                    reason_code="missing_shape_identity",
                    message="OpenTakeoff shape is missing id or sheet_id.",
                    payload=dict(shape),
                )
            )
            continue

        quantity_unit = _quantity_unit(shape)
        if quantity_unit is None:
            result.quarantined.append(
                QuarantinedPayload(
                    reason_code="unsupported_measure_role",
                    message="OpenTakeoff shape has no supported measured quantity.",
                    payload=dict(shape),
                )
            )
            continue

        quantity, unit = quantity_unit
        condition = conditions.get(shape.get("condition_id"), {})
        condition_name = condition.get("finish_tag") if isinstance(condition, Mapping) else None
        scale_value = sheet_scales.get(sheet_id)
        payload = {
            "provider_record_id": shape_id,
            "page_number": _sheet_page(sheet_id, options.page_by_sheet),
            "region_coordinates": _region_from_verts(shape.get("verts_norm")),
            "trade": options.trade,
            "scope_category": options.scope_category,
            "description": f"{options.default_description}: {shape.get('measure_role')}",
            "quantity": quantity,
            "unit": unit,
            "confidence": Decimal("0.8"),
            "condition": condition_name,
            "scale": f"units_per_px:{scale_value}" if isinstance(scale_value, int | float) else None,
        }
        try:
            evidence = provider.normalize(payload, context=context)
        except Exception as exc:  # defensive: provider returns typed quarantine in batch path
            result.quarantined.append(
                QuarantinedPayload(
                    reason_code=getattr(exc, "reason_code", "canonical_validation_failed"),
                    message=str(exc),
                    payload=payload,
                )
            )
            continue
        # OpenTakeoff exports are measured digital quantities by default.
        assert evidence.evidence_class == EvidenceClass.MEASURED.value
        assert evidence.measurement_method == MeasurementMethod.DIGITAL_MEASUREMENT.value
        result.evidence.append(evidence)

    return result
