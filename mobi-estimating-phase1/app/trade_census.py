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
        text_keywords=(
            "structural notes", "framing plan", "structural steel", "steel framing",
            "wood framing", "metal deck", "anchor bolt", "shear wall",
        ),
    ),
    TradeSignalRule(
        "civil_sitework", "Civil / Sitework", ("31", "32", "33"),
        sheet_prefixes=("C",),
        title_keywords=("civil", "site", "grading", "utility", "erosion"),
        text_keywords=(
            "accessible parking", "parking stall", "parking striping", "pavement striping", "curb ramp",
            "truncated dome", "grading", "site demolition", "storm drain",
        ),
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
        text_keywords=(
            "panel schedule", "panelboard", "lighting fixture", "power plan",
            "ev charger", "ev charging", "conduit", "switchboard",
        ),
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
        text_keywords=(
            "division 03", "cast-in-place", "concrete slab", "concrete curb",
            "concrete sidewalk", "concrete paving", "footing",
        ),
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
        text_keywords=(
            "division 07", "roofing", "roof membrane", "roof drain", "roofing system",
            "roof flashing", "waterproofing", "thermal insulation",
        ),
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

SHEET_INDEX_MARKERS = (
    "sheet index",
    "drawing index",
    "drawing list",
    "list of drawings",
    "index of drawings",
    "sheet list",
)


def _prefix_trade_rules() -> dict[str, TradeSignalRule]:
    rules: dict[str, TradeSignalRule] = {}
    for rule in TRADE_SIGNAL_RULES:
        for prefix in rule.sheet_prefixes:
            rules.setdefault(prefix, rule)
    return rules


SHEET_PREFIX_TRADE_RULES = _prefix_trade_rules()


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


def _first_keyword_line(text: str, keywords: tuple[str, ...]) -> tuple[str, str] | None:
    """Return the first keyword and source line that supports a text signal."""
    if not text or not keywords:
        return None
    for raw_line in text.splitlines():
        line = _normalize(raw_line)
        if not line:
            continue
        lower = line.lower()
        for keyword in keywords:
            if keyword.lower() in lower:
                return keyword, line[:500]
    lower_text = text.lower()
    for keyword in keywords:
        index = lower_text.find(keyword.lower())
        if index >= 0:
            start = max(0, index - 120)
            end = min(len(text), index + len(keyword) + 180)
            return keyword, _normalize(text[start:end])[:500]
    return None


def _processed_root_for_project_sheet(
    sheet: dict[str, Any], project: dict[str, Any] | None = None
) -> Any:
    """Return the project-authoritative processed root for sheet text evidence.

    The sheet row supplies the artifact path, so its tenant/company fields must
    not also define the trust boundary. Use the project row as the authoritative
    tenant context to prevent a self-consistent corrupted sheet row from reading
    another tenant's text artifact.
    """

    if project is None:
        project = get_project(UUID(str(sheet["project_id"])))
    if project is None or str(project.get("id")) != str(sheet["project_id"]):
        raise PermissionError("sheet_project_context_required")
    return storage.processed_dir(
        UUID(str(project["id"])),
        tenant_id=project.get("tenant_id"),
        company_id=project.get("company_id"),
    ).resolve()


def _read_sheet_text(sheet: dict[str, Any], *, project: dict[str, Any] | None = None) -> str:
    relative = sheet.get("text_path")
    if not relative:
        return ""
    try:
        path = storage.resolve_within_data_root(relative)
        expected_root = _processed_root_for_project_sheet(sheet, project)
        if not path.is_relative_to(expected_root):
            return ""
        if not path.exists():
            return ""
        # Keep the census deterministic and bounded; this is a signal detector, not
        # full extraction. The full text artifact remains available for later lanes.
        return path.read_text(encoding="utf-8", errors="replace")[:40_000]
    except (KeyError, TypeError, ValueError, PermissionError, OSError):
        return ""


def _evidence_ref(sheet: dict[str, Any], reason: str, *, text_quote: str | None = None) -> dict[str, Any]:
    return {
        "sheet_id": sheet.get("id"),
        "pdf_page_number": sheet.get("pdf_page_number"),
        "verified_sheet_number": sheet.get("verified_sheet_number") or sheet.get("detected_sheet_number"),
        "verified_sheet_title": sheet.get("verified_sheet_title") or sheet.get("detected_sheet_title"),
        "reason": reason,
        "text_quote": text_quote,
    }


def _evidence_for_reasons(
    sheet: dict[str, Any],
    reasons: list[str],
    *,
    title_quote: str | None = None,
    text_quote: str | None = None,
) -> dict[str, Any]:
    quote = text_quote or title_quote
    return _evidence_ref(sheet, ",".join(reasons), text_quote=quote)


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


def _detect_from_sheet(
    sheet: dict[str, Any], *, project: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    sheet_number = sheet.get("verified_sheet_number") or sheet.get("detected_sheet_number")
    sheet_title = sheet.get("verified_sheet_title") or sheet.get("detected_sheet_title")
    prefix = _sheet_prefix(sheet_number)
    text = _read_sheet_text(sheet, project=project)
    title_blob = _normalize(sheet_title)
    text_blob = " ".join([title_blob, text])

    detections: dict[str, dict[str, Any]] = {}
    for rule in TRADE_SIGNAL_RULES:
        reasons: list[str] = []
        title_quote: str | None = None
        text_quote: str | None = None
        if prefix and prefix in rule.sheet_prefixes:
            reasons.append(f"sheet_prefix:{prefix}")
        if _contains_any(title_blob, rule.title_keywords):
            reasons.append("sheet_title_keyword")
            title_quote = title_blob[:500]
        text_match = _first_keyword_line(text, rule.text_keywords)
        if text_match is not None:
            keyword, quote = text_match
            reasons.append(f"sheet_text_keyword:{keyword}")
            text_quote = quote
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
                "evidence_refs": [_evidence_for_reasons(sheet, reasons, title_quote=title_quote, text_quote=text_quote)],
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
            "evidence_refs": [
                _evidence_ref(
                    sheet,
                    f"spec_division:{division}",
                    text_quote=(_first_keyword_line(text_blob, (f"division {division}", f"division {int(division)}")) or (None, None))[1],
                )
            ],
        })

    return detections


