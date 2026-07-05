import Link from "next/link";
import {
  DOCUMENT_REVIEW_STATUSES,
  ESTIMATE_JOB_EVENT_FILTERS,
  ESTIMATE_JOB_STATUSES,
  estimateJobBadgeClass,
  estimateJobEventFilterGroup,
  estimateJobEventFilterLabel,
  estimateJobStatusLabel,
  type EstimateJobEventFilter,
  type EstimateJobNoticeCode,
  type EstimateJobNoticeTone,
} from "@/lib/estimate-jobs";
import {
  changeEstimateJobStatus,
  completeDocumentReview,
  completePricingReview,
  completeQaReview,
  completeTakeoff,
  generatePlanContext,
  regenerateIntakeReview,
  requestOwnerRevision,
  startTakeoff,
  syncEstimateJobDocumentRegister,
  updateDocumentReviewStatus,
} from "./actions";
import type { EstimateDocumentRegisterHealth } from "@/lib/estimate-jobs";

type IntakeReview = {
  completeness?: Record<string, boolean>;
  missing_or_unclear?: string[];
  risk_flags?: string[];
  recommended_next_status?: string;
  internal_notes?: string[];
  reviewed_at?: string;
};

type PlanContextPacket = {
  generated_at?: string;
  source_gaps?: string[];
  document_summary?: {
    total?: number;
    accepted?: number;
    plan_set?: number;
    spec?: number;
  };
};

type AutomationState = {
  plan_context_v1?: PlanContextPacket;
  plan_context_generated_at?: string;
};

interface EstimateJobPanelProps {
  projectId: string;
  job: {
    id: string;
    status: string;
    priority: string;
    blocked_reason: string | null;
    intake_review: IntakeReview | null;
    automation_state: AutomationState | null;
    target_delivery_at: string | null;
    updated_at: string;
  } | null;
  documents: Array<{
    id: string;
    file_name: string;
    category: string;
    document_type: string | null;
    page_count: number | null;
    processing_status: string;
    review_status: string;
    review_notes: string | null;
    sheet_index?: unknown;
  }>;
  events: Array<{
    id: string;
    event_type: string;
    summary: string;
    actor_type: string;
    created_at: string;
    payload: unknown;
  }>;
  notice: { code: EstimateJobNoticeCode; tone: EstimateJobNoticeTone; message: string } | null;
  eventFilter: EstimateJobEventFilter;
  registerHealth: EstimateDocumentRegisterHealth;
}

/** Full event details are shown for only the newest matching events; older matches collapse to a summary line. */
const FULL_DETAIL_EVENT_COUNT = 5;

/**
 * Human-readable ladder for the main EstimateJob progression, used only to render the
 * internal orientation guide below. Purely presentational — does not drive any gating
 * logic, which lives in the RPCs behind each action's server action.
 */
const WORKFLOW_LADDER: Array<{ label: string; hint: string; statuses: string[] }> = [
  {
    label: "Intake & document register",
    hint: "Documents are registered and reviewed; every registered file must be synced and at least one accepted.",
    statuses: [
      "intake_received",
      "intake_review_pending",
      "intake_needs_info",
      "ready_for_document_processing",
      "document_processing",
      "document_review_pending",
    ],
  },
  {
    label: "Takeoff ready",
    hint: "Document review is complete. Takeoff can be started.",
    statuses: ["takeoff_ready"],
  },
  {
    label: "Takeoff in progress",
    hint: "Staff are measuring/quantifying from the reviewed documents and plan context.",
    statuses: ["takeoff_in_progress"],
  },
  {
    label: "Pricing review",
    hint: "Internal pricing pass against the takeoff. No pricing is shown to the customer here.",
    statuses: ["pricing_review_pending"],
  },
  {
    label: "QA review",
    hint: "Internal quality check before the item is ready for owner sign-off.",
    statuses: ["qa_pending"],
  },
  {
    label: "Ready for owner approval",
    hint: "Awaiting Moses/internal owner review. This panel cannot approve or send anything on its own.",
    statuses: ["ready_for_owner_approval"],
  },
];

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function labelize(key: string): string {
  return key.replace(/^has_/, "").replace(/_/g, " ");
}

