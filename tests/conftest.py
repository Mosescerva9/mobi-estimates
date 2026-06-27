"""Shared pytest fixtures.

Environment variables are set *before* the application is imported so the cached
``Settings`` singleton points at a throwaway temp directory. Each test then gets
its own isolated database and upload directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a temp location before importing anything that reads settings.
_BOOT_DIR = Path(tempfile.mkdtemp(prefix="mobi-boot-"))
os.environ.setdefault("MOBI_DB_PATH", str(_BOOT_DIR / "mobi.db"))
os.environ.setdefault("MOBI_UPLOAD_DIR", str(_BOOT_DIR / "uploads"))

import fitz  # noqa: E402  (import after env setup is intentional)
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# PDF builders
# ---------------------------------------------------------------------------
def make_valid_pdf(pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def make_encrypted_pdf(user_password: str = "secret") -> bytes:
    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw=user_password,
    )
    doc.close()
    return data


def make_corrupted_pdf() -> bytes:
    # Valid signature so it passes the cheap header check, but the body is
    # garbage that PyMuPDF cannot parse.
    return b"%PDF-1.4\nthis is not a real pdf body \x00\x01\x02"


@pytest.fixture
def valid_pdf_bytes() -> bytes:
    return make_valid_pdf(1)


@pytest.fixture
def multipage_pdf_bytes() -> bytes:
    return make_valid_pdf(3)


@pytest.fixture
def encrypted_pdf_bytes() -> bytes:
    return make_encrypted_pdf()


@pytest.fixture
def corrupted_pdf_bytes() -> bytes:
    return make_corrupted_pdf()


# ---------------------------------------------------------------------------
# Client / isolation
# ---------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """A TestClient backed by a fresh, isolated database and upload directory."""
    settings.db_path = tmp_path / "mobi.db"
    settings.upload_dir = tmp_path / "uploads"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    with TestClient(app) as test_client:
        yield test_client


def upload(client: TestClient, content: bytes, *, name: str = "plans.pdf",
           project_name: str = "Test Project",
           content_type: str = "application/pdf") -> "object":
    return client.post(
        "/api/v1/projects/upload",
        data={"project_name": project_name},
        files={"plan": (name, content, content_type)},
    )
