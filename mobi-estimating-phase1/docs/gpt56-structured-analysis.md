# GPT-5.6 Structured Project-Analysis Layer

A fail-closed, source-grounded reasoning/review layer that turns already-extracted,
tenant-scoped source text into a Pydantic-validated project analysis using the
**OpenAI Responses API + Structured Outputs**.

- Model alias: **`gpt-5.6`** (exact; verified against OpenAI docs 2026-07-21). The
  config accepts only the literal `gpt-5.6`, and the client re-checks it before any
  dispatch. `gpt-5.6` resolves to **GPT-5.6 Sol**, so the *returned* model is
  accepted only when it is exactly `gpt-5.6` or a Sol snapshot
  (`gpt-5.6-sol[-…]`); `gpt-5.60`, `gpt-5.6-terra`, `gpt-5.6-luna`, and other
  variants fail closed as a model mismatch.
- Reasoning effort: **`medium`** (exact). GPT-5.6 documents the full set
  `none|low|medium|high|xhigh|max`, but this Mobi implementation **intentionally
  enforces `medium` only** — at config load *and* independently in the client
  before dispatch — so no other effort can reach a live, billable call.
- API surface: **Responses API** `client.responses.parse(..., text_format=Model)` →
  `response.output_parsed`. **No** Chat Completions / JSON-mode fallback.
- Tools: **none**. No web search, file search, or function calling. Server-side
  storage of the request is disabled (`store=False`).
- Strict Structured Outputs: every model used as `text_format` (`ProjectAnalysis`,
  the dedicated live extraction schemas, and the probe schema) is **default-free**
  — OpenAI strict schemas reject JSON-Schema `default` keywords, so optional
  fields are required-nullable (`X | None`) and the fixed schema version is
  injected into `ProviderCallMetadata` after parse, never authored by the model.
- Grounding: after a successful parse, every source reference the model emits is
  validated against the supplied request documents. Each locator the model
  supplies (document id/name/page/sheet) must EXACTLY equal the corresponding
  locator on the same supplied document — an omitted locator on the source
  document is not a wildcard, so an invented page/sheet against a source that has
  none fails closed — and any quote must be an exact normalized substring of the
  matched source text. An ungrounded reference fails closed with a safe,
  non-retryable error and is never silently downgraded.
- Item-level grounding (not just the top-level list): the important factual output
  structures each carry their OWN required, server-verifiable source reference —
  the top-level identity facts (project/customer/location/bid date), the sourced
  `project_type` (enum value + reference, or null when unestablished), each
  identified trade and relevant plan sheet (sourced values, not bare strings),
  each sheet-index entry, specification section, alternate, allowance, unit
  requirement, bid instruction, and exclusion, plus BOTH the plan and spec side of
  every plan/spec conflict. A scope item marked `observed_in_source` must carry a
  reference. Reviewer `assumptions` stay unsourced; recommended RFIs, missing
  documents, and risk flags may remain inferential with optional references, but
  any reference they do carry is still post-validated.

## What it does — and never does

It produces `app.analysis.schemas.ProjectAnalysis`: project name/customer/location,
bid due date (verbatim), project type, sheet index, spec sections, identified
trades, scope observations, alternates, allowances, unit requirements, relevant
plan sheets, bid instructions, missing documents, plan/spec conflicts, recommended
RFIs, assumptions, exclusions, risk flags, a confidence level, and grounded
`source_references`.

It **never** authors measurements, quantities, dimensions, unit costs, prices,
arithmetic, subtotals, or final totals — the schema has no numeric measurement/price
field at all. It never approves, prices, or states delivery status. It uses only the
supplied source text; unsupported findings become `null`/empty plus a
`missing_documents` or `risk_flags` entry. Provider metadata (model alias, reasoning
effort, request/response ids, schema version) is captured for audit and is **not**
estimate evidence.

## Files

- `app/config.py` — `openai_model` (`gpt-5.6`), `openai_reasoning_effort`
  (`medium`, validated), `enable_live_project_analysis`, bounds, and
  `project_analysis_readiness()` (safe; no key material).
