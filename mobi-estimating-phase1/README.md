# Mobi Automated Estimating API — Phases 1–5

Lean, deterministic FastAPI foundation for PDF plan intake, **blueprint ingestion**,
a **trade-agnostic extraction + evidence + human-review framework**, and a
**deterministic, versioned pricing engine**. No LLM ever performs pricing arithmetic,
identifies sheet numbers, or produces trusted/derived quantities. Every scope item is
backed by evidence on a **verified** sheet; all canonical quantities and money are
deterministic Python (`Decimal`); nothing is auto-approved; and no real cost data is
bundled.

> - **Phase 1** (done): stable, tested, deterministic, deployable intake + schemas.
> - **Phase 2** (done): deterministic blueprint ingestion & sheet indexing.
>   See [`docs/phase-2-blueprint-ingestion.md`](docs/phase-2-blueprint-ingestion.md).
> - **Phase 3** (done): trade-agnostic extraction framework, evidence, deterministic
>   quantity engine, human review. See
>   [`docs/phase-3-trade-extraction-framework.md`](docs/phase-3-trade-extraction-framework.md).
> - **Phase 4** (done): versioned cost books, trade assemblies, deterministic
>   pricing, indirects/overhead/profit/contingency, estimate versions, rollups,
>   JSON/CSV exports. See [`docs/phase-4-pricing-engine.md`](docs/phase-4-pricing-engine.md).
> - **Phase 5** (this milestone): deterministic client-facing **proposal generation**
>   from an approved estimate — versioned/immutable, exact sell-price allocation,
>   accept/decline lifecycle, and print-ready HTML + Markdown + JSON exports (sell +
>   scope only, no cost/margin leak). See
>   [`docs/phase-5-proposal-generation.md`](docs/phase-5-proposal-generation.md).
> - Real bid-board/local shakeout operations are documented in
>   [`docs/real-bid-board-shakeout-guide.md`](docs/real-bid-board-shakeout-guide.md).
>
> Still intentionally **excluded**: OCR, computer-vision measurement, native PDF
> binaries, payments/Stripe/invoicing/CRM, any LLM doing arithmetic, and any bundled
> market price data. Live AI extraction is **off by default** (offline mock provider).

## Repository structure

```text
mobi-estimating-phase1/
├── app/
│   ├── config.py             # Centralized, env-driven settings (MOBI_* vars)
│   ├── database.py           # SQLite access: projects, jobs, sheets, claims
│   ├── migrations.py         # Forward-only SQLite migrations + runner
│   ├── errors.py             # Structured error envelope + exception handlers
│   ├── logging_config.py     # Logging setup + request-logging middleware
│   ├── main.py               # App factory: wiring of settings/logging/routers
│   ├── routers.py            # System probes + /api/v1 project endpoints (P1)
│   ├── routers_processing.py # /api/v1 processing, sheets, verification (P2)
│   ├── routers_extraction.py # /api/v1 trades, extraction, scope items, review (P3)
│   ├── schemas.py            # Canonical strict Pydantic schemas + enums
│   ├── processing_schemas.py # Phase 2 API request/response models
│   ├── extraction_db.py      # P3 data access (runs, scope items, evidence, review)
│   ├── status_rules.py       # Project lifecycle transition graph
│   ├── estimating/           # Shared deterministic quantity engine (P3)
│   │   ├── units.py  formulas.py  quantities.py
│   ├── extraction/           # Trade-agnostic extraction core (P3)
│   │   ├── schemas.py  provider_schemas.py  base.py  registry.py
│   │   ├── mock_provider.py  openai_provider.py  cache.py  service.py
│   ├── review/               # Human-review workflow (P3)
│   │   ├── schemas.py  service.py
│   ├── trades/               # Trade modules (plugins) (P3)
│   │   ├── base.py  registry.py  __init__.py (bootstrap)
│   │   ├── painting/         # First reference trade module
│   │   └── demo_concrete/    # Demonstration second trade
│   └── services/
│       ├── pdf_service.py        # PyMuPDF validation/inspection (P1)
│       ├── sheet_detection.py    # Deterministic sheet number/title detection
│       ├── processing_service.py # Per-page ingestion orchestrator (P2)
│       └── storage.py            # Safe artifact paths + atomic writes
├── tests/                        # 284 tests across Phases 1–5
├── app/pricing/  app/pricing_db.py  app/estimates/   # Phase 4 pricing core
├── app/proposals/  app/proposals_db.py  app/routers_proposals.py  # Phase 5 proposals
├── app/trades/<trade>/assemblies.py  pricing_validation.py
├── docs/                         # phase-2/3/4 + cost-book, labor/production,
│   │                             # calculation-order, versioning, CSV, assembly guides
│   └── trades/                    # painting + concrete reference (extraction + pricing)
├── data/uploads/.gitkeep         # Runtime upload + SQLite location (gitignored)
├── .env.example
├── Dockerfile / docker-compose.yml / .dockerignore
├── pytest.ini
├── requirements.txt / requirements-dev.txt
└── README.md
```

