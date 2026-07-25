"""Deterministic multi-document PDF packet assembly.

The Phase 1 engine models ONE stored PDF per project and the OpenTakeoff worker
resolves a document by ``document_id == engine_project_id`` whose SHA-256 must
match ``projects.file_sha256``. A real solicitation package, however, arrives as
several accepted PDFs (project manual, drawings, addenda). To cross that whole
package into a single engine project without breaking the single-document /
worker-identity contract, we deterministically merge every accepted source PDF
into ONE packet PDF and carry a source manifest that preserves each source's
identity, byte count, SHA-256, page count, and contiguous page range inside the
packet.

This module is intentionally pure: it operates on in-memory bytes only, never
touches the database, storage, network, or any customer-delivery / message /
payment surface, and never silently omits a source. It is a document-ingestion
assembly primitive, NOT a takeoff, quantity, pricing, or final-estimate step.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import fitz  # PyMuPDF

# Bumped only on a breaking manifest-shape change; readers pin on this exact value.
PACKET_SCHEMA_VERSION = "engine_packet_v1"

# Conservative structural limits. A single solicitation package is a handful of
# documents; a far larger count is far more likely a bug or abuse than a real
# package, so we fail closed rather than assemble an unbounded packet.
DEFAULT_MAX_PACKET_FILES = 24

# PDF magic every source must begin with before any parser work.
_PDF_MAGIC = b"%PDF-"

_SHA256_HEX_LEN = 64


class PacketAssemblyError(ValueError):
    """A packet could not be safely assembled. ``code`` is a stable slug."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class PacketSource:
    """One accepted source PDF and its portal-side identity.

    ``data`` is the raw source bytes. ``project_file_id`` / ``storage_path`` are
    the portal's authoritative identifiers when available (they may be ``None``
    for a local/offline source). ``order`` optionally pins deterministic
    position; ``declared_sha256`` is an optional client-declared digest that is
    cross-checked against the recomputed digest and never trusted in its place.
    """

    original_filename: str
    data: bytes
    project_file_id: str | None = None
    storage_path: str | None = None
    order: int | None = None
    declared_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class AssembledPacket:
    packet_bytes: bytes
    manifest: dict[str, Any]

    @property
    def packet_sha256(self) -> str:
        return str(self.manifest["packet"]["sha256"])

    @property
    def page_count(self) -> int:
        return int(self.manifest["packet"]["page_count"])

    @property
    def source_count(self) -> int:
        return int(self.manifest["packet"]["source_count"])


def _validate_source_set(sources: list[PacketSource], *, max_files: int) -> None:
    if not sources:
        raise PacketAssemblyError("no_documents", "At least one source PDF is required to assemble a packet.")
    if len(sources) > max_files:
        raise PacketAssemblyError(
            "too_many_documents",
            f"Packet has {len(sources)} sources but the limit is {max_files}.",
        )

    seen_file_ids: set[str] = set()
    seen_storage_paths: set[str] = set()
    for source in sources:
        if not (source.original_filename or "").strip():
            raise PacketAssemblyError("missing_filename", "Every source PDF must have a non-empty filename.")
        if source.project_file_id is not None:
            if source.project_file_id in seen_file_ids:
                raise PacketAssemblyError(
                    "duplicate_project_file_id",
                    f"Source project_file_id {source.project_file_id} appears more than once.",
                )
            seen_file_ids.add(source.project_file_id)
        if source.storage_path is not None:
            if source.storage_path in seen_storage_paths:
                raise PacketAssemblyError(
                    "duplicate_storage_path",
                    f"Source storage_path {source.storage_path} appears more than once.",
                )
            seen_storage_paths.add(source.storage_path)


def _canonical_order(sources: list[PacketSource], digests: list[str]) -> list[int]:
    """Return input indices in the deterministic assembly order.

    ``order`` values must be either all absent or all present-and-distinct; a
    partial set is ambiguous and fails closed. With explicit orders we sort by
    (order, filename, sha256); without, purely by (filename, sha256) so the
    result is a stable function of content alone.
    """

    have_order = [s.order is not None for s in sources]
    if any(have_order) and not all(have_order):
        raise PacketAssemblyError(
            "inconsistent_order",
            "Either every source must declare an explicit order or none may.",
        )
    if all(have_order):
        orders = [int(s.order) for s in sources]  # type: ignore[arg-type]
        if len(set(orders)) != len(orders):
            raise PacketAssemblyError("duplicate_order", "Explicit source order values must be distinct.")

    def sort_key(index: int) -> tuple[int, str, str]:
        source = sources[index]
        primary = int(source.order) if source.order is not None else 0
        return (primary, source.original_filename, digests[index])

    return sorted(range(len(sources)), key=sort_key)


def _inspect_source(source: PacketSource, digest: str) -> int:
    """Validate one source PDF's bytes and return its page count."""
    if not source.data:
        raise PacketAssemblyError("empty_document", f"Source '{source.original_filename}' is empty.")
    if not source.data.startswith(_PDF_MAGIC):
        raise PacketAssemblyError(
            "invalid_pdf_signature",
            f"Source '{source.original_filename}' does not have a valid PDF signature.",
        )
    if source.declared_sha256 is not None and source.declared_sha256.lower() != digest:
        raise PacketAssemblyError(
            "sha256_mismatch",
            f"Source '{source.original_filename}' bytes do not match its declared SHA-256.",
        )
    try:
        with fitz.open(stream=source.data, filetype="pdf") as document:
            if document.needs_pass or document.is_encrypted:
                raise PacketAssemblyError(
                    "encrypted_document",
                    f"Source '{source.original_filename}' is encrypted/password-protected.",
                )
            page_count = document.page_count
            if page_count < 1:
                raise PacketAssemblyError(
                    "empty_document",
                    f"Source '{source.original_filename}' contains no pages.",
                )
            return int(page_count)
    except PacketAssemblyError:
        raise
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises broad errors on corruption
        raise PacketAssemblyError(
            "corrupt_document",
            f"Source '{source.original_filename}' is not a readable PDF.",
        ) from exc