type EventPayloadShape = {
  previous_status?: string;
  next_status?: string;
  status?: string;
  blocked_reason?: string | null;
  takeoff_notes?: string | null;
  pricing_notes?: string | null;
  qa_notes?: string | null;
  revision_target?: string;
  revision_notes?: string | null;
  review_status?: string;
  previous_review_status?: string;
  review_notes?: string | null;
  counts?: Record<string, number>;
  total?: number;
  accepted?: number;
  ignored?: number;
  pending?: number;
  needs_replacement?: number;
  project_files?: number;
  registered_project_files?: number;
  missing_registered_project_files?: number;
  document_summary?: Record<string, number>;
  source_gaps?: string[];
  generated_at?: string;
  plan_context?: {
    document_summary?: Record<string, number>;
    source_gaps?: string[];
  };
};

/**
 * Pulls a fixed whitelist of known-safe fields out of an event's raw payload
 * for internal audit display. Never renders arbitrary payload JSON — only the
 * specific keys the EstimateJob RPCs are known to write.
 */
function eventDetailRows(payload: unknown): Array<{ label: string; value: string }> {
  if (!payload || typeof payload !== "object") return [];
  const p = payload as EventPayloadShape;
  const rows: Array<{ label: string; value: string }> = [];

  if (p.previous_status && (p.next_status || p.status)) {
    rows.push({ label: "Status change", value: `${p.previous_status} → ${p.next_status ?? p.status}` });
  } else if (p.status) {
    rows.push({ label: "Status", value: p.status });
  }
  if (p.blocked_reason) rows.push({ label: "Blocked reason", value: p.blocked_reason });
  if (p.takeoff_notes) rows.push({ label: "Takeoff notes", value: p.takeoff_notes });
  if (p.pricing_notes) rows.push({ label: "Pricing notes", value: p.pricing_notes });
  if (p.qa_notes) rows.push({ label: "QA notes", value: p.qa_notes });
  if (p.revision_target) rows.push({ label: "Revision target", value: estimateJobStatusLabel(p.revision_target) });
  if (p.revision_notes) rows.push({ label: "Revision notes", value: p.revision_notes });
  if (p.review_status) {
    rows.push({
      label: "Document review",
      value: p.previous_review_status ? `${p.previous_review_status} → ${p.review_status}` : p.review_status,
    });
  }
  if (p.review_notes) rows.push({ label: "Review notes", value: p.review_notes });

  const topLevelCounts = {
    total: p.total,
    accepted: p.accepted,
    ignored: p.ignored,
    pending: p.pending,
    needs_replacement: p.needs_replacement,
    project_files: p.project_files,
    registered_project_files: p.registered_project_files,
    missing_registered_project_files: p.missing_registered_project_files,
  };
  const counts = p.counts ?? Object.fromEntries(
    Object.entries(topLevelCounts).filter(([, value]) => typeof value === "number"),
  );
  if (counts && typeof counts === "object") {
    const summary = Object.entries(counts)
      .map(([key, value]) => `${labelize(key)}: ${value}`)
      .join(" · ");
    if (summary) rows.push({ label: "Document counts", value: summary });
  }

  const docSummary = p.plan_context?.document_summary ?? p.document_summary;
  if (docSummary && typeof docSummary === "object") {
    const summary = Object.entries(docSummary)
      .map(([key, value]) => `${labelize(key)}: ${value}`)
      .join(" · ");
    if (summary) rows.push({ label: "Plan context docs", value: summary });
  }

  const gaps = p.plan_context?.source_gaps ?? p.source_gaps;
  if (Array.isArray(gaps) && gaps.length > 0) {
    const preview = gaps.slice(0, 3).join("; ");
    rows.push({
      label: "Source gaps",
      value: gaps.length > 3 ? `${gaps.length} flagged — ${preview}…` : `${gaps.length} flagged — ${preview}`,
    });
  }

  if (p.generated_at) rows.push({ label: "Generated at", value: fmtDateTime(p.generated_at) });

  return rows;
}

