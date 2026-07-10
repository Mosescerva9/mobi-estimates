"""Pydantic schemas for the Phase 2 processing & sheet API boundary.

These API models intentionally use a *non-strict* config so documented enum
string values (e.g. ``"verified"``) submitted by JSON clients are accepted, while
still forbidding unknown fields. The canonical estimating schemas in
``app.schemas`` remain strict and are not weakened.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.schemas import JobStatus, PageProcessingStatus, ProjectStatus, SheetReviewStatus


class ApiModel(BaseModel):
    # Lenient parsing (string -> enum, etc.) but no unexpected fields.
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


def _as_bool(value: Any) -> bool:
    return bool(value)


def _text_layer_quality(row: dict) -> str:
    if _as_bool(row.get("requires_ocr")):
        return "ocr_required"
    text_char_count = row.get("text_char_count")
    if not isinstance(text_char_count, int):
        return "unknown"
    if text_char_count < settings.very_low_information_text_chars:
        return "very_low_information_text_layer"
    if text_char_count < settings.low_information_text_chars:
        return "low_information_text_layer"
    return "usable_text_layer"


def _recommended_extraction_routes(row: dict) -> list[str]:
    quality = _text_layer_quality(row)
    routes: list[str] = []
    if quality == "ocr_required":
        routes.extend(["ocr", "vision"])
    elif quality in {"very_low_information_text_layer", "low_information_text_layer"}:
        routes.extend(["ocr", "vision", "table_schedule_extraction"])
    else:
        routes.append("text_extraction")
    title = " ".join(
        str(row.get(key) or "")
        for key in ("verified_sheet_title", "detected_sheet_title")
    ).lower()
    if "schedule" in title and "table_schedule_extraction" not in routes:
        routes.append("table_schedule_extraction")
    return routes


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------
class ProcessingRequest(ApiModel):
    force: bool = Field(default=False, description="Force a safe reprocess.")


class ProcessingAcceptedResponse(ApiModel):
    project_id: UUID
    project_status: ProjectStatus
    job_id: UUID
    job_status: JobStatus
    message: str


class ProcessingStatusResponse(ApiModel):
    project_id: UUID
    project_status: ProjectStatus
    job_id: UUID | None = None
    job_status: JobStatus | None = None
    attempt: int | None = None
    pages_discovered: int = 0
    pages_completed: int = 0
    pages_failed: int = 0
    pages_requiring_ocr: int = 0
    pages_requiring_review: int = 0
    duration_ms: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None

    @classmethod
    def from_rows(cls, project: dict, job: dict | None) -> "ProcessingStatusResponse":
        data: dict[str, Any] = {
            "project_id": project["id"],
            "project_status": project["status"],
        }
        if job is not None:
            data.update(
                {
                    "job_id": job["id"],
                    "job_status": job["status"],
                    "attempt": job["attempt"],
                    "pages_discovered": job["pages_discovered"],
                    "pages_completed": job["pages_completed"],
                    "pages_failed": job["pages_failed"],
                    "pages_requiring_ocr": job["pages_requiring_ocr"],
                    "pages_requiring_review": job["pages_requiring_review"],
                    "duration_ms": job["duration_ms"],
                    "started_at": job["started_at"],
                    "completed_at": job["completed_at"],
                    "error_code": job["error_code"],
                    "error_message": job["error_message"],
                }
            )
        return cls(**data)


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------
class SheetSummary(ApiModel):
    sheet_id: UUID
    project_id: UUID
    pdf_page_number: int
    page_index: int
    detected_sheet_number: str | None = None
    verified_sheet_number: str | None = None
    detected_sheet_title: str | None = None
    verified_sheet_title: str | None = None
    detection_confidence: float | None = None
    requires_review: bool
    requires_ocr: bool
    text_layer_quality: str
    recommended_extraction_routes: list[str]
    is_duplicate: bool
    duplicate_of_sheet_id: UUID | None = None
    processing_status: PageProcessingStatus
    review_status: SheetReviewStatus

    @classmethod
    def from_row(cls, row: dict) -> "SheetSummary":
        return cls(
            sheet_id=row["id"],
            project_id=row["project_id"],
            pdf_page_number=row["pdf_page_number"],
            page_index=row["page_index"],
            detected_sheet_number=row["detected_sheet_number"],
            verified_sheet_number=row["verified_sheet_number"],
            detected_sheet_title=row["detected_sheet_title"],
            verified_sheet_title=row["verified_sheet_title"],
            detection_confidence=row["detection_confidence"],
            requires_review=_as_bool(row["requires_review"]),
            requires_ocr=_as_bool(row["requires_ocr"]),
            text_layer_quality=_text_layer_quality(row),
            recommended_extraction_routes=_recommended_extraction_routes(row),
            is_duplicate=row["duplicate_of_sheet_id"] is not None,
            duplicate_of_sheet_id=row["duplicate_of_sheet_id"],
            processing_status=row["processing_status"],
            review_status=row["review_status"],
        )


class SheetArtifacts(ApiModel):
    """API URLs for generated artifacts (never raw filesystem paths)."""

    image_available: bool
    thumbnail_available: bool
    text_available: bool
    image_url: str | None = None
    thumbnail_url: str | None = None


class SheetDetail(SheetSummary):
    text_char_count: int
    page_width_points: float | None = None
    page_height_points: float | None = None
    rotation: int
    page_sha256: str | None = None
    processing_error: str | None = None
    review_notes: str | None = None
    artifacts: SheetArtifacts
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: dict, *, base_url: str) -> "SheetDetail":
        has_image = bool(row["full_image_path"])
        has_thumb = bool(row["thumbnail_path"])
        has_text = bool(row["text_path"])
        artifacts = SheetArtifacts(
            image_available=has_image,
            thumbnail_available=has_thumb,
            text_available=has_text,
            image_url=f"{base_url}/image" if has_image else None,
            thumbnail_url=f"{base_url}/thumbnail" if has_thumb else None,
        )
        return cls(
            sheet_id=row["id"],
            project_id=row["project_id"],
            pdf_page_number=row["pdf_page_number"],
            page_index=row["page_index"],
            detected_sheet_number=row["detected_sheet_number"],
            verified_sheet_number=row["verified_sheet_number"],
            detected_sheet_title=row["detected_sheet_title"],
            verified_sheet_title=row["verified_sheet_title"],
            detection_confidence=row["detection_confidence"],
            requires_review=_as_bool(row["requires_review"]),
            requires_ocr=_as_bool(row["requires_ocr"]),
            text_layer_quality=_text_layer_quality(row),
            recommended_extraction_routes=_recommended_extraction_routes(row),
            is_duplicate=row["duplicate_of_sheet_id"] is not None,
            duplicate_of_sheet_id=row["duplicate_of_sheet_id"],
            processing_status=row["processing_status"],
            review_status=row["review_status"],
            text_char_count=row["text_char_count"],
            page_width_points=row["page_width_points"],
            page_height_points=row["page_height_points"],
            rotation=row["rotation"],
            page_sha256=row["page_sha256"],
            processing_error=row["processing_error"],
            review_notes=row["review_notes"],
            artifacts=artifacts,
            verified_at=row["verified_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class SheetListResponse(ApiModel):
    items: list[SheetSummary]
    total: int
    limit: int
    offset: int


class SheetVerificationRequest(ApiModel):
    verified_sheet_number: str | None = Field(default=None, max_length=64)
    verified_sheet_title: str | None = Field(default=None, max_length=255)
    review_notes: str | None = Field(default=None, max_length=1000)
    review_status: SheetReviewStatus = SheetReviewStatus.VERIFIED
