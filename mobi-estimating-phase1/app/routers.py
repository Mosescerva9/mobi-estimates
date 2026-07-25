"""API routers: unversioned system probes and versioned (``/api/v1``) resources."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)

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
    get_project_by_portal_identity,
    get_project_by_sha256,
    update_project_status_for_tenant,
)
from app.schemas import ProjectStatus, ProjectStatusResponse
from app.services import storage
from app.services.packet_assembly import (
    PacketAssemblyError,
    PacketSource,
    assemble_packet,
)
from app.services.pdf_service import InvalidPDFError, inspect_pdf
from app.status_rules import InvalidStatusTransition
from app.tenant_boundary import (
    assert_request_matches_project_tenant,
    build_tenant_project_context,
    get_tenant_boundary_discovery,
    get_two_tenant_test_plan,
)

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


@system_router.get("/tenant-boundary")
def tenant_boundary_manifest() -> dict[str, object]:
    """Read-only tenant-boundary truth surface (audit P0-2).

    This manifest exposes the current tenant-isolation discovery and required
    two-tenant adversarial test plan without creating projects, reading artifacts,
    approving delivery, or implying release readiness. It intentionally reports a
    blocked posture until tenant-scoped identity is enforced end-to-end.
    """

    discovery = get_tenant_boundary_discovery()
    return {
        "tenant_boundary": discovery,
        "two_tenant_test_plan": get_two_tenant_test_plan(),
        "release_posture": {
            "tenant_isolation_ready": discovery["tenant_isolation_ready"],
            "release_start_allowed": discovery["release_start_allowed"],
            "status": discovery["status"],
            "reason": (
                "GPT-5.6 Sol audit PAUSE AND REPAIR: end-to-end tenant identity, "
                "storage/object isolation, queue/cache isolation, and model-call "
                "tenant context are not fully proven."
            ),
        },
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
) -> tuple[str, str]:
    """Return required tenant/company identity for new project creation.

    Upload is the canonical entry point for normal engine projects, so it must
    fail closed before file persistence or DB insert when tenant identity is
    absent. Allowing ``None`` here creates tenantless rows that can later be
    reached by UUID-only project routes.
    """
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
    project_dir = storage.project_dir(
        project_id,
        tenant_id=tenant_id,
        company_id=company_id,
    )
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
            stored_file_path=storage.relative_to_data_root(destination),
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


def _parse_packet_sources_metadata(raw: str | None, count: int) -> list[dict[str, object]]:
    """Parse the optional per-source metadata array aligned to the plans list.

    The array (if provided) must be JSON and exactly parallel to the uploaded
    files by index. It carries only portal identity (project_file_id,
    storage_path, order, declared_sha256) — never a filesystem path or secret.
    """
    if raw is None or raw.strip() == "":
        return [{} for _ in range(count)]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sources_metadata is not valid JSON") from exc
    if not isinstance(parsed, list) or len(parsed) != count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sources_metadata must be a JSON array parallel to the uploaded plans",
        )
    normalized: list[dict[str, object]] = []
    for entry in parsed:
        if entry is None:
            normalized.append({})
        elif isinstance(entry, dict):
            normalized.append(entry)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="each sources_metadata entry must be an object or null",
            )
    return normalized


@projects_router.post(
    "/upload-packet",
    status_code=status.HTTP_201_CREATED,
)
async def upload_packet(
    request: Request,
    project_name: str = Form(..., min_length=1, max_length=255),
    portal_project_id: str = Form(..., min_length=1, max_length=255),
    contractor_name: str | None = Form(default=None, max_length=255),
    expected_engine_project_id: str | None = Form(default=None, max_length=64),
    plans: list[UploadFile] = File(..., description="Accepted PDF plan/spec/addendum set"),
    sources_metadata: str | None = Form(default=None),
    x_mobi_tenant_id: str | None = Header(default=None),
    x_mobi_company_id: str | None = Header(default=None),
) -> dict[str, object]:
    """Deterministically merge every accepted PDF into ONE engine project packet.

    This is the multi-document analogue of ``/upload``. The four-file customer
    package (project manual, drawings, addenda) is assembled into a single packet
    PDF that becomes the project's one stored document, so the existing
    single-document engine model and the OpenTakeoff worker's
    ``document_id == engine_project_id`` + SHA-256 identity contract are both
    preserved. A source manifest recording per-source identity, bytes, SHA-256,
    page count, and contiguous packet page range is stored server-side alongside
    the packet. It never runs extraction, takeoff, or pricing.

    Engine-project reuse is keyed on the immutable ``portal_project_id`` (the
    originating portal project), never on packet content or project name:

    * same portal project + same packet SHA -> idempotent reuse of one engine id;
    * same portal project + a DIFFERENT packet -> 409, the established link is
      never silently replaced;
    * different portal projects + identical packet -> distinct engine ids;
    * ``expected_engine_project_id`` that does not match the stored link -> 409.
    """
    portal_project_id = portal_project_id.strip()
    if not portal_project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="portal_project_id is required")
    expected_engine_project_id = _optional_str(expected_engine_project_id)

    # Resolve tenant/company identity FIRST, before any body is read or any PDF
    # is parsed/merged. A request that cannot establish a tenant scope must not
    # be able to drive multi-file reads and PyMuPDF assembly work at all, and the
    # engine-project id every downstream check is keyed on is minted here.
    project_id = uuid4()
    tenant_id, company_id = _tenant_identity_from_headers(
        x_mobi_tenant_id, x_mobi_company_id, project_id
    )

    if not plans:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one PDF plan file is required")

    # Resource-limit preflight BEFORE any file read: reject an over-count package
    # and an over-large declared body (Content-Length may be absent/forged, so it
    # is only a coarse early guard — per-file/aggregate byte limits are still
    # enforced while streaming below).
    if len(plans) > settings.max_packet_files:
        raise HTTPException(
            status_code=413,
            detail=f"Packet has {len(plans)} files but the limit is {settings.max_packet_files}.",
        )
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            if int(declared_length) > settings.max_packet_output_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Declared request body exceeds the {settings.max_packet_output_bytes} "
                        "byte packet limit"
                    ),
                )
        except ValueError:
            pass  # malformed Content-Length is ignored; streaming limits still apply

    metadata = _parse_packet_sources_metadata(sources_metadata, len(plans))

    # Read every uploaded file into memory, enforcing BOTH the per-source and the
    # aggregate byte limits as we stream so a large multi-file submission fails
    # closed early rather than after unbounded reads.
    packet_sources: list[PacketSource] = []
    total_bytes = 0
    try:
        for index, plan in enumerate(plans):
            original_name = Path(plan.filename or f"document-{index + 1}.pdf").name
            if Path(original_name).suffix.lower() != ".pdf":
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Only PDF files are supported; '{original_name}' is not a PDF",
                )
            buffer = bytearray()
            source_bytes = 0
            while chunk := await plan.read(settings.upload_chunk_bytes):
                source_bytes += len(chunk)
                total_bytes += len(chunk)
                if source_bytes > settings.max_packet_source_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Source '{original_name}' exceeds the "
                            f"{settings.max_packet_source_bytes} byte per-file limit"
                        ),
                    )
                if total_bytes > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Combined packet exceeds the {settings.max_upload_bytes} byte upload limit",
                    )
                buffer.extend(chunk)
            entry = metadata[index]
            packet_sources.append(
                PacketSource(
                    original_filename=original_name,
                    data=bytes(buffer),
                    project_file_id=_optional_str(entry.get("project_file_id")),
                    storage_path=_optional_str(entry.get("storage_path")),
                    order=_optional_int(entry.get("order"), default=index),
                    declared_sha256=_optional_str(entry.get("declared_sha256")),
                )
            )
    finally:
        for plan in plans:
            await plan.close()

    try:
        assembled = assemble_packet(
            packet_sources,
            max_files=settings.max_packet_files,
            max_total_bytes=settings.max_upload_bytes,
            max_source_pages=settings.max_packet_source_pages,
            max_total_pages=settings.max_packet_pages,
            max_output_bytes=settings.max_packet_output_bytes,
        )
    except PacketAssemblyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

    # Portal-identity reuse/conflict resolution. This replaces content-only
    # dedup: identical documents under two different portal projects must NOT
    # collapse to one engine project.
    existing = get_project_by_portal_identity(
        portal_project_id, tenant_id=tenant_id, company_id=company_id
    )
    if existing is not None:
        existing_id = str(existing["id"])
        if expected_engine_project_id is not None and expected_engine_project_id != existing_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "expected_engine_project_id does not match the engine project already "
                    f"linked to this portal project (linked={existing_id})."
                ),
            )
        # Verify the STORED packet SHA before reusing: same portal + same packet is
        # idempotent; same portal + a different packet is a hard conflict.
        if existing.get("file_sha256") == assembled.packet_sha256:
            response = _status_response(existing).model_dump(mode="json")
            response["portal_project_id"] = portal_project_id
            response["packet_manifest"] = _load_stored_manifest(
                UUID(existing_id), tenant_id=tenant_id, company_id=company_id
            ) or assembled.manifest
            response["idempotent_reuse"] = True
            return response
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This portal project is already linked to a different engine packet; "
                "the established link is not replaced."
            ),
        )

    if expected_engine_project_id is not None:
        # A retry that expected an existing engine link but none exists for this
        # portal identity must fail closed rather than silently create a new one.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "expected_engine_project_id was supplied but no engine project is linked "
                "to this portal project."
            ),
        )

    project_dir = storage.project_dir(project_id, tenant_id=tenant_id, company_id=company_id)
    project_dir.mkdir(parents=True, exist_ok=False)
    destination = project_dir / "original.pdf"
    try:
        destination.write_bytes(assembled.packet_bytes)
        # Persist the manifest server-side next to the packet. It is engine-written
        # (never a client-supplied blob) and carries no source content or secrets.
        (project_dir / "packet_manifest.json").write_text(
            json.dumps(assembled.manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        packet_name = f"{project_name} — combined packet.pdf"[:255]
        row = create_project(
            project_id=project_id,
            name=project_name,
            contractor_name=contractor_name,
            original_file_name=packet_name,
            stored_file_path=storage.relative_to_data_root(destination),
            status=ProjectStatus.UPLOADED.value,
            page_count=assembled.page_count,
            file_sha256=assembled.packet_sha256,
            file_size_bytes=len(assembled.packet_bytes),
            tenant_id=tenant_id,
            company_id=company_id,
            portal_project_id=portal_project_id,
        )
    except HTTPException:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise
    except sqlite3.IntegrityError as exc:
        # Only the uq_projects_portal_identity index -- a concurrent send that
        # won the (tenant, company, portal_project_id) race -- is resolvable as a
        # reuse/conflict here. Any OTHER integrity failure is a real defect and
        # must not be dressed up as portal contention; it falls through to the
        # 500 handler so the failure stays visible.
        if "projects.portal_project_id" not in str(exc):
            shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to store the assembled packet",
            ) from exc
        # Resolve idempotently: reuse if the winner's packet matches, else 409.
        # Never overwrite the established link.
        shutil.rmtree(project_dir, ignore_errors=True)
        winner = get_project_by_portal_identity(
            portal_project_id, tenant_id=tenant_id, company_id=company_id
        )
        if winner is not None and winner.get("file_sha256") == assembled.packet_sha256:
            response = _status_response(winner).model_dump(mode="json")
            response["portal_project_id"] = portal_project_id
            response["packet_manifest"] = _load_stored_manifest(
                UUID(str(winner["id"])), tenant_id=tenant_id, company_id=company_id
            ) or assembled.manifest
            response["idempotent_reuse"] = True
            return response
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This portal project was concurrently linked to a different engine packet.",
        )
    except Exception as exc:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to store the assembled packet",
        ) from exc

    response = _status_response(row).model_dump(mode="json")
    response["portal_project_id"] = portal_project_id
    response["packet_manifest"] = assembled.manifest
    response["idempotent_reuse"] = False
    return response


def _load_stored_manifest(
    project_id: UUID, *, tenant_id: str, company_id: str
) -> dict[str, object] | None:
    """Read the engine-written packet manifest for an existing project, if present."""
    try:
        manifest_path = storage.project_dir(
            project_id, tenant_id=tenant_id, company_id=company_id
        ) / "packet_manifest.json"
        if not manifest_path.exists():
            return None
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


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
        row = update_project_status_for_tenant(
            project_id,
            new_status,
            tenant_id=x_mobi_tenant_id,
            company_id=x_mobi_company_id,
            error_message=error_message,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
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