## Local setup (without Docker)

```bash
cd mobi-estimating-phase1
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

- Swagger UI: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness: http://localhost:8000/ready

## Docker setup

```bash
cd mobi-estimating-phase1
docker compose up --build
```

This builds the image and starts the API on http://localhost:8000. A named volume
(`mobi_data`) is mounted at `/app/data`, so both the SQLite database
(`/app/data/mobi.db`) and uploaded PDFs (`/app/data/uploads/`) persist across
container restarts:

```bash
docker compose restart        # data survives
docker compose down && docker compose up   # data still survives (named volume)
```

To validate the compose file without building:

```bash
docker compose config
```

## API endpoints

| Method | Path                                                     | Purpose                                  |
| ------ | -------------------------------------------------------- | ---------------------------------------- |
| GET    | `/health`                                                | Liveness probe                           |
| GET    | `/ready`                                                 | Readiness probe (DB + upload dir)        |
| POST   | `/api/v1/projects/upload`                                | Upload + validate a PDF plan set         |
| GET    | `/api/v1/projects/{id}/status`                           | Fetch a project's status                 |
| PATCH  | `/api/v1/projects/{id}/status`                           | Transition status (rules enforced)       |
| POST   | `/api/v1/projects/{id}/process`                          | Start/queue deterministic processing (202)|
| GET    | `/api/v1/projects/{id}/processing-status`                | Processing progress + job info           |
| GET    | `/api/v1/projects/{id}/sheets`                           | List sheets (paginated, page order)      |
| GET    | `/api/v1/projects/{id}/sheets/{sheet_id}`                | Full sheet metadata                      |
| PATCH  | `/api/v1/projects/{id}/sheets/{sheet_id}/verification`   | Human-verify sheet number/title          |
| GET    | `/api/v1/projects/{id}/sheets/{sheet_id}/thumbnail`      | Sheet thumbnail PNG (controlled)         |
| GET    | `/api/v1/projects/{id}/sheets/{sheet_id}/image`          | Sheet full image PNG (controlled)        |
| GET    | `/api/v1/trades`                                         | List registered trades (Phase 3)         |
| GET    | `/api/v1/trades/{trade_code}`                            | Trade definition                         |
| GET    | `/api/v1/projects/{id}/trades/{trade}/eligible-sheets`   | Routing preview (per trade)              |
| PATCH  | `/api/v1/projects/{id}/trades/{trade}/sheets/{sid}/eligibility` | Manual include/exclude            |
| POST   | `/api/v1/projects/{id}/trades/{trade}/extractions`       | Start extraction run (202)               |
| GET    | `/api/v1/projects/{id}/trades/{trade}/extractions/{run_id}` | Extraction run status                 |
| GET    | `/api/v1/projects/{id}/trades/{trade}/extractions`       | List runs (paginated)                    |
| GET    | `/api/v1/projects/{id}/scope-items`                      | List scope items (filters + pagination)  |
| GET    | `/api/v1/projects/{id}/scope-items/{item_id}`            | Scope item + evidence + history          |
| PATCH  | `/api/v1/projects/{id}/scope-items/{item_id}`            | Correct (re-validated)                   |
| POST   | `/api/v1/projects/{id}/scope-items/{item_id}/approve`    | Approve (rules enforced)                 |
| POST   | `/api/v1/projects/{id}/scope-items/{item_id}/reject`     | Reject (reason required)                 |
| POST   | `/api/v1/projects/{id}/scope-items/{item_id}/recalculate`| Recompute via a registered formula       |

`/health` and `/ready` are also mounted under `/api/v1` for convenience.

### Phase 4 — pricing endpoints (under `/api/v1`)

Cost books: `POST/GET /cost-books`, `GET /cost-books/{id}`,
`POST/GET /cost-books/{id}/versions`, `GET /cost-books/{id}/versions/{vid}`,
`POST .../publish`, `POST .../archive`. Cost inputs (draft-only) under
`/cost-books/{id}/versions/{vid}/`: `sources`, `labor-rates`, `crews`,
`production-rates`, `material-rates`, `equipment-rates`, `subcontract-quotes`,
`other-direct-costs` (each create + list), plus `assemblies` (create/list/get/validate)
and `imports/{kind}/preview|commit` (CSV). Mappings:
`POST/GET /projects/{pid}/scope-items/{sid}/assembly-mapping`. Pricing:
`POST /projects/{pid}/pricing/preview`, `POST /projects/{pid}/estimates`,
`POST .../estimates/{eid}/versions/{vid}/price`, `POST .../estimates/{eid}/reprice`,
`GET .../line-items|rollup|exceptions`, `POST .../approve`,
`POST .../line-items/{lid}/override`, `GET .../export.json|export.csv`.

Live pricing incurs **zero** model cost — it is pure local Python.

### Phase 3 — extract → review (mock provider, offline)

```bash
# 1) after upload + processing, verify the relevant sheets (Phase 2), then:
curl "http://localhost:8000/api/v1/trades"                       # list trades
curl "http://localhost:8000/api/v1/projects/PID/trades/painting/eligible-sheets"
curl -X POST "http://localhost:8000/api/v1/projects/PID/trades/painting/extractions" \
  -H "Content-Type: application/json" -d '{"force": false, "dry_run": false}'