export function EstimateJobPanel({ projectId, job, documents, events, notice, eventFilter, registerHealth }: EstimateJobPanelProps) {
  if (!job) {
    return (
      <section className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
        <h2 className="text-base font-bold text-navy">Estimate job</h2>
        <EstimateJobNoticeBanner notice={notice} />
        <p className="mt-2 text-sm text-amber-800">
          No internal EstimateJob was found. Regenerate intake review after the database migration is applied.
        </p>
        {registerHealth.customerFileCount > 0 && (
          <div className="mt-3">
            <p className="text-sm text-amber-800">
              {registerHealth.customerFileCount} customer file(s) are uploaded but not yet registered to a job.
            </p>
            <SyncRegisterForm projectId={projectId} estimateJobId={null} />
          </div>
        )}
      </section>
    );
  }

  const review = (job.intake_review ?? {}) as IntakeReview;
  const completeness = Object.entries(review.completeness ?? {});
  const planContext = job.automation_state?.plan_context_v1 ?? null;
  const sourceGaps = planContext?.source_gaps ?? [];
  const planContextLocked = ["closed", "canceled"].includes(job.status);
  const missing = review.missing_or_unclear ?? [];
  const risks = review.risk_flags ?? [];
  const documentReviewLocked = [
    "takeoff_ready",
    "takeoff_in_progress",
    "pricing_review_pending",
    "qa_pending",
    "ready_for_owner_approval",
    "closed",
    "canceled",
  ].includes(job.status);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-navy">Estimate job</h2>
          <p className="mt-1 text-sm text-slate-500">
            Internal-only workflow. Nothing in this panel is shown to the customer.
          </p>
        </div>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${estimateJobBadgeClass(job.status)}`}>
          {estimateJobStatusLabel(job.status)}
        </span>
      </div>

      <EstimateJobNoticeBanner notice={notice} />

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Detail label="Priority" value={job.priority} />
        <Detail label="Target delivery" value={fmtDateTime(job.target_delivery_at)} />
        <Detail label="Review generated" value={fmtDateTime(review.reviewed_at)} />
      </div>
      {job.blocked_reason && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Blocked: {job.blocked_reason}
        </p>
      )}

      <WorkflowGuide status={job.status} />

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="text-sm font-bold text-navy">Intake completeness</h3>
          {completeness.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">No intake review packet generated yet.</p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {completeness.map(([key, ok]) => (
                <li key={key} className="flex items-center gap-2">
                  <span className={ok ? "text-green-600" : "text-amber-600"}>{ok ? "✓" : "!"}</span>
                  <span className="capitalize text-slate-700">{labelize(key)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="space-y-4">
          <ListBlock title="Missing / unclear" items={missing} empty="No missing items flagged." tone="amber" />
          <ListBlock title="Risk flags" items={risks} empty="No risk flags." tone="red" />
          {review.recommended_next_status && (
            <p className="text-sm text-slate-600">
              Recommended next status: <strong>{estimateJobStatusLabel(review.recommended_next_status)}</strong>
            </p>
          )}
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <form action={regenerateIntakeReview}>
          <input type="hidden" name="projectId" value={projectId} />
          <button className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
            Generate / refresh intake review
          </button>
        </form>
        <form action={changeEstimateJobStatus} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <input type="hidden" name="projectId" value={projectId} />
          <input type="hidden" name="estimateJobId" value={job.id} />
          <select name="estimateJobStatus" defaultValue={job.status}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            {ESTIMATE_JOB_STATUSES.map((status) => (
              <option key={status} value={status}>{estimateJobStatusLabel(status)}</option>
            ))}
          </select>
          <input name="blockedReason" placeholder="Blocked reason (if blocked)" defaultValue={job.blocked_reason ?? ""}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <button className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-navy hover:border-brand hover:text-brand">
            Save job status
          </button>
          <p className="text-xs text-slate-500 sm:col-span-3">
            Manual override — bypasses the guided ladder above. Use it to unblock, cancel, or correct a job&apos;s
            status; it never sends, publishes, or bills anything.
          </p>
        </form>
      </div>

      <div className="mt-6">
        <h3 className="text-sm font-bold text-navy">Document register</h3>
        <RegisterHealthSummary registerHealth={registerHealth} projectId={projectId} estimateJobId={job.id} />
        {documents.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No documents registered yet.</p>
        ) : (
          <>
            <DocumentReviewSummary documents={documents} />
            <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-3 py-2">File</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Processing</th>
                  <th className="px-3 py-2">Review</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {documents.map((doc) => (
                  <tr key={doc.id}>
                    <td className="px-3 py-2">
                      <div className="font-medium text-navy">{doc.file_name}</div>
                      <div className="text-xs text-slate-400">{doc.category}</div>
                    </td>
                    <td className="px-3 py-2 text-slate-600">{doc.document_type ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-600">{doc.processing_status}</td>
                    <td className="px-3 py-2">
                      <form action={updateDocumentReviewStatus} className="flex flex-wrap items-center gap-2">
                        <input type="hidden" name="projectId" value={projectId} />
                        <input type="hidden" name="estimateJobId" value={job.id} />
                        <input type="hidden" name="documentId" value={doc.id} />
                        <select name="reviewStatus" defaultValue={doc.review_status}
                          className="rounded border border-slate-300 px-2 py-1 text-xs">
                          {DOCUMENT_REVIEW_STATUSES.map((status) => (
                            <option key={status} value={status}>{status}</option>
                          ))}
                        </select>
                        <input name="reviewNotes" defaultValue={doc.review_notes ?? ""} placeholder="Notes"
                          className="min-w-0 rounded border border-slate-300 px-2 py-1 text-xs" />
                        <button className="rounded-full border border-slate-300 px-2 py-1 text-xs font-semibold text-navy hover:border-brand hover:text-brand">
                          Save
                        </button>
                      </form>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            {documentReviewLocked ? (
              <p className="mt-3 text-xs text-slate-500">
                Document review is already complete or locked for the current job status.
              </p>
            ) : (
              <form action={completeDocumentReview} className="mt-3 flex flex-wrap items-center gap-3">
                <input type="hidden" name="projectId" value={projectId} />
                <input type="hidden" name="estimateJobId" value={job.id} />
                <button className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
                  Complete document review
                </button>
                <p className="text-xs text-slate-500">
                  Every registered project file must be synced and reviewed before advancing. At least one document
                  must be accepted. Any document marked &quot;needs replacement&quot; will send the job back to intake instead
                  of takeoff.
                </p>
                {registerHealth.missingCount > 0 && (
                  <p className="w-full rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    {registerHealth.missingCount} customer file(s) are not yet in this register. Sync the document
                    register above before completing review, or this review may not cover every uploaded file.
                  </p>
                )}
              </form>
            )}
          </>
        )}
      </div>

      <div className="mt-6 rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-bold text-navy">Plan context intake</h3>
        <p className="mt-1 text-sm text-slate-500">
          Internal-only. Builds a deterministic packet from project details, requested scope, and the document
          register. This does not create quantities, pricing, a final estimate, or a customer deliverable.
        </p>
        {planContextLocked ? (
          <p className="mt-3 text-sm text-slate-500">
            Plan context is locked because this job is {estimateJobStatusLabel(job.status)}.
          </p>
        ) : (
          <form action={generatePlanContext} className="mt-3">
            <input type="hidden" name="projectId" value={projectId} />
            <input type="hidden" name="estimateJobId" value={job.id} />
            <button className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
              Generate / refresh plan context
            </button>
          </form>
        )}
        {planContext ? (
          <div className="mt-4 space-y-3">
            <dl className="flex flex-wrap gap-4 text-sm">
              <SummaryStat label="Last generated" value={fmtDateTime(planContext.generated_at)} tone="text-slate-700" />
              <SummaryStat label="Accepted docs" value={planContext.document_summary?.accepted ?? 0} tone="text-green-700" />
              <SummaryStat label="Plan set docs" value={planContext.document_summary?.plan_set ?? 0} tone="text-slate-700" />
              <SummaryStat label="Spec docs" value={planContext.document_summary?.spec ?? 0} tone="text-slate-700" />
              <SummaryStat label="Source gaps" value={sourceGaps.length} tone={sourceGaps.length > 0 ? "text-amber-700" : "text-green-700"} />
            </dl>
            <ListBlock title="Source gaps" items={sourceGaps} empty="No source gaps flagged." tone="amber" />
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">No plan context packet generated yet.</p>
        )}
      </div>

      <div className="mt-6 rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-bold text-navy">Start takeoff</h3>
        <p className="mt-1 text-sm text-slate-500">
          Takeoff can only start once document review has completed and at least one document is accepted.
          The document register is refreshed before starting to catch any last-minute uploads.
        </p>
        {job.status === "takeoff_ready" ? (
          <form action={startTakeoff} className="mt-3">
            <input type="hidden" name="projectId" value={projectId} />
            <input type="hidden" name="estimateJobId" value={job.id} />
            <button className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
              Start takeoff
            </button>
          </form>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            Job is currently <strong>{estimateJobStatusLabel(job.status)}</strong>. It must be{" "}
            <strong>{estimateJobStatusLabel("takeoff_ready")}</strong> before takeoff can start.
          </p>
        )}
      </div>

      <div className="mt-6 rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-bold text-navy">Complete takeoff</h3>
        <p className="mt-1 text-sm text-slate-500">
          This only advances the job to pricing review — it does not create a final estimate or any
          customer-facing deliverable.
        </p>
        {job.status === "takeoff_in_progress" ? (
          <form action={completeTakeoff} className="mt-3 flex flex-col gap-3">
            <input type="hidden" name="projectId" value={projectId} />
            <input type="hidden" name="estimateJobId" value={job.id} />
            <textarea
              name="takeoffNotes"
              rows={2}
              placeholder="Takeoff notes (optional, internal only)"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <div>
              <button className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
                Complete takeoff
              </button>
            </div>
          </form>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            Job is currently <strong>{estimateJobStatusLabel(job.status)}</strong>. It must be{" "}
            <strong>{estimateJobStatusLabel("takeoff_in_progress")}</strong> before takeoff can be completed.
          </p>
        )}
      </div>

      <div className="mt-6 rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-bold text-navy">Complete pricing review</h3>
        <p className="mt-1 text-sm text-slate-500">
          Internal-only. This only advances the job to QA — it does not create a final estimate, customer
          deliverable, approval package, email, or pricing visible to the customer.
        </p>
        {job.status === "pricing_review_pending" ? (
          <form action={completePricingReview} className="mt-3 flex flex-col gap-3">
            <input type="hidden" name="projectId" value={projectId} />
            <input type="hidden" name="estimateJobId" value={job.id} />
            <input type="hidden" name="expectedJobUpdatedAt" value={job.updated_at} />
            <textarea
              name="pricingNotes"
              rows={2}
              placeholder="Pricing notes (optional, internal only)"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <div>
              <button className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
                Complete pricing review
              </button>
            </div>
          </form>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            Job is currently <strong>{estimateJobStatusLabel(job.status)}</strong>. It must be{" "}
            <strong>{estimateJobStatusLabel("pricing_review_pending")}</strong> before pricing review can be completed.
          </p>
        )}
      </div>

      <div className="mt-6 rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-bold text-navy">Complete QA review</h3>
        <p className="mt-1 text-sm text-slate-500">
          Internal-only. This only marks the job ready for Moses/internal owner approval — it does not
          send, publish, or deliver a final estimate to the customer, and does not create any customer-facing
          content.
        </p>
        {job.status === "qa_pending" ? (
          <form action={completeQaReview} className="mt-3 flex flex-col gap-3">
            <input type="hidden" name="projectId" value={projectId} />
            <input type="hidden" name="estimateJobId" value={job.id} />
            <input type="hidden" name="expectedJobUpdatedAt" value={job.updated_at} />
            <textarea
              name="qaNotes"
              rows={2}
              placeholder="QA notes (optional, internal only)"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <div>
              <button className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
                Complete QA review
              </button>
            </div>
          </form>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            Job is currently <strong>{estimateJobStatusLabel(job.status)}</strong>. It must be{" "}
            <strong>{estimateJobStatusLabel("qa_pending")}</strong> before QA review can be completed.
          </p>
        )}
      </div>

      <div className="mt-6 rounded-lg border border-slate-200 p-4">
        <h3 className="text-sm font-bold text-navy">Request internal revision</h3>
        <p className="mt-1 text-sm text-slate-500">
          Internal-only. Sends this owner-review item back to QA or pricing for corrections — it does not
          approve, send, publish, or deliver anything customer-facing.
        </p>
        {job.status === "ready_for_owner_approval" ? (
          <form action={requestOwnerRevision} className="mt-3 flex flex-col gap-3">
            <input type="hidden" name="projectId" value={projectId} />
            <input type="hidden" name="estimateJobId" value={job.id} />
            <select
              name="revisionTarget"
              defaultValue="qa_pending"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="qa_pending">{estimateJobStatusLabel("qa_pending")}</option>
              <option value="pricing_review_pending">{estimateJobStatusLabel("pricing_review_pending")}</option>
            </select>
            <textarea
              name="revisionNotes"
              rows={2}
              placeholder="Revision notes (optional, internal only)"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <div>
              <button className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark">
                Request internal revision
              </button>
            </div>
          </form>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            Job is currently <strong>{estimateJobStatusLabel(job.status)}</strong>. It must be{" "}
            <strong>{estimateJobStatusLabel("ready_for_owner_approval")}</strong> before a revision can be requested.
          </p>
        )}
      </div>

      <div className="mt-6">
        <h3 className="text-sm font-bold text-navy">Internal evidence timeline</h3>
        <p className="mt-1 text-sm text-slate-500">
          Internal audit context only. Details below are pulled from the raw event log for staff review — never
          shown to the customer.
        </p>

        <div className="mt-3 flex flex-wrap gap-2">
          {ESTIMATE_JOB_EVENT_FILTERS.map((filter) => (
            <Link
              key={filter}
              href={`/admin/projects/${projectId}?estimateJobEventFilter=${filter}`}
              className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                filter === eventFilter
                  ? "border-brand bg-brand text-white"
                  : "border-slate-300 text-slate-600 hover:border-brand hover:text-brand"
              }`}
            >
              {estimateJobEventFilterLabel(filter)}
            </Link>
          ))}
        </div>

        <EstimateJobEventTimeline events={events} eventFilter={eventFilter} />
      </div>
    </section>
  );
}

