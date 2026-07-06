"use client";

import { useState, useTransition } from "react";
import {
  applyAutomationPricingInput,
  applyAutomationQuantityInput,
  getAutomationInputNeeds,
  getAutomationReadiness,
  runAutomationDraftChain,
  type AutomationActionResult,
} from "./actions";

type AutomationV1PanelProps = {
  projectId: string;
  engineProjectId: string | null;
  engineStatus: string | null;
  estimateJobStatus: string | null;
};

type ReadinessSummary = {
  status?: string;
  ready_for_owner_review?: boolean;
  customer_delivery_ready?: boolean;
  summary?: {
    scope_item_count?: number;
    coverage_complete?: boolean;
    open_quantity_requirement_count?: number;
    missing_pricing_input_count?: number;
    open_scope_blocker_count?: number;
    critical_qa_finding_count?: number;
    major_qa_finding_count?: number;
    boe_status?: string;
  };
  blockers?: Array<{ code?: string; count?: number }>;
};

type QuantityRequirement = {
  id: string;
  status?: string;
  trade_code?: string;
  suggested_unit?: string | null;
  suggested_method?: string | null;
  scope_item_id?: string;
};

type ScopeItem = {
  id: string;
  trade_code?: string;
  description?: string;
  review_status?: string;
  blocking_issues?: Array<{ code?: string; message?: string }>;
  trade_data?: {
    pricing_method?: string;
    pricing_ready?: boolean;
  };
};

type InputNeeds = {
  quantityRequirements?: { items?: QuantityRequirement[] };
  scopeItems?: { items?: ScopeItem[] };
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
    label: "Quantity Requirements",
    endpoint: "POST /quantity-requirements/draft",
    purpose: "Create explicit missing-quantity requirements instead of guessing.",
  },
  {
    label: "QA Findings",
    endpoint: "POST /qa/findings/draft",
    purpose: "Surface missing quantities, rates, quotes, allowances, and coverage issues.",
  },
  {
    label: "Estimate Readiness",
    endpoint: "GET /estimate-readiness",
    purpose: "Report blocked vs ready-for-owner-review without customer delivery.",
  },
];

function readinessLabel(engineProjectId: string | null, estimateJobStatus: string | null): string {
  if (!engineProjectId) return "Waiting for engine sync";
  if (estimateJobStatus === "delivered" || estimateJobStatus === "completed") return "Ready for post-delivery revision intake";
  return "Ready for internal automation drafts";
}

function asReadiness(data: unknown): ReadinessSummary | null {
  if (!data || typeof data !== "object") return null;
  return data as ReadinessSummary;
}

function asInputNeeds(data: unknown): InputNeeds | null {
  if (!data || typeof data !== "object") return null;
  return data as InputNeeds;
}

