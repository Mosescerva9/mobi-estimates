# Paused automation inventory

Updated: 2026-07-15T02:13:33Z
Branch: `pilot-readiness-ai-assisted-mvp`

## Scope
This inventory records Mobi-related autonomous development workflows inspected during Milestone 1 of the pilot reset. The prior release-gate vocabulary loop is terminated. Items are paused reversibly; nothing was deleted.

## Verification summary
- Hermes cron scheduler: inspected and all six configured jobs are paused.
- Hermes background process registry: empty.
- Systemd user timers: inspected; `mobi-hermes-self-heal.timer` remains active because it maintains Hermes/gateway availability, not release-gate PR generation.
- Systemd services: `mobi-estimating.service`, Hermes gateways, Docker, cron, and OS maintenance services remain active.
- Root crontab inspection attempted through sudo was blocked by the terminal approval guard; no destructive action was attempted. User-level systemd/cron and visible process checks found no obsolete PR-generation process still running.

## Paused items

| Name | Type | Schedule | Command / script | File path | Purpose | Previous state | Current state | Reason paused | Exact restoration command |
|---|---|---|---|---|---|---|---|---|---|
| Mobi Chief of Staff Morning Brief | Hermes cron LLM job | `0 7 * * *` | scheduled prompt with `mobi-chief-of-staff`, `mobi-control-center`, `mobi-executive-reporting`, `obsidian` | Hermes profile cron DB | Daily internal brief | enabled/scheduled | paused | Prevent old status/report loop from running during pilot-control reset | Hermes tool: `cronjob(action="resume", job_id="b931739e8de6")` |
| Mobi P0 Foundation Builder Loop — Continuous | Hermes cron LLM job | `every 5m` | scheduled prompt using `mobi-product-builder`, `mobi-technical-delivery`, `claude-code`, `codex`, `obsidian` | workdir `/home/hermes/work/mobi-estimates` | Prior P0 release-gate builder | enabled/scheduled | paused | This was the main obsolete release-gate PR generation loop | Hermes tool: `cronjob(action="resume", job_id="fbeda3d3c693")` |
| Mobi P0 Foundation QA Review — Event Triggered Fallback | Hermes cron LLM job | `every 720m` | scheduled QA/review prompt using `codex`, `obsidian`, `mobi-technical-delivery` | workdir `/home/hermes/work/mobi-estimates` | Prior release-gate QA fallback | enabled/scheduled | paused | QA loop was tied to obsolete release-gate vocabulary/helper churn | Hermes tool: `cronjob(action="resume", job_id="369bdc6dfb1a")` |
| Mobi P0 Foundation Daily Status | Hermes cron LLM job | `0 8 * * *` | scheduled status prompt using `mobi-executive-reporting`, `obsidian` | workdir `/home/hermes/work/mobi-estimates` | Daily status for previous audit-remediation track | enabled/scheduled | paused | Replaced by pilot progress/status files and milestone reporting | Hermes tool: `cronjob(action="resume", job_id="ecbca272455c")` |
| Mobi Option A QA Head-Change Watcher | Hermes cron no-agent script | `every 3m` | `mobi_option_a_qa_watcher.py` | `~/.hermes/profiles/mobi/scripts/mobi_option_a_qa_watcher.py` | Event-triggered QA watcher for old PR heads | enabled/scheduled | paused | It auto-reviewed/triggered old release-gate branches without new milestone approval | Hermes tool: `cronjob(action="resume", job_id="75fa1bed975b")` |
| Mobi Option A Productivity Audit | Hermes cron no-agent script | `every 360m` | `mobi_option_a_productivity_audit.py` | `~/.hermes/profiles/mobi/scripts/mobi_option_a_productivity_audit.py` | Productivity audit for Option A old loop | enabled/scheduled | paused | Old-loop productivity metric no longer reflects pilot progress | Hermes tool: `cronjob(action="resume", job_id="f7e2bb653bbe")` |

## Inspected and intentionally left active

| Name | Type | State | Reason kept active |
|---|---|---|---|
| `hermes-gateway.service` | systemd user service | active | Required Telegram communication path for this profile. Not a PR generator. |
| `hermes-gateway-mobimarketing.service` | systemd user service | active | Separate marketing gateway; not part of release-gate validator loop. No external messages sent by this action. |
| `mobi-hermes-self-heal.timer` / service | systemd user timer/service | timer active, service inactive between runs | Keeps Hermes model/gateway availability stable. Does not generate Mobi PRs or edit release validators. |
| `mobi-estimating.service` | systemd service | active | Production/internal FastAPI estimating engine uptime. Required infrastructure. |
| `cron.service` | systemd service | active | OS cron service; disabling it could affect system maintenance. Hermes cron jobs above are paused individually. |
| `docker.service` | systemd service | active | Required infrastructure. |
| `dpkg-db-backup.timer`, `apt-daily*`, `logrotate.timer`, `fstrim.timer`, `e2scrub_all.timer`, `systemd-tmpfiles-clean.timer` | system timers | active | Backups and server maintenance explicitly must not be disabled. |
| Marketing helper servers under `marketing-site/marketing_ops` | processes spawned by `mobimarketing` gateway | active | Not part of old release-gate development loop. Untracked path remains untouched pending owner classification. |

## Open obsolete-development PRs frozen
- PR #89 remains open but should not be merged as-is; recommendation is to extract useful architecture/tests and replace with canonical evidence schema/provider boundary.
- PR #88 remains open; recommendation is to extract the reusable provenance-preservation pattern into canonical evidence normalization, not merge automatically.
- PR #73 is stale and should be closed/superseded by provider-neutral evidence/takeoff architecture.

## Confirmation
At this checkpoint, no Hermes cron job remains enabled. Visible process and user/systemd inspections found no active obsolete release-gate builder, QA watcher, autoresearch PR loop, or recurring validator-vocabulary loop.
