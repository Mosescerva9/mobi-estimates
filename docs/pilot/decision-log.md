# Pilot decision log

Updated: 2026-07-15T02:13:33Z

| Date | Decision | Evidence | Consequence | Revisit when |
|---|---|---|---|---|
| 2026-07-15 | Terminate the prior release-gate vocabulary loop. | Cron inventory showed builder/QA/watchers repeatedly focused on release-gate aliases; user directive explicitly terminated that loop. | Pause all old cron jobs; freeze synonym/alias expansion; move to milestone/product capability work. | Only if a specific safety defect is found in the new architecture. |
| 2026-07-15 | Start pilot work from `origin/main` on `pilot-readiness-ai-assisted-mvp`. | `origin/main` at `5005ba8...` includes latest merged SEO/production fixes; PR #88/#89 remain unmerged and are not automatic base. | New branch avoids inheriting old-loop validator churn. | If a current PR is explicitly extracted/ported. |
| 2026-07-15 | PR #88 should be extracted, not auto-merged. | PR preserves nested provenance metadata for readiness source rows; useful pattern but not full canonical evidence architecture. | Reuse in Milestone 2 evidence normalization. | During canonical evidence implementation. |
| 2026-07-15 | PR #89 should be frozen/reduced, not auto-merged. | PR contains many small release-gate vocabulary/helper commits and demonstrates old endless loop; some lineage tests are useful. | Replace with typed canonical evidence schema and boundary validation. | After canonical schema exists, selectively port tests/ideas if still valuable. |
