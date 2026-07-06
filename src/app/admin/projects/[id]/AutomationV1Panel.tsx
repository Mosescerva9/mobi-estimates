"use client";

import { useState, useTransition } from "react";
import {
  applyAutomationPricingInput,
  applyAutomationQuantityInput,
  decideAutomationCustomerRevision,
  getAutomationCustomerRevisions,
  getAutomationInputNeeds,
  getAutomationReadiness,
  getOwnerReviewPackage,
  parseAutomationCustomerRevision,
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

type PricingNeed = {
  id?: string;
  scope_item_id?: string;
  trade_code?: string;
  description?: string;
  pricing_method?: string;
};

type InputNeeds = {
  quantityRequirements?: { items?: QuantityRequirement[] };
  scopeItems?: { items?: ScopeItem[] };
  pricingNeeds?: PricingNeed[];
};

type OwnerReviewPackage = {
  status?: string;
  ready_for_owner_review?: boolean;
  customer_delivery_ready?: boolean;
  executive_summary?: {
    scope_item_count?: number;
    open_quantity_requirement_count?: number;
    missing_pricing_input_count?: number;
    critical_qa_finding_count?: number;
    boe_status?: string;
  };
  blockers?: Array<{ code?: string; count?: number }>;
};

type CustomerRevisionRequest = {
  id: string;
  action?: string;
  trade_code?: string | null;
  status?: string;
  summary?: string;
  confidence?: number;
  payload?: {
    sheet_refs?: string[];
    review_decision?: {
      decision?: string;
      follow_up_task?: string;
      notes?: string | null;
    };
  };
};

type CustomerRevisionPacket = {
  items?: CustomerRevisionRequest[];
  total?: number;
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

function asOwnerReviewPackage(data: unknown): OwnerReviewPackage | null {
  if (!data || typeof data !== "object") return null;
  return data as OwnerReviewPackage;
}

function asCustomerRevisionPacket(data: unknown): CustomerRevisionPacket | null {
  if (!data || typeof data !== "object") return null;
  const packet = data as CustomerRevisionPacket;
  const items = Array.isArray(packet.items)
    ? packet.items
        .filter((item): item is CustomerRevisionRequest => Boolean(item) && typeof item === "object")
        .map((item) => ({
          ...item,
          payload: item.payload
            ? {
                ...item.payload,
                sheet_refs: Array.isArray(item.payload.sheet_refs) ? item.payload.sheet_refs : [],
                review_decision:
                  item.payload.review_decision && typeof item.payload.review_decision === "object"
                    ? item.payload.review_decision
                    : undefined,
              }
            : undefined,
        }))
    : [];
  return { ...packet, items };
}

function scopeItemsToPricingNeeds(items: ScopeItem[] | undefined): PricingNeed[] {
  return (items ?? [])
    .filter((item) => item.trade_data?.pricing_method && !item.trade_data?.pricing_ready)
    .map((item) => ({
      id: item.id,
      scope_item_id: item.id,
      trade_code: item.trade_code,
      description: item.description,
      pricing_method: item.trade_data?.pricing_method,
    }));
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
  const [ownerReviewResult, setOwnerReviewResult] = useState<AutomationActionResult | null>(null);
  const [revisionResult, setRevisionResult] = useState<AutomationActionResult | null>(null);
  const [revisionPacket, setRevisionPacket] = useState<CustomerRevisionPacket | null>(null);
  const [revisionText, setRevisionText] = useState("");
  const readinessPacket = asReadiness(result?.data);
  const inputNeeds = asInputNeeds(inputResult?.data);
  const ownerReviewPackage = asOwnerReviewPackage(ownerReviewResult?.data);
  const openQuantityRequirements = (inputNeeds?.quantityRequirements?.items ?? []).filter((item) => item.status === "open");
  const pricingNeeds = Array.isArray(inputNeeds?.pricingNeeds)
    ? inputNeeds.pricingNeeds
    : scopeItemsToPricingNeeds(inputNeeds?.scopeItems?.items);

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

  function onLoadOwnerReview() {
    setOwnerReviewResult(null);
    startTransition(async () => {
      setOwnerReviewResult(await getOwnerReviewPackage(projectId));
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

  function onApplyPricing(item: PricingNeed) {
    const method = item.pricing_method;
    const scopeItemId = item.scope_item_id ?? item.id;
    if (!method || !scopeItemId) return;
    const amount = window.prompt(`Verified ${method} amount for ${item.trade_code ?? "scope"}?`, "100");
    if (!amount) return;
    startTransition(async () => {
      const applied = await applyAutomationPricingInput(projectId, scopeItemId, method, amount);
      setResult(applied);
      setInputResult(await getAutomationInputNeeds(projectId));
    });
  }

  async function reloadRevisions(): Promise<AutomationActionResult> {
    const res = await getAutomationCustomerRevisions(projectId);
    if (res.ok) setRevisionPacket(asCustomerRevisionPacket(res.data));
    return res;
  }

  function onLoadRevisions() {
    startTransition(async () => {
      setRevisionResult(await reloadRevisions());
    });
  }

  function onParseRevisions() {
    if (!revisionText.trim()) {
      setRevisionResult({ ok: false, message: "Paste customer revision text before parsing." });
      return;
    }
    startTransition(async () => {
      const parsed = await parseAutomationCustomerRevision(projectId, revisionText);
      // On success, reload the list so newly parsed requests appear immediately.
      if (parsed.ok) {
        setRevisionText("");
        await reloadRevisions();
      }
      setRevisionResult(parsed);
    });
  }

  function onDecideRevision(
    request: CustomerRevisionRequest,
    decision: "accepted" | "rejected" | "needs_clarification",
  ) {
    const note = window.prompt(
      decision === "needs_clarification"
        ? "Internal clarification note (what needs clarifying):"
        : `Internal note for "${decision}" (optional):`,
      "",
    );
    if (note === null) return; // cancelled — do not record a decision
    startTransition(async () => {
      const decided = await decideAutomationCustomerRevision(
        projectId,
        request.id,
        decision,
        note.trim() || undefined,
      );
      // Reload after every response so stale/double-decision states self-heal
      // while the error message still surfaces below.
      await reloadRevisions();
      setRevisionResult(decided);
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
        <button
          type="button"
          onClick={onLoadOwnerReview}
          disabled={pending || !engineProjectId}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          Load owner-review package
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
                  <li key={item.scope_item_id ?? item.id} className="rounded-lg border border-slate-100 p-3 text-sm">
                    <div className="font-semibold text-slate-700">{item.trade_code ?? "unknown trade"}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {item.description ?? "Generic scope item"} · {item.pricing_method ?? "pricing input"}
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

      {ownerReviewResult && !ownerReviewResult.ok && (
        <div className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          {ownerReviewResult.message}
        </div>
      )}

      {ownerReviewPackage && (
        <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-bold text-navy">Owner-review package</h3>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${ownerReviewPackage.ready_for_owner_review ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
              {ownerReviewPackage.status ?? "unknown"}
            </span>
          </div>
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
            <Metric label="Scope items" value={ownerReviewPackage.executive_summary?.scope_item_count} />
            <Metric label="Open qty reqs" value={ownerReviewPackage.executive_summary?.open_quantity_requirement_count} />
            <Metric label="Missing pricing" value={ownerReviewPackage.executive_summary?.missing_pricing_input_count} />
            <Metric label="Critical QA" value={ownerReviewPackage.executive_summary?.critical_qa_finding_count} />
            <Metric label="BOE" value={ownerReviewPackage.executive_summary?.boe_status ?? "—"} />
            <Metric label="Customer delivery" value={ownerReviewPackage.customer_delivery_ready ? "ready" : "locked"} />
          </dl>
          {ownerReviewPackage.blockers && ownerReviewPackage.blockers.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
              {ownerReviewPackage.blockers.map((blocker, index) => (
                <li key={`${blocker.code ?? "blocker"}-${index}`}>
                  {blocker.code ?? "blocker"}: {blocker.count ?? 0}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs text-slate-500">
            This is an internal owner-review packet only. It cannot approve, send, bill, publish, or deliver a final customer estimate.
          </p>
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

      <div className="mt-6 rounded-xl border border-slate-200 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold text-navy">Customer revision review</h3>
            <p className="mt-1 text-xs text-slate-500">
              Paste customer revision text to parse it into internal revision requests, then decide each one.
            </p>
          </div>
          <button
            type="button"
            onClick={onLoadRevisions}
            disabled={pending || !engineProjectId}
            className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            Refresh requests
          </button>
        </div>

        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Internal only. Parsing and deciding here never sends a customer message, never generates a revised
          estimate, and never unlocks a final estimate or customer delivery.
        </p>

        <div className="mt-3">
          <textarea
            value={revisionText}
            onChange={(event) => setRevisionText(event.target.value)}
            rows={4}
            disabled={pending || !engineProjectId}
            placeholder="Paste the customer's revision request text here…"
            className="w-full rounded-lg border border-slate-300 p-3 text-sm text-slate-700 disabled:opacity-60"
          />
          <div className="mt-2 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onParseRevisions}
              disabled={pending || !engineProjectId || !revisionText.trim()}
              className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
            >
              {pending ? "Working…" : "Parse into internal requests"}
            </button>
          </div>
        </div>

        {revisionResult && (
          <div
            className={`mt-3 rounded-lg px-3 py-2 text-sm ${
              revisionResult.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"
            }`}
          >
            {revisionResult.message}
          </div>
        )}

        {revisionPacket && (
          <div className="mt-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Parsed revision requests ({revisionPacket.items?.length ?? revisionPacket.total ?? 0})
            </div>
            {(revisionPacket.items ?? []).length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">No revision requests yet. Paste text above and parse.</p>
            ) : (
              <ul className="mt-3 space-y-3">
                {(revisionPacket.items ?? []).map((req) => {
                  const decision = req.payload?.review_decision;
                  const open = isRevisionOpen(req);
                  return (
                    <li key={req.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="font-semibold text-slate-700">
                          {req.action ?? "revision"} · {req.trade_code ?? "no trade"}
                        </div>
                        <div className="flex items-center gap-2">
                          {typeof req.confidence === "number" && (
                            <span className="text-xs text-slate-400">confidence {req.confidence}</span>
                          )}
                          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusTone(req.status)}`}>
                            {req.status ?? "open"}
                          </span>
                        </div>
                      </div>
                      {req.summary && <p className="mt-1 text-slate-600">{req.summary}</p>}
                      {req.payload?.sheet_refs && req.payload.sheet_refs.length > 0 && (
                        <div className="mt-1 text-xs text-slate-500">Sheets: {req.payload.sheet_refs.join(", ")}</div>
                      )}
                      {decision?.decision && (
                        <div className="mt-2 rounded-lg bg-slate-50 px-2 py-1.5 text-xs text-slate-600">
                          Decision: <span className="font-semibold">{decision.decision}</span>
                          {decision.follow_up_task && <> · follow-up: {decision.follow_up_task}</>}
                          {decision.notes && <> · {decision.notes}</>}
                        </div>
                      )}
                      {open && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => onDecideRevision(req, "accepted")}
                            disabled={pending}
                            className="rounded-full bg-green-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                          >
                            Accept
                          </button>
                          <button
                            type="button"
                            onClick={() => onDecideRevision(req, "rejected")}
                            disabled={pending}
                            className="rounded-full bg-red-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                          >
                            Reject
                          </button>
                          <button
                            type="button"
                            onClick={() => onDecideRevision(req, "needs_clarification")}
                            disabled={pending}
                            className="rounded-full bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                          >
                            Needs clarification
                          </button>
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>

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

/** A request is still open for a decision until a review_decision is recorded. */
function isRevisionOpen(req: CustomerRevisionRequest): boolean {
  if (req.payload?.review_decision?.decision) return false;
  return !["accepted", "accepted_for_rescope", "rejected", "needs_clarification", "needs_customer_clarification"].includes(
    req.status ?? "open",
  );
}

function statusTone(status: string | undefined): string {
  switch (status) {
    case "accepted":
    case "accepted_for_rescope":
      return "bg-green-100 text-green-700";
    case "rejected":
      return "bg-red-100 text-red-700";
    case "needs_clarification":
    case "needs_customer_clarification":
      return "bg-amber-100 text-amber-700";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

function Metric({ label, value }: { label: string; value: string | number | boolean | undefined }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-700">{value === undefined ? "—" : String(value)}</dd>
    </div>
  );
}
