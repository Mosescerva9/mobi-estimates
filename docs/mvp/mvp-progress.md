# MVP Progress

Updated: 2026-07-17T12:02:12Z

## Current milestone
Milestone 4 — Interactive estimator drawing workbench started after production worker proof.

## Completed in this cycle
- Verified repo remote: `https://github.com/Mosescerva9/mobi-estimates.git`.
- Stashed pre-existing local dirty work before creating MVP branch.
- Created branch `mvp-opentakeoff-customer-launch` from `origin/main` at `2269b8a`.
- Verified old autonomous Mobi loops are paused/enabled=false; documented in `docs/operations/paused-automation-inventory.md`.
- Verified no user crontab, no tmux/screen coding loops, no active Claude/Codex builder process.
- Verified essential host services `cron`, `ssh`, `caddy`, `docker`, and Mobi engine process are active.
- Inventoried open PRs in `docs/mvp/open-pr-inventory.md`.
- Created required MVP docs: master plan, progress, status JSON, decision log, launch checklist, current-state audit, AI usage ledger.
- Cloned OpenTakeoff to `/tmp/opentakeoff-eval` at `36a9aa7ebe0a6dde116c0a3d68a16fe39a0c94bf`.
- Reviewed OpenTakeoff license/NOTICE/dependencies in `docs/legal/opentakeoff-license-review.md`.
- Installed/tested OpenTakeoff MCP; MCP typecheck and tests passed 20/20.
- Verified `npx -y opentakeoff-mcp` through an MCP client and exercised all 10 required tools.
- Ran a real Golden Set OpenTakeoff attempt on Patton reroof G001; failed safely because MCP saw the sheet as raster/no vector linework and could not extract the verified `19,337 SF` roofing area.
- Probed Golden Set vector/raster status; two plan sets show vector linework, Patton reroof is raster-only for MCP.
- Began canonical provider implementation: added OpenTakeoff, CustomerSupplied, and FutureThirdParty provider lanes plus `condition` and `scale` canonical evidence fields.
- Ran focused Codex review on PR #95; Codex found two blockers (mutated applied migrations, and missing raw-vs-flattened fail-closed checks for `condition`/`scale`).
- Fixed those blockers with forward SQLite migration v38, Supabase migration `0025_canonical_takeoff_evidence_provider_fields.sql`, null-safe deserialization checks, and regression tests.
- Reran Codex focused review after fixes: `PASS - no blocking issues`; Codex also reran the focused Python tests in its snapshot.
- Added the first OpenTakeoff export normalizer (`opentakeoff.takeoff_canvas.v1` export → `OpenTakeoffProvider` → canonical evidence rows) with tests for area, linear, count, unsupported schema/roles, and server-owned identity protection.
- Codex reviewed the adapter slice and blocked alias-like role/field fallbacks; fixed by limiting normalization to explicit export contract fields and adding regression coverage for alias quarantine.
- Fixed the boolean numeric-conversion blocker in commit `721b98104b25fe9db1d09f22397b14e96b006bfb`: boolean, string, missing, and object-valued OpenTakeoff computed quantities now quarantine instead of raising or becoming evidence.
- Codex focused review of the boolean fix returned `PASS - no blocking issues`.
- Pushed docs status commit `3fa259d46255065ed382963966ac83f8f17facf8`; PR #95 became mergeable/clean with green Vercel marketing and portal checks.
- Reduced root filesystem usage from 98% to 69% by deleting 113G of disposable `/tmp/mobi-codex-*snapshot*` review snapshots. No customer uploads, databases, Docker volumes, active containers, repos, env files, backups, production artifacts, or OpenTakeoff benchmark evidence were deleted.
- Merged PR #95 with merge commit `9276b7643144c2fdba3ae12bb09e3bdaa8a8908a`; confirmed `origin/main` contains branch head `600c1e20464acf763feb32eb2e02cc9bd58cd393` and canonical evidence migrations `0024`/`0025` plus SQLite migrations 37/38.
- Created branch `opentakeoff-real-measurement-proof` from updated `origin/main`.
- Ran the first real OpenTakeoff geometric measurement proof on public Golden Set fixture `ca-dgs-24-253614-lot-50-evcs-v2`, sheet `C011` / PDF page 4. This is OpenTakeoff-measured evidence, not schedule-extracted evidence.
- Measurement target: Level GA horizontal printed dimension `5 EVCS TYPE 2 @ 7.5' = 37'-6"`; scale explicitly calibrated from a separate printed `15'-0"` stall-depth dimension on the same sheet.
- Result: OpenTakeoff `measure_line` = `37.5 LF`, verified quantity = `37.5 LF`, absolute error `0`, percentage error `0%`, processing time `1958 ms`, human correction/selection time `240 s`, classification `PASS`.

