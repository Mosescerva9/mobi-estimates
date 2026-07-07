#!/usr/bin/env python3
"""Discover/import public construction bid-board PDFs for Mobi testing.

This collector is intentionally conservative. It is for public/authorized
sources only: SAM.gov API results and allowlisted public agency bid pages. It
must not bypass login, paywalls, CAPTCHA, robots.txt, or session-gated files.
Downloaded documents are marked internal-testing-only and are meant to feed the
local real-document harness, not customer delivery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable

SAM_OPPORTUNITIES_ENDPOINT = "https://api.sam.gov/opportunities/v2/search"
DEFAULT_OUTPUT_ROOT = Path("data/bid_board_imports")
USER_AGENT = "MobiEstimatesPublicBidBoardCollector/1.0 (+https://mobiestimates.com; public-doc-testing)"
MAX_DOWNLOAD_BYTES = 75 * 1024 * 1024
DOWNLOAD_EXTENSIONS = {".pdf", ".zip"}

# Construction NAICS families: buildings, heavy/civil, and specialty trades.
CONSTRUCTION_NAICS_PREFIXES = ("236", "237", "238")
BID_KEYWORDS = {
    "bid", "bids", "bidding", "ifb", "invitation for bid", "solicitation",
    "request for bids", "rfb", "rfq", "sealed bid", "addendum", "planholders",
    "pre-bid", "construction", "contract documents", "project manual",
}
CONSTRUCTION_KEYWORDS = {
    "construction", "renovation", "improvement", "repair", "replacement",
    "modernization", "site work", "public works", "building", "facility",
    "drawings", "plans", "specifications", "specs", "project manual",
    "division 00", "division 01", "division 02", "division 03", "division 04",
    "division 05", "division 06", "division 07", "division 08", "division 09",
    "division 10", "division 21", "division 22", "division 23", "division 26",
    "division 27", "division 28", "division 31", "division 32", "division 33",
}
DOCUMENT_KEYWORDS = {
    "plans", "drawings", "specifications", "specs", "project manual",
    "bid documents", "contract documents", "addendum", "plan set", "drawing set",
    "attachments", "solicitation package",
}

TRADE_KEYWORDS: dict[str, set[str]] = {
    "general": {"general requirements", "division 01", "general contractor", "gc", "prime contractor", "all trades", "full project", "complete project"},
    "civil_site": {"civil", "site work", "sitework", "grading", "drainage", "stormwater", "erosion", "survey", "division 31", "division 32", "division 33"},
    "earthwork_utilities": {"earthwork", "excavation", "trenching", "backfill", "utilities", "water line", "sewer", "storm drain", "underground"},
    "demolition": {"demolition", "demo", "selective demolition", "division 02"},
    "concrete": {"concrete", "rebar", "reinforcing", "slab", "footing", "foundation", "division 03"},
    "masonry": {"masonry", "cmu", "brick", "block", "division 04"},
    "steel": {"steel", "structural steel", "metal fabrications", "metals", "division 05", "joist", "decking"},
    "carpentry": {"carpentry", "rough carpentry", "finish carpentry", "millwork", "casework", "division 06"},
    "roofing": {"roofing", "roof", "membrane", "flashing", "division 07"},
    "doors_windows": {"doors", "windows", "glazing", "storefront", "hardware", "division 08"},
    "drywall_framing": {"drywall", "gypsum", "framing", "metal studs", "studs", "gwb", "partition"},
    "finishes": {"finishes", "ceilings", "acoustical", "tile", "specialties", "division 09", "division 10"},
    "flooring": {"flooring", "carpet", "resilient", "vct", "lvt", "tile flooring", "epoxy floor"},
    "painting": {"painting", "paint", "coatings", "division 09"},
    "mechanical_hvac": {"mechanical", "hvac", "air handling", "ductwork", "diffuser", "chiller", "boiler", "division 23"},
    "plumbing": {"plumbing", "domestic water", "sanitary", "gas piping", "fixtures", "division 22"},
    "electrical": {"electrical", "lighting", "power", "panels", "conduit", "division 26"},
    "fire_protection": {"fire protection", "sprinkler", "fire alarm", "division 21", "division 28"},
    "low_voltage": {"low voltage", "data", "telecommunications", "security", "access control", "division 27", "division 28"},
    "landscaping": {"landscaping", "irrigation", "planting", "turf", "division 32"},
    "paving": {"paving", "asphalt", "parking lot", "striping", "sidewalk", "curb", "gutter"},
}
ALL_TRADE_HINTS = {
    "all trades", "full project", "complete project", "project manual",
    "contract documents", "plans and specifications",
    "drawings and specifications", "general construction", "prime contract",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_norm_text(v) for v in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def _token_matches(text: str, keywords: Iterable[str]) -> list[str]:
    hay = text.lower()
    matches = []
    for keyword in sorted(keywords):
        if keyword.lower() in hay:
            matches.append(keyword)
    return matches


def classify_trades(*parts: Any) -> tuple[list[str], bool]:
    text = _norm_text(parts).lower()
    trades = []
    for trade, keywords in TRADE_KEYWORDS.items():
        if _token_matches(text, keywords):
            trades.append(trade)
    all_trade = bool(_token_matches(text, ALL_TRADE_HINTS)) or len(trades) >= 5
    if all_trade and "general" not in trades:
        trades.insert(0, "general")
    return sorted(set(trades)), all_trade


def construction_score(*parts: Any, naics: str | None = None) -> tuple[int, list[str], list[str]]:
    text = _norm_text(parts)
    lower = text.lower()
    matched_keywords = []
    score = 0
    if naics and any(str(naics).startswith(prefix) for prefix in CONSTRUCTION_NAICS_PREFIXES):
        score += 45
        matched_keywords.append(f"naics:{naics}")
    bid_matches = _token_matches(lower, BID_KEYWORDS)
    construction_matches = _token_matches(lower, CONSTRUCTION_KEYWORDS)
    doc_matches = _token_matches(lower, DOCUMENT_KEYWORDS)
    matched_keywords.extend(bid_matches + construction_matches + doc_matches)
    score += min(25, len(bid_matches) * 5)
    score += min(35, len(construction_matches) * 5)
    score += min(20, len(doc_matches) * 4)
    trades, all_trade = classify_trades(text)
    if trades:
        score += min(25, len(trades) * 4)
    if all_trade:
        score += 15
        matched_keywords.append("all_trade_or_full_project")
    rejection_reasons: list[str] = []
    if score < 35:
        rejection_reasons.append("construction_score_below_threshold")
    if not (bid_matches or naics):
        rejection_reasons.append("missing_bid_or_construction_naics_signal")
    if not (doc_matches or "resourceLinks" in text):
        rejection_reasons.append("missing_document_signal")
    return score, sorted(set(matched_keywords)), rejection_reasons


@dataclass
class BidDocument:
    source_type: str
    source_url: str
    document_url: str
    project_title: str
    file_name: str
    file_type: str
    agency: str | None = None
    solicitation_id: str | None = None
    posted_date: str | None = None
    deadline: str | None = None
    naics: str | None = None
    psc: str | None = None
    access_policy: str = "public_allowlisted"
    robots_checked: bool = False
    allowed_by_robots: bool | None = None
    internal_testing_only: bool = True
    matched_keywords: list[str] = field(default_factory=list)
    matched_trades: list[str] = field(default_factory=list)
    all_trade_or_full_project: bool = False
    construction_score: int = 0
    accepted: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    sha256: str | None = None
    downloaded_path: str | None = None
    downloaded_bytes: int | None = None
    error: str | None = None

    def as_manifest(self) -> dict[str, Any]:
        return asdict(self)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attrs_dict = {k.lower(): v for k, v in attrs}
            self._current_href = attrs_dict.get("href")
            self._current_text = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href:
            self.links.append((self._current_href, _norm_text(self._current_text)))
            self._current_href = None
            self._current_text = []


def _safe_filename(name: str, fallback: str = "document") -> str:
    parsed = urllib.parse.urlparse(name)
    base = Path(parsed.path).name if parsed.path else name
    base = urllib.parse.unquote(base) or fallback
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return base or fallback


def _extension_for_url(url: str, content_type: str | None = None) -> str:
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext in DOWNLOAD_EXTENSIONS:
        return ext
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) if content_type else None
    return guessed.lower() if guessed and guessed.lower() in DOWNLOAD_EXTENSIONS else ext


def document_url_looks_importable(url: str, link_text: str = "") -> bool:
    parsed = urllib.parse.urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    if ext in DOWNLOAD_EXTENSIONS:
        return True
    text = f"{url} {link_text}".lower()
    return bool(_token_matches(text, DOCUMENT_KEYWORDS)) and ("download" in text or "attachment" in text)


def sam_resource_url_allowed(url: str) -> bool:
    """SAM attachment URLs must come from SAM-controlled HTTPS hosts."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    return parsed.scheme == "https" and (host == "sam.gov" or host.endswith(".sam.gov"))