curl "http://localhost:8000/api/v1/projects/PID/scope-items?trade_code=painting"
curl "http://localhost:8000/api/v1/projects/PID/scope-items/ITEM_ID"
# recompute a derived quantity with a registered formula:
curl -X POST "http://localhost:8000/api/v1/projects/PID/scope-items/ITEM_ID/recalculate" \
  -H "Content-Type: application/json" \
  -d '{"formula_id":"painting.wall_gross_area","inputs":{"length_ft":"30","height_ft":"10"}}'
# approve (requires trusted evidence + a resolved quantity):
curl -X POST "http://localhost:8000/api/v1/projects/PID/scope-items/ITEM_ID/approve"
```

> **Security note:** the artifact endpoints (`/thumbnail`, `/image`) resolve files
> strictly inside the configured data root and reject traversal, but they are
> **unauthenticated** in this phase. They must be placed behind authentication/
> authorization before any public production deployment.

### Processing lifecycle

```
uploaded → queued → processing → ready_for_review
                        └────────→ failed → queued (retry)
complete = terminal   (ready_for_review → queued only on explicit force reprocess)
```

Processing is **idempotent**: each run clears prior sheet rows and regenerated
artifacts first, and a partial unique index allows at most one active job per
project, so duplicate/concurrent `process` calls never create duplicate sheets.
The original `original.pdf` is never modified.

### Artifact storage layout

```
data/uploads/<project_uuid>/
├── original.pdf
└── processed/
    ├── manifest.json
    └── sheets/page-0001/{full.png, thumbnail.png, text.txt}
