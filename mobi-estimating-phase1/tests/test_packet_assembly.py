"""Regression coverage for deterministic multi-document packet assembly.

Covers ordering, corruption, missing docs, limits, manifest integrity, partial
failure, duplicate identity, and the /upload-packet endpoint that ingests an
assembled packet as ONE engine project (preserving the single-document + worker
identity contract).
"""

from __future__ import annotations

import hashlib
import json

import fitz
import pytest

from app.services.packet_assembly import (
    PACKET_SCHEMA_VERSION,
    AssembledPacket,
    PacketAssemblyError,
    PacketSource,
    assemble_packet,
)
from tests.conftest import (
    TEST_TENANT_HEADERS,
    make_corrupted_pdf,
    make_encrypted_pdf,
    make_valid_pdf,
)

BIG_LIMIT = 200 * 1024 * 1024


def _source(name: str, pages: int, **kwargs) -> PacketSource:
    return PacketSource(original_filename=name, data=make_valid_pdf(pages), **kwargs)


def _assemble(sources: list[PacketSource], **kwargs) -> AssembledPacket:
    kwargs.setdefault("max_total_bytes", BIG_LIMIT)
    return assemble_packet(sources, **kwargs)


# ---------------------------------------------------------------------------
# Manifest integrity + ordering
# ---------------------------------------------------------------------------
def test_manifest_integrity_and_contiguous_ranges():
    sources = [
        _source("a.pdf", 3, project_file_id="f1", storage_path="p/a.pdf", order=0),
        _source("b.pdf", 2, project_file_id="f2", storage_path="p/b.pdf", order=1),
        _source("c.pdf", 4, project_file_id="f3", storage_path="p/c.pdf", order=2),
    ]
    packet = _assemble(sources)

    assert packet.manifest["schema_version"] == PACKET_SCHEMA_VERSION
    assert packet.page_count == 9
    assert packet.manifest["packet"]["source_count"] == 3
    # Reopen the packet to prove it is a real, readable PDF.
    with fitz.open(stream=packet.packet_bytes, filetype="pdf") as doc:
        assert doc.page_count == 9

    ranges = [(s["combined_page_start"], s["combined_page_end"]) for s in packet.manifest["sources"]]
    assert ranges == [(1, 3), (4, 5), (6, 9)]
    # Contiguous coverage: every page belongs to exactly one source.
    covered = []
    for start, end in ranges:
        covered.extend(range(start, end + 1))
    assert covered == list(range(1, 10))
    assert sum(s["source_page_count"] for s in packet.manifest["sources"]) == packet.page_count

    first = packet.manifest["sources"][0]
    assert first["project_file_id"] == "f1"
    assert first["storage_path"] == "p/a.pdf"
    assert first["source_sha256"] == hashlib.sha256(sources[0].data).hexdigest()
    assert first["source_bytes"] == len(sources[0].data)


def test_assembly_is_deterministic():
    sources = [_source("a.pdf", 2, order=0), _source("b.pdf", 3, order=1)]
    first = _assemble(sources)
    second = _assemble(sources)
    assert first.packet_bytes == second.packet_bytes
    assert first.packet_sha256 == second.packet_sha256


def test_explicit_order_is_respected_over_input_order():
    # Provide input list out of intended order; explicit order pins assembly.
    sources = [
        _source("second.pdf", 5, order=1),
        _source("first.pdf", 2, order=0),
    ]
    packet = _assemble(sources)
    names = [s["original_filename"] for s in packet.manifest["sources"]]
    assert names == ["first.pdf", "second.pdf"]
    assert packet.manifest["sources"][0]["combined_page_start"] == 1
    assert packet.manifest["sources"][0]["source_page_count"] == 2


def test_orderless_sources_sort_deterministically_by_content():
    a = _source("z.pdf", 1)
    b = _source("a.pdf", 1)
    packet = _assemble([a, b])
    names = [s["original_filename"] for s in packet.manifest["sources"]]
    assert names == ["a.pdf", "z.pdf"]  # filename-sorted, order-independent


# ---------------------------------------------------------------------------
# Validation failures — never silently omit
# ---------------------------------------------------------------------------
def test_empty_source_list_rejected():
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble([])
    assert exc.value.code == "no_documents"


def test_too_many_documents_rejected():
    sources = [_source(f"{i}.pdf", 1, order=i) for i in range(5)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources, max_files=4)
    assert exc.value.code == "too_many_documents"


def test_duplicate_project_file_id_rejected():
    sources = [_source("a.pdf", 1, project_file_id="dup", order=0), _source("b.pdf", 1, project_file_id="dup", order=1)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources)
    assert exc.value.code == "duplicate_project_file_id"


def test_duplicate_storage_path_rejected():
    sources = [_source("a.pdf", 1, storage_path="p/x.pdf", order=0), _source("b.pdf", 1, storage_path="p/x.pdf", order=1)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources)
    assert exc.value.code == "duplicate_storage_path"