function EstimateJobEventTimeline({
  events,
  eventFilter,
}: {
  events: EstimateJobPanelProps["events"];
  eventFilter: EstimateJobEventFilter;
}) {
  const filteredEvents =
    eventFilter === "all" ? events : events.filter((event) => estimateJobEventFilterGroup(event.event_type) === eventFilter);

  return (
    <div className="mt-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Showing {filteredEvents.length} of {events.length} recent events
      </p>
      {filteredEvents.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">
          {events.length === 0
            ? "No internal events logged yet."
            : "No internal events match this filter. Internal audit context only — try another filter above."}
        </p>
      ) : (
        <>
          {filteredEvents.length > FULL_DETAIL_EVENT_COUNT && (
            <p className="mt-2 text-xs text-slate-500">
              Only the newest {FULL_DETAIL_EVENT_COUNT} matching events show full details below; older matching
              events are summarized for compactness.
            </p>
          )}
          <ol className="mt-3 space-y-3">
            {filteredEvents.map((event, index) => {
              if (index >= FULL_DETAIL_EVENT_COUNT) {
                return (
                  <li key={event.id} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-sm">
                    <div className="font-medium text-slate-600">{event.summary}</div>
                    <div className="text-xs text-slate-400">
                      {event.event_type} · {event.actor_type} · {fmtDateTime(event.created_at)}
                    </div>
                  </li>
                );
              }
              const details = eventDetailRows(event.payload);
              return (
                <li key={event.id} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
                  <div className="font-semibold text-navy">{event.summary}</div>
                  <div className="text-xs text-slate-400">
                    {event.event_type} · {event.actor_type} · {fmtDateTime(event.created_at)}
                  </div>
                  {details.length > 0 && (
                    <dl className="mt-2 space-y-1 border-t border-slate-100 pt-2">
                      {details.map((row) => (
                        <div key={row.label} className="flex flex-wrap gap-1 text-xs">
                          <dt className="font-semibold uppercase tracking-wide text-slate-400">{row.label}:</dt>
                          <dd className="text-slate-600">{row.value}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </li>
              );
            })}
          </ol>
        </>
      )}
    </div>
  );
}

/**
 * Compact orientation guide for staff new to the EstimateJob workflow. Presentational only —
 * it reads `status` to highlight where the job sits on {@link WORKFLOW_LADDER}, but never
 * gates or triggers any action itself.
 */
function WorkflowGuide({ status }: { status: string }) {
  const offLadder = ["blocked", "canceled", "closed"].includes(status);

  return (
    <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <h3 className="text-sm font-bold text-navy">Internal workflow guide</h3>
      <p className="mt-1 text-sm text-slate-500">
        Orientation only, for staff working this job. It does not change how any action below behaves.
      </p>

      <ol className="mt-3 space-y-2">
        {WORKFLOW_LADDER.map((step, index) => {
          const active = step.statuses.includes(status);
          return (
            <li
              key={step.label}
              className={`flex gap-3 rounded-lg border px-3 py-2 text-sm ${
                active ? "border-brand bg-white" : "border-transparent"
              }`}
            >
              <span
                className={`flex h-5 w-5 flex-none items-center justify-center rounded-full text-xs font-semibold ${
                  active ? "bg-brand text-white" : "bg-slate-200 text-slate-500"
                }`}
              >
                {index + 1}
              </span>
              <span>
                <span className={active ? "font-semibold text-navy" : "font-medium text-slate-600"}>
                  {step.label}
                </span>
                <span className="block text-xs text-slate-500">{step.hint}</span>
              </span>
            </li>
          );
        })}
      </ol>

      <p className="mt-3 text-xs text-slate-500">
        <strong>Plan context packet</strong> can be generated alongside intake and document review (up until the
        job is closed or canceled) — it assembles a deterministic reference packet, not quantities or pricing.{" "}
        <strong>Owner revision loop</strong>: from &quot;Ready for owner approval&quot;, the job can be sent back
        to QA or pricing review for corrections instead of moving forward.
      </p>

      {offLadder && (
        <p className="mt-3 text-xs text-slate-500">
          Current status <strong>{estimateJobStatusLabel(status)}</strong> is off the main ladder above.
        </p>
      )}

      <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        Guardrail: nothing in this panel approves, publishes, sends, emails, bills, or delivers a final estimate
        or any customer-facing content. Every action here is internal-only staff tooling.
      </p>
    </div>
  );
}

/**
 * Admin-only visibility into whether every uploaded customer project_file has
 * a matching estimate_job_documents row. Surfaces a "Sync document register"
 * action when there's a gap, so a failed/partial registration doesn't sit
 * invisible until someone notices missing documents during takeoff.
 */
function RegisterHealthSummary({
  registerHealth,
  projectId,
  estimateJobId,
}: {
  registerHealth: EstimateDocumentRegisterHealth;
  projectId: string;
  estimateJobId: string;
}) {
  const hasGap = registerHealth.missingCount > 0;
  return (
    <div className={`mt-3 rounded-lg border p-3 ${hasGap ? "border-amber-200 bg-amber-50" : "border-slate-200 bg-slate-50"}`}>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Document register health</p>
      <dl className="mt-2 flex flex-wrap gap-4 text-sm">
        <SummaryStat label="Customer files" value={registerHealth.customerFileCount} tone="text-slate-700" />
        <SummaryStat label="Registered docs" value={registerHealth.registeredCount} tone="text-slate-700" />
        <SummaryStat
          label="Missing registration"
          value={registerHealth.missingCount}
          tone={hasGap ? "text-amber-700" : "text-green-700"}
        />
      </dl>
      {hasGap && (
        <div className="mt-3">
          <p className="text-sm text-amber-800">
            {registerHealth.missingCount} customer file(s) are uploaded but not registered into this job&apos;s
            document register.
          </p>
          <SyncRegisterForm projectId={projectId} estimateJobId={estimateJobId} />
        </div>
      )}
    </div>
  );
}

function SyncRegisterForm({ projectId, estimateJobId }: { projectId: string; estimateJobId: string | null }) {
  return (
    <form action={syncEstimateJobDocumentRegister} className="mt-2">
      <input type="hidden" name="projectId" value={projectId} />
      {estimateJobId && <input type="hidden" name="estimateJobId" value={estimateJobId} />}
      <button className="rounded-full border border-amber-400 bg-white px-4 py-2 text-sm font-semibold text-amber-800 hover:bg-amber-100">
        Sync document register
      </button>
    </form>
  );
}

function DocumentReviewSummary({ documents }: { documents: EstimateJobPanelProps["documents"] }) {
  const counts = {
    accepted: documents.filter((d) => d.review_status === "accepted").length,
    pending: documents.filter((d) => d.review_status === "pending").length,
    needs_replacement: documents.filter((d) => d.review_status === "needs_replacement").length,
    ignored: documents.filter((d) => d.review_status === "ignored").length,
  };
  return (
    <dl className="mt-3 flex flex-wrap gap-4 text-sm">
      <SummaryStat label="Accepted" value={counts.accepted} tone="text-green-700" />
      <SummaryStat label="Pending" value={counts.pending} tone="text-amber-700" />
      <SummaryStat label="Needs replacement" value={counts.needs_replacement} tone="text-red-700" />
      <SummaryStat label="Ignored" value={counts.ignored} tone="text-slate-500" />
    </dl>
  );
}

function SummaryStat({ label, value, tone }: { label: string; value: number | string; tone: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={`mt-0.5 font-semibold ${tone}`}>{value}</dd>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-700">{value}</dd>
    </div>
  );
}

/**
 * Internal-only banner for the result of a guarded EstimateJob action. `notice`
 * is already resolved server-side against the fixed whitelist in
 * lib/estimate-jobs.ts, so this only ever renders one of those known messages
 * — never raw text from the URL.
 */
function EstimateJobNoticeBanner({
  notice,
}: {
  notice: { tone: EstimateJobNoticeTone; message: string } | null;
}) {
  if (!notice) return null;
  const toneClass =
    notice.tone === "success"
      ? "border-green-200 bg-green-50 text-green-800"
      : "border-amber-200 bg-amber-50 text-amber-800";
  return (
    <p className={`mt-4 rounded-lg border px-3 py-2 text-sm ${toneClass}`}>
      {notice.message}
    </p>
  );
}

function ListBlock({ title, items, empty, tone }: { title: string; items: string[]; empty: string; tone: "amber" | "red" }) {
  const color = tone === "amber" ? "text-amber-800 bg-amber-50 border-amber-200" : "text-red-800 bg-red-50 border-red-200";
  return (
    <div>
      <h3 className="text-sm font-bold text-navy">{title}</h3>
      {items.length === 0 ? (
        <p className="mt-1 text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="mt-2 space-y-1">
          {items.map((item) => (
            <li key={item} className={`rounded border px-2 py-1 text-sm ${color}`}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
