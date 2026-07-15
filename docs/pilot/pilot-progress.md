# Mobi pilot progress

Updated: 2026-07-15T02:13:33Z

## Current milestone
Milestone 2 — Canonical evidence + provider-neutral takeoff architecture (started).
Milestone 1 — Stop obsolete automation and establish control (complete).

## Milestone 2 progress
- Added `app/takeoff/` package: canonical, versioned, Pydantic evidence contract
  (`evidence.py`) that forbids unknown fields, plus the provider-neutral takeoff
  interface (`providers.py`).
- `CanonicalEvidence` carries tenancy/document coordinates, controlled
  provenance enums (`EvidenceClass`, `MeasurementMethod`, `TakeoffProviderKind`),
  scope/measurement, review state, and lineage.
- Provider shells (`MobiNative`, `ManualImport`, `HumanVerified`,
  `AuthorizedThirdParty`, `FutureCadBim`) normalize explicitly mapped payloads
  into canonical evidence and fail closed on unknown/unmapped payloads via typed
  `EvidenceQuarantineError` / `ProviderNormalizationResult` — no synonym scanning.
- Focused verification passed after Codex blocker fix:
  `python -m pytest tests/test_takeoff_evidence.py tests/test_extraction_api.py tests/test_schemas.py -q` (53 tests passing).
- Codex re-review after schema-version fail-closed fix: PASS - no blocking issues.

## Completed work
- Paused all six Hermes cron jobs that were running or reporting on the prior P0/release-gate loop.
- Verified Hermes background process registry is empty.
- Inspected visible systemd timers/services and running processes.
- Verified essential services remain active: Hermes gateways, `mobi-estimating.service`, Docker, cron, OS maintenance timers.
- Created pilot branch from current `origin/main`: `pilot-readiness-ai-assisted-mvp` at `5005ba8bc7751fbf6b22684505fd1f8a7d60f0f9`.
- Started required pilot control files.

## Tests / checks run
- `cronjob list`: all six jobs paused.
- `process list`: no Hermes-tracked background processes.
- `systemctl --user list-timers --all`: only `mobi-hermes-self-heal.timer` and standard cache cleanup visible.
- `systemctl is-active cron docker mobi-estimating qemu-guest-agent lvm2-monitor`: active.
- `systemctl --user is-active hermes-gateway.service hermes-gateway-mobimarketing.service mobi-hermes-self-heal.timer`: active.
- `git fetch origin --prune`; open PR inventory collected through GitHub CLI.

## Benchmark changes
None yet. The pilot reset changes the benchmark priority away from release-gate vocabulary expansion toward real estimate capability: source-backed scope, quantity accuracy, schedule extraction, turnaround, human QA time, and contractor correction capture.

## Open PRs
| PR | Recommendation |
|---|---|
| #88 P0: preserve readiness delivery-source provenance | Extract the provenance-preservation idea into canonical evidence normalization. Do not merge automatically. |
| #89 P0: reject model-generated release quantities | Freeze/reduce. It contains useful evidence-lineage ideas, but the branch demonstrates the old endless validator/vocabulary loop and should be replaced by typed schema/boundary validation. |
| #92 Add Mobi SEO blog quality standard | Separate marketing PR. Not part of estimating pilot milestone lane. |
| #73 Normalize quantity extraction candidates | Stale. Supersede with provider-neutral takeoff/evidence architecture. |
| #5 Pay-first checkout | Stale/dirty. Revisit under customer portal/payment milestone after pilot estimating pipeline is controlled. |

## Review results
- Codex review from the interrupted PR #89 loop passed for a snapshot, but PR #89 is no longer the active strategy.
- Current directive freezes new release-gate vocabulary work.

## Blockers
- Root crontab inspection was blocked by the terminal approval guard. No destructive action was attempted.
- Untracked `marketing-site/drafts/` and `marketing-site/marketing_ops/` remain untouched.
- Disk usage is high at 91%; large blueprint experiments should use caches and avoid unnecessary duplicated artifacts.

## Decisions required
None immediately. Owner approval still required for purchases, external messages, pricing/legal/DNS/payment changes, production data deletion, and final estimate delivery.

## Next task
Finish Milestone 1 repo audit documentation and begin Milestone 2 with a typed canonical evidence schema plus provider-neutral takeoff interface.

## Estimated pilot readiness status
- Foundation/control: improving, old loop paused.
- Real pilot estimating capability: not ready yet.
- Private paid pilot: blocked until canonical evidence/provider architecture, intake, takeoff proof, estimator command center, revision learning, delivery package, and five-project shakeout are complete.
