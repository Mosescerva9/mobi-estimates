# Mobi Automated Estimating API — Phase 1

Lean, deterministic FastAPI foundation for PDF plan intake and the canonical
estimating schemas. Pricing arithmetic is intentionally excluded from the API and
schema layers; it will live in a separate **deterministic Python pricing engine**.
No LLM ever performs pricing arithmetic, and every extracted quantity must carry a
page number, sheet number, evidence reference, confidence score, and an explicit
review-required flag.

> Phase 1 scope: stable, tested, deterministic, deployable intake + schema layer.
> Blueprint/AI extraction is **not** part of this phase.

## Repository structure

```text
mobi-estimating-phase1/
├── app/
│   ├── __init__.py
│   ├── config.py            # Centralized, env-driven settings (MOBI_* vars)
│   ├── database.py          # SQLite access, schema init, status transitions
│   ├── errors.py            # Structured error envelope + exception handlers
│   ├── logging_config.py    # Logging setup + request-logging middleware
│   ├── main.py              # App factory: wiring of settings/logging/routers
│   ├── routers.py           # System probes + /api/v1 project endpoints
│   ├── schemas.py           # Canonical strict Pydantic schemas
│   └── services/
│       ├── __init__.py
│       └── pdf_service.py   # PyMuPDF inspection (no takeoff/pricing)
├── tests/
│   ├── conftest.py          # Fixtures + PDF builders
│   ├── test_api.py          # HTTP-level tests
│   ├── test_schemas.py      # Schema/validation guarantees
│   └── test_status_rules.py # Lifecycle transition tests
├── data/
│   └── uploads/.gitkeep     # Runtime upload + SQLite location (gitignored)
├── .env.example
├── .dockerignore
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
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

| Method | Path                                  | Purpose                              |
| ------ | ------------------------------------- | ------------------------------------ |
| GET    | `/health`                             | Liveness probe                       |
| GET    | `/ready`                              | Readiness probe (DB + upload dir)    |
| POST   | `/api/v1/projects/upload`             | Upload + validate a PDF plan set     |
| GET    | `/api/v1/projects/{id}/status`        | Fetch a project's status             |
| PATCH  | `/api/v1/projects/{id}/status`        | Transition status (rules enforced)   |

`/health` and `/ready` are also mounted under `/api/v1` for convenience.

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
| `MOBI_LOG_LEVEL`          | `INFO`             | Logging level                            |
| `MOBI_JSON_LOGS`          | `false`            | Emit JSON access logs when `true`        |
| `MOBI_APP_VERSION`        | `0.1.0`            | Reported app/version string              |
| `MOBI_API_V1_PREFIX`      | `/api/v1`          | Versioned API prefix                     |

## Testing

```bash
cd mobi-estimating-phase1
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

The suite covers the health/readiness endpoints, valid/invalid/empty/corrupted/
encrypted/oversized uploads, MIME and extension checks, duplicate (SHA-256)
detection, SQLite persistence, status-transition rules, and the strict Pydantic
schema guarantees (required page/sheet/evidence references, quantity/confidence
bounds, the human-review rule, and estimate line-item pricing consistency).

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

## Current limitations

- **No blueprint/AI extraction yet** — upload stores and validates the PDF and
  records page count only; it does not produce sheets, scope items, or estimates.
- **No pricing engine yet** — `PricingBreakdown`/`EstimateLineItem` schemas exist
  but nothing populates them.
- **Strict enum input** — because schemas are strict, any future JSON ingestion of
  extraction results must supply enum *members* / `Decimal` values (or a lax
  ingestion adapter must be added). This is intentional for Phase 1 determinism.
- **Single-trade (Painting)** — only CSI Division 09 Painting is modeled.
- **SQLite single-node** — fine for the MVP; not built for concurrent multi-writer
  deployments.
- **No authentication / rate limiting** — intended to run behind a trusted gateway
  in this phase.
- **Docker base image** — building the image requires pulling `python:3.12-slim`
  from Docker Hub; in restricted-egress environments that pull may be blocked.

## Next recommended development milestone (Phase 2)

Deterministic extraction + pricing on top of the stable Phase 1 intake layer:

1. **Sheet indexing** — extract per-page sheet numbers/titles/disciplines into the
   `sheets` table with page references (no guessing; low-confidence → review).
2. **Painting takeoff (assisted, evidence-anchored)** — produce `PaintingScopeItem`
   records where every quantity carries page/sheet/evidence/confidence, with
   anything uncertain flagged `review_required=true`.
3. **Deterministic Python pricing engine** — a pure-Python module that turns scope
   items into `EstimateLineItem` + `PricingBreakdown`, versioned and unit-tested,
   with **no** LLM arithmetic.
4. **Review workflow** — endpoints to list/approve/correct review-required items
   and drive the `needs_review → complete` transition.
5. **Persistence for sheets/trades/estimates** — extend the schema and add
   migrations.
