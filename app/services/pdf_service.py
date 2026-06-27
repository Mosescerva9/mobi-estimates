from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF


class InvalidPDFError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PDFMetadata:
    page_count: int
    is_encrypted: bool


def inspect_pdf(path: Path) -> PDFMetadata:
    """Open and validate a PDF without performing takeoff or pricing logic."""
    try:
        with fitz.open(path) as document:
            if document.needs_pass:
                raise InvalidPDFError("Password-protected PDFs are not supported")
            if document.page_count < 1:
                raise InvalidPDFError("The uploaded PDF contains no pages")
            return PDFMetadata(
                page_count=document.page_count,
                is_encrypted=bool(document.is_encrypted),
            )
    except InvalidPDFError:
        raise
    except Exception as exc:
        raise InvalidPDFError("The uploaded file is not a readable PDF") from exc
