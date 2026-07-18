# Backup / Restore Verification — 2026-07-18

## Scope

This note records the verified recovery status after the live workbench proof deployment and production test-data exercise.

## Results

| Area | Status | Evidence |
|---|---|---|
| Worker SQLite DB backup | working | Copied `/var/lib/mobi-worker-staging/mobi.db` into `/tmp/mobi-backup-verify-20260718T201916Z.tgz`; `pragma integrity_check` returned `ok`; 44 tables present. |
| Worker SQLite scratch restore | working | Restored archive into `/tmp/mobi-restore-verify-20260718T201938Z`; queried `opentakeoff_worker_jobs` count = 8 and production proof evidence `c941ef8e-b965-45d8-acb5-c9770999044a` quantity = `162 LF`. |
| Legacy estimating-engine SQLite DB backup | working | Copied `/opt/mobi-estimating-engine/data/mobi.db` into the same archive; `pragma integrity_check` returned `ok`; 37 tables present. |
| Legacy estimating-engine SQLite scratch restore | working | Restored archive into scratch dir; queried project count = 1 and C011 project sheet count = 20. |
| Supabase app-table read access | working | Service-role logical snapshot summary succeeded for `companies`, `profiles`, `company_members`, `subscriptions`, `projects`, `project_files`, `estimate_jobs`, `estimate_job_documents`, and `deliverables`. |
| Supabase physical backup metadata | not_verified | Supabase Management API calls to project and backup endpoints returned Cloudflare/Supabase `403 Error 1010: browser_signature_banned`; no physical backup list could be verified from this host. |
| Direct Postgres dump/restore | missing | Production env available to this session contains Supabase URL, anon key, and service-role key only; no direct Postgres connection string/pooler URL is available. |
| Supabase scratch restore | not_verified | No safe direct DB connection or Management API backup access was available from this host, so a scratch Supabase restore was not performed. |
| Storage/object restore | partially_working | Project upload E2E previously proved private Storage upload/read/delete behavior with temporary data; no full bucket export/restore was verified in this backup slice. |

## Backup artifact created

- Archive: `/tmp/mobi-backup-verify-20260718T201916Z.tgz`
- SHA-256: `64a9f95e79f6b8144746b11bbf6ec04ae69056a1f43fdec7d499ddc5fd96f93e`

This archive is a verification artifact on the VPS temp filesystem, not a durable offsite backup.

## Operational conclusion

Current recovery posture is **partially_working**:

- The VPS worker/engine SQLite data can be backed up and restored into a scratch directory.
- The restored worker DB contains the latest production workbench proof evidence (`162 LF`).
- Supabase app data can be read through service-role APIs, but physical Supabase backup metadata and a full scratch restore are not verified from this host due to Management API `403 Error 1010` and lack of direct DB connection.

## Required next hardening

1. Add a durable backup destination outside `/tmp` for worker/engine SQLite archives.
2. Add a scheduled backup job for `/var/lib/mobi-worker-staging` and `/opt/mobi-estimating-engine/data`.
3. Obtain/verify an approved Supabase direct Postgres connection string or unblock Management API access.
4. Run a true Supabase scratch restore or logical export/import drill.
5. Add Storage bucket export/restore verification for `project-files`.

No customer-facing estimate was generated or delivered as part of this verification.
