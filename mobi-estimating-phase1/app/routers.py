"""API routers: unversioned system probes and versioned (``/api/v1``) resources."""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, Response, UploadFile, status

from app.capability_registry import (
    SUPPORTED_CUSTOMER_DELIVERY_TRADES,
    capability_gaps,
    get_capability_registry,
)
from app.config import settings
from app.database import (
    check_health,
    create_project,
    get_project,
    get_project_by_sha256,
    update_project_status,
)
from app.schemas import ProjectStatus, ProjectStatusResponse
from app.services.pdf_service import InvalidPDFError, inspect_pdf
from app.status_rules import InvalidStatusTransition
from app.tenant_boundary import assert_request_matches_project_tenant, build_tenant_project_context

system_router = APIRouter(tags=["system"])
projects_router = APIRouter(prefix="/projects", tags=["projects"])


@system_router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: the process is up and serving requests."""
    return {"status": "ok", "version": settings.app_version}


@system_router.get("/ready")
def ready(response: Response) -> dict[str, object]:
    """Readiness probe: dependencies (database, upload dir) are usable."""
    db_ok = check_health()
    uploads_ok = settings.upload_dir.exists() and settings.upload_dir.is_dir()
    ready_ = db_ok and uploads_ok
    if not ready_:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "ready": ready_,
        "checks": {"database": db_ok, "upload_dir": uploads_ok},
    }


@system_router.get("/capability-registry")
def capability_registry() -> dict[str, object]:
    """Read-only capability truth surface (audit P0-1).

    Returns the truthful capability registry plus an explicit, fail-closed
    customer-delivery-lock summary so docs and release checks can query current
    capability truth without creating, pricing, approving, or delivering an
    estimate. This endpoint accepts no input, mutates no database rows or files,
    sends no messages, and exposes no secrets. It reports capability state only;
    it never implies production readiness or accuracy validation.
    """
    registry = get_capability_registry()
    gaps = capability_gaps()
    final_delivery = registry["capabilities"]["final_customer_delivery"]
    delivery_lock = {
        "schema_version": "customer_delivery_lock_v1",
        "fail_closed": True,
        "final_customer_delivery_enabled": False,
        "final_customer_delivery_stage": final_delivery["stage"],
        "all_required_delivery_grade": registry["all_required_delivery_grade"],
        "supported_customer_delivery_trades": sorted(
            SUPPORTED_CUSTOMER_DELIVERY_TRADES
        ),
        "capability_gaps": gaps,
        "summary": (
            "Final customer estimate delivery is not enabled. This is an "
            "internal Phase-0 engine; no capability is delivery-grade and the "
            "delivery lock stays closed until every requirement is affirmatively "
            "satisfied."
        ),
    }
    release_posture = {
        "paid_automated_estimating": "no_go",
        "autonomous_final_estimate_delivery": "no_go",
        "broad_multi_trade_accuracy_claims": "no_go",
        "reason": "GPT-5.6 Sol audit PAUSE AND REPAIR: P0/P1 evidence gates remain open.",
        "final_delivery_requires": [
            "complete verified evidence",
            "accuracy-validated supported scope",
            "required internal reviews",
            "explicit owner approval",
        ],
    }
    return {
        "capability_registry": registry,
        "customer_delivery_lock": delivery_lock,
        "release_posture": release_posture,
    }


def _status_response(row: dict) -> ProjectStatusResponse:
    return ProjectStatusResponse.model_validate(
        {
            "project_id": UUID(row["id"]),
            "name": row["name"],
            "status": ProjectStatus(row["status"]),
            "original_file_name": row["original_file_name"],
            "page_count": row["page_count"],
            "file_sha256": row["file_sha256"],
            "file_size_bytes": row["file_size_bytes"],
            "created_at": datetime.fromisoformat(row["created_at"]),
            "updated_at": datetime.fromisoformat(row["updated_at"]),
            "error_message": row["error_message"],
        }
    )


def _tenant_identity_from_headers(
    tenant_id: str | None, company_id: str | None, project_id: UUID
) -> tuple[str | None, str | None]:
    if tenant_id is None and company_id is None:
        return (None, None)
    try:
        context = build_tenant_project_context(
            tenant_id=tenant_id,
            company_id=company_id,
            project_id=str(project_id),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    return (context["tenant_id"], context["company_id"])


def _enforce_project_tenant_headers(
    row: dict,
    tenant_id: str | None,
    company_id: str | None,
) -> None:
    try:
        assert_request_matches_project_tenant(
            project_row=row,
            request_tenant_id=tenant_id,
            request_company_id=company_id,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@projects_router.post(
    "/upload",
    response_model=ProjectStatusResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_plan(
    project_name: str = Form(..., min_length=1, max_length=255),
    contractor_name: str | None = Form(default=None, max_length=255),
    plan: UploadFile = File(..., description="PDF plan set"),
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> ProjectStatusResponse:
    """Save and validate a PDF plan set, then create the initial project record.

    This endpoint intentionally does not run extraction, takeoff, or pricing yet.
    """
    original_name = Path(plan.filename or "plans.pdf").name
    if Path(original_name).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF plan files are supported in Phase 1",
        )

    # Reject obviously wrong MIME types early. Browsers may send
    # 'application/octet-stream', so we accept that and rely on signature/parser
    # checks below; we only hard-reject clearly non-PDF content types.
    allowed_content_types = {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
        "binary/octet-stream",
        "",
        None,
    }
    if plan.content_type not in allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type '{plan.content_type}'; expected a PDF",
        )

    project_id = uuid4()
    tenant_id, company_id = _tenant_identity_from_headers(
        x_mobi_tenant_id, x_mobi_company_id, project_id
    )
    project_dir = settings.upload_dir / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=False)
    destination = project_dir / "original.pdf"

    bytes_written = 0
    digest = hashlib.sha256()
    try:
        with destination.open("wb") as output:
            while chunk := await plan.read(settings.upload_chunk_bytes):
                bytes_written += len(chunk)
                if bytes_written > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,  # Content Too Large (version-safe literal)
                        detail=(
                            f"PDF exceeds the {settings.max_upload_bytes} byte "
                            "upload limit"
                        ),
                    )
                digest.update(chunk)
                output.write(chunk)

        if bytes_written == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded PDF is empty",
            )

        # PDF signature check catches renamed non-PDF files before parser work.
        with destination.open("rb") as uploaded_file:
            if uploaded_file.read(5) != b"%PDF-":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file does not have a valid PDF signature",
                )

        file_sha256 = digest.hexdigest()

        # Duplicate detection is tenant-local only. Global file-hash checks can
        # reveal another customer's project UUID and block legitimate cross-tenant
        # uploads of the same plan/spec PDF.
        existing = get_project_by_sha256(
            file_sha256,
            tenant_id=tenant_id,
            company_id=company_id,
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "An identical PDF has already been uploaded "
                    "for this tenant/company context "
                    f"(project_id={existing['id']})"
                ),
            )

        metadata = inspect_pdf(destination)
        row = create_project(
            project_id=project_id,
            name=project_name,
            contractor_name=contractor_name,
            original_file_name=original_name,
            stored_file_path=str(destination),
            status=ProjectStatus.UPLOADED.value,
            page_count=metadata.page_count,
            file_sha256=file_sha256,
            file_size_bytes=bytes_written,
            tenant_id=tenant_id,
            company_id=company_id,
        )
        return _status_response(row)

    except HTTPException:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise
    except InvalidPDFError as exc:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to store the uploaded plan set",
        ) from exc
    finally:
        await plan.close()


@projects_router.get("/{project_id}/status", response_model=ProjectStatusResponse)
def project_status(
    project_id: UUID,
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> ProjectStatusResponse:
    row = get_project(project_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    _enforce_project_tenant_headers(row, x_mobi_tenant_id, x_mobi_company_id)
    return _status_response(row)


@projects_router.patch(
    "/{project_id}/status",
    response_model=ProjectStatusResponse,
)
def transition_project_status(
    project_id: UUID,
    new_status: ProjectStatus = Form(..., description="Target lifecycle status"),
    error_message: str | None = Form(default=None, max_length=1000),
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> ProjectStatusResponse:
    """Transition a project's status, enforcing lifecycle transition rules."""
    existing = get_project(project_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    _enforce_project_tenant_headers(existing, x_mobi_tenant_id, x_mobi_company_id)
    try:
        row = update_project_status(
            project_id, new_status, error_message=error_message
        )
    except InvalidStatusTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return _status_response(row)
