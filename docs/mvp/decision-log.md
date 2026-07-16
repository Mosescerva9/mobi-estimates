# Decision Log

Updated: 2026-07-16T00:40Z

| Time | Decision | Reason | Owner approval needed? |
|---|---|---|---|
| 2026-07-16T00:04Z | Start MVP OpenTakeoff customer-launch branch from `origin/main` (`2269b8a`) | User directive requires clean dedicated branch from current base | No |
| 2026-07-16T00:04Z | Leave essential services and Mobi engine running | User explicitly said not to disable backups, uptime, auth, DB health, security/essential deployment services | No |
| 2026-07-16T00:04Z | Do not clean disk yet despite 95% usage | Deleting non-scratch files is approval-gated | Yes, if cleanup requires deletion |
| 2026-07-16T00:18Z | Treat old PR #5 as design input, not merge input | It is checkout-relevant but conflicting/stale | No |
| 2026-07-16T00:18Z | Keep marketing/blog PR #92 out of MVP branch | User instructed not to merge unrelated blog/marketing into MVP | No |
| 2026-07-16T00:18Z | Freeze PR #73 and reduce/avoid PR #89-style vocabulary/release-gate expansion | New direction is provider boundary/canonical evidence/OpenTakeoff, not more synonym scanners | No |
| 2026-07-16T00:30Z | Add OpenTakeoff/CustomerSupplied/FutureThirdParty provider lanes instead of coupling directly to OpenTakeoff | Maintains provider-neutral architecture and future replacement path | No |
| 2026-07-16T00:34Z | Treat raster fallback as required before launch | Golden Set Patton raster plan failed safely through MCP; many customer plans may be scans | No |
| 2026-07-16T00:55Z | Do not mutate applied migration 37 / Supabase 0024 for new evidence fields | Codex review found this would fail existing databases that already recorded those migrations | No |
| 2026-07-16T01:05Z | Use forward SQLite migration v38 and Supabase migration 0025 for `condition`/`scale` and provider enum expansion | Preserves migration history and keeps raw-vs-flattened provenance fail-closed | No |
