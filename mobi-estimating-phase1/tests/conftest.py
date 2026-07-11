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

TEST_TENANT_HEADERS = {"X-Mobi-Tenant-Id": "test_tenant", "X-Mobi-Company-Id": "test_company"}


class TenantAwareTestClient(TestClient):
    """Test client that exercises the normal authenticated tenant path by default.

    The audit P0/P1 tenant-boundary repair makes project-scoped engine routes
    fail closed without tenant identity. Most existing tests are ordinary
    same-tenant flow tests, so default headers keep those tests focused on their
    original behavior while still allowing explicit negative tests to pass
    ``headers={}`` or mismatched tenant headers.
    """

    def request(self, method: str, url: str, **kwargs):  # type: ignore[override]
        if kwargs.get("headers") is None:
            kwargs["headers"] = dict(TEST_TENANT_HEADERS)
        return super().request(method, url, **kwargs)


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


# ---------------------------------------------------------------------------
# Richer PDF builders for Phase 2 processing tests
# ---------------------------------------------------------------------------
def _add_title_block(page, number: str | None, title: str | None) -> None:
    """Place a sheet number/title in the bottom-right title-block region."""
    w, h = page.rect.width, page.rect.height
    if number:
        page.insert_text((w * 0.78, h * 0.94), number, fontsize=11)
    if title:
        page.insert_text((w * 0.66, h * 0.97), title, fontsize=9)


def make_sheet_pdf(specs: list[dict]) -> bytes:
    """Build a PDF from page specs.

    Each spec may contain: ``number``, ``title``, ``body`` (drawing text),
    ``width``, ``height``, ``rotation``, ``blank`` (no content), ``image_only``
    (raster image, no text), ``duplicate_text`` (force identical content).
    """
    doc = fitz.open()
    for spec in specs:
        width = spec.get("width", 612)
        height = spec.get("height", 792)
        page = doc.new_page(width=width, height=height)
        if spec.get("blank"):
            pass
        elif spec.get("image_only"):
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 240, 240), False)
            pix.set_rect(pix.irect, (210, 190, 160))
            page.insert_image(page.rect, pixmap=pix)
        else:
            body = spec.get("body", "GENERAL NOTES\nDrawing content for this page.")
            page.insert_text((72, 72), body, fontsize=10)
            _add_title_block(page, spec.get("number"), spec.get("title"))
            for extra in spec.get("extra_numbers", []):
                page.insert_text(
                    (page.rect.width * 0.80, page.rect.height * 0.90),
                    extra,
                    fontsize=11,
                )
        if spec.get("rotation"):
            page.set_rotation(spec["rotation"])
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def sheet_pdf_bytes() -> bytes:
    """Two clean pages, each with a confident sheet number and title."""
    return make_sheet_pdf(
        [
            {"number": "A-101", "title": "FLOOR PLAN"},
            {"number": "S2.01", "title": "FRAMING PLAN"},
        ]
    )


def upload_and_process(client, content: bytes, *, project_name: str = "Proj",
                       force: bool = False):
    """Helper: upload a PDF then run processing, returning (project_id, response)."""
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": project_name},
        files={"plan": ("plans.pdf", content, "application/pdf")},
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    resp = client.post(
        f"/api/v1/projects/{pid}/process",
        json={"force": force},
        headers=TEST_TENANT_HEADERS,
    )
    return pid, resp


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
def client(tmp_path: Path):
    """A TestClient backed by a fresh, isolated database and upload directory.

    Both the Painting and demonstration Concrete trades are enabled so the suite
    can prove the core is trade-agnostic.
    """
    from app.extraction.cache import extraction_cache

    settings.db_path = tmp_path / "mobi.db"
    settings.upload_dir = tmp_path / "uploads"
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.enabled_trades = ["painting", "demo_concrete", "general_trade"]
    extraction_cache.clear()
    init_db()
    with TenantAwareTestClient(app) as test_client:  # lifespan bootstraps the trade registry
        yield test_client