def _meets_trade_scope(trades: list[str], all_trade: bool, *, include_single_trade: bool = False) -> bool:
    if include_single_trade:
        return bool(trades)
    return all_trade or len(set(trades)) >= 5


def sam_documents_from_response(payload: dict[str, Any], *, include_single_trade: bool = False) -> list[BidDocument]:
    opportunities = payload.get("opportunitiesData") or payload.get("data") or payload.get("opportunities") or []
    docs: list[BidDocument] = []
    if not isinstance(opportunities, list):
        return docs
    for opp in opportunities:
        if not isinstance(opp, dict):
            continue
        title = _norm_text(opp.get("title") or opp.get("solicitationTitle") or opp.get("description") or "Untitled SAM.gov opportunity")
        agency = _norm_text(opp.get("fullParentPathName") or opp.get("department") or opp.get("subTier") or opp.get("officeAddress") or "") or None
        notice_id = _norm_text(opp.get("noticeId") or opp.get("noticeid") or opp.get("solicitationNumber") or opp.get("solnum") or "") or None
        naics = _norm_text(opp.get("naicsCode") or opp.get("naics") or "") or None
        psc = _norm_text(opp.get("classificationCode") or opp.get("psc") or "") or None
        posted = _norm_text(opp.get("postedDate") or opp.get("publishDate") or "") or None
        deadline = _norm_text(opp.get("responseDeadLine") or opp.get("responseDeadline") or opp.get("archiveDate") or "") or None
        source_url = _norm_text(opp.get("uiLink") or opp.get("samUrl") or opp.get("links", {}).get("self") if isinstance(opp.get("links"), dict) else "") or "https://sam.gov/"
        resource_links = opp.get("resourceLinks") or opp.get("resource_links") or []
        if isinstance(resource_links, str):
            resource_links = [resource_links]
        context = json.dumps(opp, default=str)
        score, matched, reject = construction_score(title, agency, context, naics=naics)
        trades, all_trade = classify_trades(title, agency, context)
        if not trades and naics and any(naics.startswith(prefix) for prefix in CONSTRUCTION_NAICS_PREFIXES):
            trades = ["general"]
        if not resource_links:
            reject = sorted(set(reject + ["no_resource_links"]))
        for url in resource_links if isinstance(resource_links, list) else []:
            if not isinstance(url, str) or not url.strip():
                continue
            file_name = _safe_filename(url, fallback=f"sam_{notice_id or 'document'}.pdf")
            ext = Path(file_name).suffix.lower()
            file_type = ext.lstrip(".") or "unknown"
            reasons = list(reject)
            if not document_url_looks_importable(url, file_name):
                reasons.append("resource_link_not_pdf_or_zip_like")
            if not sam_resource_url_allowed(url):
                reasons.append("sam_resource_link_host_not_allowlisted")
            if not _meets_trade_scope(trades, all_trade, include_single_trade=include_single_trade):
                reasons.append("not_all_trade_or_multi_trade_scope")
            accepted = score >= 35 and not reasons
            docs.append(BidDocument(
                source_type="sam_gov",
                source_url=source_url,
                document_url=url,
                project_title=title,
                file_name=file_name,
                file_type=file_type,
                agency=agency,
                solicitation_id=notice_id,
                posted_date=posted,
                deadline=deadline,
                naics=naics,
                psc=psc,
                access_policy="sam_gov_public_api_resource_link",
                robots_checked=False,
                allowed_by_robots=None,
                matched_keywords=matched,
                matched_trades=trades,
                all_trade_or_full_project=all_trade,
                construction_score=score,
                accepted=accepted,
                rejection_reasons=sorted(set(reasons)),
            ))
    return docs


