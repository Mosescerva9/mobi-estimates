# GPT-5.6 Live Scope Analysis — Secure Activation Runbook

Staff-only activation of exact GPT-5.6 **Medium** live scope analysis for an
already-uploaded/processed engine project. This is the smallest safe connected
path: an explicit, bounded, review-pending, fail-closed run started from the
admin project workflow. There is **no** public/customer analysis route and it
does **not** auto-run on upload.

Model lock (never change without a new review): model alias `gpt-5.6`, reasoning
effort `medium`, OpenAI Responses API + Structured Outputs, `tools=[]`,
`store=false`, no fallback models.

## What was added

- Backend fail-closed guard (`app/routers_extraction.py`): a request with
  `use_live_provider=true` returns **409** ("Live extraction is not enabled")
  when the live gate is off, or **503** ("Live extraction is not available")
  when armed but keyless — **before** `claim_extraction_run`, so no run row and
  no silent mock fallback are ever created.
- Backend readiness surface: `GET /api/v1/projects/{id}/extraction/live-readiness`
  (tenant-guarded) reports `live_enabled`, `api_key_present`,
  `ready_for_live_call`, the locked model/effort, and the enabled-trade
  allowlist. It never returns key material.
- Staff-only server actions (`src/app/admin/projects/[id]/actions.ts`):
  `getLiveScopeExtractionReadiness` and `startLiveScopeExtraction`. The start
  action re-checks readiness, validates the trade against the server-fetched
  allowlist, posts the fixed payload `{ use_live_provider: true, force: false,
  dry_run: false }` (no caller sheet ids), and returns only a sanitized run.
- Admin UI: **Live GPT-5.6 scope analysis** panel with "Check live availability"
  and a clearly labeled "Run GPT-5.6 scope analysis" button. It fails closed
  with "Live analysis is not enabled" and disables duplicate submissions.
- Gated verification script:
  `mobi-estimating-phase1/scripts/verify_gpt56_live_extraction.py`.

## Cost boundary

- One activation click = **one extraction run** for the selected trade. A single
  run is **not** necessarily a single provider request: on a retryable provider
  error the run retries in place, so the normal maximum number of provider
  requests for one run is `MOBI_EXTRACTION_MAX_RETRIES + 1` (attempts =
  `extraction_max_retries + 1`). With the shipped default of
  `MOBI_EXTRACTION_MAX_RETRIES=2` that is up to **3** requests per run; the
  verification script forces `MOBI_EXTRACTION_MAX_RETRIES=0` so it makes exactly
  **1** request.
- **Set `MOBI_EXTRACTION_MAX_RETRIES` deliberately in production** to bound
  worst-case live spend per activation — it is a direct multiplier on the number
  of paid requests a single run can make. Page volume per run is separately
  capped by `MOBI_EXTRACTION_MAX_PAGES` / `MOBI_EXTRACTION_MAX_PAGES_PER_TRADE`.
- The live model returns **only** a category code, a sheet-relevance verdict, and
  one or more **verbatim source quotes** — it authors **no** description,
  location, assumptions, exclusions, classification reason, quantities, units,
  prices, arithmetic, totals, approval, delivery, payment, messaging, or estimate
  status. The live output schema itself exposes **no** descriptive prose field, so
  no model-authored descriptive text can ever reach persistence. The server
  derives every scope description **from the verbatim source quote** (bounded), and
  requires each quote to be a **literal exact substring** (case/whitespace/
  punctuation exact) of the raw embedded text on the same cited page — anything not
  literally present is dropped. Every scope item and quote persists
  `pending`/`blocked` for human review with a null quantity. A defense-in-depth
  free-text validator is retained for tests (it also rejects spelled-out number
  words), but denylist completeness is no longer a persistence dependency.

## Secure activation steps (owner)

1. Confirm the engine service env holds a real `MOBI_OPENAI_API_KEY` (secret;
   never commit, never log, never place behind `NEXT_PUBLIC_`).
2. Set on the **engine service** only:
   - `MOBI_ENABLE_LIVE_EXTRACTION=true`
   - `MOBI_OPENAI_MODEL=gpt-5.6` (default; load fails closed on any other value)
   - `MOBI_OPENAI_REASONING_EFFORT=medium` (default; load fails closed otherwise)
