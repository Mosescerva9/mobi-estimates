"""Artifact storage layout and safe, atomic filesystem helpers.

All generated artifacts live under ``<data_root>/<project_uuid>/processed/``.
Paths stored in the database are always *relative* to the data root so they stay
portable across machines and containers. Every read path is resolved strictly
inside the data root to prevent path traversal.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from app.config import settings


def data_root() -> Path:
    return settings.data_root.resolve()


def project_dir(project_id: UUID) -> Path:
    return data_root() / str(project_id)


def processed_dir(project_id: UUID) -> Path:
    return project_dir(project_id) / "processed"


def sheets_dir(project_id: UUID) -> Path:
    return processed_dir(project_id) / "sheets"


def page_dirname(pdf_page_number: int) -> str:
    return f"page-{pdf_page_number:04d}"


def page_dir(project_id: UUID, pdf_page_number: int) -> Path:
    return sheets_dir(project_id) / page_dirname(pdf_page_number)


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


def reset_processed_dir(project_id: UUID) -> None:
    """Remove and recreate only the generated artifacts directory.

    The original uploaded PDF (a sibling of ``processed/``) is never touched.
    """
    target = processed_dir(project_id)
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