class FetchResponse:
    def __init__(self, url: str, body: bytes, status: int = 200, content_type: str | None = None) -> None:
        self.url = url
        self.body = body
        self.status = status
        self.content_type = content_type


Fetcher = Callable[[str], FetchResponse]


def default_fetcher(url: str, *, timeout: int = 30) -> FetchResponse:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - public allowlisted fetcher
        return FetchResponse(
            url=response.geturl(),
            body=response.read(),
            status=getattr(response, "status", 200),
            content_type=response.headers.get("content-type"),
        )


def robots_allowed(url: str, user_agent: str = USER_AGENT, fetcher: Fetcher | None = None) -> tuple[bool, bool]:
    parsed = urllib.parse.urlparse(url)
    robots_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    try:
        if fetcher is None:
            rp = urllib.robotparser.RobotFileParser(robots_url)
            rp.read()
            return True, bool(rp.can_fetch(user_agent, url))
        response = fetcher(robots_url)
        rp = urllib.robotparser.RobotFileParser(robots_url)
        rp.parse(response.body.decode("utf-8", "ignore").splitlines())
        return True, bool(rp.can_fetch(user_agent, url))
    except Exception:
        # Fail closed for unknown robots state.
        return True, False


def agency_documents_from_html(
    page_url: str,
    html_text: str,
    *,
    agency_name: str | None = None,
    allow_domains: list[str] | None = None,
    fetcher: Fetcher | None = None,
    respect_robots: bool = True,
    include_single_trade: bool = False,
) -> list[BidDocument]:
    parser = LinkParser()
    parser.feed(html_text)
    page_host = urllib.parse.urlparse(page_url).netloc.lower()
    allowed_hosts = {page_host, *(host.lower() for host in (allow_domains or []))}
    page_text = re.sub(r"<[^>]+>", " ", html_text)
    docs: list[BidDocument] = []
    seen: set[str] = set()
    for href, link_text in parser.links:
        absolute = urllib.parse.urljoin(page_url, href)
        parsed = urllib.parse.urlparse(absolute)
        host = parsed.netloc.lower()
        context = f"{page_text[:4000]} {link_text} {absolute}"
        score, matched, reject = construction_score(context)
        trades, all_trade = classify_trades(context)
        reasons = list(reject)
        robots_checked = False
        allowed_by_robots: bool | None = None
        if host not in allowed_hosts:
            reasons.append("host_not_allowlisted")
        if not document_url_looks_importable(absolute, link_text):
            reasons.append("link_not_pdf_zip_or_document_download")
        if respect_robots and "host_not_allowlisted" not in reasons and "link_not_pdf_zip_or_document_download" not in reasons:
            robots_checked, allowed_by_robots = robots_allowed(absolute, fetcher=fetcher)
            if not allowed_by_robots:
                reasons.append("robots_disallow")
        if not _meets_trade_scope(trades, all_trade, include_single_trade=include_single_trade):
            reasons.append("not_all_trade_or_multi_trade_scope")
        file_name = _safe_filename(absolute, fallback="agency_document.pdf")
        ext = Path(file_name).suffix.lower()
        key = absolute.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        accepted = score >= 35 and not reasons
        docs.append(BidDocument(
            source_type="public_agency_page",
            source_url=page_url,
            document_url=absolute,
            project_title=_norm_text(link_text) or _norm_text(agency_name) or "Public agency bid document",
            file_name=file_name,
            file_type=ext.lstrip(".") or "unknown",
            agency=agency_name,
            access_policy="public_agency_allowlisted_page",
            robots_checked=robots_checked,
            allowed_by_robots=allowed_by_robots,
            matched_keywords=matched,
            matched_trades=trades,
            all_trade_or_full_project=all_trade,
            construction_score=score,
            accepted=accepted,
            rejection_reasons=sorted(set(reasons)),
        ))
    return docs