def _looks_like_index_or_cover_sheet(sheet: dict[str, Any], text_blob: str) -> bool:
    sheet_number = _normalize(sheet.get("verified_sheet_number") or sheet.get("detected_sheet_number")).upper()
    title = _normalize(sheet.get("verified_sheet_title") or sheet.get("detected_sheet_title")).lower()
    lower_text = text_blob.lower()
    if any(marker in title or marker in lower_text for marker in SHEET_INDEX_MARKERS):
        return True
    if "cover" in title or "title sheet" in title:
        return True
    if sheet_number in {"G-000", "G-001", "G000", "G001", "A-000", "A-001", "A000", "A001"}:
        return True
    return False


def _detect_from_sheet_index(
    sheet: dict[str, Any], *, project: dict[str, Any] | None = None
) -> dict[str, dict[str, Any]]:
    """Detect trades from real cover-sheet/sheet-index text.

    This is a fallback for sparse plans where individual drawing pages are hard to
    classify but a cover sheet or sheet index lists discipline sheet numbers. It
    uses actual extracted sheet text/evidence, not the project title, and it only
    seeds internal draft coverage rows for later blocked generic scope review.
    """
    sheet_title = _normalize(sheet.get("verified_sheet_title") or sheet.get("detected_sheet_title"))
    text = _read_sheet_text(sheet, project=project)
    text_blob = "\n".join(part for part in (sheet_title, text) if part)
    if not text_blob or not _looks_like_index_or_cover_sheet(sheet, text_blob):
        return {}

    detections: dict[str, dict[str, Any]] = {}
    for raw_line in text_blob.splitlines():
        line = _normalize(raw_line)
        if not line:
            continue
        # Common sheet-index entries: C-101 Civil Site Plan, A101 Floor Plan,
        # E0.01 Electrical Symbols. Require a digit after the discipline prefix
        # so ordinary words on a cover sheet do not become trade detections.
        for match in re.finditer(r"\b([A-Z]{1,3})[\s.\-]*\d{1,3}(?:\.\d+)?\b", line.upper()):
            prefix = match.group(1)
            rule = SHEET_PREFIX_TRADE_RULES.get(prefix)
            if rule is None:
                continue
            detections[rule.trade_code] = {
                "trade_code": rule.trade_code,
                "trade_name": rule.trade_name,
                "csi_divisions": list(rule.csi_divisions),
                "detected_from": [f"sheet_index_prefix:{prefix}"],
                "confidence": 0.74,
                "evidence_refs": [_evidence_ref(sheet, f"sheet_index_prefix:{prefix}", text_quote=line[:500])],
            }

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
    project = get_project(project_id)
    detections: dict[str, dict[str, Any]] = {}
    skipped = 0
    for sheet in sheets:
        if sheet.get("processing_status") != "complete":
            skipped += 1
            continue
        if sheet.get("requires_ocr"):
            skipped += 1
            continue
        _merge_detections(detections, _detect_from_sheet(sheet, project=project))
        _merge_detections(detections, _detect_from_sheet_index(sheet, project=project))

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
