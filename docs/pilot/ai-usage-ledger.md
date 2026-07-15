# AI usage ledger

Updated: 2026-07-15T02:13:33Z

| Date | Task | Model/tool | Reason used | Usage category | Calls | Cache hits | Retries | Result | Benchmark improvement | Human time saved |
|---|---|---|---|---|---:|---:|---:|---|---|---|
| 2026-07-15 | Milestone 1 control reset | Hermes GPT-5.5 + deterministic shell/GitHub/Cron tools | User directive execution, orchestration, docs | medium | n/a | n/a | 0 | Old cron loop paused; audit started | none yet | Avoided continuing obsolete PR loop |
| 2026-07-15 | Milestone 2 canonical evidence slice | Claude Code Opus + Hermes deterministic verification + Codex focused review | Claude implemented additive schema/interface; Hermes verified tests; Codex reviewed blocker/fix | medium | 2 Claude/Codex review calls plus local tests | n/a | 1 Codex blocker fixed | Canonical evidence/provider slice verified | architecture foundation only | Reduces future rework around provider evidence normalization |
| 2026-07-15 | Milestone 2 evidence persistence slice | Claude Code Opus + Hermes deterministic verification + Codex focused review | Claude implemented additive persistence; Codex caught raw-payload identity and SQL NULL fail-closed gaps; Hermes fixed and verified | medium | 1 Claude call + 4 Codex focused reviews + local tests | n/a | 3 Codex blockers fixed | Persistence slice verified with 101 focused tests | architecture foundation only | Prevents future tenant/evidence isolation rework before import integration |

## Policy
Record exact token/cost data when available. If unavailable, use low/medium/high category. Optimize for verified product progress per AI cost, not lowest cost alone.