def discover_sam_live(
    api_key: str,
    *,
    posted_from: str,
    posted_to: str,
    limit: int = 50,
    include_single_trade: bool = False,
) -> list[BidDocument]:
    docs: list[BidDocument] = []
    for naics_prefix in CONSTRUCTION_NAICS_PREFIXES:
        params = {
            "api_key": api_key,
            "postedFrom": posted_from,
            "postedTo": posted_to,
            "limit": str(limit),
            "offset": "0",
            "ptype": "o,k,p",  # solicitation, combined synopsis/solicitation, presolicitation
            "ncode": naics_prefix,
        }
        url = SAM_OPPORTUNITIES_ENDPOINT + "?" + urllib.parse.urlencode(params)
        response = default_fetcher(url)
        payload = json.loads(response.body.decode("utf-8"))
        docs.extend(sam_documents_from_response(payload, include_single_trade=include_single_trade))
    return docs


def discover_from_config(config: dict[str, Any], *, fetcher: Fetcher | None = None) -> list[BidDocument]:
    docs: list[BidDocument] = []
    include_single_trade = bool(config.get("include_single_trade", False))
    sam = config.get("sam") if isinstance(config.get("sam"), dict) else None
    if sam:
        fixture = sam.get("fixture")
        if fixture:
            payload = json.loads(Path(fixture).read_text())
            docs.extend(sam_documents_from_response(payload, include_single_trade=include_single_trade))
        elif sam.get("enabled"):
            api_key = sam.get("api_key") or os.environ.get("SAM_GOV_API_KEY")
            if not api_key:
                raise SystemExit("SAM.gov live discovery requires SAM_GOV_API_KEY or sam.api_key in config.")
            docs.extend(discover_sam_live(
                api_key,
                posted_from=str(sam.get("posted_from") or "01/01/2026"),
                posted_to=str(sam.get("posted_to") or "12/31/2026"),
                limit=int(sam.get("limit") or 50),
                include_single_trade=include_single_trade,
            ))
    for page in config.get("agency_pages", []) or []:
        if not isinstance(page, dict):
            continue
        url = page.get("url")
        if not url:
            continue
        if page.get("fixture"):
            html_text = Path(page["fixture"]).read_text()
        else:
            if bool(config.get("respect_robots", True)):
                source_robots_checked, source_allowed = robots_allowed(str(url), fetcher=fetcher)
                if not source_allowed:
                    docs.append(BidDocument(
                        source_type="public_agency_page",
                        source_url=str(url),
                        document_url=str(url),
                        project_title=_norm_text(page.get("name")) or "Public agency bid page",
                        file_name=_safe_filename(str(url), fallback="source_page.html"),
                        file_type="html",
                        agency=page.get("name"),
                        access_policy="public_agency_allowlisted_page",
                        robots_checked=source_robots_checked,
                        allowed_by_robots=False,
                        accepted=False,
                        rejection_reasons=["source_page_robots_disallow"],
                    ))
                    continue
            if fetcher is None:
                response = default_fetcher(str(url))
            else:
                response = fetcher(str(url))
            html_text = response.body.decode("utf-8", "ignore")
        docs.extend(agency_documents_from_html(
            str(url),
            html_text,
            agency_name=page.get("name"),
            allow_domains=list(page.get("allow_domains") or []),
            fetcher=fetcher,
            respect_robots=bool(config.get("respect_robots", True)),
            include_single_trade=include_single_trade,
        ))
    return docs


