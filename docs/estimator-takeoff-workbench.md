# Estimator takeoff workbench (internal, staff-only)

First internal slice of the estimator takeoff workbench, wired to the **real**
merged OpenTakeoff MCP runtime (PR #99: `mobi-estimating-phase1/app/takeoff/`).

## What ships

- `src/lib/estimator-takeoff-workbench.ts` — typed domain model: queue states,
  provenance/review labels, quantity display metadata, correction records,
  training-eligibility values, interaction timing (seconds) + targets, review
  action state model, worker job status model, and a mapper from the real
  runtime JSON payload into a workbench preview.
- `mobi-estimating-phase1/scripts/opentakeoff_workbench_bridge.py` — drives the
  **pinned local `opentakeoff-mcp` subprocess** (not a mock) against the PR #96
  public Golden Set fixture `ca_dgs_24_253614_plans.pdf`, reproducing the target
  C011 line measurement (**37.5 LF**) and emitting JSON for the workbench.
- `scripts/harness-estimator-takeoff-workbench.ts` — end-to-end proof: public
  fixture → C011 → confirm scale → line coords → actual OpenTakeoff runtime →
  37.5 LF → approve → canonical evidence-like record persisted to a temp file →
  reload → verify.
- `src/app/admin/projects/[id]/TakeoffWorkbenchPanel.tsx` — staff-only preview
  surface under the `requireStaff()`-gated `/admin` route.

## Provenance labels (preserved exactly)

`OpenTakeoff measured`, `Human verified`, `Schedule extracted`,
`Customer supplied`, `Model candidate`. Model candidates are rendered distinctly
(dashed/amber) and can never be presented as human-verified. Unreviewed and
model records default to `not_training_eligible`.

## Runtime path & the deployed-environment constraint

The real measurement path is:

```
ResolvedProjectDocument (public fixture PDF)
  → OpenTakeoffWorkerService.create_job
  → OpenTakeoffMCPClient (real Node subprocess: node_modules/opentakeoff-mcp)
  → run_linear_or_polygon_export: load_plan → set_scale → measure_line → export
  → normalize_opentakeoff_export → CanonicalEvidence
```

This needs a local **Node subprocess + `pdfinfo`**. A deployed Next.js server
action cannot safely launch that subprocess, so live measurement is
**internal/local-only** and stays in the harness/bridge. The admin panel
previews the actual captured runtime result and the review state model; it does
**not** claim to run measurements in the browser, and full interactive PDF
drawing is a TODO (a deterministic coordinate form stands in for it).

Nothing here delivers a customer estimate. The bridge runs with `persist=False`
and uses only the public fixture — no confidential customer files.

## Verification commands

```bash
npm run test:estimator-takeoff-workbench          # domain model contract checks
npm run harness:estimator-takeoff-workbench       # real runtime E2E (37.5 LF)
npm run typecheck
npm run build

cd mobi-estimating-phase1
MOBI_DEPLOYMENT_ENVIRONMENT=local PYTHONPATH=. \
  python scripts/opentakeoff_workbench_bridge.py  # real runtime, prints JSON
MOBI_DEPLOYMENT_ENVIRONMENT=local PYTHONPATH=. \
  python -m pytest tests/test_opentakeoff_mcp_runtime.py -q
```
