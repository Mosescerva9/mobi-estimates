type AutomationV1PanelProps = {
  engineProjectId: string | null;
  engineStatus: string | null;
  estimateJobStatus: string | null;
};

const ARTIFACTS = [
  {
    label: "Trade Coverage Matrix",
    endpoint: "POST /coverage/draft",
    purpose: "Detect trades from processed sheets and seed coverage rows.",
  },
  {
    label: "Generic Scope Candidates",
    endpoint: "POST /coverage/generic-scope/draft",
    purpose: "Create blocked internal generic scope items per detected trade.",
  },
  {
    label: "Pricing Prep",
    endpoint: "POST /pricing/generic-methods/draft",
    purpose: "Assign safe pricing methods without creating prices.",
  },
  {
    label: "QA Findings",
    endpoint: "POST /qa/findings/draft",
    purpose: "Surface missing quantities, rates, quotes, allowances, and coverage issues.",
  },
  {
    label: "BOE Draft",
    endpoint: "GET /boe/draft",
    purpose: "Summarize documents, coverage, scope, QA, assumptions, and open questions.",
  },
  {
    label: "Customer Revisions",
    endpoint: "POST /customer-revisions/parse",
    purpose: "Convert free-text customer revision feedback into internal request rows.",
  },
];

function readinessLabel(engineProjectId: string | null, estimateJobStatus: string | null): string {
  if (!engineProjectId) return "Waiting for engine sync";
  if (estimateJobStatus === "delivered" || estimateJobStatus === "completed") return "Ready for post-delivery revision intake";
  return "Ready for internal automation drafts";
}

export function AutomationV1Panel({
  engineProjectId,
  engineStatus,
  estimateJobStatus,
}: AutomationV1PanelProps) {
  const readiness = readinessLabel(engineProjectId, estimateJobStatus);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-navy">Automation v1 visibility</h2>
          <p className="mt-1 text-sm text-slate-500">
            Read-only map of the new backend automation artifacts. These controls are intentionally
            internal: they do not send customer messages, publish pricing, or deliver final estimates.
          </p>
        </div>
        <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
          {readiness}
        </span>
      </div>

      <dl className="mt-4 grid gap-x-6 gap-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Engine project</dt>
          <dd className="mt-0.5 break-all font-mono text-xs text-slate-600">{engineProjectId ?? "Not synced"}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Engine status</dt>
          <dd className="mt-0.5 text-slate-700">{engineStatus ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Estimate job</dt>
          <dd className="mt-0.5 text-slate-700">{estimateJobStatus ?? "—"}</dd>
        </div>
      </dl>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {ARTIFACTS.map((artifact) => (
          <div key={artifact.label} className="rounded-xl border border-slate-200 p-4">
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-sm font-bold text-navy">{artifact.label}</h3>
              <code className="rounded bg-slate-100 px-2 py-1 text-[11px] text-slate-600">
                {artifact.endpoint}
              </code>
            </div>
            <p className="mt-2 text-sm text-slate-500">{artifact.purpose}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
