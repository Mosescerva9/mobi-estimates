# Mobi Estimates customer-project operating guide (MVP)

Updated: 2026-07-21

## Safety gates

- A staff reviewer must approve quantities, pricing, assumptions, exclusions, RFIs, and the final package.
- Do not upload a customer deliverable or change a project to a final delivery status until the delivery gate is open and Moses approves final estimate delivery.
- Do not run a live Stripe checkout, charge, refund, pricing change, production deployment, or external message without the required approval.
- Never treat model text, test-only quantities, or fictional cost data as final estimate evidence.

## 1. Onboard a customer

1. Use the normal account claim/signup flow at `https://portal.mobiestimates.com/login`.
2. Confirm the user belongs to the correct company before project creation.
3. For an internal/free test, use a dedicated test identity and clearly label the project `TEST ONLY`.
4. For a paid customer, confirm Stripe payment state before consuming a Pay Per Project credit or enabling paid access. Do not manually mark payment successful without Stripe evidence.

## 2. Accept payment

1. Customer selects the approved offer on `https://mobiestimates.com/pricing`.
2. Customer completes Stripe Checkout.
3. Confirm the webhook created/updated the checkout claim and entitlement.
4. Confirm the portal shows the correct access. If checkout or webhook proof is missing, stop and reconcile Stripe before starting estimating work.

Current limitation: live checkout has not been exercised in this launch run. Use Stripe test mode for E2E when test credentials are configured; live checkout remains approval-gated.

## 3. Create a project and upload files

1. Sign in to the customer portal.
2. Open **Submit a project**.
3. Enter project name, type, location, bid date, requested trades/scopes, estimate type, alternates/allowances, exclusions, and open questions.
4. Upload plans, specifications, addenda, and instructions. Files go to the private `project-files` bucket.
5. Confirm the project page lists every file. If the page reports a partial upload or register-sync error, retry only the failed file/register operation; do not create a duplicate project.

## 4. Start document processing

1. Staff opens `/admin/projects/<project-id>`.
2. Confirm the EstimateJob document register contains every uploaded file.
3. Mark each document accepted, replacement required, or rejected with notes.
4. Generate the deterministic intake/plan-context packet.
5. Use **Send to engine** for the selected plan PDF.
6. Poll the engine status until sheet processing completes. A failed job must retain its project record and show the safe error; correct the source/configuration and retry.

Current limitation: the production portal engine and production OpenTakeoff worker use separate SQLite databases/data roots. Do not claim a newly uploaded portal project is available to the worker until the joined data plane is deployed and verified.

## 5. Run AI analysis

1. Verify the engine is configured for the approved live provider and exact approved model.
2. Confirm live extraction is enabled only when an API key is present.
3. Start extraction by trade from the admin Automation panel.
4. Review source document/page/sheet references, missing documents, conflicts, assumptions, exclusions, and clarification candidates.
5. Reject unsupported output. AI text must never create a quantity, rate, or approved estimate value without deterministic validation and source evidence.

Current limitation: production has no verified GPT-5.6 Medium configuration/API key. The existing live OpenAI provider is disabled and defaults to a legacy configurable model. Live AI analysis is therefore blocked.

## 6. Operate the takeoff workbench

1. Confirm the engine project and processed sheet list are visible in the staff workbench.
2. Select the correct plan and sheet.
3. Verify the printed scale using a known dimension; record the scale source.
4. Draw the measurement geometry.
5. Submit the worker job and poll until `awaiting_review`.
6. Review quantity, unit, geometry, sheet/page, scale, provider, and evidence metadata.
7. Approve, correct, or replace the measurement. Preserve the correction/review record.

Verified capability: a real OpenTakeoff linear measurement and polygon/area API exist with canonical evidence. Current limitation: count measurement is not exposed by the deployed worker API, and the portal-upload/worker data plane is not joined.

## 7. Apply or edit pricing

1. Use only a controlled cost-book version or reviewer-entered/project-specific quotes with source notes.
2. Map reviewed scope items to assemblies or explicit generic pricing bases.
3. Enter labor, material, equipment, subcontract, other direct cost, waste, tax, indirects, overhead, profit, contingency, allowances, alternates, and manual adjustments as applicable.
4. Run deterministic pricing.
5. Resolve every blocking exception.
6. Use line-item override only with a reason and reviewer identity; then regenerate/reprice into a new version when required.

