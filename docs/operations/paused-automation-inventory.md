# Paused Automation Inventory

Updated: 2026-07-16T00:04:33Z

## Verification summary
- Hermes cron jobs inspected with `cronjob list` and `/home/hermes/.hermes/profiles/mobi/cron/jobs.json`.
- All Mobi autonomous builder/QA/status jobs are currently `state: paused`, `enabled: false`.
- User crontab has no entries.
- System timers are OS maintenance only; no Mobi release-gate/development automation found there.
- User timer `mobi-hermes-self-heal.timer` remains active because it is an essential gateway/config health service, not a product-development loop.
- Process scan found no active Claude/Codex builder loops, no tmux/screen coding sessions, and no running release-gate/benchmark watcher.

## Paused jobs

| Name | Type | Schedule | Command / prompt | Location | Previous state | Current state | Reason paused | Restoration command |
|---|---|---:|---|---|---|---|---|---|
| Mobi Chief of Staff Morning Brief | Hermes cron LLM job | `0 7 * * *` | Chief-of-staff morning brief prompt | `~/.hermes/profiles/mobi/cron/jobs.json`, id `b931739e8de6` | enabled recurring brief | paused / enabled=false | Non-essential status/reporting loop during MVP reset | `cronjob(action="resume", job_id="b931739e8de6")` |
| Mobi P0 Foundation Builder Loop — Continuous | Hermes cron LLM builder loop | `every 5m` | Autonomous P0 foundation builder prompt | `~/.hermes/profiles/mobi/cron/jobs.json`, id `fbeda3d3c693` | active autonomous builder loop | paused / enabled=false | Obsolete relative to OpenTakeoff/customer-launch directive; could keep generating release-gate/evidence-vocabulary PRs without MVP customer progress | `cronjob(action="resume", job_id="fbeda3d3c693")` |
| Mobi P0 Foundation QA Review — Event Triggered Fallback | Hermes cron LLM QA loop | `every 720m` | Autonomous P0 QA/review prompt | `~/.hermes/profiles/mobi/cron/jobs.json`, id `369bdc6dfb1a` | active fallback QA loop | paused / enabled=false | Tied to old P0 release-gate loop and unchanged-code review risk | `cronjob(action="resume", job_id="369bdc6dfb1a")` |
| Mobi P0 Foundation Daily Status | Hermes cron LLM report | `0 8 * * *` | Daily P0 foundation status prompt | `~/.hermes/profiles/mobi/cron/jobs.json`, id `ecbca272455c` | enabled daily report | paused / enabled=false | Non-essential reporting loop; status now maintained in MVP docs | `cronjob(action="resume", job_id="ecbca272455c")` |
| Mobi Option A QA Head-Change Watcher | Hermes no-agent script cron | `every 3m` | `mobi_option_a_qa_watcher.py` | `~/.hermes/profiles/mobi/cron/jobs.json`, id `75fa1bed975b` | active PR-head watcher | paused / enabled=false | Directly tied to old PR QA loop; could retrigger review/burn usage | `cronjob(action="resume", job_id="75fa1bed975b")` |
| Mobi Option A Productivity Audit | Hermes no-agent script cron | `every 360m` | `mobi_option_a_productivity_audit.py` | `~/.hermes/profiles/mobi/cron/jobs.json`, id `f7e2bb653bbe` | active productivity audit | paused / enabled=false | Old-loop productivity reporting not needed during MVP reset | `cronjob(action="resume", job_id="f7e2bb653bbe")` |

## Not disabled
- `mobi-hermes-self-heal.timer` — essential Hermes profile/gateway health.
- `cron.service`, `ssh.service`, `caddy.service`, `docker.service` — essential host services.
- `/opt/mobi-estimating-engine` uvicorn on `127.0.0.1:8000` — production/engine service left running.
- OS maintenance timers (`apt`, `logrotate`, `dpkg-db-backup`, `sysstat`, etc.) — not Mobi autonomous development loops.

## Backup/service note
Current disk is 95% full (`/dev/sda1` 367G used / 21G available). This is a launch blocker to track; no cleanup was performed because deleting files outside scratch is approval-gated.
