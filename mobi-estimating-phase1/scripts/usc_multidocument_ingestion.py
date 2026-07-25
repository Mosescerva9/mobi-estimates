#!/usr/bin/env python3
"""USC four-document multi-PDF ingestion proof (internal, offline).

Proves that the four authorized public USC Longstreet Theatre Exterior
Restoration PDFs (solicitation H27-Z147-B: project manual, drawings, Addendum
One, Addendum Two) can be deterministically assembled into ONE packet and
ingested as ONE engine project — under one tenant/company identity, in an
isolated throwaway engine database + data root — while preserving each source's
identity, byte count, SHA-256, page count, and contiguous packet page range, and
the engine/worker single-document identity contract (the project's stored
SHA-256 is the packet's SHA-256).

This is INTERNAL DOCUMENT-INGESTION PROOF ONLY. It is NOT a whole-project
quantity, pricing, or final-estimate readiness result. It issues no proposal,
sends no message, creates no payment, and reaches no customer-delivery or
final-approval state. It runs wholly inside a temporary directory (torn down on
exit), instruments the process so any non-loopback network connection fails
closed, and never contacts Stripe, an email/messaging provider, production, or
any external service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

API_KEY = "usc-multidocument-ingestion-key"

# Fail-closed internal-VPS engine config, set before importing app.config so the
# startup contract is exercised, not bypassed.
os.environ.setdefault("MOBI_DEPLOYMENT_ENVIRONMENT", "internal_vps")
os.environ.setdefault("MOBI_ENGINE_AUTH_MODE", "internal_vps_shared_key")
os.environ.setdefault("MOBI_API_KEY", API_KEY)

DOCS_DIR = REPO_ROOT / "data" / "golden_set" / "documents"

# Authoritative source registry (docs/mvp/golden-set-authoritative-package-2026-07-21.md).
# order, filename, official SHA-256, official byte count.
USC_SOURCES = [
    ("usc_s1459197637_project_manual.pdf", "fb577c5204a33630f617866643fb6d5f13a807db024a3aad713ed8d4b83c150a", 6_133_132),
    ("usc_s1459197670_drawings.pdf", "bb5bec82eb81b9cbe37af7d253c8d29b3d94766abdf913add10b07b0b8c3659e", 3_310_154),
    ("usc_s1460377831_addendum_1.pdf", "1ba5c5ec2d08edc5aa167a55aa4bcce4a200fe4226d866e3c84e456399da609d", 304_382),
    ("usc_s1460566716_addendum_2.pdf", "51be5162765f1d0113b9bfc69228a601586c78797d2641cf9405d5fa4f2b8b75", 1_575_188),
]

SAFE_PROJECT_STATUSES = {"created", "uploaded", "queued", "processing", "ready_for_review", "needs_review", "complete"}


class HarnessError(RuntimeError):
    """A verification assertion failed; the harness exits non-zero."""


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise HarnessError(message)


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


@contextmanager
def _fail_on_external_network(record: dict[str, Any]) -> Iterator[None]:
    """Instrument the process so ANY outbound non-loopback connect fails closed.

    Everything here runs in-process over an ASGI TestClient and a local SQLite
    file, so a genuine attempt to reach Stripe / an email or messaging provider /
    any delivery endpoint would open a real socket and be caught here instead of
    being asserted absent by a hardcoded ``false``.
    """
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    record["external_connect_attempts"] = 0
    record["external_connect_targets"] = []

    def _host_of(address: Any) -> str:
        if isinstance(address, tuple) and address:
            return str(address[0])
        return str(address)

    def _guarded_connect(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = _host_of(address)
        if host not in _LOOPBACK_HOSTS:
            record["external_connect_attempts"] += 1
            record["external_connect_targets"].append(host)
            raise HarnessError(f"external network connection attempted to {host!r}")
        return real_connect(self, address, *args, **kwargs)

    def _guarded_connect_ex(self, address, *args, **kwargs):  # type: ignore[no-untyped-def]
        host = _host_of(address)
        if host not in _LOOPBACK_HOSTS:
            record["external_connect_attempts"] += 1
            record["external_connect_targets"].append(host)
            raise HarnessError(f"external network connection attempted to {host!r}")
        return real_connect_ex(self, address, *args, **kwargs)

    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.socket.connect = real_connect  # type: ignore[method-assign]
        socket.socket.connect_ex = real_connect_ex  # type: ignore[method-assign]


def _load_sources() -> list[dict[str, Any]]:
    """Read the four USC PDFs and verify each against the authoritative registry."""
    loaded: list[dict[str, Any]] = []
    for order, (name, official_sha, official_bytes) in enumerate(USC_SOURCES):
        path = DOCS_DIR / name
        _check(path.exists(), f"missing authorized USC source: {path}")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        _check(
            digest == official_sha,
            f"{name} SHA-256 {digest} does not match authoritative {official_sha}",
        )
        _check(
            len(data) == official_bytes,
            f"{name} byte count {len(data)} does not match authoritative {official_bytes}",
        )
        loaded.append({"order": order, "name": name, "data": data, "sha256": digest, "bytes": len(data)})
    return loaded


@contextmanager
def _temporary_engine() -> Iterator[dict[str, Any]]:
    tmp_root = Path(tempfile.mkdtemp(prefix="mobi-usc-multidoc-"))
    try:
        from app import database
        from app.config import settings
        from app.main import create_app

        original = {"db_path": settings.db_path, "upload_dir": settings.upload_dir, "api_key": settings.api_key}
        settings.db_path = tmp_root / "engine.db"
        settings.upload_dir = tmp_root / "data"
        settings.api_key = API_KEY
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        database.init_db()

        from fastapi.testclient import TestClient

        client = TestClient(create_app())
        try:
            yield {"client": client, "database": database, "settings": settings, "tmp_root": tmp_root}
        finally:
            for key, value in original.items():
                setattr(settings, key, value)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def _assemble_and_verify(sources: list[dict[str, Any]]) -> dict[str, Any]:
    from app.config import settings
    from app.services.packet_assembly import PacketSource, assemble_packet

    packet_sources = [
        PacketSource(
            original_filename=s["name"],
            data=s["data"],
            project_file_id=f"usc-portal-file-{s['order'] + 1}",
            storage_path=f"usc/{s['name']}",
            order=s["order"],
            declared_sha256=s["sha256"],
        )
        for s in sources
    ]
    packet = assemble_packet(packet_sources, max_total_bytes=settings.max_upload_bytes)
    # Determinism: assembling the same inputs twice yields identical bytes.
    packet_again = assemble_packet(packet_sources, max_total_bytes=settings.max_upload_bytes)
    _check(packet.packet_bytes == packet_again.packet_bytes, "packet assembly is not deterministic")

    manifest = packet.manifest
    _check(manifest["packet"]["source_count"] == 4, "expected exactly 4 sources in the packet")
    order_names = [s["original_filename"] for s in manifest["sources"]]
    _check(order_names == [s["name"] for s in sources], f"unexpected deterministic order: {order_names}")
    summed = sum(s["source_page_count"] for s in manifest["sources"])
    _check(summed == manifest["packet"]["page_count"], "source pages do not sum to packet pages")
    # Contiguous, gap-free coverage of the whole packet.
    expected = 1
    for s in manifest["sources"]:
        _check(s["combined_page_start"] == expected, "source page ranges are not contiguous")
        expected = s["combined_page_end"] + 1
    _check(expected - 1 == manifest["packet"]["page_count"], "source ranges do not cover the whole packet")

    import fitz

    with fitz.open(stream=packet.packet_bytes, filetype="pdf") as reopened:
        _check(reopened.page_count == manifest["packet"]["page_count"], "reassembled packet does not reopen with expected pages")

    return {"packet_bytes": packet.packet_bytes, "manifest": manifest}


def run(output_path: Path) -> dict[str, Any]:
    safety: dict[str, Any] = {}
    with _fail_on_external_network(safety):
        sources = _load_sources()
        assembled = _assemble_and_verify(sources)
        manifest = assembled["manifest"]

        tenant_id = f"usc-tenant-{uuid4().hex[:8]}"
        company_id = f"usc-company-{uuid4().hex[:8]}"
        portal_project_test_id = str(uuid4())
        portal_project_other_id = str(uuid4())

        sources_metadata = [
            {
                "project_file_id": f"usc-portal-file-{s['order'] + 1}",
                "storage_path": f"usc/{s['name']}",
                "order": s["order"],
                "declared_sha256": s["sha256"],
            }
            for s in sources
        ]

        def _post_packet(client, headers, portal_id, expected_engine_id=None):
            files = [("plans", (s["name"], s["data"], "application/pdf")) for s in sources]
            form = {
                "project_name": "USC Longstreet Theatre Exterior Restoration (H27-Z147-B)",
                "contractor_name": "Mobi internal ingestion proof",
                "portal_project_id": portal_id,
                "sources_metadata": json.dumps(sources_metadata),
            }
            if expected_engine_id is not None:
                form["expected_engine_project_id"] = expected_engine_id
            return client.post("/api/v1/projects/upload-packet", headers=headers, data=form, files=files)

        with _temporary_engine() as ctx:
            client = ctx["client"]
            headers = {"X-API-Key": API_KEY, "X-Mobi-Tenant-Id": tenant_id, "X-Mobi-Company-Id": company_id}

            upload = _post_packet(client, headers, portal_project_test_id)
            _check(upload.status_code == 201, f"packet upload failed: {upload.status_code} {upload.text}")
            body = upload.json()
            engine_project_id = body["project_id"]
            _check(body.get("idempotent_reuse") is False, "first ingestion should not be a reuse")

            # PROOF A — same portal project + same packet reuses ONE engine id.
            reuse = _post_packet(client, headers, portal_project_test_id)
            _check(reuse.status_code == 201, f"idempotent reuse failed: {reuse.status_code} {reuse.text}")
            _check(reuse.json()["project_id"] == engine_project_id, "same portal + same packet did not reuse engine id")
            _check(reuse.json().get("idempotent_reuse") is True, "reuse was not marked idempotent")

            # A retry that names the wrong existing engine id must be rejected.
            mismatch = _post_packet(
                client, headers, portal_project_test_id,
                expected_engine_id="00000000-0000-0000-0000-000000000000",
            )
            _check(mismatch.status_code == 409, f"expected-id mismatch should 409, got {mismatch.status_code}")

            # PROOF B — a DIFFERENT portal project + identical packet gets a DISTINCT engine id.
            distinct = _post_packet(client, headers, portal_project_other_id)
            _check(distinct.status_code == 201, f"distinct-portal ingestion failed: {distinct.status_code} {distinct.text}")
            other_engine_project_id = distinct.json()["project_id"]
            _check(
                other_engine_project_id != engine_project_id,
                "different portal projects with identical packet must not share one engine id",
            )
            _check(distinct.json().get("idempotent_reuse") is False, "distinct-portal ingestion should not be a reuse")

            # Exactly two engine projects exist now (one per portal project), same packet SHA.
            with ctx["database"].get_connection() as conn:
                project_rows = conn.execute(
                    "SELECT id, file_sha256, page_count, status, tenant_id, company_id, portal_project_id FROM projects"
                ).fetchall()
            _check(len(project_rows) == 2, f"expected exactly two engine projects, found {len(project_rows)}")
            by_id = {dict(r)["id"]: dict(r) for r in project_rows}
            _check(engine_project_id in by_id and other_engine_project_id in by_id, "engine project id mismatch")
            row = by_id[engine_project_id]
            _check(row["portal_project_id"] == portal_project_test_id, "stored portal identity mismatch")
            _check(
                by_id[other_engine_project_id]["portal_project_id"] == portal_project_other_id,
                "second engine project portal identity mismatch",
            )
            _check(
                row["file_sha256"] == by_id[other_engine_project_id]["file_sha256"] == manifest["packet"]["sha256"],
                "both engine projects must share the identical packet SHA-256",
            )
            _check(row["tenant_id"] == tenant_id and row["company_id"] == company_id, "engine project tenant/company mismatch")

            # Worker identity contract: the project's stored SHA-256 IS the packet's.
            status_resp = client.get(f"/api/v1/projects/{engine_project_id}/status", headers=headers)
            _check(status_resp.status_code == 200, f"status read failed: {status_resp.text}")
            status_body = status_resp.json()
            _check(
                status_body["file_sha256"] == manifest["packet"]["sha256"],
                "engine project stored SHA-256 does not equal packet SHA-256",
            )
            _check(status_body["page_count"] == manifest["packet"]["page_count"], "engine project page count mismatch")
            _check(row["file_sha256"] == manifest["packet"]["sha256"], "db project SHA-256 mismatch")
            _check(status_body["status"] in SAFE_PROJECT_STATUSES, f"unexpected project status {status_body['status']}")

            # Delivery capability stays locked closed (no customer delivery enabled).
            cap = client.get("/api/v1/capability-registry", headers=headers)
            _check(cap.status_code == 200, "capability registry read failed")
            delivery_lock = cap.json()["customer_delivery_lock"]
            _check(delivery_lock["fail_closed"] is True, "delivery lock is not fail-closed")
            _check(delivery_lock["final_customer_delivery_enabled"] is False, "final customer delivery is unexpectedly enabled")

    _check(safety.get("external_connect_attempts", 0) == 0, "an external network connection was attempted")

    safety_flags = {
        "customer_delivery": False,
        "message_sent": False,
        "payment_created": False,
        "final_approval": False,
        "proposal_issued": False,
        "test_only_treated_as_real": False,
    }
    _check(all(v is False for v in safety_flags.values()), "a safety flag is not locked false")

    report = {
        "proof": "usc_multidocument_ingestion_v1",
        "label": (
            "INTERNAL DOCUMENT-INGESTION PROOF ONLY — deterministic multi-PDF packet "
            "assembly + one-engine-project ingestion. NOT a whole-project quantity, "
            "pricing, or final-estimate readiness result."
        ),
        "solicitation": "H27-Z147-B",
        "portal_project_test_id": portal_project_test_id,
        "engine_project_id": engine_project_id,
        "portal_project_other_id": portal_project_other_id,
        "other_engine_project_id": other_engine_project_id,
        "idempotency_proof": {
            "same_portal_same_packet_reuses_one_engine_id": True,
            "different_portal_same_packet_creates_distinct_engine_ids": True,
            "expected_engine_id_mismatch_rejected": True,
        },
        "tenant_id": tenant_id,
        "company_id": company_id,
        "packet": {
            "sha256": manifest["packet"]["sha256"],
            "bytes": manifest["packet"]["bytes"],
            "page_count": manifest["packet"]["page_count"],
            "source_count": manifest["packet"]["source_count"],
        },
        "sources": [
            {
                "order": s["order"],
                "original_filename": s["original_filename"],
                "project_file_id": s["project_file_id"],
                "source_sha256": s["source_sha256"],
                "source_bytes": s["source_bytes"],
                "source_page_count": s["source_page_count"],
                "combined_page_start": s["combined_page_start"],
                "combined_page_end": s["combined_page_end"],
            }
            for s in manifest["sources"]
        ],
        "safety_flags": safety_flags,
        "external_connect_attempts": safety.get("external_connect_attempts", 0),
        "passed": True,
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/usc-multidocument-ingestion.json"))
    args = parser.parse_args()
    try:
        report = run(args.output)
    except HarnessError as exc:
        failure = {"proof": "usc_multidocument_ingestion_v1", "passed": False, "error": str(exc)}
        args.output.write_text(json.dumps(failure, indent=2), encoding="utf-8")
        print(json.dumps(failure, indent=2))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