def assemble_packet(
    sources: list[PacketSource],
    *,
    max_files: int = DEFAULT_MAX_PACKET_FILES,
    max_total_bytes: int,
    max_source_pages: int = 2000,
    max_total_pages: int = 5000,
    max_output_bytes: int | None = None,
) -> AssembledPacket:
    """Deterministically merge accepted source PDFs into ONE packet + manifest.

    Every source is validated and included; a single unreadable/encrypted/empty
    source fails the whole assembly closed rather than silently dropping a PDF.
    The returned packet bytes are reproducible for a given input set and the
    manifest fully describes source and packet identity and page coverage.

    Resource limits are enforced before any expensive work: source count, source
    bytes, per-source and aggregate page counts, and the serialized output byte
    size. Any breach fails closed (no partial packet, no persistence).
    """

    _validate_source_set(sources, max_files=max_files)

    total_bytes = sum(len(s.data) for s in sources)
    if total_bytes > max_total_bytes:
        raise PacketAssemblyError(
            "packet_too_large",
            f"Combined source bytes {total_bytes} exceed the {max_total_bytes} byte packet limit.",
        )

    digests = [hashlib.sha256(s.data).hexdigest() for s in sources]
    page_counts = [_inspect_source(sources[i], digests[i]) for i in range(len(sources))]

    # Page-count guards bound PyMuPDF work and assembled output independent of
    # raw byte size (a small file can still expand to many pages).
    for source, page_count in zip(sources, page_counts):
        if page_count > max_source_pages:
            raise PacketAssemblyError(
                "source_too_many_pages",
                f"Source '{source.original_filename}' has {page_count} pages but the "
                f"per-source limit is {max_source_pages}.",
            )
    total_pages = sum(page_counts)
    if total_pages > max_total_pages:
        raise PacketAssemblyError(
            "packet_too_many_pages",
            f"Combined source pages {total_pages} exceed the {max_total_pages} page packet limit.",
        )

    ordering = _canonical_order(sources, digests)

    merged = fitz.open()
    manifest_sources: list[dict[str, Any]] = []
    next_start = 1
    try:
        for position, index in enumerate(ordering):
            source = sources[index]
            page_count = page_counts[index]
            with fitz.open(stream=source.data, filetype="pdf") as document:
                merged.insert_pdf(document)
            combined_start = next_start
            combined_end = combined_start + page_count - 1
            next_start = combined_end + 1
            manifest_sources.append(
                {
                    "order": position,
                    "project_file_id": source.project_file_id,
                    "original_filename": source.original_filename,
                    "storage_path": source.storage_path,
                    "source_sha256": digests[index],
                    "source_bytes": len(source.data),
                    "source_page_count": page_count,
                    "combined_page_start": combined_start,
                    "combined_page_end": combined_end,
                }
            )

        # Scrub metadata so packet bytes are a pure function of the ordered source
        # content — reproducible run to run (no creation date / random file id).
        merged.set_metadata({})
        try:
            merged.del_xml_metadata()
        except Exception:  # noqa: BLE001 - absent XMP metadata is fine
            pass
        packet_bytes = merged.tobytes(garbage=4, deflate=True, no_new_id=True)
        packet_page_count = merged.page_count
    finally:
        merged.close()

    if max_output_bytes is not None and len(packet_bytes) > max_output_bytes:
        raise PacketAssemblyError(
            "packet_output_too_large",
            f"Assembled packet is {len(packet_bytes)} bytes but the output limit is "
            f"{max_output_bytes}.",
        )

    _assert_page_coverage(manifest_sources, packet_page_count)

    packet_sha256 = hashlib.sha256(packet_bytes).hexdigest()
    manifest = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet": {
            "sha256": packet_sha256,
            "bytes": len(packet_bytes),
            "page_count": packet_page_count,
            "source_count": len(manifest_sources),
        },
        "sources": manifest_sources,
    }
    return AssembledPacket(packet_bytes=packet_bytes, manifest=manifest)


def _assert_page_coverage(manifest_sources: list[dict[str, Any]], packet_page_count: int) -> None:
    """Verify source ranges are contiguous and exactly cover the whole packet."""
    summed = sum(int(s["source_page_count"]) for s in manifest_sources)
    if summed != packet_page_count:
        raise PacketAssemblyError(
            "page_count_mismatch",
            f"Sum of source pages ({summed}) does not equal packet pages ({packet_page_count}).",
        )
    expected_start = 1
    for source in manifest_sources:
        if int(source["combined_page_start"]) != expected_start:
            raise PacketAssemblyError(
                "noncontiguous_pages",
                f"Source '{source['original_filename']}' does not start where the previous source ended.",
            )
        expected_start = int(source["combined_page_end"]) + 1
    if expected_start - 1 != packet_page_count:
        raise PacketAssemblyError(
            "incomplete_page_coverage",
            f"Source ranges cover {expected_start - 1} pages but the packet has {packet_page_count}.",
        )


def is_valid_sha256(value: str | None) -> bool:
    if not value or len(value) != _SHA256_HEX_LEN:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True
