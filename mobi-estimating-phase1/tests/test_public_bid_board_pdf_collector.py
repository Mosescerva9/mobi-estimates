"""Public bid-board PDF collector tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.public_bid_board_pdf_collector import (
    BidDocument,
    FetchResponse,
    agency_documents_from_html,
    classify_trades,
    construction_score,
    discover_from_config,
    download_documents,
    sam_documents_from_response,
    write_manifest,
)


def test_sam_fixture_accepts_construction_resource_links() -> None:
    payload = {
        "opportunitiesData": [
            {
                "title": "Renovation of municipal building - plans and specifications",
                "noticeId": "ABC-123",
                "naicsCode": "236220",
                "fullParentPathName": "General Services Administration",
                "postedDate": "07/01/2026",
                "responseDeadLine": "07/31/2026",
                "resourceLinks": [
                    "https://sam.gov/api/prod/opps/v3/opportunities/resources/files/abc/plans.pdf",
                    "https://sam.gov/api/prod/opps/v3/opportunities/resources/files/abc/specifications.zip",
                ],
            }
        ]
    }

    docs = sam_documents_from_response(payload)

    assert len(docs) == 2
    assert all(doc.accepted for doc in docs)
    assert all(doc.source_type == "sam_gov" for doc in docs)
    assert docs[0].internal_testing_only is True
    assert docs[0].naics == "236220"
    assert "general" in docs[0].matched_trades
    assert docs[0].construction_score >= 35
    assert docs[0].access_policy == "sam_gov_public_api_resource_link"


def test_sam_fixture_rejects_nonconstruction_without_resources() -> None:
    payload = {
        "opportunitiesData": [
            {
                "title": "Office paper supply purchase",
                "noticeId": "SUPPLY-1",
                "naicsCode": "424120",
                "resourceLinks": [],
            }
        ]
    }

    docs = sam_documents_from_response(payload)

    assert docs == []


def test_sam_fixture_rejects_off_domain_resource_link() -> None:
    payload = {
        "opportunitiesData": [
            {
                "title": "Complete construction project manual plans and specifications for concrete, roofing, HVAC, plumbing, electrical, paving",
                "noticeId": "BAD-LINK",
                "naicsCode": "236220",
                "resourceLinks": ["https://evil.example.com/plans.pdf"],
            }
        ]
    }

    docs = sam_documents_from_response(payload)

    assert len(docs) == 1
    assert docs[0].accepted is False
    assert "sam_resource_link_host_not_allowlisted" in docs[0].rejection_reasons


def test_single_trade_docs_are_rejected_by_default_but_can_be_opted_in() -> None:
    payload = {
        "opportunitiesData": [
            {
                "title": "HVAC construction bid documents and specifications",
                "noticeId": "HVAC-ONLY",
                "naicsCode": "238220",
                "resourceLinks": ["https://sam.gov/files/hvac-only.pdf"],
            }
        ]
    }

    default_docs = sam_documents_from_response(payload)
    opt_in_docs = sam_documents_from_response(payload, include_single_trade=True)

    assert default_docs[0].accepted is False
    assert "not_all_trade_or_multi_trade_scope" in default_docs[0].rejection_reasons
    assert opt_in_docs[0].accepted is True


def test_agency_source_page_robots_disallow_prevents_page_fetch() -> None:
    calls: list[str] = []

    def fetcher(url: str) -> FetchResponse:
        calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResponse(url, b"User-agent: *\nDisallow: /bids\n", content_type="text/plain")
        raise AssertionError("source page should not be fetched when robots disallows it")

    docs = discover_from_config(
        {
            "respect_robots": True,
            "agency_pages": [{"name": "Blocked Agency", "url": "https://blocked.example.gov/bids"}],
        },
        fetcher=fetcher,
    )

    assert calls == ["https://blocked.example.gov/robots.txt"]
    assert len(docs) == 1
    assert docs[0].accepted is False
    assert docs[0].document_url == "https://blocked.example.gov/bids"
    assert docs[0].rejection_reasons == ["source_page_robots_disallow"]


def test_agency_html_extracts_relative_construction_pdf_and_respects_robots() -> None:
    html = """
    <html><body>
      <h1>Invitation for Bid - Fire Station Renovation</h1>
      <p>Download plans and specifications for all trades including mechanical, plumbing, electrical, roofing, concrete, painting.</p>
      <a href="/bids/fire-station/plans.pdf">Plans and specifications PDF</a>
      <a href="https://evil.example.com/private.pdf">Private outside host</a>
    </body></html>
    """

    def fetcher(url: str) -> FetchResponse:
        if url.endswith("/robots.txt"):
            return FetchResponse(url, b"User-agent: *\nAllow: /bids/\nDisallow: /private/\n", content_type="text/plain")
        raise AssertionError(f"unexpected fetch {url}")

    docs = agency_documents_from_html(
        "https://city.example.gov/procurement/bids.html",
        html,
        agency_name="Example City",
        allow_domains=["city.example.gov"],
        fetcher=fetcher,
    )

    accepted = [doc for doc in docs if doc.accepted]
    rejected = [doc for doc in docs if not doc.accepted]
    assert len(accepted) == 1
    assert accepted[0].document_url == "https://city.example.gov/bids/fire-station/plans.pdf"
    assert accepted[0].robots_checked is True
    assert accepted[0].allowed_by_robots is True
    assert accepted[0].all_trade_or_full_project is True
    assert {"mechanical_hvac", "plumbing", "electrical", "roofing", "concrete", "painting"}.issubset(
        set(accepted[0].matched_trades)
    )
    assert any("host_not_allowlisted" in doc.rejection_reasons for doc in rejected)


def test_agency_html_blocks_robots_disallowed_pdf() -> None:
    html = """
    <h1>Construction bid - Water treatment plant improvements</h1>
    <a href="/private/specs.pdf">Bid documents and drawings</a>
    """

    def fetcher(url: str) -> FetchResponse:
        assert url.endswith("/robots.txt")
        return FetchResponse(url, b"User-agent: *\nDisallow: /private/\n", content_type="text/plain")

    docs = agency_documents_from_html(
        "https://agency.example.gov/bids",
        html,
        agency_name="Agency",
        fetcher=fetcher,
    )

    assert len(docs) == 1
    assert docs[0].accepted is False
    assert "robots_disallow" in docs[0].rejection_reasons
    assert docs[0].robots_checked is True
    assert docs[0].allowed_by_robots is False


def test_manifest_and_mock_download_write_internal_testing_metadata(tmp_path: Path) -> None:
    doc = BidDocument(
        source_type="public_agency_page",
        source_url="https://county.example.gov/bids",
        document_url="https://county.example.gov/files/courthouse-plans.pdf",
        project_title="Courthouse renovations bid documents",
        file_name="courthouse-plans.pdf",
        file_type="pdf",
        agency="County",
        accepted=True,
        matched_keywords=["bid", "plans", "construction"],
        matched_trades=["general", "electrical", "plumbing"],
        all_trade_or_full_project=True,
        construction_score=90,
    )

    def fetcher(url: str) -> FetchResponse:
        assert url == doc.document_url
        return FetchResponse(url, b"%PDF-1.4\nfixture\n", content_type="application/pdf")

    docs = download_documents([doc], tmp_path / "files", fetcher=fetcher, delay_seconds=0)
    manifest = write_manifest(docs, tmp_path / "manifest.json")

    assert docs[0].sha256
    assert Path(docs[0].downloaded_path or "").exists()
    assert manifest["safety"]["internal_testing_only"] is True
    assert manifest["safety"]["customer_delivery_ready"] is False
    assert manifest["summary"]["downloaded_count"] == 1
    assert manifest["summary"]["all_trade_or_full_project_count"] == 1
    saved = json.loads((tmp_path / "manifest.json").read_text())
    assert saved["documents"][0]["internal_testing_only"] is True


def test_discover_from_config_uses_offline_fixtures(tmp_path: Path) -> None:
    sam_fixture = tmp_path / "sam.json"
    sam_fixture.write_text(json.dumps({
        "opportunitiesData": [
            {
                "title": "School complete project manual plans and specifications for HVAC, electrical, plumbing, concrete, roofing, painting, paving, landscaping",
                "naicsCode": "238220",
                "noticeId": "HVAC-1",
                "resourceLinks": ["https://sam.gov/files/hvac-plans.pdf"],
            }
        ]
    }))
    agency_fixture = tmp_path / "agency.html"
    agency_fixture.write_text(
        "<h1>Public Works Complete Project Construction Bid</h1>"
        "<p>Complete project plans and specifications for roadway paving, concrete sidewalk, drainage, landscaping, electrical, plumbing and site utilities.</p>"
        "<a href='docs/roadway-plans.PDF'>Plan set</a>"
    )
    config = {
        "respect_robots": False,
        "sam": {"fixture": str(sam_fixture)},
        "agency_pages": [
            {"name": "Town", "url": "https://town.example.gov/bids/current", "fixture": str(agency_fixture)}
        ],
    }

    docs = discover_from_config(config)

    assert len(docs) == 2
    assert all(doc.accepted for doc in docs)
    assert any(doc.source_type == "sam_gov" for doc in docs)
    assert any(doc.document_url.endswith("roadway-plans.PDF") for doc in docs)


def test_trade_classifier_covers_all_trade_signal() -> None:
    trades, all_trade = classify_trades(
        "Complete project manual plans and specifications for civil site work, concrete, masonry, steel, roofing, "
        "doors, drywall, painting, HVAC, plumbing, electrical, fire protection, low voltage, paving, landscaping."
    )
    assert all_trade is True
    for expected in [
        "general", "civil_site", "concrete", "masonry", "steel", "roofing", "doors_windows",
        "drywall_framing", "painting", "mechanical_hvac", "plumbing", "electrical", "fire_protection",
        "low_voltage", "paving", "landscaping",
    ]:
        assert expected in trades

    score, matched, reasons = construction_score("Invitation for Bid complete construction drawings and specifications", naics="236220")
    assert score >= 35
    assert not reasons
    assert "naics:236220" in matched
