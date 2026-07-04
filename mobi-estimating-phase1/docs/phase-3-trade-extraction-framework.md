# Phase 3 — Trade-Agnostic Extraction Framework, Evidence, and Human Review

Phase 3 builds the reusable extraction + evidence + review framework that every
construction trade will plug into. **Painting is only the first reference trade
module** — the shared core contains no Painting-specific logic, proven by a second
demonstration trade (`demo_concrete`) and a fake trade module in the tests.

AI output is treated as **untrusted candidates**. AI may identify, transcribe,
classify, and organize; it may never perform trusted/derived quantity arithmetic or
pricing. All canonical quantities are deterministic Python (`Decimal`). Every scope
item must be backed by evidence on a **verified** sheet, and nothing is ever
auto-approved.

## Pipeline

```text
Processed plans (Phase 2 sheets, verified)
      ↓
Trade routing            (per-trade eligibility: eligible / excluded /
      ↓                   blocked_unverified / blocked_ocr / requires_review)
Trade registry           (enabled trade modules only)
      ↓
Selected trade module    (categories, units, formulas, prompts, validation)
      ↓
Provider candidate extraction   (mock by default; OpenAI optional, off by default)
      ↓
Shared evidence validation      (rebuilt server-side from verified DB sheets;
      ↓                          provider sheet numbers are never trusted)
Trade-specific validation       (trade_data payload + candidate rules)
      ↓
Deterministic quantity engine   (Python Decimal; derived bases recomputed)
      ↓
Human review                    (pending/blocked → corrected/approved/rejected)
      ↓
Approved scope items            (exact schema + module versions preserved)
```

```mermaid
flowchart TD
    P[Verified sheets] --> R[Trade routing]
    R --> REG[Trade registry]
    REG --> M[Selected trade module]
    M --> PV[Provider candidates (untrusted)]
    PV --> EV[Shared evidence validation\nverified sheet # from DB]
    EV --> TV[Trade-specific validation]
    TV --> Q[Deterministic quantity engine\nDecimal, registered formulas]
    Q --> HR[Human review]
    HR --> A[Approved scope items]
    HR -. correct/reject .-> HR
```

## Two layers

**Shared core** (`app/extraction`, `app/estimating`, `app/review`, plus
`extraction_db`): projects, processed sheets, trade identification, extraction runs,
scope items, quantity candidates, evidence references, source validation, units,
deterministic derivations, conflicts, assumptions/exclusions, review, approval
states, audit history, provider abstraction, caching, re-extraction, API.

**Trade modules** (`app/trades/<trade>`): trade definition, scope categories,
extraction/payload schema, sheet-routing rules, prompt templates, quantity types,
allowed units, deterministic formulas, validation rules, conflict rules, approval
requirements. Painting is the reference; `demo_concrete` proves reuse.

The core loads behavior through the **trade registry** — there is no
`if trade == "painting"` branch anywhere in the shared services.

## Trade-specific payload strategy (and trade-offs)

Chosen: **validated JSON `trade_data` column** on the shared `scope_items` table,
validated by the registered trade module's Pydantic payload model, with the
`trade_schema_version` stored alongside every row.

- **Pros:** lean for SQLite; no per-trade tables; shared core fields stay
  normalized; unknown trade fields are rejected (`extra="forbid"`); old rows remain
  interpretable because their schema version is recorded and the module validates
  against it.
- **Cons:** trade payloads aren't directly SQL-queryable (acceptable — filtering
  happens on shared fields); module-side version handling is required as payloads
  evolve.
- **Rejected:** one wide table with dozens of nullable Painting-only columns
  (not trade-agnostic), and one scope-item table per trade (premature for the MVP).

## Non-negotiables enforced here

- AI candidates are untrusted; never auto-approved.
- Derived quantities (`dimension_inputs`, `deterministic_derivation`) are recomputed
  in Python; providers may only transcribe explicit/schedule values.
- Evidence is rebuilt from DB sheet records; the provider's claimed sheet number is
  discarded and replaced with the verified number.
- A detected-but-unverified sheet can never satisfy trusted evidence.
- Missing info stays null; blocking conflicts/issues prevent approval.
- Re-extraction never overwrites approved work (new run, new candidates).
- Live provider calls are disabled by default; the app runs with no API key.
- Customer plan text is never written to normal logs; secrets are never committed.

## Database migrations (forward-only, additive)

Migrations 4–11 add: `trade_definitions`, `extraction_runs` (one active run per
project+trade via a partial unique index), `sheet_routing_decisions`, `scope_items`,
`evidence_references`, `quantity_derivations`, `conflicts`, and the append-only
`review_events`. Existing Phase 1/2 data is preserved.

## Provider integration status

The default provider is the deterministic offline **mock**, which supports multiple
trades. The **OpenAI** provider is implemented behind the interface but disabled by
default (requires both an API key and `MOBI_ENABLE_LIVE_EXTRACTION=true`). The live
call path could not be executed or verified in this environment (no network/docs);
it uses the stable `chat.completions` JSON contract and should be re-verified against
the current official SDK before production enablement. No unstable SDK methods are
guessed, and the live path never runs in the test suite.

## Recommended Phase 4

A shared, deterministic **price-book + assemblies + pricing** engine layered on
approved scope items — see the README "Recommended Phase 4" section.
