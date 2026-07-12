"""Phase 2 API: deterministic processing, sheet indexing, and artifact serving.

All routes are mounted under ``/api/v1`` by the application factory.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.config import settings
from app.database import (
    claim_processing_slot,
    get_job,
    get_latest_job,
    get_project,
    get_sheet,
    list_sheets,
    update_sheet_verification,
)
from app.processing_schemas import (
    ProcessingAcceptedResponse,
    ProcessingRequest,
    ProcessingStatusResponse,
    SheetDetail,
    SheetListResponse,
    SheetSummary,
    SheetVerificationRequest,
)
from app.schemas import SheetReviewStatus
from app.services import storage
from app.services.processing_service import (
    process_project,
    resolve_original_pdf_for_project,
    ProcessingError,
)
from app.tenant_boundary import assert_request_matches_project_tenant

processing_router = APIRouter(prefix="/projects", tags=["processing"])


def _require_project(
    project_id: UUID,
    *,
    tenant_id: str | None = None,
    company_id: str | None = None,
) -> dict:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    try:
        assert_request_matches_project_tenant(
            project_row=project,
            request_tenant_id=tenant_id,
            request_company_id=company_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return project


# ---------------------------------------------------------------------------
# Start processing
# ---------------------------------------------------------------------------
@processing_router.post(
    "/{project_id}/process",
    response_model=ProcessingAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_processing(
    project_id: UUID,
    background: BackgroundTasks,
    request: ProcessingRequest | None = None,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> ProcessingAcceptedResponse:
    project = _require_project(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )

    # The original PDF must exist and remain under this tenant/company/project
    # root before we start a job. ``stored_file_path`` is DB state and can drift.
    try:
        resolve_original_pdf_for_project(project)
    except ProcessingError as exc:
        if exc.code == "missing_original_pdf":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The original uploaded PDF is missing for this project",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Original uploaded PDF path does not match project tenant context",
        ) from exc

    force = request.force if request is not None else False
    outcome, job, project = claim_processing_slot(project_id, force=force)

    if outcome == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    if outcome == "terminal":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project is complete and cannot be reprocessed",
        )
    if outcome == "already_processed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project already processed; pass force=true to reprocess",
        )
    if outcome == "invalid_state":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project status '{project['status']}' cannot start processing",
        )
    if outcome == "tenant_unscoped":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project tenant/company identity is required before processing",
        )

    if outcome == "active":
        # Idempotent: a job is already running; do not start another.
        return ProcessingAcceptedResponse(
            project_id=project_id,
            project_status=project["status"],
            job_id=job["id"],
            job_status=job["status"],
            message="Processing already in progress",
        )

    # outcome == "created": run the job.
    job_id = UUID(job["id"])
    if settings.process_inline:
        process_project(project_id, job_id)
        project = get_project(project_id)
        job = get_job(job_id)
    else:
        background.add_task(process_project, project_id, job_id)

    return ProcessingAcceptedResponse(
        project_id=project_id,
        project_status=project["status"],
        job_id=job["id"],
        job_status=job["status"],
        message="Processing started",
    )


# ---------------------------------------------------------------------------
# Processing status
# ---------------------------------------------------------------------------
@processing_router.get(
    "/{project_id}/processing-status",
    response_model=ProcessingStatusResponse,
)
def processing_status(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> ProcessingStatusResponse:
    project = _require_project(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
    job = get_latest_job(project_id)
    return ProcessingStatusResponse.from_rows(project, job)


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------
@processing_router.get(
    "/{project_id}/sheets",
    response_model=SheetListResponse,
)
def list_project_sheets(
    project_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> SheetListResponse:
    _require_project(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
    rows, total = list_sheets(project_id, limit=limit, offset=offset)
    return SheetListResponse(
        items=[SheetSummary.from_row(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@processing_router.get(
    "/{project_id}/sheets/{sheet_id}",
    response_model=SheetDetail,
)
def get_project_sheet(
    project_id: UUID,
    sheet_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> SheetDetail:
    _require_project(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
    sheet = get_sheet(project_id, sheet_id)
    if sheet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found"
        )
    base_url = f"{settings.api_v1_prefix}/projects/{project_id}/sheets/{sheet_id}"
    return SheetDetail.from_row(sheet, base_url=base_url)


@processing_router.patch(
    "/{project_id}/sheets/{sheet_id}/verification",
    response_model=SheetDetail,
)
def verify_project_sheet(
    project_id: UUID,
    sheet_id: UUID,
    body: SheetVerificationRequest,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> SheetDetail:
    _require_project(
        project_id,
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
    sheet = get_sheet(project_id, sheet_id)
    if sheet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found"
        )

    review_status = SheetReviewStatus(body.review_status)
    # A sheet still needs review unless it has been explicitly verified.
    requires_review = review_status != SheetReviewStatus.VERIFIED

    updated = update_sheet_verification(
        project_id,
        sheet_id,
        verified_sheet_number=body.verified_sheet_number,
        verified_sheet_title=body.verified_sheet_title,
        review_notes=body.review_notes,
        review_status=review_status.value,
        requires_review=requires_review,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found"
        )
    base_url = f"{settings.api_v1_prefix}/projects/{project_id}/sheets/{sheet_id}"
    return SheetDetail.from_row(updated, base_url=base_url)


# ---------------------------------------------------------------------------
# Artifact serving (controlled; resolves strictly inside the data root)
# ---------------------------------------------------------------------------
def _serve_artifact(
    project_id: UUID,
    sheet_id: UUID,
    column: str,
    *,
    tenant_id: str | None = None,
    company_id: str | None = None,
) -> FileResponse:
    project = _require_project(project_id, tenant_id=tenant_id, company_id=company_id)
    sheet = get_sheet(project_id, sheet_id)
    if sheet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Sheet not found"
        )
    relative_path = sheet.get(column)
    if not relative_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not available"
        )
    try:
        resolved = storage.resolve_within_data_root(relative_path)
        expected_project_artifact_root = storage.processed_dir(
            project_id,
            tenant_id=project.get("tenant_id"),
            company_id=project.get("company_id"),
        ).resolve()
    except (PermissionError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unsafe artifact path"
        )
    if not resolved.is_relative_to(expected_project_artifact_root):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Artifact path does not match project tenant context",
        )
    if not resolved.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file missing"
        )
    return FileResponse(resolved, media_type="image/png")


@processing_router.get("/{project_id}/sheets/{sheet_id}/thumbnail")
def get_sheet_thumbnail(
    project_id: UUID,
    sheet_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> FileResponse:
    return _serve_artifact(
        project_id,
        sheet_id,
        "thumbnail_path",
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )


@processing_router.get("/{project_id}/sheets/{sheet_id}/image")
def get_sheet_image(
    project_id: UUID,
    sheet_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> FileResponse:
    return _serve_artifact(
        project_id,
        sheet_id,
        "full_image_path",
        tenant_id=x_mobi_tenant_id,
        company_id=x_mobi_company_id,
    )
