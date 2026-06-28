# Phase 2 — Deterministic Blueprint Ingestion and Sheet Indexing

Phase 2 turns an uploaded PDF plan set into a per-page, fully traceable set of
**sheet** records with review images, thumbnails, extracted text, page metadata,
duplicate detection, and conservative deterministic sheet-number/title detection.

Everything is deterministic Python on top of **PyMuPDF**. There is **no OCR, no
LLM, and no pricing** in this phase. A detected sheet number is only ever a
*candidate* — it must be human-verified before it can back a trusted downstream
source reference.

## Architecture

```mermaid
flowchart TD
    U[Contractor uploads PDF] -->|POST /projects/upload| API[(FastAPI /api/v1)]
    API --> DB[(SQLite + migrations)]
    API -->|POST /projects/{id}/process| CLAIM{claim_processing_slot\n(atomic, unique active job)}
    CLAIM -->|created| PROC[processing_service.process_project]
    CLAIM -->|active| IDEM[202 idempotent: existing job]
    CLAIM -->|already_processed / terminal / invalid| ERR[409 structured error]

    subgraph Deterministic processing (PyMuPDF)
        PROC --> P1[For each page index 0..N-1]
        P1 --> T[Extract + normalize text -> text.txt]
        P1 --> R[Render full PNG + thumbnail PNG\nDPI / max-pixel guard]
        P1 --> C[Page checksum = sha256(pixmap)]
        C --> DUP[Duplicate detection within project]
        P1 --> SD[sheet_detection: number + title candidates]
        SD --> FLAG[Flag requires_review / requires_ocr]
        T --> SHEET[(sheets row)]
        R --> SHEET
        DUP --> SHEET
        FLAG --> SHEET
    end

    PROC --> MAN[processed/manifest.json]
    PROC --> JOB[(processing_jobs: progress, counts, timing)]
    PROC --> ST[project status -> ready_for_review / failed]

    REV[Human reviewer] -->|PATCH .../sheets/{id}/verification| DB
    REV -->|GET .../image, .../thumbnail| ART[Controlled artifact serving\nresolved inside data root]
```

## Processing lifecycle (project status)

```
uploaded ──▶ queued ──▶ processing ──▶ ready_for_review
   │            │            │
   │            └────────────┴────────▶ failed ──▶ queued (retry)
   │
   └─(Phase 1 paths preserved: uploaded▶processing, processing▶needs_review/complete)
ready_for_review ──▶ queued   (only on explicit force reprocess)
complete  = terminal
```

* Transitions are enforced by `app/status_rules.py`.
* `complete` is the only fully terminal state; `failed` may be re-queued.

## Idempotency & concurrency

* A **partial unique index** (`uq_jobs_active_per_project`) guarantees at most one
  active (`queued`/`processing`) job per project — two simultaneous `POST
  /process` calls cannot both start work.
* `claim_processing_slot()` atomically creates the job and moves the project to
  `queued`. A lost race returns the existing active job (HTTP 202, no duplicate).
* `process_project()` clears prior sheet rows and regenerates artifacts before
  inserting new ones, so repeated/forced runs never duplicate records or files.
* The original `original.pdf` is never modified or deleted.

## Storage layout

```
data/uploads/<project_uuid>/
├── original.pdf                 # never modified by processing
└── processed/
    ├── manifest.json            # project-level summary (relative paths only)
    └── sheets/
        ├── page-0001/{full.png, thumbnail.png, text.txt}
        └── page-0002/{full.png, thumbnail.png, text.txt}
```

* Only **relative** paths (relative to the data root) are stored in SQLite.
* Artifact endpoints resolve requested files strictly inside the data root and
  reject traversal attempts.
* Writes are atomic (temp file + `os.replace`).

## Database (migrations)

Forward-only migrations in `app/migrations.py`, tracked in `schema_migrations`:

1. `projects` (Phase 1 baseline; no-op on existing databases)
2. `processing_jobs`
3. `sheets`

Migrations are safe to run repeatedly and upgrade an existing Phase 1 database in
place without resetting data.

## Why OCR and AI extraction are deferred

* **OCR** would add heavy native dependencies and non-deterministic output. Phase
  2 instead *flags* pages with insufficient embedded text (`requires_ocr`) so a
  later phase can target only those pages.
* **AI/LLM extraction** is intentionally excluded so that every value in the
  system remains traceable to deterministic rules and human verification. Sheet
  numbers are detected by regex + geometry and must be verified by a person before
  they are trusted.

## Recommended Phase 3 milestone

**Deterministic, evidence-anchored painting takeoff over verified sheets** — see
the main README for the full Phase 3 plan.
