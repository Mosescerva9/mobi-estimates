"""Deterministic PDF ingestion and per-page sheet processing.

Pure Python + PyMuPDF. No OCR, no LLM, no pricing. The service is deliberately
decoupled from FastAPI: it takes identifiers and talks to the database/storage
layers, so it can run inline in tests or inside a background task in development,
and could later be driven by an external worker.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import fitz  # PyMuPDF

from app.config import settings
from app.database import (
    delete_sheets_for_project,
    get_project,
    insert_sheet,
    update_job,
    update_project_status,
)
from app.schemas import (
    JobStatus,
    PageProcessingStatus,
    ProjectStatus,
    SheetReviewStatus,
)
from app.services import storage
from app.services.sheet_detection import (
    TextBlock,
    detect_sheet_number,
    detect_sheet_title,
)

logger = logging.getLogger("mobi.processing")


class ProcessingError(Exception):
    """A processing failure with a safe, client-facing error code and message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    """Normalize line endings to ``\\n`` without altering meaningful content."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _render_zoom(page_width_pt: float, page_height_pt: float) -> float:
    """Compute a render zoom honoring DPI and the max-pixel decompression guard."""
    base = settings.render_dpi / 72.0
    width_px = page_width_pt * base
    height_px = page_height_pt * base
    pixels = max(width_px * height_px, 1.0)
    if pixels > settings.max_render_pixels:
        scale = math.sqrt(settings.max_render_pixels / pixels)
        return max(base * scale, 1.0 / 72.0)
    return base


def _build_blocks(page: "fitz.Page") -> list[TextBlock]:
    blocks: list[TextBlock] = []
    for block in page.get_text("blocks"):
        # block = (x0, y0, x1, y1, text, block_no, block_type)
        if len(block) >= 7 and block[6] != 0:
            continue  # skip non-text (image) blocks
        x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
        if text and text.strip():
            blocks.append(TextBlock(x0, y0, x1, y1, text))
    return blocks


def _process_single_page(
    *,
    project_id: UUID,
    job_id: UUID,
    document: "fitz.Document",
    page_index: int,
    seen_checksums: dict[str, str],
) -> dict:
    """Process one page and return the sheet record dict that was inserted."""
    pdf_page_number = page_index + 1
    page_start = time.perf_counter()
    sheet_id = uuid4()
    page = document.load_page(page_index)
    pix = None
    thumb = None
    try:
        width_pt = float(page.rect.width)
        height_pt = float(page.rect.height)
        rotation = int(page.rotation)

        # 1) Embedded text + normalization + artifact.
        raw_text = page.get_text("text") or ""
        text = _normalize_text(raw_text)
        text_char_count = len(text.strip())

        page_directory = storage.page_dir(project_id, pdf_page_number)
        text_path = page_directory / "text.txt"
        storage.atomic_write_text(text_path, text)

        # 2) Full-resolution render (with decompression-bomb guard) + checksum.
        zoom = _render_zoom(width_pt, height_pt)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        page_sha256 = hashlib.sha256(pix.samples).hexdigest()
        full_path = page_directory / "full.png"
        storage.atomic_write_bytes(full_path, pix.tobytes("png"))

        # 3) Thumbnail render.
        thumb_zoom = min(
            settings.thumbnail_max_width / max(width_pt, 1.0), zoom
        )
        thumb = page.get_pixmap(matrix=fitz.Matrix(thumb_zoom, thumb_zoom), alpha=False)
        thumb_path = page_directory / "thumbnail.png"
        storage.atomic_write_bytes(thumb_path, thumb.tobytes("png"))

        # 4) Duplicate detection (exact visual match within this project).
        duplicate_of = seen_checksums.get(page_sha256)
        if duplicate_of is None:
            seen_checksums[page_sha256] = str(sheet_id)

        # 5) Deterministic sheet-number / title candidate detection.
        blocks = _build_blocks(page)
        number_result = detect_sheet_number(
            text, blocks=blocks, page_width=width_pt, page_height=height_pt
        )
        detected_number = number_result.detected_value
        detected_title = detect_sheet_title(
            text,
            blocks=blocks,
            page_width=width_pt,
            page_height=height_pt,
            sheet_number=detected_number,
        )

        # 6) OCR flag for image-only / scanned pages.
        requires_ocr = text_char_count < settings.min_text_chars

        requires_review = bool(
            number_result.requires_review or detected_title is None or requires_ocr
        )

        record = {
            "id": str(sheet_id),
            "project_id": str(project_id),
            "job_id": str(job_id),
            "pdf_page_number": pdf_page_number,
            "page_index": page_index,
            "detected_sheet_number": detected_number,
            "verified_sheet_number": None,
            "detected_sheet_title": detected_title,
            "verified_sheet_title": None,
            "detection_confidence": number_result.confidence,
            "requires_review": 1 if requires_review else 0,
            "requires_ocr": 1 if requires_ocr else 0,
            "text_char_count": text_char_count,
            "page_width_points": width_pt,
            "page_height_points": height_pt,
            "rotation": rotation,
            "page_sha256": page_sha256,
            "duplicate_of_sheet_id": duplicate_of,
            "full_image_path": storage.relative_to_data_root(full_path),
            "thumbnail_path": storage.relative_to_data_root(thumb_path),
            "text_path": storage.relative_to_data_root(text_path),
            "processing_status": PageProcessingStatus.COMPLETE.value,
            "processing_error": None,
            "review_status": SheetReviewStatus.PENDING.value,
            "review_notes": None,
            "verified_at": None,
        }
        inserted = insert_sheet(record)
        logger.info(
            "page processed project_id=%s job_id=%s page=%s duration_ms=%.1f "
            "status=success requires_review=%s requires_ocr=%s",
            project_id, job_id, pdf_page_number,
            (time.perf_counter() - page_start) * 1000,
            requires_review, requires_ocr,
        )
        return inserted
    except Exception as exc:  # isolate a single bad page; never leak details
        logger.warning(
            "page processed project_id=%s job_id=%s page=%s duration_ms=%.1f "
            "status=failed error_code=page_processing_failed",
            project_id, job_id, pdf_page_number,
            (time.perf_counter() - page_start) * 1000,
        )
        record = {
            "id": str(sheet_id),
            "project_id": str(project_id),
            "job_id": str(job_id),
            "pdf_page_number": pdf_page_number,
            "page_index": page_index,
            "requires_review": 1,
            "requires_ocr": 0,
            "text_char_count": 0,
            "rotation": 0,
            # No artifact paths recorded for a failed page.
            "processing_status": PageProcessingStatus.FAILED.value,
            "processing_error": "Page could not be processed",
            "review_status": SheetReviewStatus.PENDING.value,
        }
        return insert_sheet(record)
    finally:
        if pix is not None:
            pix = None
        if thumb is not None:
            thumb = None
        page = None


def _write_manifest(
    project_id: UUID, job_id: UUID, sheets: list[dict], counts: dict
) -> None:
    """Write a deterministic, machine-specific-path-free processing manifest."""
    manifest = {
        "project_id": str(project_id),
        "job_id": str(job_id),
        "generated_at": _now_iso(),
        "render_dpi": settings.render_dpi,
        "thumbnail_max_width": settings.thumbnail_max_width,
        "counts": counts,
        "sheets": [
            {
                "sheet_id": s["id"],
                "pdf_page_number": s["pdf_page_number"],
                "detected_sheet_number": s.get("detected_sheet_number"),
                "detected_sheet_title": s.get("detected_sheet_title"),
                "detection_confidence": s.get("detection_confidence"),
                "requires_review": bool(s.get("requires_review")),
                "requires_ocr": bool(s.get("requires_ocr")),
                "duplicate_of_sheet_id": s.get("duplicate_of_sheet_id"),
                "processing_status": s.get("processing_status"),
                "full_image_path": s.get("full_image_path"),
                "thumbnail_path": s.get("thumbnail_path"),
                "text_path": s.get("text_path"),
            }
            for s in sheets
        ],
    }
    manifest_path = storage.processed_dir(project_id) / "manifest.json"
    storage.atomic_write_text(
        manifest_path, json.dumps(manifest, indent=2, sort_keys=True)
    )


def process_project(project_id: UUID, job_id: UUID) -> dict:
    """Run deterministic ingestion for a project. Returns a result summary.

    Idempotent: it clears any prior sheets and generated artifacts before
    processing, so repeated/forced runs never duplicate records or files. The
    original uploaded PDF is never modified.
    """
    job_start = time.perf_counter()
    project = get_project(project_id)
    if project is None:
        raise ProcessingError("project_not_found", "Project not found")

    update_job(
        job_id, status=JobStatus.PROCESSING.value, started_at=_now_iso()
    )
    update_project_status(project_id, ProjectStatus.PROCESSING)

    try:
        pdf_path = Path(project["stored_file_path"])
        if not pdf_path.exists():
            raise ProcessingError(
                "missing_original_pdf",
                "The original uploaded PDF could not be found",
            )

        # Idempotency: clear prior sheet rows and regenerate artifacts only.
        delete_sheets_for_project(project_id)
        storage.reset_processed_dir(project_id)

        sheets: list[dict] = []
        seen_checksums: dict[str, str] = {}
        counts = {
            "pages_discovered": 0,
            "pages_completed": 0,
            "pages_failed": 0,
            "pages_requiring_ocr": 0,
            "pages_requiring_review": 0,
            "duplicate_pages": 0,
        }

        with fitz.open(pdf_path) as document:
            page_count = document.page_count
            if page_count > settings.max_page_count:
                raise ProcessingError(
                    "too_many_pages",
                    f"PDF exceeds the maximum of {settings.max_page_count} pages",
                )
            counts["pages_discovered"] = page_count
            update_job(job_id, pages_discovered=page_count)

            for page_index in range(page_count):
                sheet = _process_single_page(
                    project_id=project_id,
                    job_id=job_id,
                    document=document,
                    page_index=page_index,
                    seen_checksums=seen_checksums,
                )
                sheets.append(sheet)
                if sheet["processing_status"] == PageProcessingStatus.COMPLETE.value:
                    counts["pages_completed"] += 1
                else:
                    counts["pages_failed"] += 1
                if sheet.get("requires_ocr"):
                    counts["pages_requiring_ocr"] += 1
                if sheet.get("requires_review"):
                    counts["pages_requiring_review"] += 1
                if sheet.get("duplicate_of_sheet_id"):
                    counts["duplicate_pages"] += 1

        _write_manifest(project_id, job_id, sheets, counts)

        duration_ms = int((time.perf_counter() - job_start) * 1000)
        update_job(
            job_id,
            status=JobStatus.SUCCEEDED.value,
            pages_discovered=counts["pages_discovered"],
            pages_completed=counts["pages_completed"],
            pages_failed=counts["pages_failed"],
            pages_requiring_ocr=counts["pages_requiring_ocr"],
            pages_requiring_review=counts["pages_requiring_review"],
            duration_ms=duration_ms,
            completed_at=_now_iso(),
            error_code=None,
            error_message=None,
        )
        update_project_status(project_id, ProjectStatus.READY_FOR_REVIEW)
        logger.info(
            "job complete project_id=%s job_id=%s duration_ms=%s status=success "
            "pages=%s failed=%s",
            project_id, job_id, duration_ms,
            counts["pages_completed"], counts["pages_failed"],
        )
        return {"status": JobStatus.SUCCEEDED.value, "counts": counts,
                "duration_ms": duration_ms}

    except ProcessingError as exc:
        _fail_job(project_id, job_id, exc.code, exc.safe_message, job_start)
        return {"status": JobStatus.FAILED.value, "error_code": exc.code}
    except Exception:
        logger.exception(
            "job failed project_id=%s job_id=%s error_code=internal_error",
            project_id, job_id,
        )
        _fail_job(
            project_id, job_id, "internal_error", "Processing failed", job_start
        )
        return {"status": JobStatus.FAILED.value, "error_code": "internal_error"}


def _fail_job(
    project_id: UUID, job_id: UUID, code: str, message: str, job_start: float
) -> None:
    duration_ms = int((time.perf_counter() - job_start) * 1000)
    update_job(
        job_id,
        status=JobStatus.FAILED.value,
        error_code=code,
        error_message=message,
        duration_ms=duration_ms,
        completed_at=_now_iso(),
    )
    # Best-effort project transition to failed.
    try:
        update_project_status(project_id, ProjectStatus.FAILED, error_message=message)
    except Exception:
        logger.exception("could not transition project to failed project_id=%s", project_id)