```

Only relative paths are stored in SQLite. See
[`docs/phase-2-blueprint-ingestion.md`](docs/phase-2-blueprint-ingestion.md).

### Example curl commands

Health / readiness:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Upload a PDF plan set (returns `201` with the new project record):

```bash
curl -X POST "http://localhost:8000/api/v1/projects/upload" \
  -F "project_name=Downtown Office Renovation" \
  -F "contractor_name=Example GC" \
  -F "plan=@./plans.pdf;type=application/pdf"
```

Check project status:

```bash
curl "http://localhost:8000/api/v1/projects/PROJECT_UUID/status"
```

Transition project status (lifecycle rules enforced; invalid transitions → `409`):

```bash
curl -X PATCH "http://localhost:8000/api/v1/projects/PROJECT_UUID/status" \
  -F "new_status=processing"
```

**Process a newly uploaded project** (deterministic ingestion; returns `202`):

```bash
curl -X POST "http://localhost:8000/api/v1/projects/PROJECT_UUID/process" \
  -H "Content-Type: application/json" -d '{"force": false}'
```

**Inspect processing status**:

```bash
curl "http://localhost:8000/api/v1/projects/PROJECT_UUID/processing-status"
```

**List sheets** (paginated, ordered by PDF page number):

```bash
curl "http://localhost:8000/api/v1/projects/PROJECT_UUID/sheets?limit=50&offset=0"
```

**Get one sheet's full metadata**:

```bash
curl "http://localhost:8000/api/v1/projects/PROJECT_UUID/sheets/SHEET_UUID"
```

**Verify (or correct) sheet metadata** — detected values are preserved:

```bash
curl -X PATCH \
  "http://localhost:8000/api/v1/projects/PROJECT_UUID/sheets/SHEET_UUID/verification" \
  -H "Content-Type: application/json" \
  -d '{"verified_sheet_number":"A-101","verified_sheet_title":"FLOOR PLAN","review_status":"verified"}'
```

**Fetch a sheet image / thumbnail**:

```bash
curl -o sheet.png  "http://localhost:8000/api/v1/projects/PROJECT_UUID/sheets/SHEET_UUID/image"
curl -o thumb.png  "http://localhost:8000/api/v1/projects/PROJECT_UUID/sheets/SHEET_UUID/thumbnail"
```

**Force a safe reprocess** (idempotent; replaces only generated artifacts):

```bash
curl -X POST "http://localhost:8000/api/v1/projects/PROJECT_UUID/process" \
  -H "Content-Type: application/json" -d '{"force": true}'