## 8. Generate and verify the estimate

1. Generate the estimate version.
2. Confirm rollup `reconciled=true` and no unpriced/incomplete/blocking lines remain.
3. Review assumptions, exclusions, clarifications/RFIs, source evidence, and revision history.
4. Generate the Excel workbook through `GET /api/v1/projects/{project_id}/estimates/{estimate_id}/versions/{version_id}/export.xlsx` only after the final delivery lock allows export.
5. Open the workbook and inspect **Project Summary**, **Detailed Line Items**, assumptions, exclusions, RFIs/clarifications, allowances, alternates, and revision history.
6. Independently compare the workbook final total to the engine rollup.

## 9. Approve and deliver

1. Reviewer approves the fully priced version.
2. Confirm the final delivery gate has complete self-scoped evidence, supported scope, all required reviews, and explicit owner approval.
3. Upload approved files to the private `deliverables` bucket.
4. Change the project status only through the guarded delivery workflow.
5. Customer signs in and downloads the approved files using a short-lived signed URL.
6. Save any customer correction as a revision request; preserve the prior approved version.

Current limitation: final customer delivery remains intentionally fail-closed in the current code. Do not bypass the gate.

## 10. Retry a failed job

1. Record the job id, project id, stage, safe error code/message, and timestamp.
2. Confirm the source project/files still exist.
3. Correct the underlying issue (bad file, missing scale, provider timeout, configuration, or worker connectivity).
4. Retry with a new caller idempotency suffix when a genuinely new attempt is required; reusing the same idempotency key returns the original job.
5. Staff UI: in the admin project takeoff workbench ("Submit to real worker" section), a **Retry failed job** button appears only while the current worker job status is exactly `failed`. It calls the staff-only durable-retry action, is disabled while a worker action is pending, and shows the returned safe message. On success it adopts the linked retry attempt's job id/status so you continue the normal confirm-scale/measure flow, while a retained note keeps the original failed job id/error visible (the backend never mutates the original failed job). The button does not auto-retry, measure, approve, deliver, message, or price.
6. Confirm the failed record remains auditable and the successful retry creates/preserves canonical evidence.

## 11. Health, logs, restarts, and rollback

Health checks:

- Portal: `https://portal.mobiestimates.com/login`
- Main API: `https://api.mobiestimates.com/health`
- Versioned API: `https://api.mobiestimates.com/api/v1/health`
- Local main service: `http://127.0.0.1:8000/health`
- Local worker service: `http://127.0.0.1:8001/health`

Logs (read-only):

```bash
sudo journalctl -u mobi-estimating.service -n 200 --no-pager
sudo journalctl -u mobi-estimating-worker-api.service -n 200 --no-pager
sudo journalctl -u caddy.service -n 200 --no-pager
```

Restart after an approved production change:

```bash
sudo systemctl restart mobi-estimating.service
sudo systemctl restart mobi-estimating-worker-api.service
sudo systemctl reload caddy.service
```

Verify after restart:

```bash
systemctl is-active mobi-estimating.service mobi-estimating-worker-api.service caddy.service
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8001/ready
```

Rollback:

1. Stop and preserve evidence; do not delete failed deployment data.
2. Restore the previously verified application release directory/config and database backup.
3. Restart the affected service only.
4. Verify database integrity, health/readiness, and the last known read-only project before reopening processing.
5. Do not narrow a database constraint while rows still use a newer status/value.

## Known launch blockers

- Claude Code and Codex CLI are not authenticated on this host, so required implementation/review lanes are blocked.
- Live GPT-5.6 Medium analysis is not configured or verified.
- The portal-upload engine and OpenTakeoff worker are not joined for a newly uploaded project.
- Count measurement is not exposed through the live worker API/workbench.
- Excel export is implemented on the launch branch but is not merged/deployed.
- Live Stripe checkout/test-mode webhook E2E is not verified in this run.
- Final delivery remains fail-closed and no real customer estimate has been delivered.
