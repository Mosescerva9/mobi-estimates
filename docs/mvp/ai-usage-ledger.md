# AI Usage Ledger

Updated: 2026-07-16T00:40Z

| Time | Task | Model | Reason used | Usage category | Retries | Cache hits | Result | Benchmark improvement | Human time saved |
|---|---|---|---|---|---:|---:|---|---|---|
| 2026-07-16T00:04Z | MVP reset coordination and docs | Hermes active model | Owner directive orchestration | coordination | 0 | 0 | Started branch/docs | not_measured | not_measured |
| 2026-07-16T00:25Z | Canonical provider/schema implementation | Claude Code `claude-opus-4-8` | Multi-file code change; user preference is Claude for implementation | implementation | 0 | existing repo tests | Added OpenTakeoff/CustomerSupplied/FutureThirdParty provider lanes plus condition/scale fields; 108 focused tests passed | Enables OpenTakeoff normalization work; no quantity benchmark gain yet | avoids manual multi-file edit/review |
| 2026-07-16T00:30Z | OpenTakeoff technical spike analysis | Hermes active model + deterministic MCP scripts | Interpret real MCP output and document legal/technical findings | verification/documentation | 0 | OpenTakeoff docs/tests | MCP tools passed on demo; Golden Set raster gap found | Identified launch blocker before integration | prevents wrong architecture assumption |
| 2026-07-16T00:55Z | PR #95 focused blocker review | Codex GPT-5.5 via snapshot fallback | Independent review of Claude/Hermes diff | review | 0 | repo snapshot | BLOCK: mutated applied migrations; missing raw-vs-flattened condition/scale checks | Caught migration/release blocker before merge | prevents production migration failure |
| 2026-07-16T01:05Z | Fix Codex blockers | Claude Code `claude-opus-4-8` partial run + Hermes verification | Multi-file migration/test fix | implementation | 0 | existing tests | Added forward SQLite v38, Supabase 0025, null-safe checks; 122 focused tests passed | Hardens canonical evidence store | avoids manual migration rewrite |