# ---------------------------------------------------------------------------
# Phase 3 helpers
# ---------------------------------------------------------------------------
def make_trade_pdf() -> bytes:
    """A 2-page PDF: a painting finish sheet (A-101) and a concrete sheet (S-101)."""
    return make_sheet_pdf(
        [
            {"number": "A-101", "title": "FINISH PLAN",
             "body": (
                 "ROOM FINISH SCHEDULE\nWALLS: PT-1 PAINT 2 COATS\nPAINTING NOTES\n"
                 * 8
             )},
            {"number": "S-101", "title": "FOUNDATION PLAN",
             "body": (
                 "CONCRETE SLAB ON GRADE SCHEDULE\n6 INCH SLAB 3000 PSI\n"
                 * 8
             )},
        ]
    )


# Fictional cost-book values for tests ONLY. Not real market prices.
def seed_published_cost_book(client: TestClient, *, project_id: str | None = None) -> str:
    """Create + publish a cost book with FICTIONAL painting + concrete rates and
    assemblies. Returns the published cost-book version id."""
    cb = client.post("/api/v1/cost-books", json={"name": "Test Book"}).json()
    cbid = cb["id"]
    v = client.post(f"/api/v1/cost-books/{cbid}/versions", json={
        "version_label": "v1", "effective_date": "2026-01-01",
        "pricing_date": "2026-06-01"}).json()
    vid = v["id"]
    base = f"/api/v1/cost-books/{cbid}/versions/{vid}"
    src = client.post(f"{base}/sources", json={
        "source_type": "contractor_rate", "source_name": "Fictional",
        "effective_date": "2026-01-01", "verified": True}).json()
    sid = src["id"]

    def labor(c, rate):
        client.post(f"{base}/labor-rates", json={
            "classification": c, "trade_code": "painting", "rate_type": "manual_all_in",
            "manual_all_in_rate": rate, "effective_date": "2026-01-01", "source_id": sid})

    def prod(code, basis, value, **kw):
        client.post(f"{base}/production-rates", json={
            "production_code": code, "trade_code": kw.get("trade", "painting"),
            "scope_category": kw.get("cat", "interior_walls"), "quantity_unit": kw.get("unit", "SF"),
            "basis": basis, "value": value, "crew_code": kw.get("crew"),
            "effective_date": "2026-01-01", "source_id": sid})

    def material(code, cost, unit="GAL", coverage=None):
        body = {"material_code": code, "description": code, "trade_code": "painting",
                "purchase_unit": unit, "unit_cost": cost,
                "effective_date": "2026-01-01", "source_id": sid}
        if coverage:
            body["coverage_per_unit"] = coverage
            body["coverage_unit"] = "SF"
        client.post(f"{base}/material-rates", json=body)

    # Painting (fictional)
    labor("PAINTER", "50.00")
    prod("PROD-PT-PREP", "units_per_labor_hour", "200")
    prod("PROD-PT-FINISH", "units_per_labor_hour", "150")
    prod("PROD-PT-FRAME", "labor_hours_per_unit", "0.5", cat="door_frames", unit="EA")
    material("MAT-PT-PRIMER", "30.00", coverage="300")
    material("MAT-PT-FINISH", "40.00", coverage="350")
    client.post(f"{base}/other-direct-costs", json={
        "odc_code": "ODC-MASKING", "cost_type": "masking", "unit": "SF",
        "unit_rate": "0.10", "source_id": sid})

    # Concrete (fictional) — crew-hour labor + equipment with a minimum charge.
    client.post(f"{base}/crews", json={
        "crew_code": "CREW-CONC", "trade_code": "demo_concrete", "name": "Concrete crew",
        "members": [{"classification": "FINISHER", "count": 3}],
        "loaded_crew_hour_rate": "200.00"})
    prod("PROD-CONC-PLACE", "crew_hours_per_unit", "0.30", trade="demo_concrete",
         cat="slab_on_grade", unit="CY", crew="CREW-CONC")
    prod("PROD-CONC-FINISH", "crew_hours_per_unit", "0.20", trade="demo_concrete",
         cat="slab_on_grade", unit="CY", crew="CREW-CONC")
    for code, cost, unit in [("MAT-CONC-MIX", "150.00", "CY"), ("MAT-REBAR", "0.80", "LB")]:
        client.post(f"{base}/material-rates", json={
            "material_code": code, "description": code, "trade_code": "demo_concrete",
            "purchase_unit": unit, "unit_cost": cost, "effective_date": "2026-01-01",
            "source_id": sid})
    client.post(f"{base}/equipment-rates", json={
        "equipment_code": "EQ-PUMP", "description": "Pump", "basis": "day",
        "base_rate": "1200.00", "minimum_charge": "1200.00",
        "effective_date": "2026-01-01", "source_id": sid})

    # Assemblies from the trade templates (structure only).
    from app.trades.registry import trade_registry
    for code in ("painting", "demo_concrete"):
        for tmpl in trade_registry.get(code).get_assembly_templates():
            client.post(f"{base}/assemblies", json={**tmpl, "trade_code": code})

    pub = client.post(f"{base}/publish")
    assert pub.status_code == 200, pub.text
    return vid


