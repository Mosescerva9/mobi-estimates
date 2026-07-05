import {
  DOCUMENT_REVIEW_STATUSES,
  ESTIMATE_JOB_STATUSES,
  estimateJobBadgeClass,
  estimateJobStatusLabel,
} from "@/lib/estimate-jobs";
import {
  changeEstimateJobStatus,
  completeDocumentReview,
  completeTakeoff,
  regenerateIntakeReview,
  startTakeoff,
  updateDocumentReviewStatus,
} from "./actions";

type IntakeReview = {
  completeness?: Record<string, boolean>;
  missing_or_unclear?: string[];
  risk_flags?: string[];
  recommended_next_status?: string;
  internal_notes?: string[];
  reviewed_at?: string;
};

interface EstimateJobPanelProps {
  projectId: string;
  job: {
    id: string;
    status: string;
    priority: string;
    blocked_reason: string | null;
    intake_review: IntakeReview | null;
    target_delivery_at: string | null;
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
  }>;
  events: Array<{
    id: string;
    event_type: string;
    summary: string;
    actor_type: string;
    created_at: string;
  }>;
}

function fmtDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function labelize(key: string): string {
  return key.replace(/^has_/, "").replace(/_/g, " ");
}

export function EstimateJobPanel({ projectId, job, documents, events }: EstimateJobPanelProps) {
  if (!job) {
    return (
      <section className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
        <h2 className="text-base font-bold text-navy">Estimate job</h2>
        <p className="mt-2 text-sm text-amber-800">
          No internal EstimateJob was found. Regenerate intake review after the database migration is applied.
        </p>
      </section>
    );
  }

  const review = (job.intake_review ?? {}) as IntakeReview;
  const completeness = Object.entries(review.completeness ?? {});
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
        </form>
      </div>

      <div className="mt-6">
        <h3 className="text-sm font-bold text-navy">Document register</h3>
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
              </form>
            )}
          </>
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

      <div className="mt-6">
        <h3 className="text-sm font-bold text-navy">Internal evidence timeline</h3>
        {events.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">No internal events logged yet.</p>
        ) : (
          <ol className="mt-3 space-y-3">
            {events.map((event) => (
              <li key={event.id} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
                <div className="font-semibold text-navy">{event.summary}</div>
                <div className="text-xs text-slate-400">
                  {event.event_type} · {event.actor_type} · {fmtDateTime(event.created_at)}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
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

function SummaryStat({ label, value, tone }: { label: string; value: number; tone: string }) {
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