- `app/analysis/schemas.py` — strict Pydantic analysis + metadata schemas.
- `app/analysis/openai_client.py` — the only SDK touch point; fail-closed error
  taxonomy.
- `app/analysis/service.py` — bounded, tenant-scoped orchestration + prompt
  contract.
- `app/extraction/live_schemas.py` — dedicated, strict, **numeric-free** live
  classification/scope output schemas used as `text_format` (no quantity/price/
  confidence fields; no `default` keywords; `extra="forbid"`).
- `app/extraction/openai_provider.py` — the extraction OpenAI path, now on the same
  Responses structured-output client. It sends the strict live schemas above and
  **adapts** them into the existing caller contract server-side: page → verified
  sheet id, quantities left null, and evidence type/confidence assigned by the
  server. The model never authors a number or evidence metadata.
- `scripts/verify_gpt56_live.py` — gated, single-request live probe with an
  explicit exact-model/effort preflight that costs zero SDK calls on mismatch.

## Why the legacy extraction schemas are not sent to the model

`app/extraction/provider_schemas.py` (`ScopeExtractionResponse` etc.) carry
model-authored `Decimal` quantity/confidence fields, `dict[str, Any]` maps
(`additionalProperties: true`), and Pydantic defaults — all unsafe or rejected
under strict Structured Outputs, and they would let the model author quantities/
prices. The live path therefore sends the dedicated numeric-free schemas in
`app/extraction/live_schemas.py` and reconstructs the legacy contract on the
server with null quantities. If a safe adaptation is ever impossible, the correct
posture is to fail closed rather than send the legacy schemas.

## Tenant-scope limitation (honest current truth)

`analyze_project` is **declarative / not wired to any production route**. Its
`ProjectAnalysisRequest` is tenant/company/project-scoped and takes
caller-assembled source text. No public route exposes it, and this correction
does **not** add one: caller-assembled source text must not become a public route,
and any future route must load documents exclusively through the existing
authenticated, tenant-authorized project repository boundary. Until that boundary
exists, the tenant scoping here is an input contract, not an enforced runtime
authorization.

## Production posture (current truth)

Live is OFF. `MOBI_ENABLE_LIVE_EXTRACTION=false`, `MOBI_EXTRACTION_PROVIDER=mock`,
`MOBI_ENABLE_LIVE_PROJECT_ANALYSIS=false`, no key installed. The app runs fully
offline; nothing here makes a paid call by default.

## Secure activation (do NOT paste secrets into chat, commits, or logs)

Provision the key through your platform's secret manager / environment only:

1. Set `MOBI_OPENAI_API_KEY` via the secret store (never in source, never echoed).
2. `MOBI_OPENAI_MODEL=gpt-5.6`, `MOBI_OPENAI_REASONING_EFFORT=medium`.
3. Arm the gate: `MOBI_ENABLE_LIVE_PROJECT_ANALYSIS=true` (and/or
   `MOBI_ENABLE_LIVE_EXTRACTION=true` for the extraction path).
4. Confirm readiness via `settings.project_analysis_readiness()` — it reports
   `ready_for_live_call` without exposing the key.

Live requires **both** a key **and** the explicit enablement flag. Either alone
stays offline and fails closed with a safe, non-retryable error.

### Opt-in live verification

`scripts/verify_gpt56_live.py` makes exactly one bounded paid request with a tiny
schema and a synthetic, non-customer payload. It refuses to run unless
`MOBI_GPT56_LIVE_VERIFY=1`, a key, and `MOBI_ENABLE_LIVE_PROJECT_ANALYSIS=true` are
all present, and writes sanitized JSON evidence (configured/returned model, request
id, parse success, response receipt/usage when returned, and
`contains_customer_data: false`). It never makes a billing claim when a transport
failure leaves provider billing unknowable. It never approves, delivers,
prices, messages, pays, or mutates any database.

## Rollback

Set `MOBI_ENABLE_LIVE_PROJECT_ANALYSIS=false` (and `MOBI_ENABLE_LIVE_EXTRACTION=false`),
`MOBI_EXTRACTION_PROVIDER=mock`, and restart the service. The layer immediately
returns to offline/mock behavior; no key value is ever stored in code or logs.
