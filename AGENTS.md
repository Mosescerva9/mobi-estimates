# AGENTS.md

## Cursor Cloud specific instructions

This repo is a monorepo with three independent parts. Standard commands live in
`package.json`, `README.md`, and `mobi-estimating-phase1/README.md`; only the
non-obvious cloud gotchas are captured here.

### Services

| Part | What it is | Run (dev) | Port |
| --- | --- | --- | --- |
| Root (`src/`) | **Mobi Portal** — Next.js 15 client/admin portal (Supabase auth, Stripe, intake) | `npm run dev` | 3000 |
| `mobi-estimating-phase1/` | **Mobi Estimating Engine** — standalone FastAPI takeoff/pricing service (offline mock provider by default) | `uvicorn app.main:app --host 0.0.0.0 --port 8000` (run inside its `.venv`) | 8000 |
| `marketing-site/` | Static brochure site (pre-generated HTML) | `python3 -m http.server 8080` (or `python3 generate.py` to rebuild) | 8080 |

### System dependencies (baked into the VM image, not the update script)
- `python3.12-venv` — required to create the engine's virtualenv.
- `poppler-utils` — provides the `pdfinfo` binary. The engine's OpenTakeoff
  runtime does a `pdfinfo` **preflight page count**; without it, plan loading fails
  with `unsupported_document` ("pdfinfo is required for preflight page count") and
  the `tests/test_opentakeoff_*` suites fail. Install with
  `sudo apt-get install -y poppler-utils` if a fresh image ever lacks it.

### Engine (`mobi-estimating-phase1`)
- Always run/test inside its own venv: `mobi-estimating-phase1/.venv`.
- `MOBI_DEPLOYMENT_ENVIRONMENT=local` is **required** at startup and for tests —
  `staging`/`production` intentionally fail closed.
- Tests: `MOBI_DEPLOYMENT_ENVIRONMENT=local pytest` (~1400 tests, ~2.5 min).
- All project-scoped API routes fail closed without tenant headers. Send
  `X-Mobi-Tenant-Id` and `X-Mobi-Company-Id` on every `/api/v1/projects...` call
  (see `tests/conftest.py` `TEST_TENANT_HEADERS`).
- The OpenTakeoff MCP runtime spawns `node node_modules/opentakeoff-mcp/dist/server.js`
  from the **repo root** (`/workspace`), so the root `npm ci` (which installs
  `opentakeoff-mcp`) must have run for those integration tests to pass.
- Live AI extraction is off by default (deterministic mock provider); no OpenAI key
  is needed for tests or the demo flow.

### Portal (root)
- `next.config.js` bakes in browser-safe defaults for
  `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`, so the app boots and
  renders with zero env setup and points at the live `mobi-portal` Supabase project.
- The live Supabase project has **email confirmation enabled**, so browser signup
  lands on a "check your email" step and cannot complete to an authenticated session
  without mailbox access. Free-tier email sends are rate-limited (429
  `over_email_send_rate_limit`) after a couple of signups.
- Server-side write paths that use the **service-role** admin client (e.g. public
  lead capture in `src/lib/lead-capture-server.ts`, Stripe webhooks) require
  `SUPABASE_SERVICE_ROLE_KEY` and return 503/throw when it is unset. Provide it (and,
  for authenticated E2E, real test-login credentials or a confirmed account) to
  exercise those flows end to end.
- Lint: `npm run lint`. Types: `npm run typecheck`. Portal test scripts are
  standalone `tsx` runners; `npm run test:mvp-flow` runs the core suite.
