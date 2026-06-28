# Mobi Automated Estimating API — Phases 1 & 2

Lean, deterministic FastAPI foundation for PDF plan intake, **blueprint
ingestion**, and the canonical estimating schemas. Pricing arithmetic is
intentionally excluded from the API and schema layers; it will live in a separate
**deterministic Python pricing engine**. No LLM ever performs pricing arithmetic
or identifies sheet numbers, and every extracted quantity must carry a page
number, a **verified** sheet number, an evidence reference, a confidence score,
and an explicit review-required flag.

> - **Phase 1** (done): stable, tested, deterministic, deployable intake + schemas.
> - **Phase 2** (this milestone): deterministic blueprint ingestion & sheet
>   indexing — per-page records, text/image/thumbnail artifacts, page metadata,
>   duplicate detection, conservative sheet-number/title detection, and a human
>   verification workflow. See [`docs/phase-2-blueprint-ingestion.md`](docs/phase-2-blueprint-ingestion.md).
>
> Still intentionally **excluded**: OCR, any LLM/AI, and pricing.

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
│   ├── schemas.py            # Canonical strict Pydantic schemas + enums
│   ├── processing_schemas.py # Phase 2 API request/response models
│   ├── status_rules.py       # Project lifecycle transition graph
│   └── services/
│       ├── pdf_service.py        # PyMuPDF validation/inspection (P1)
│       ├── sheet_detection.py    # Deterministic sheet number/title detection
│       ├── processing_service.py # Per-page ingestion orchestrator (P2)
│       └── storage.py            # Safe artifact paths + atomic writes
├── tests/
│   ├── conftest.py               # Fixtures + PDF builders
│   ├── test_api.py               # Phase 1 HTTP tests
│   ├── test_schemas.py           # Schema/validation guarantees
│   ├── test_status_rules.py      # Lifecycle transition tests
│   ├── test_sheet_detection.py   # Detector unit tests
│   ├── test_processing.py        # Processing pipeline + endpoints
│   ├── test_sheets_api.py        # Sheet list/detail/verify/artifacts
│   ├── test_migrations.py        # Migration + concurrency guard
│   └── test_source_reference.py  # Verified-vs-detected guarantee
├── docs/
│   └── phase-2-blueprint-ingestion.md
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

`/health` and `/ready` are also mounted under `/api/v1` for convenience.

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
| `MOBI_LOG_LEVEL`          | `INFO`             | Logging level                            |
| `MOBI_JSON_LOGS`          | `false`            | Emit JSON access logs when `true`        |
| `MOBI_APP_VERSION`        | `0.1.0`            | Reported app/version string              |
| `MOBI_API_V1_PREFIX`      | `/api/v1`          | Versioned API prefix                     |

## Database migrations

The schema is managed by a tiny forward-only migration runner (`app/migrations.py`)
tracked in a `schema_migrations` table. `init_db()` applies any pending migrations
on startup. Migrations are **safe and idempotent**: they never drop or recreate
data and they upgrade an existing Phase 1 database in place (adding the
`processing_jobs` and `sheets` tables). There is no separate migration command —
just start the app (or run the tests).

## Testing

```bash
cd mobi-estimating-phase1
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

The suite (122 tests) covers, in addition to the Phase 1 intake/schema tests:
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

## Current limitations

- **No OCR yet (intentional)** — pages with insufficient embedded text are flagged
  `requires_ocr=true` for a later phase rather than processed with OCR. OCR is
  deferred to avoid heavy native dependencies and non-deterministic output.
- **No AI/LLM (intentional)** — sheet numbers/titles are detected with regex +
  geometry only, and must be human-verified before they are trusted. No LLM is
  used anywhere.
- **No pricing engine yet** — `PricingBreakdown`/`EstimateLineItem` schemas exist
  but nothing populates them.
- **In-process worker** — processing runs inline (or as a FastAPI background task).
  An external worker (still **without** Redis/Celery if a lean queue suffices) is
  required before high-volume production use.
- **Conservative detection** — the detector favors flagging for review over
  guessing, so clean title blocks detect well but unusual layouts will often be
  marked `requires_review` with no detected number. This is by design.
- **Strict canonical schemas** — the estimating schemas remain strict (enum members
  / `Decimal`); the Phase 2 *API* models are lenient (accept enum strings) but do
  not weaken the canonical models.
- **Single-trade (Painting)** — only CSI Division 09 Painting is modeled downstream.
- **SQLite single-node** — fine for the MVP; not built for concurrent multi-writer
  deployments.
- **No authentication / rate limiting** — artifact and all endpoints must be placed
  behind auth before public deployment.
- **Docker base image** — building the image requires pulling `python:3.12-slim`
  from Docker Hub; in restricted-egress environments that pull may be blocked
  (an environment limitation, not an application defect).

## Recommended next milestone (Phase 3)

Deterministic, evidence-anchored painting takeoff + pricing over **verified**
sheets:

1. **Sheet classification & discipline tagging** — deterministically map verified
   sheets to disciplines and identify the architectural/finish sheets relevant to
   painting.
2. **Painting takeoff (evidence-anchored)** — derive `PaintingScopeItem` candidates
   from finish schedules and room/wall data, where every quantity carries
   page + **verified** sheet number + evidence + confidence, and anything uncertain
   is flagged `review_required=true`. Use `build_source_reference()` so only
   verified sheets can anchor a quantity.
3. **Deterministic Python pricing engine** — a pure-Python, versioned, unit-tested
   module turning scope items into `EstimateLineItem` + `PricingBreakdown`, with
   **no** LLM arithmetic.
4. **Review & approval workflow** — endpoints to approve/correct scope items and
   drive `ready_for_review → needs_review → complete`.
5. **Optional targeted OCR** — only for pages flagged `requires_ocr`, behind a
   clearly isolated, swappable adapter.