```

### Error responses

Every error uses a single structured envelope:

```json
{
  "error": {
    "code": "not_found",
    "message": "Project not found",
    "details": null
  },
  "request_id": "0f1a2b..."
}
```

The same `request_id` is returned in the `X-Request-ID` response header and logged
on the server for correlation.

## Environment variables

All variables are prefixed with `MOBI_` and may be placed in a `.env` file
(see `.env.example`).

| Variable                  | Default            | Description                              |
| ------------------------- | ------------------ | ---------------------------------------- |
| `MOBI_DB_PATH`            | `data/mobi.db`     | SQLite database path                     |
| `MOBI_UPLOAD_DIR`         | `data/uploads`     | Directory for stored PDF uploads         |
| `MOBI_MAX_UPLOAD_BYTES`   | `104857600` (100M) | Maximum accepted upload size in bytes    |
| `MOBI_UPLOAD_CHUNK_BYTES` | `1048576` (1M)     | Streaming read chunk size                |
| `MOBI_RENDER_DPI`         | `150`              | Full-resolution render DPI               |
| `MOBI_THUMBNAIL_MAX_WIDTH`| `320`              | Thumbnail max width (px)                  |
| `MOBI_MIN_TEXT_CHARS`     | `12`               | Below this embedded-text count → flag OCR |
| `MOBI_MAX_PAGE_COUNT`     | `1000`             | Max pages processed per PDF              |
| `MOBI_MAX_RENDER_PIXELS`  | `40000000`         | Decompression-bomb guard (px per page)   |
| `MOBI_PROCESS_INLINE`     | `true`             | Process inline (true) or background task |
| `MOBI_ENABLED_TRADES`     | `painting`         | Comma-separated enabled trade codes      |
| `MOBI_EXTRACTION_PROVIDER`| `mock`             | `mock` (offline) or `openai`             |
| `MOBI_ENABLE_LIVE_EXTRACTION` | `false`        | Enable live AI calls (off by default)    |
| `MOBI_OPENAI_API_KEY`     | _(empty)_          | Secret; never logged or returned         |
| `MOBI_OPENAI_MODEL`       | `gpt-4o-mini`      | Model id for the live provider           |
| `MOBI_EXTRACTION_MAX_PAGES`| `50`              | Cost cap: max pages per run              |
| `MOBI_EXTRACTION_MAX_PAGES_PER_TRADE`| `50`    | Cost cap: max pages per trade            |
| `MOBI_EXTRACTION_MAX_TEXT_CHARS_PER_PAGE`| `20000` | Cost cap: text sent per page         |
| `MOBI_EXTRACTION_TIMEOUT_SECONDS`| `60`        | Provider timeout                         |
| `MOBI_EXTRACTION_MAX_RETRIES`| `2`             | Provider retry budget                    |
| `MOBI_EXTRACTION_STORE_RAW_RESPONSE`| `false`  | Store raw provider output (privacy risk) |
| `MOBI_EXTRACTION_INLINE`  | `true`             | Run extraction inline vs background       |
| `MOBI_EXTRACTION_CACHE_ENABLED`| `true`        | Cache results by content + versions      |
| `MOBI_LOG_LEVEL`          | `INFO`             | Logging level                            |
| `MOBI_JSON_LOGS`          | `false`            | Emit JSON access logs when `true`        |
| `MOBI_APP_VERSION`        | `0.1.0`            | Reported app/version string              |
| `MOBI_API_V1_PREFIX`      | `/api/v1`          | Versioned API prefix                     |

## Database migrations

The schema is managed by a tiny forward-only migration runner (`app/migrations.py`)
tracked in a `schema_migrations` table. `init_db()` applies any pending migrations
on startup. Migrations are **safe and idempotent**: they never drop or recreate
data and they upgrade an existing database in place. There are now **16**
migrations — Phase 1/2 (3), Phase 3 (4–11), Phase 4 (12–15), and Phase 5 (16:
proposals). There is no separate migration command — just start the app (or run tests).

## Testing

```bash
cd mobi-estimating-phase1
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