def test_empty_document_rejected():
    sources = [_source("a.pdf", 1, order=0), PacketSource(original_filename="b.pdf", data=b"", order=1)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources)
    assert exc.value.code == "empty_document"


def test_invalid_signature_rejected():
    sources = [_source("a.pdf", 1, order=0), PacketSource(original_filename="b.pdf", data=b"not a pdf", order=1)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources)
    assert exc.value.code == "invalid_pdf_signature"


def test_encrypted_document_rejected():
    sources = [
        _source("a.pdf", 1, order=0),
        PacketSource(original_filename="b.pdf", data=make_encrypted_pdf(), order=1),
    ]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources)
    assert exc.value.code == "encrypted_document"


def test_corrupt_document_rejected():
    sources = [
        _source("a.pdf", 1, order=0),
        PacketSource(original_filename="b.pdf", data=make_corrupted_pdf(), order=1),
    ]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources)
    assert exc.value.code == "corrupt_document"


def test_packet_over_total_size_limit_rejected():
    sources = [_source("a.pdf", 1, order=0), _source("b.pdf", 1, order=1)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources, max_total_bytes=10)
    assert exc.value.code == "packet_too_large"


def test_declared_sha256_mismatch_rejected():
    sources = [PacketSource(original_filename="a.pdf", data=make_valid_pdf(1), declared_sha256="0" * 64, order=0)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources)
    assert exc.value.code == "sha256_mismatch"


def test_declared_sha256_match_accepted():
    data = make_valid_pdf(1)
    digest = hashlib.sha256(data).hexdigest()
    sources = [PacketSource(original_filename="a.pdf", data=data, declared_sha256=digest, order=0)]
    packet = _assemble(sources)
    assert packet.manifest["sources"][0]["source_sha256"] == digest


def test_partial_order_rejected():
    sources = [_source("a.pdf", 1, order=0), _source("b.pdf", 1)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources)
    assert exc.value.code == "inconsistent_order"


# ---------------------------------------------------------------------------
# Endpoint: /upload-packet — ingest packet as one engine project
# ---------------------------------------------------------------------------
_PORTAL_COUNTER = 0


def _new_portal_id() -> str:
    global _PORTAL_COUNTER
    _PORTAL_COUNTER += 1
    return f"portal-project-{_PORTAL_COUNTER}"


def _upload_packet(
    client,
    files_meta,
    *,
    project_name="Multi-doc project",
    portal_project_id=None,
    expected_engine_project_id=None,
    headers=TEST_TENANT_HEADERS,
):
    files = [("plans", (name, data, "application/pdf")) for name, data, _ in files_meta]
    data = {
        "project_name": project_name,
        "portal_project_id": portal_project_id or _new_portal_id(),
    }
    if expected_engine_project_id is not None:
        data["expected_engine_project_id"] = expected_engine_project_id
    metadata = [meta for _, _, meta in files_meta]
    if any(metadata):
        data["sources_metadata"] = json.dumps(metadata)
    return client.post("/api/v1/projects/upload-packet", data=data, files=files, headers=headers)