## Verification run
- `npm run typecheck` → passed.
- `npm run lint` → passed.
- `npm run build` → passed.
- `cd mobi-estimating-phase1 && python -m pytest tests/test_golden_set_extraction_eval.py tests/test_mobi_autoresearch.py tests/test_real_document_harness.py -q` → passed.
- `cd mobi-estimating-phase1 && python -m pytest tests/test_takeoff_evidence.py tests/test_takeoff_store.py tests/test_migrations.py -q` → 108 passed.
- After Codex blocker fixes: `cd mobi-estimating-phase1 && python -m pytest tests/test_takeoff_evidence.py tests/test_takeoff_store.py tests/test_migrations.py -q` → 122 passed.
- Adapter slice after boolean/malformed numeric fix: `cd mobi-estimating-phase1 && python -m pytest tests/test_opentakeoff_adapter.py tests/test_takeoff_evidence.py tests/test_takeoff_store.py tests/test_migrations.py -q` → 129 passed.
- Real measurement proof: `cd mobi-estimating-phase1 && python -m pytest tests/test_opentakeoff_real_measurement_proof.py tests/test_opentakeoff_adapter.py tests/test_takeoff_evidence.py tests/test_takeoff_store.py tests/test_migrations.py -q` → passed.
- `cd mobi-estimating-phase1 && python -m compileall app/takeoff tests/test_opentakeoff_adapter.py` → passed.
- `cd mobi-estimating-phase1 && python -m compileall app/takeoff tests/test_opentakeoff_real_measurement_proof.py` → passed.
- `npm run test:checkout-flow` → 13/13 passed using in-memory fakes only.
- `npm run test:checkout-prefetch` → passed.
- `npm run test:checkout-readiness` → 6/6 passed.
- `npm run test:project-upload` → 14/14 passed.
- `npm run test:deliverable-gate` → 36/36 passed.
- `npm run test:deliverable-rls-gate` → 3/3 passed.
- `npm run test:engine-tenant-context` → passed.
- `npm run test:customer-revision-portal` → passed.
- `npm run test:admin-revision-workflow` → passed.
- `git diff --check` → passed before and after Codex blocker fixes.

## Blockers / risks
- Root filesystem was 98% full and is now 69% after cleanup of disposable agent `/tmp` snapshots.
- OpenTakeoff MCP raster gap is real: Patton Golden Set scanned/raster plan failed to produce the verified schedule quantity.
- OpenTakeoff MCP `npm install` reported one moderate vulnerability; not remediated in this slice.
- App/DB backups beyond OS package backups are still not fully verified.
- Production/live checkout was not exercised; live payment side effects remain approval-gated.

## 2026-07-17 production worker proof and cleanup checkpoint
- PR #105 (`Fix live takeoff worker client contract`) merged to `main` as `ed4fac544c2bf071aff934fca1934bff4453231e` and deployed through Vercel `mobi-portal` to canonical production `https://mobiestimates.com`.
- Verified production browser/admin UI → Next.js server action → authenticated VPS OpenTakeoff worker path using approved public C011 fixture project `2eb73f2a-ab1c-4454-bb26-2acfa9dbc09b`.
- Production worker job `3a5e27ca-6ca4-487b-99c4-da9dfebde8d1` returned `awaiting_review`; duplicate idempotent create returned the same job safely with `created: false`.
- Active worker DB persisted canonical evidence `9c287010-6851-47a7-8858-8b08f5f666b8`: `37.5 LF`, sheet `f59858ee-bd8b-4535-a772-4956ffce7bf5`, page 4, scale `units_per_px:0.08012820512820511`, condition `RUNTIME-LINE`.
- Production UI loaded artifact metadata for `opentakeoff_export`, `canonical_evidence`, `marked_region_metadata`, and `worker_metadata`.
- Temporary proof fixture is retained as an auditable regression fixture for now; do not delete its project/job/evidence until a replacement regression-fixture policy exists.
- Cleanup status: local Vercel link restored to `mobi-portal`; one-time auth/link/password artifacts removed; temporary staff proof account `hermes-staff-proof-1784255242@mobiestimates.test` disabled via Supabase Admin API; unintended Vercel project `mobi-estimates` exists and needs env/alias uniqueness inspection before removal.

## Next task
Build `estimator-interactive-takeoff` visual staff workbench so estimators no longer type geometry manually.