The suite (**284 tests**) covers Phases 1–5. Phase 5 adds proposal generation:
deterministic largest-remainder sell allocation (exact reconciliation), build only
from an approved estimate, trade/line/summary detail, issue→immutable+snapshot,
accept/decline (reason required), regenerate/supersede (accepted preserved), export
HTML/Markdown/JSON with no cost/margin/rate/path leak, snapshot reproducibility, and
ownership checks. Earlier phases: Phase 4 adds: Decimal/money rules
(NaN/Infinity/negative rejection, markup≠margin, margin≥100% rejected, currency
quantization, repeating decimals, large totals), the pricing engine (material with
coverage+waste, labor-hour and crew-hour calculations kept distinct, equipment min
charge, missing-component-blocks-line, unpriced-but-visible scope, expired/unverified
rate exceptions, determinism), cost-book versioning + immutability + CSV import
(preview/atomic commit/invalid rejection), and end-to-end painting + concrete pricing,
reprice/supersede, approve/immutability, manual override preserving the original,
snapshot reproducibility, exports without secrets/paths, preview creating no version,
unapproved-scope exclusion, and a 3,000-line benchmark. Earlier phases: Phase 3 adds: the deterministic
quantity engine (Decimal precision, unit/negative-input rejection, reproducibility,
formula-version, arbitrary/unregistered-formula rejection), the trade registry
(register, second trade, duplicate/unknown/disabled, fake-trade proof the core
isn't Painting-bound), routing (eligible/blocked-unverified/blocked-ocr/excluded,
manual include/exclude, per-trade differences, ownership), the provider layer (mock
multi-trade, malformed/unknown-field/missing-evidence rejection, timeout + retries,
live disabled by default, missing key safe), canonical + trade-payload schemas, the
extraction lifecycle (duplicate active run, separate per-trade runs, forced/dry-run,
restart persistence, approved items untouched after re-extraction), the review
workflow (pending start, evidence/quantity-gated approval, correction preserving the
original candidate, manual-quantity marking, registered-formula recalculation,
reason-required rejection, append-only history, ownership), and the full API surface
(no filesystem paths exposed). It also covers, from Phases 1–2:
single/multi-page processing, embedded-text extraction + text artifacts, full
image + thumbnail rendering, manifest creation, page dimensions/rotation, mixed
page sizes, blank and image-only (OCR-flagged) pages, deterministic sheet-number
and title detection (including "no reliable number" and "conflicting candidates"),
duplicate-page detection, page-checksum stability, processing progress, status
transitions, invalid project / missing original PDF, duplicate + forced + idempotent
reprocessing, sheet listing order + pagination, sheet detail, ownership validation,
human verification (with detected values preserved), unsafe-path rejection, missing
artifacts, persistence across restart, migration from the Phase 1 schema, and the
guarantee that an unverified detected sheet number cannot back a trusted source
reference.

## Architectural guarantees in this phase

- Unknown JSON fields are rejected by the canonical Pydantic schemas (`extra="forbid"`).
- Schemas run in Pydantic **strict** mode: enums must be passed as enum members
  and numbers as `Decimal` (no silent float→Decimal or string→enum coercion).
- Extracted quantities require a 1-based PDF page number, a sheet number, and an
  evidence string (`SourceReference`).
- Painting scope items below `0.900` confidence cannot bypass review.
- Quantities and money use `Decimal`, never binary floating point.
- Pricing schemas store deterministic engine results but perform **no** arithmetic.
- Uploads are size-limited (streamed), signature-checked, MIME-checked, and
  deduplicated by SHA-256.
- Project status changes are constrained by an explicit transition graph.
- SQLite runs in WAL mode; connections are always closed (no leaks).
- **(Phase 2)** Every page yields one fully-traceable sheet record (PDF page
  number, page index, dimensions, rotation, checksum, artifacts).
- **(Phase 2)** Sheet numbers/titles are *candidates* until human-verified; a
  detected value can never satisfy a trusted source reference.
- **(Phase 2)** Processing is idempotent and concurrency-guarded; the original
  PDF is never modified; artifacts are written atomically; render size is capped.
- **(Phase 3)** The extraction core is trade-agnostic — behavior is loaded from a
  trade registry, with no `if trade == "painting"` in shared code.
- **(Phase 3)** AI output is untrusted: candidates are never auto-approved, derived
  quantities are recomputed in Python, and evidence is anchored to verified sheets
  using DB records (provider sheet numbers are discarded).
- **(Phase 3)** Re-extraction never overwrites approved work; review history is
  append-only; the original provider candidate is always preserved.
- **(Phase 3)** Live AI is off by default; the app runs offline with a deterministic
  mock provider; API keys are never logged or returned.

## Current limitations

