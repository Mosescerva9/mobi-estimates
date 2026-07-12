"""Artifact storage layout and safe, atomic filesystem helpers.

Tenant-scoped uploads and generated artifacts live under
``<data_root>/tenants/<tenant_id>/companies/<company_id>/projects/<project_uuid>/``.
Legacy project-only helpers remain available for older local rows/tests, but new
customer-facing call sites should pass tenant/company identity so object paths do
not become a tenantless UUID namespace. Paths stored in the database are always
*relative* to the data root so they stay portable across machines and containers.
Every read path is resolved strictly inside the data root to prevent path
traversal.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from app.config import settings
from app.tenant_boundary import build_tenant_project_context


def data_root() -> Path:
    return settings.data_root.resolve()


def _path_component(value: str) -> str:
    """Encode untrusted identity text into one filesystem path segment.

    ``urllib.parse.quote`` intentionally leaves ``.`` unescaped, which would let
    ``..`` collapse path segments when a header value is used as a directory
    name. Percent-encode every UTF-8 byte instead so even dots, slashes, and
    backslashes are inert filename text.
    """

    return "".join(f"%{byte:02X}" for byte in value.encode("utf-8"))


def project_dir(
    project_id: UUID,
    *,
    tenant_id: str | None = None,
    company_id: str | None = None,
) -> Path:
    if tenant_id is None and company_id is None:
        return data_root() / str(project_id)
    context = build_tenant_project_context(
        tenant_id=tenant_id,
        company_id=company_id,
        project_id=str(project_id),
    )
    return (
        data_root()
        / "tenants"
        / _path_component(context["tenant_id"])
        / "companies"
        / _path_component(context["company_id"])
        / "projects"
        / context["project_id"]
    )


def processed_dir(
    project_id: UUID,
    *,
    tenant_id: str | None = None,
    company_id: str | None = None,
) -> Path:
    return project_dir(
        project_id,
        tenant_id=tenant_id,
        company_id=company_id,
    ) / "processed"


def sheets_dir(
    project_id: UUID,
    *,
    tenant_id: str | None = None,
    company_id: str | None = None,
) -> Path:
    return processed_dir(
        project_id,
        tenant_id=tenant_id,
        company_id=company_id,
    ) / "sheets"


def page_dirname(pdf_page_number: int) -> str:
    return f"page-{pdf_page_number:04d}"


def page_dir(
    project_id: UUID,
    pdf_page_number: int,
    *,
    tenant_id: str | None = None,
    company_id: str | None = None,
) -> Path:
    return sheets_dir(
        project_id,
        tenant_id=tenant_id,
        company_id=company_id,
    ) / page_dirname(pdf_page_number)


def relative_to_data_root(path: Path) -> str:
    """Return a forward-slash path relative to the data root for DB storage."""
    return path.resolve().relative_to(data_root()).as_posix()


def resolve_within_data_root(relative_path: str) -> Path:
    """Resolve a stored relative path to an absolute path inside the data root.

    Raises ``ValueError`` if the path escapes the data root (traversal attempt)
    or is absolute.
    """
    if not relative_path or relative_path.startswith(("/", "\\")):
        raise ValueError("Unsafe artifact path")
    root = data_root()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Resolved artifact path escapes the data root")
    return target


def reset_processed_dir(
    project_id: UUID,
    *,
    tenant_id: str | None = None,
    company_id: str | None = None,
) -> None:
    """Remove and recreate only the generated artifacts directory.

    The original uploaded PDF (a sibling of ``processed/``) is never touched.
    New tenant-scoped rows must pass tenant/company identity so cleanup cannot
    target another tenant's project-UUID directory.
    """
    target = processed_dir(
        project_id,
        tenant_id=tenant_id,
        company_id=company_id,
    )
    if target.exists():
        shutil.rmtree(target)
    (target / "sheets").mkdir(parents=True, exist_ok=True)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))