def test_upload_packet_creates_single_project(client):
    resp = _upload_packet(
        client,
        [
            ("manual.pdf", make_valid_pdf(3), {"project_file_id": "f1", "order": 0}),
            ("drawings.pdf", make_valid_pdf(2), {"project_file_id": "f2", "order": 1}),
            ("addendum.pdf", make_valid_pdf(1), {"project_file_id": "f3", "order": 2}),
        ],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["page_count"] == 6
    manifest = body["packet_manifest"]
    assert manifest["packet"]["page_count"] == 6
    assert manifest["packet"]["source_count"] == 3
    assert [s["project_file_id"] for s in manifest["sources"]] == ["f1", "f2", "f3"]

    # The engine project's stored SHA-256 is the packet's — worker identity intact.
    project_id = body["project_id"]
    status_resp = client.get(f"/api/v1/projects/{project_id}/status", headers=TEST_TENANT_HEADERS)
    assert status_resp.status_code == 200
    assert status_resp.json()["file_sha256"] == manifest["packet"]["sha256"]
    assert status_resp.json()["page_count"] == 6


def test_upload_packet_fails_closed_on_one_corrupt_source(client):
    resp = _upload_packet(
        client,
        [
            ("good.pdf", make_valid_pdf(2), {"order": 0}),
            ("bad.pdf", make_corrupted_pdf(), {"order": 1}),
        ],
    )
    # A single unreadable source fails the whole assembly — never silently dropped.
    assert resp.status_code == 400, resp.text


def test_upload_packet_duplicate_packet_is_idempotent(client):
    # A deterministic packet re-upload must reuse the existing engine project,
    # not create a second linked engine id.
    files_meta = [
        ("manual.pdf", make_valid_pdf(3), {"order": 0}),
        ("drawings.pdf", make_valid_pdf(2), {"order": 1}),
    ]
    portal = "portal-idempotent"
    first = _upload_packet(client, files_meta, portal_project_id=portal)
    assert first.status_code == 201
    second = _upload_packet(client, files_meta, portal_project_id=portal)
    assert second.status_code == 201
    assert second.json()["project_id"] == first.json()["project_id"]
    assert second.json().get("idempotent_reuse") is True
    assert second.json()["packet_manifest"]["packet"]["sha256"] == first.json()["packet_manifest"]["packet"]["sha256"]


def test_upload_packet_requires_pdf_suffix(client):
    resp = _upload_packet(client, [("notes.txt", b"%PDF-1.4 x", {"order": 0})])
    assert resp.status_code == 415


def test_upload_packet_requires_portal_project_id(client):
    files = [("plans", ("a.pdf", make_valid_pdf(1), "application/pdf"))]
    resp = client.post(
        "/api/v1/projects/upload-packet",
        data={"project_name": "No portal id"},
        files=files,
        headers=TEST_TENANT_HEADERS,
    )
    assert resp.status_code == 422  # portal_project_id is a required form field


# ---------------------------------------------------------------------------
# Adversarial portal-project identity (blocker 1)
# ---------------------------------------------------------------------------
def test_different_portal_ids_same_packet_create_distinct_engine_ids(client):
    files_meta = [("a.pdf", make_valid_pdf(2), {"order": 0}), ("b.pdf", make_valid_pdf(1), {"order": 1})]
    first = _upload_packet(client, files_meta, portal_project_id="portal-A")
    second = _upload_packet(client, files_meta, portal_project_id="portal-B")
    assert first.status_code == 201 and second.status_code == 201
    # Identical documents, different portal projects => two distinct engine ids.
    assert first.json()["project_id"] != second.json()["project_id"]
    assert first.json()["file_sha256"] == second.json()["file_sha256"]
    assert second.json()["idempotent_reuse"] is False


def test_same_portal_id_different_packet_conflicts(client):
    portal = "portal-conflict"
    first = _upload_packet(client, [("a.pdf", make_valid_pdf(2), {"order": 0})], portal_project_id=portal)
    assert first.status_code == 201
    # Same portal project, a DIFFERENT packet => 409, established link untouched.
    second = _upload_packet(client, [("a.pdf", make_valid_pdf(5), {"order": 0})], portal_project_id=portal)
    assert second.status_code == 409, second.text


def test_expected_engine_id_mismatch_conflicts(client):
    portal = "portal-expected"
    first = _upload_packet(client, [("a.pdf", make_valid_pdf(2), {"order": 0})], portal_project_id=portal)
    assert first.status_code == 201
    resp = _upload_packet(
        client,
        [("a.pdf", make_valid_pdf(2), {"order": 0})],
        portal_project_id=portal,
        expected_engine_project_id="00000000-0000-0000-0000-000000000000",
    )
    assert resp.status_code == 409, resp.text


def test_expected_engine_id_without_existing_link_conflicts(client):
    resp = _upload_packet(
        client,
        [("a.pdf", make_valid_pdf(2), {"order": 0})],
        portal_project_id="portal-never-linked",
        expected_engine_project_id="00000000-0000-0000-0000-000000000000",
    )
    assert resp.status_code == 409, resp.text


def test_cross_tenant_same_portal_id_and_packet_do_not_leak(client):
    files_meta = [("a.pdf", make_valid_pdf(2), {"order": 0})]
    portal = "shared-portal-id"
    first = _upload_packet(client, files_meta, portal_project_id=portal, headers=TEST_TENANT_HEADERS)
    assert first.status_code == 201
    other_headers = {
        **TEST_TENANT_HEADERS,
        "X-Mobi-Tenant-Id": "other-tenant",
        "X-Mobi-Company-Id": "other-company",
    }
    second = _upload_packet(client, files_meta, portal_project_id=portal, headers=other_headers)
    # Different tenant/company: same portal id + same packet must not reuse/leak.
    assert second.status_code == 201, second.text
    assert second.json()["project_id"] != first.json()["project_id"]


# ---------------------------------------------------------------------------
# Adversarial resource limits (blocker 5)
# ---------------------------------------------------------------------------
def test_upload_packet_over_file_count_rejected(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_packet_files", 2)
    files_meta = [(f"{i}.pdf", make_valid_pdf(1), {"order": i}) for i in range(3)]
    resp = _upload_packet(client, files_meta)
    assert resp.status_code == 413, resp.text


def test_assemble_over_source_pages_rejected():
    sources = [_source("a.pdf", 4, order=0)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources, max_source_pages=3)
    assert exc.value.code == "source_too_many_pages"


def test_assemble_over_total_pages_rejected():
    sources = [_source("a.pdf", 3, order=0), _source("b.pdf", 3, order=1)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources, max_total_pages=5)
    assert exc.value.code == "packet_too_many_pages"


def test_assemble_over_output_bytes_rejected():
    sources = [_source("a.pdf", 2, order=0)]
    with pytest.raises(PacketAssemblyError) as exc:
        _assemble(sources, max_output_bytes=10)
    assert exc.value.code == "packet_output_too_large"