3. Restart the engine. Verify readiness (staff): open an admin project and click
   **Check live availability** — it must show model `gpt-5.6`, effort `medium`,
   live call `available`.
4. Run one live analysis: pick an enabled trade → **Run GPT-5.6 scope
   analysis**. Confirm the returned run shows `provider=openai`,
   `model=gpt-5.6`, and that resulting scope items are pending/blocked review.

## Proof steps (before trusting broader use)

Run the gated one-call verification against a synthetic project (real paid call;
never in CI):

```bash
export OPENAI_API_KEY=...
export MOBI_OPENAI_API_KEY=$OPENAI_API_KEY
export MOBI_ENABLE_LIVE_EXTRACTION=true
export MOBI_GPT56_LIVE_EXTRACTION_VERIFY=1
cd mobi-estimating-phase1
python -m scripts.verify_gpt56_live_extraction --out evidence/gpt56_live_extraction.json
```

The script binds a `TemporaryDirectory` DB/upload root **before** importing
settings (and asserts the resolved paths are under that owned temp root, so a
stray production `MOBI_DB_PATH` in the environment can never be touched), uses a
synthetic non-customer painting spec, and checks every HTTP status before
reading a body. It writes only **sanitized measured facts** — no source text,
quotes, raw provider output, key material, filesystem paths, or customer IDs.

The evidence records, and the script exits non-zero unless all hold:

- run `status = needs_review`, `provider = openai`, `model = gpt-5.6`,
  `candidate_count > 0`, and a non-empty scope-item set;
- every scope item is `pending`/`blocked` review, quantity `null`, `approved_at`
  `null`, with non-empty evidence that carries a verified sheet id/number/page,
  `requires_human_verification = true`, a non-empty quote, and a quote that is a
  **literal exact substring** of the synthetic source on that same page;
- the **measured** provider-dispatch count (from wrapping the provider method the
  retry loop calls) is exactly `1` — not a recorded constant;
- exactly **one** extraction run exists in the throwaway DB and its single trade
  is `painting` (both the row count and the distinct-trade set are asserted);
- a direct query of the throwaway DB proves zero proposal/estimate/QA/customer-
  revision rows, zero approved review events, and zero approved scope items
  (delivery/payment/messaging have no engine-side table; those effects live only
  in the portal, which the harness never touches).

The scratch DB/uploads are always cleaned up (even on failure) and the cleanup is
explicitly verified (`scratch_cleanup_verified`, failing the contract if the temp
root still exists); only the sanitized evidence file, written outside the temp
root, is retained. This proves
the *activated extraction path* behaves safely for one synthetic run — it does
**not** by itself constitute production activation or authorize broader live use.

## Rollback (instant, safe)

- Set `MOBI_ENABLE_LIVE_EXTRACTION=false` on the engine and restart. Every
  subsequent live request fails closed (409) with no run row; the UI shows
  "Live analysis is not enabled". Mock/offline paths are unaffected.
- To fully de-provision, also remove `MOBI_OPENAI_API_KEY`; an armed-but-keyless
  live request returns 503.
- No data migration or code revert is required to disable.

## Guardrails preserved

- Tenant/company isolation and server-owned project/document/sheet identity are
  unchanged; the readiness endpoint and the run endpoint both go through the
  project tenant guard.
- Source text is loaded server-side from tenant-scoped storage; the caller
  cannot supply arbitrary text or paths.
- Fail-closed is enforced twice: the router rejects an unarmed live request
  before a run row is claimed, and the provider registry re-checks live
  enablement + key readiness at **dispatch time**. If the flag is flipped off or
  the key removed between claim and execution (e.g. a queued run resumed after a
  restart), an `openai`-labeled run raises `LiveExtractionUnavailable` and the
  run is marked failed — it **never** silently falls back to the offline mock or
  persists mock candidates.
- The UI never exposes provider raw payloads, credentials, filesystem paths, or
  internal errors, and makes no customer-facing delivery claims.

## Regression coverage

- Backend: `mobi-estimating-phase1/tests/test_extraction_live_activation.py`
  (wrong tenant, disabled live, missing key, invalid/disabled trade, readiness
  contract, successful staff payload contract with no network call).
- Frontend: `npm run test:live-scope-extraction` (payload/normalizer contract,
  allowlist enforcement, run sanitization, wired-action/panel posture).
