# Public Bid-Board PDF Collector

The public bid-board PDF collector creates a safe, traceable seed set of real construction bid documents for Mobi's local real-document harness.

It is for **public or authorized sources only**. It does not bypass logins, paywalls, CAPTCHA, robots.txt, session gates, or commercial bid-board restrictions. Every collected file is marked `internal_testing_only=true` and is not a customer deliverable.

## Sources supported

### 1. SAM.gov opportunities

The collector understands SAM.gov Opportunities API-style JSON and live SAM.gov search when a public API key is supplied.

- Construction NAICS families included:
  - `236xxx` — building construction
  - `237xxx` — heavy/civil construction
  - `238xxx` — specialty trade contractors
- It reads `resourceLinks` as attachment URLs.
- It keeps only construction/bid/document-like attachments.
- Live mode requires `SAM_GOV_API_KEY` or `--sam-api-key`.

### 2. Public agency bid pages

The collector can read allowlisted public agency bid pages and extract PDF/ZIP links.

It will:

- normalize relative links
- restrict downloads to the agency page host plus explicit `allow_domains`
- respect `robots.txt` by default
- score links for construction/bid/document signals
- tag trade coverage
- reject non-document, off-domain, low-score, or robots-disallowed links

## Trade coverage tags

Each accepted candidate is tagged with matching trades/categories, including:

- `general`
- `civil_site`
- `earthwork_utilities`
- `demolition`
- `concrete`
- `masonry`
- `steel`
- `carpentry`
- `roofing`
- `doors_windows`
- `drywall_framing`
- `finishes`
- `flooring`
- `painting`
- `mechanical_hvac`
- `plumbing`
- `electrical`
- `fire_protection`
- `low_voltage`
- `landscaping`
- `paving`

The collector defaults to **all-trade/full-project or strong multi-trade bid documents** because Mobi needs whole-project estimating coverage first. Single-trade construction bid documents are rejected by default with `not_all_trade_or_multi_trade_scope`; use `--include-single-trade` only when intentionally building a trade-specific supplemental corpus.

## Source config

Example config:

```json
{
  "respect_robots": true,
  "sam": {
    "enabled": true,
    "posted_from": "07/01/2026",
    "posted_to": "07/07/2026",
    "limit": 50
  },
  "agency_pages": [
    {
      "name": "Example City Public Works",
      "url": "https://example.gov/procurement/current-bids",
      "allow_domains": ["example.gov"]
    }
  ]
}
```

For offline testing, use fixtures instead of live URLs:

```json
{
  "respect_robots": false,
  "sam": { "fixture": "fixtures/sam-opportunities.json" },
  "agency_pages": [
    {
      "name": "Fixture City",
      "url": "https://city.example.gov/bids",
      "fixture": "fixtures/agency-bids.html"
    }
  ]
}
```

## Dry-run discovery

Dry-run discovery writes a manifest but does not download files:

```bash
python scripts/public_bid_board_pdf_collector.py \
  --config path/to/source-config.json \
  --output data/bid_board_imports/dry-run/manifest.json
```

The command exits `0` when at least one candidate is accepted. It exits `2` when no accepted candidates are found.

## Import/download

Downloading must be explicit:

```bash
SAM_GOV_API_KEY=... python scripts/public_bid_board_pdf_collector.py \
  --config path/to/source-config.json \
  --download \
  --output data/bid_board_imports/20260707/manifest.json \
  --output-dir data/bid_board_imports/20260707/files
```

Download safeguards:

- public/allowlisted hosts only
- SAM.gov resource links must use SAM-controlled HTTPS hosts
- source listing pages and document links respect robots.txt by default
- PDF/ZIP extension or content type required
- all-trade/full-project or strong multi-trade scope required by default
- SHA256 recorded
- file size limited
- delay between downloads
- all files marked internal testing only

## Manifest fields

The manifest includes:

- source type and URL
- project title
- agency/solicitation metadata when available
- document URL
- file name/type
- SHA256 and local path when downloaded
- `internal_testing_only=true`
- robots/access-policy fields
- matched construction keywords
- matched trade tags
- construction score
- accepted/rejected status
- rejection reasons

## Feed imported PDFs into the real-document harness

After import, run the existing batch shakeout against the downloaded file folder:

```bash
python scripts/bid_board_batch_shakeout.py \
  data/bid_board_imports/20260707/files \
  --workdir data/bid_board_imports/20260707/harness-workdir \
  --output data/bid_board_imports/20260707/batch-report.json \
  --apply-test-inputs
```

Do not treat these reports as customer-ready estimates. They are internal accuracy/readiness measurements only.

## Do not use this collector for

- gated commercial bid boards without written/authorized export rights
- BuildingConnected/Dodge/ConstructConnect/PlanHub private bid packages unless imported from an authorized account/export path approved by Moses
- CAPTCHA bypass
- login/session scraping
- paid download circumvention
- external messages to agencies, GCs, or contractors
- customer estimate delivery