def prepare_priced_project(client: TestClient):
    """Full chain: verified project → extract painting+concrete → approve items →
    published cost book. Returns (project_id, cost_book_version_id)."""
    pid = prepare_verified_project(client, project_name="Priced")
    for trade in ("painting", "demo_concrete"):
        client.post(f"/api/v1/projects/{pid}/trades/{trade}/extractions", json={})
    # Correct the painting door-frame item so it has a coating system, then approve.
    items = client.get(f"/api/v1/projects/{pid}/scope-items").json()["items"]
    for it in items:
        if it["category_code"] == "door_frames":
            client.patch(f"/api/v1/projects/{pid}/scope-items/{it['id']}",
                         json={"trade_data": {"coating_system": "alkyd", "substrate": "hollow metal"}})
        client.post(f"/api/v1/projects/{pid}/scope-items/{it['id']}/approve")
    vid = seed_published_cost_book(client, project_id=pid)
    return pid, vid


def prepare_approved_estimate(client: TestClient, *, detail_trades=("painting", "demo_concrete")):
    """Full chain through an APPROVED priced estimate. Returns
    (project_id, estimate_id, estimate_version_id, final_sell_price)."""
    pid, vid = prepare_priced_project(client)
    est = client.post(f"/api/v1/projects/{pid}/estimates", json={
        "name": "Estimate", "cost_book_version_id": vid,
        "adjustments": [
            {"adjustment_type": "overhead", "name": "OH", "method": "markup",
             "percent": "0.10", "sequence": 1, "base_categories": ["direct_subtotal"]},
            {"adjustment_type": "profit", "name": "P", "method": "margin",
             "percent": "0.10", "sequence": 2}]}).json()
    eid, evid = est["estimate"]["id"], est["version"]["id"]
    priced = client.post(
        f"/api/v1/projects/{pid}/estimates/{eid}/versions/{evid}/price").json()
    client.post(f"/api/v1/projects/{pid}/estimates/{eid}/versions/{evid}/approve")
    return pid, eid, evid, priced["rollup"]["totals"]["final_sell_price"]


def prepare_verified_project(client: TestClient, *, project_name: str = "P3") -> str:
    """Upload + process the trade PDF and verify both sheets. Returns project_id."""
    pid = client.post(
        "/api/v1/projects/upload",
        data={"project_name": project_name},
        files={"plan": ("plans.pdf", make_trade_pdf(), "application/pdf")},
        headers=TEST_TENANT_HEADERS,
    ).json()["project_id"]
    client.post(f"/api/v1/projects/{pid}/process", headers=TEST_TENANT_HEADERS)
    for sheet in client.get(f"/api/v1/projects/{pid}/sheets", headers=TEST_TENANT_HEADERS).json()["items"]:
        number = "A-101" if sheet["pdf_page_number"] == 1 else "S-101"
        client.patch(
            f"/api/v1/projects/{pid}/sheets/{sheet['sheet_id']}/verification",
            json={"verified_sheet_number": number, "review_status": "verified"},
            headers=TEST_TENANT_HEADERS,
        )
    return pid


def upload(client: TestClient, content: bytes, *, name: str = "plans.pdf",
           project_name: str = "Test Project",
           content_type: str = "application/pdf") -> "object":
    return client.post(
        "/api/v1/projects/upload",
        data={"project_name": project_name},
        files={"plan": (name, content, content_type)},
        headers=TEST_TENANT_HEADERS,
    )