- **No OCR yet (intentional)** — pages with insufficient embedded text are flagged
  `requires_ocr=true` for a later phase rather than processed with OCR. OCR is
  deferred to avoid heavy native dependencies and non-deterministic output.
- **No AI/LLM (intentional)** — sheet numbers/titles are detected with regex +
  geometry only, and must be human-verified before they are trusted. No LLM is
  used anywhere.
- **Pricing engine exists, but real-rate readiness is not proven** — Phase 4
  deterministic pricing services, schemas, cost books, imports, rollups, and
  tests exist. Cost books still ship empty, and the generic all-trade path still
  needs harness-level pricing readiness/output metrics before real bid-board
  estimates can be considered test-ready.
- **In-process worker** — processing runs inline (or as a FastAPI background task).
  An external worker (still **without** Redis/Celery if a lean queue suffices) is
  required before high-volume production use.
- **Conservative detection** — the detector favors flagging for review over
  guessing, so clean title blocks detect well but unusual layouts will often be
  marked `requires_review` with no detected number. This is by design.
- **Strict canonical schemas** — the estimating schemas remain strict (enum members
  / `Decimal`); the Phase 2 *API* models are lenient (accept enum strings) but do
  not weaken the canonical models.
- **Painting is the only production trade** — it is the first *reference* module;
  `demo_concrete` is a demonstration trade (enable only intentionally). The core is
  trade-agnostic and ready for additional modules.
- **Mock provider by default** — real AI extraction quality is not yet exercised; the
  OpenAI live path is implemented behind the interface but could not be verified in
  this environment (no network/docs). Re-verify the SDK contract before enabling.
- **SQLite single-node** — fine for the MVP; not built for concurrent multi-writer
  deployments.
- **No authentication / rate limiting** — artifact and all endpoints must be placed
  behind auth before public deployment.
- **No bundled cost data (Phase 4)** — cost books ship empty; the user (or a CSV
  import) supplies all rates. Tests use clearly fictional values. The Painting and
  Concrete assemblies prove the architecture, not nationwide production pricing.
- **Proposals (Phase 5) show sell + scope only** — no cost/margin/rate/hour data;
  built only from an approved estimate; HTML export is print-to-PDF (no native PDF
  binary). No payments/invoicing/CRM.
- **Docker base image** — building the image requires pulling `python:3.12-slim`
  from Docker Hub; in restricted-egress environments that pull may be blocked
  (an environment limitation, not an application defect).

### Phase 5 — proposal endpoints (under `/api/v1/projects/{id}/proposals`)

`POST /proposals` (build from an approved estimate), `GET /proposals`,
`GET /proposals/{pid}`, `GET .../versions`, `GET .../versions/{vid}`,
`POST .../versions/{vid}/issue|accept|decline`, `POST .../regenerate`,
`GET .../versions/{vid}/review-events`, and
`GET .../versions/{vid}/export.json|export.md|export.html`. Exports show sell prices
+ scope only. The HTML export is print-to-PDF ready.

## Recommended next milestone (Phase 6)

On top of approved estimates + issued proposals (still no LLM arithmetic):

1. **Subcontractor bid leveling** — a full quote-comparison module building on the
   Phase 4 subcontract inputs (scope-aligned, apples-to-apples).
2. **Multi-currency + escalation curves** — extend the money layer beyond USD with
   dated FX and escalation indices, all `Decimal` and auditable.
3. **Historical cost feedback** — capture actuals vs estimate to refine production/
   material rates over time (deterministic, reviewer-gated).
4. **Native PDF rendering** — an optional server-side HTML→PDF renderer behind a
   swappable adapter (kept out of the core to avoid heavy deps).
5. **AI *assistant* (suggestions only)** — propose mappings/assemblies or flag
   anomalies for human confirmation; never priced arithmetic, never auto-approval.

See [`docs/phase-5-proposal-generation.md`](docs/phase-5-proposal-generation.md)
and the other `docs/` files for the architecture this builds on.