def write_manifest(docs: list[BidDocument], output: Path, *, source_config: dict[str, Any] | None = None) -> dict[str, Any]:
    accepted = [d for d in docs if d.accepted]
    rejected = [d for d in docs if not d.accepted]
    trade_counts: dict[str, int] = {}
    for doc in accepted:
        for trade in doc.matched_trades:
            trade_counts[trade] = trade_counts.get(trade, 0) + 1
    manifest = {
        "generated_at": _now(),
        "schema_version": "public_bid_board_pdf_manifest_v1",
        "safety": {
            "public_or_authorized_sources_only": True,
            "internal_testing_only": True,
            "respect_robots_default": True,
            "no_login_bypass": True,
            "no_payment_or_checkout": True,
            "no_external_messages": True,
            "customer_delivery_ready": False,
        },
        "summary": {
            "candidate_count": len(docs),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "downloaded_count": sum(1 for d in docs if d.downloaded_path),
            "trade_counts": dict(sorted(trade_counts.items())),
            "all_trade_or_full_project_count": sum(1 for d in accepted if d.all_trade_or_full_project),
        },
        "source_config": source_config or {},
        "documents": [d.as_manifest() for d in docs],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def download_documents(
    docs: list[BidDocument],
    output_dir: Path,
    *,
    fetcher: Fetcher | None = None,
    delay_seconds: float = 1.0,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> list[BidDocument]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        if not doc.accepted:
            continue
        try:
            response = (fetcher or default_fetcher)(doc.document_url)
            content_type = response.content_type or ""
            ext = _extension_for_url(doc.document_url, content_type)
            if ext not in DOWNLOAD_EXTENSIONS:
                doc.accepted = False
                doc.error = f"download_content_type_not_pdf_or_zip:{content_type or 'unknown'}"
                doc.rejection_reasons.append("download_content_type_not_pdf_or_zip")
                continue
            if len(response.body) > max_bytes:
                doc.accepted = False
                doc.error = f"download_exceeds_max_bytes:{len(response.body)}"
                doc.rejection_reasons.append("download_exceeds_max_bytes")
                continue
            digest = hashlib.sha256(response.body).hexdigest()
            name = _safe_filename(doc.file_name)
            if not Path(name).suffix:
                name = f"{name}{ext}"
            target = output_dir / name
            if target.exists():
                stem = target.stem
                suffix = target.suffix
                target = output_dir / f"{stem}_{digest[:8]}{suffix}"
            target.write_bytes(response.body)
            doc.sha256 = digest
            doc.downloaded_path = str(target)
            doc.downloaded_bytes = len(response.body)
        except Exception as exc:  # pragma: no cover - defensive runtime path
            doc.error = str(exc)
            doc.rejection_reasons.append("download_error")
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    return docs


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover/import public construction bid-board PDFs for Mobi testing.")
    parser.add_argument("--config", required=True, help="JSON source config with sam fixture/live settings and agency_pages.")
    parser.add_argument("--output", help="Manifest JSON path. Defaults under data/bid_board_imports/<run_id>/manifest.json.")
    parser.add_argument("--download", action="store_true", help="Download accepted public PDFs/ZIPs. Default is dry-run manifest only.")
    parser.add_argument("--output-dir", help="Download directory. Defaults next to the manifest.")
    parser.add_argument("--sam-api-key", help="SAM.gov API key. Prefer SAM_GOV_API_KEY env var; never commit this.")
    parser.add_argument("--delay-seconds", type=float, default=1.0, help="Delay between downloads when --download is used.")
    parser.add_argument("--max-bytes", type=int, default=MAX_DOWNLOAD_BYTES, help="Maximum bytes per downloaded file.")
    parser.add_argument(
        "--include-single-trade",
        action="store_true",
        help="Opt in to accepting single-trade construction bid docs. Default requires all-trade/full-project or strong multi-trade scope.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    config_path = Path(args.config)
    config = json.loads(config_path.read_text())
    if args.sam_api_key:
        config.setdefault("sam", {})["api_key"] = args.sam_api_key
    if args.include_single_trade:
        config["include_single_trade"] = True
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.output) if args.output else DEFAULT_OUTPUT_ROOT / run_id / "manifest.json"
    output_dir = Path(args.output_dir) if args.output_dir else output.parent / "files"

    docs = discover_from_config(config)
    if args.download:
        docs = download_documents(docs, output_dir, delay_seconds=args.delay_seconds, max_bytes=args.max_bytes)
    manifest = write_manifest(docs, output, source_config={"config_path": str(config_path), "download": bool(args.download)})
    print(json.dumps({"manifest": str(output), "summary": manifest["summary"]}, indent=2, sort_keys=True))
    return 0 if manifest["summary"]["accepted_count"] > 0 else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
