# AI efficiency log

Updated: 2026-07-15T02:13:33Z

## 2026-07-15 — Pilot reset
- Wasteful loop detected: prior release-gate builder/QA cadence repeatedly expanded aliases/synonyms and validator scans without direct pilot capability progress.
- Action: paused all Hermes cron jobs tied to that loop and froze release-gate vocabulary work.
- Replacement: milestone-driven pilot loop with compact status files, focused tests, Codex review only on meaningful diffs, and GPT-5.6 reserved for architecture/failure analysis.
- Next efficiency improvement: create compact `docs/architecture/current-system-map.md`, `docs/pilot/decision-log.md`, and `docs/pilot/known-patterns.md` so future agents do not rediscover the repository every cycle.

## 2026-07-15 — Milestone 2 slice 1
- Useful model calls: Claude Code implemented the additive schema/interface; Codex found one real blocker (schema_version was not fail-closed) and passed after the focused fix.
- Unnecessary/reduced usage: no broad repo audit from Codex; no GPT-5.6 architecture call required because the directive and existing patterns were sufficient.
- Reusable output: `docs/architecture/current-system-map.md`, `docs/pilot/known-patterns.md`, and the new `app/takeoff` package reduce rediscovery and synonym-loop risk.
