"""Deterministic Automatic Trade Census Draft Generation v1.

This is the first automation layer on top of the Trade Coverage Matrix. It reads
already-processed sheet records and their extracted text artifacts, detects likely
trades from deterministic sheet-number/title/text signals, and seeds coverage
rows without pricing, sending messages, or delivering customer-facing estimates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.coverage_db import list_coverage_rows, upsert_coverage_row
from app.database import get_project, list_sheets
from app.services import storage


@dataclass(frozen=True)
class TradeSignalRule:
    trade_code: str
    trade_name: str
    csi_divisions: tuple[str, ...]
    sheet_prefixes: tuple[str, ...] = ()
    title_keywords: tuple[str, ...] = ()
    text_keywords: tuple[str, ...] = ()


TRADE_SIGNAL_RULES: tuple[TradeSignalRule, ...] = (
    TradeSignalRule(
        "architectural_general", "Architectural / General", ("01",),
        sheet_prefixes=("A", "G"),
        title_keywords=("architectural", "floor plan", "reflected ceiling", "general notes"),
    ),
    TradeSignalRule(
        "structural", "Structural", ("05",),
        sheet_prefixes=("S",),
        title_keywords=("structural", "framing", "foundation", "steel"),
        text_keywords=("structural notes", "framing plan"),
    ),
    TradeSignalRule(
        "civil_sitework", "Civil / Sitework", ("31", "32", "33"),
        sheet_prefixes=("C",),
        title_keywords=("civil", "site", "grading", "utility", "erosion"),
    ),
    TradeSignalRule(
        "landscape", "Landscape", ("32",),
        sheet_prefixes=("L",),
        title_keywords=("landscape", "planting", "irrigation"),
    ),
    TradeSignalRule(
        "plumbing", "Plumbing", ("22",),
        sheet_prefixes=("P",),
        title_keywords=("plumbing", "fixture", "sanitary", "domestic water"),
        text_keywords=("plumbing fixture", "sanitary", "domestic water"),
    ),
    TradeSignalRule(
        "hvac", "Mechanical / HVAC", ("23",),
        sheet_prefixes=("M", "H"),
        title_keywords=("mechanical", "hvac", "air handling", "duct", "ventilation"),
        text_keywords=("air handling", "diffuser", "ductwork", "hvac"),
    ),
    TradeSignalRule(
        "electrical", "Electrical", ("26",),
        sheet_prefixes=("E",),
        title_keywords=("electrical", "lighting", "power", "panel"),
        text_keywords=("panel schedule", "lighting fixture", "power plan"),
    ),
    TradeSignalRule(
        "low_voltage", "Technology / Low Voltage", ("27",),
        sheet_prefixes=("T", "LV"),
        title_keywords=("technology", "low voltage", "telecom", "data", "security"),
        text_keywords=("data outlet", "telecom", "low voltage"),
    ),
    TradeSignalRule(
        "fire_alarm", "Fire Alarm", ("28",),
        sheet_prefixes=("FA",),
        title_keywords=("fire alarm",),
        text_keywords=("fire alarm", "horn strobe", "smoke detector"),
    ),
    TradeSignalRule(
        "fire_protection", "Fire Protection", ("21",),
        sheet_prefixes=("FP",),
        title_keywords=("fire protection", "sprinkler"),
        text_keywords=("sprinkler", "fire protection"),
    ),
    TradeSignalRule(
        "concrete", "Concrete", ("03",),
        title_keywords=("concrete", "slab", "foundation", "footing"),
        text_keywords=("division 03", "cast-in-place", "concrete slab", "footing"),
    ),
    TradeSignalRule(
        "doors_hardware", "Doors / Windows / Hardware", ("08",),
        title_keywords=("door schedule", "window schedule", "hardware"),
        text_keywords=("division 08", "door schedule", "hardware set", "window schedule"),
    ),
    TradeSignalRule(
        "finishes", "Finishes", ("09",),
        sheet_prefixes=("ID", "I"),
        title_keywords=("finish", "interior", "flooring", "paint", "ceiling"),
        text_keywords=("division 09", "finish schedule", "paint", "flooring", "acoustical ceiling"),
    ),
    TradeSignalRule(
        "roofing_waterproofing", "Roofing / Waterproofing", ("07",),
        title_keywords=("roof", "waterproofing", "insulation"),
        text_keywords=("division 07", "roofing", "waterproofing", "thermal insulation"),
    ),
)

# Broad spec-division fallback for division mentions not otherwise caught.
CSI_DIVISION_FALLBACKS: dict[str, tuple[str, str]] = {
    "02": ("existing_conditions", "Existing Conditions"),
    "04": ("masonry", "Masonry"),
    "06": ("wood_plastics_composites", "Wood / Plastics / Composites"),
    "10": ("specialties", "Specialties"),
    "11": ("equipment", "Equipment"),
    "12": ("furnishings", "Furnishings"),
    "13": ("special_construction", "Special Construction"),
    "14": ("conveying_equipment", "Conveying Equipment"),
}


def _normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _sheet_prefix(sheet_number: str | None) -> str:
    number = _normalize(sheet_number).upper()
    if not number:
        return ""
    match = re.match(r"([A-Z]+)", number)
    return match.group(1) if match else ""


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    lower = haystack.lower()
    return any(needle.lower() in lower for needle in needles)


def _read_sheet_text(sheet: dict[str, Any]) -> str:
    relative = sheet.get("text_path")
    if not relative:
        return ""
    try:
        path = storage.resolve_within_data_root(relative)
        if not path.exists():
            return ""
        # Keep the census deterministic and bounded; this is a signal detector, not
        # full extraction. The full text artifact remains available for later lanes.
        return path.read_text(encoding="utf-8", errors="replace")[:40_000]
    except Exception:
        return ""


def _evidence_ref(sheet: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "sheet_id": sheet.get("id"),
        "pdf_page_number": sheet.get("pdf_page_number"),
        "verified_sheet_number": sheet.get("verified_sheet_number") or sheet.get("detected_sheet_number"),
        "verified_sheet_title": sheet.get("verified_sheet_title") or sheet.get("detected_sheet_title"),
        "reason": reason,
    }


def _division_mentions(text: str) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(r"\b(?:division|div\.?|csi)\s*0?([0-9]{2})\b", text, flags=re.I):
        found.add(match.group(1).zfill(2))
    return found


def _project_evidence_ref(reason: str, project_name: str) -> dict[str, Any]:
    return {
        "sheet_id": None,
        "pdf_page_number": None,
        "verified_sheet_number": None,
        "verified_sheet_title": None,
        "reason": f"{reason}: {project_name[:200]}",
    }


def _title_has_any(title: str, needles: tuple[str, ...]) -> bool:
    return any(needle in title for needle in needles)


def _detect_from_project_name(project_name: str) -> dict[str, dict[str, Any]]:
    """Return conservative internal fallback detections from the project name.

    Some image-heavy plan sets produce sparse OCR and blank sheet numbers/titles, but
    the project title entered at upload still carries useful bid-package context. These
    detections are lower confidence than sheet-prefix detections and only seed blocked
    generic scope candidates for downstream review.
    """
    title = _normalize(project_name).lower()
    detections: dict[str, dict[str, Any]] = {}

    def add(
        trade_code: str,
        trade_name: str,
        csi_divisions: tuple[str, ...],
        reason: str,
        confidence: float = 0.58,
    ) -> None:
        detections[trade_code] = {
            "trade_code": trade_code,
            "trade_name": trade_name,
            "csi_divisions": list(csi_divisions),
            "detected_from": [reason],
            "confidence": confidence,
            "evidence_refs": [_project_evidence_ref(reason, project_name)],
        }

    if _title_has_any(title, ("evcs", "ev charger", "ev charging", "charging station")):
        add("electrical", "Electrical", ("26",), "project_name:ev_charging_scope", 0.64)

    if _title_has_any(
        title,
        ("parking", "accessibility", "accessible", "striping", "restriping", "site", "curb", "paving", "stalls"),
    ):
        add("civil_sitework", "Civil / Sitework", ("31", "32", "33"), "project_name:site_accessibility_scope", 0.61)

    if _title_has_any(title, ("curb", "sidewalk", "concrete", "accessibility upgrade", "accessibility upgrades")):
        add("concrete", "Concrete", ("03",), "project_name:accessibility_flatwork_scope", 0.57)

    if _title_has_any(title, ("roof", "reroof", "roofing", "roof replacement")):
        add("roofing_waterproofing", "Roofing / Waterproofing", ("07",), "project_name:roof_scope", 0.66)
        add("architectural_general", "Architectural / General", ("01",), "project_name:building_roof_project", 0.56)

    if _title_has_any(title, ("structural", "framing", "foundation")) or (
        _title_has_any(title, ("roof replacement", "reroof"))
        and _title_has_any(title, ("building", "administration", "annex"))
    ):
        add("structural", "Structural", ("05",), "project_name:structural_review_scope", 0.55)

    return detections


def _detect_from_sheet(sheet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sheet_number = sheet.get("verified_sheet_number") or sheet.get("detected_sheet_number")
    sheet_title = sheet.get("verified_sheet_title") or sheet.get("detected_sheet_title")
    prefix = _sheet_prefix(sheet_number)
    text = _read_sheet_text(sheet)
    title_blob = _normalize(sheet_title)
    text_blob = " ".join([title_blob, text])

    detections: dict[str, dict[str, Any]] = {}
    for rule in TRADE_SIGNAL_RULES:
        reasons: list[str] = []
        if prefix and prefix in rule.sheet_prefixes:
            reasons.append(f"sheet_prefix:{prefix}")
        if _contains_any(title_blob, rule.title_keywords):
            reasons.append("sheet_title_keyword")
        if _contains_any(text_blob, rule.text_keywords):
            reasons.append("sheet_text_keyword")
        if reasons:
            confidence = 0.9 if any(r.startswith("sheet_prefix") for r in reasons) else 0.72
            if len(reasons) >= 2:
                confidence = min(0.98, confidence + 0.05)
            detections[rule.trade_code] = {
                "trade_code": rule.trade_code,
                "trade_name": rule.trade_name,
                "csi_divisions": list(rule.csi_divisions),
                "detected_from": reasons,
                "confidence": confidence,
                "evidence_refs": [_evidence_ref(sheet, ",".join(reasons))],
            }

    for division in _division_mentions(text_blob):
        fallback = CSI_DIVISION_FALLBACKS.get(division)
        if fallback is None:
            continue
        trade_code, trade_name = fallback
        detections.setdefault(trade_code, {
            "trade_code": trade_code,
            "trade_name": trade_name,
            "csi_divisions": [division],
            "detected_from": [f"spec_division:{division}"],
            "confidence": 0.68,
            "evidence_refs": [_evidence_ref(sheet, f"spec_division:{division}")],
        })

    return detections


def _merge_detections(existing: dict[str, dict[str, Any]], detected: dict[str, dict[str, Any]]) -> None:
    for code, item in detected.items():
        if code not in existing:
            existing[code] = item
            continue
        current = existing[code]
        current["csi_divisions"] = sorted(set(current.get("csi_divisions", [])) | set(item.get("csi_divisions", [])))
        current["detected_from"] = sorted(set(current.get("detected_from", [])) | set(item.get("detected_from", [])))
        current["confidence"] = max(float(current.get("confidence") or 0), float(item.get("confidence") or 0))
        current["evidence_refs"] = [*current.get("evidence_refs", []), *item.get("evidence_refs", [])]


def draft_trade_census(project_id: UUID) -> dict[str, Any]:
    """Seed/update coverage rows from deterministic processed-sheet signals."""
    sheets, total = list_sheets(project_id, limit=1000, offset=0)
    detections: dict[str, dict[str, Any]] = {}
    skipped = 0
    for sheet in sheets:
        if sheet.get("processing_status") != "complete":
            skipped += 1
            continue
        if sheet.get("requires_ocr"):
            skipped += 1
            continue
        _merge_detections(detections, _detect_from_sheet(sheet))

    project = get_project(project_id)
    project_name = str((project or {}).get("name") or "").strip()
    if project_name:
        _merge_detections(detections, _detect_from_project_name(project_name))

    rows: list[dict[str, Any]] = []
    for code in sorted(detections):
        detected = detections[code]
        payload = {
            "trade_code": detected["trade_code"],
            "trade_name": detected["trade_name"],
            "csi_divisions": detected["csi_divisions"],
            "detected_from": detected["detected_from"],
            "disposition": "undispositioned",
            "basis_note": (
                "Automatically detected by Trade Census v1 from processed sheet "
                "signals. This is not pricing or final scope; it requires downstream "
                "generic/trade-specific scope generation or explicit exclusion."
            ),
            "confidence": detected["confidence"],
            "status": "draft",
            "blockers": [],
            "evidence_refs": detected["evidence_refs"],
        }
        rows.append(upsert_coverage_row(project_id, payload))

    coverage_rows = list_coverage_rows(project_id)
    return {
        "project_id": str(project_id),
        "sheet_count": total,
        "processed_sheet_count": len(sheets) - skipped,
        "skipped_sheet_count": skipped,
        "detected_trade_count": len(detections),
        "coverage_row_count": len(coverage_rows),
        "rows": rows,
    }