export function AutomationV1Panel({
  projectId,
  engineProjectId,
  engineStatus,
  estimateJobStatus,
}: AutomationV1PanelProps) {
  const readiness = readinessLabel(engineProjectId, estimateJobStatus);
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<AutomationActionResult | null>(null);
  const [inputResult, setInputResult] = useState<AutomationActionResult | null>(null);
  const readinessPacket = asReadiness(result?.data);
  const inputNeeds = asInputNeeds(inputResult?.data);
  const openQuantityRequirements = (inputNeeds?.quantityRequirements?.items ?? []).filter((item) => item.status === "open");
  const pricingNeeds = (inputNeeds?.scopeItems?.items ?? []).filter(
    (item) => item.trade_data?.pricing_method && !item.trade_data?.pricing_ready,
  );

  function onRunDraftChain() {
    setResult(null);
    startTransition(async () => {
      setResult(await runAutomationDraftChain(projectId));
    });
  }

  function onLoadReadiness() {
    setResult(null);
    startTransition(async () => {
      setResult(await getAutomationReadiness(projectId));
    });
  }

  function onLoadInputs() {
    setInputResult(null);
    startTransition(async () => {
      setInputResult(await getAutomationInputNeeds(projectId));
    });
  }

  function onApplyQuantity(requirement: QuantityRequirement) {
    const quantity = window.prompt(`Verified quantity for ${requirement.trade_code ?? "scope"}?`, "10");
    if (!quantity) return;
    const unit = window.prompt("Unit?", requirement.suggested_unit ?? "EA");
    if (!unit) return;
    startTransition(async () => {
      const applied = await applyAutomationQuantityInput(projectId, requirement.id, quantity, unit);
      setResult(applied);
      setInputResult(await getAutomationInputNeeds(projectId));
    });
  }

  function onApplyPricing(item: ScopeItem) {
    const method = item.trade_data?.pricing_method;
    if (!method) return;
    const amount = window.prompt(`Verified ${method} amount for ${item.trade_code ?? "scope"}?`, "100");
    if (!amount) return;
    startTransition(async () => {
      const applied = await applyAutomationPricingInput(projectId, item.id, method, amount);
      setResult(applied);
      setInputResult(await getAutomationInputNeeds(projectId));
    });
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-navy">Automation v1 controls</h2>
          <p className="mt-1 text-sm text-slate-500">
            Staff-only internal controls for the backend estimating chain. These actions do not send customer messages,
            publish pricing, approve work, bill anyone, or deliver final estimates.
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

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onRunDraftChain}
          disabled={pending || !engineProjectId}
          className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
        >
          {pending ? "Working…" : "Run automation draft chain"}
        </button>
        <button
          type="button"
          onClick={onLoadReadiness}
          disabled={pending || !engineProjectId}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          Load readiness
        </button>
        <button
          type="button"
          onClick={onLoadInputs}
          disabled={pending || !engineProjectId}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          Load quantity/pricing inputs
        </button>
      </div>

      {!engineProjectId && (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Send this project to the estimating engine before running automation drafts.
        </p>
      )}

      {result && (
        <div className={`mt-4 rounded-lg px-3 py-2 text-sm ${result.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>
          {result.message}
        </div>
      )}

      {inputResult && !inputResult.ok && (
        <div className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {inputResult.message}
        </div>
      )}

      {inputNeeds && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-slate-200 p-4">
            <h3 className="text-sm font-bold text-navy">Open quantity requirements</h3>
            {openQuantityRequirements.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">No open quantity requirements loaded.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {openQuantityRequirements.map((req) => (
                  <li key={req.id} className="rounded-lg border border-slate-100 p-3 text-sm">
                    <div className="font-semibold text-slate-700">{req.trade_code ?? "unknown trade"}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      Suggested: {req.suggested_unit ?? "EA"} · {req.suggested_method ?? "method pending"}
                    </div>
                    <button
                      type="button"
                      onClick={() => onApplyQuantity(req)}
                      disabled={pending}
                      className="mt-2 rounded-full bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                    >
                      Apply verified quantity
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="rounded-xl border border-slate-200 p-4">
            <h3 className="text-sm font-bold text-navy">Missing pricing basis</h3>
            {pricingNeeds.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">No missing pricing basis items loaded.</p>
            ) : (
              <ul className="mt-3 space-y-2">
                {pricingNeeds.map((item) => (
                  <li key={item.id} className="rounded-lg border border-slate-100 p-3 text-sm">
                    <div className="font-semibold text-slate-700">{item.trade_code ?? "unknown trade"}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {item.description ?? "Generic scope item"} · {item.trade_data?.pricing_method}
                    </div>
                    <button
                      type="button"
                      onClick={() => onApplyPricing(item)}
                      disabled={pending}
                      className="mt-2 rounded-full bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                    >
                      Apply verified pricing basis
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {readinessPacket && (
        <div className="mt-4 rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-bold text-navy">Latest readiness</h3>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${readinessPacket.ready_for_owner_review ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"}`}>
              {readinessPacket.status ?? "unknown"}
            </span>
          </div>
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
            <Metric label="Scope items" value={readinessPacket.summary?.scope_item_count} />
            <Metric label="Open qty reqs" value={readinessPacket.summary?.open_quantity_requirement_count} />
            <Metric label="Missing pricing" value={readinessPacket.summary?.missing_pricing_input_count} />
            <Metric label="Scope blockers" value={readinessPacket.summary?.open_scope_blocker_count} />
            <Metric label="Critical QA" value={readinessPacket.summary?.critical_qa_finding_count} />
            <Metric label="BOE" value={readinessPacket.summary?.boe_status ?? "—"} />
          </dl>
          {readinessPacket.blockers && readinessPacket.blockers.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
              {readinessPacket.blockers.map((blocker, index) => (
                <li key={`${blocker.code ?? "blocker"}-${index}`}>
                  {blocker.code ?? "blocker"}: {blocker.count ?? 0}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-slate-400">
            Customer delivery remains locked even when owner-review readiness is true.
          </p>
        </div>
      )}

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

function Metric({ label, value }: { label: string; value: string | number | boolean | undefined }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-700">{value === undefined ? "—" : String(value)}</dd>
    </div>
  );
}
