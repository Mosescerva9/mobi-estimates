"use client";

import { useState, useTransition } from "react";
import {
  applyAutomationPricingInput,
  applyAutomationQuantityInput,
  decideAutomationCustomerRevision,
  getAutomationCustomerRevisions,
  getAutomationInputNeeds,
  getAutomationReadiness,
  getAutomationRevisionRescopeVersions,
  getOwnerReviewPackage,
  parseAutomationCustomerRevision,
  resolveAutomationRevisionRescope,
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

type RevisionRescopeSnapshot = {
  customer_revision_request?: {
    status?: string;
    updated_at?: string;
  };
  scope_item?: {
    id?: string;
    review_status?: string;
    conflict_status?: string;
    blocking_issues?: unknown[];
    updated_at?: string;
  };
};

type CustomerRevisionRescopeVersion = {
  id: string;
  version_number?: number;
  status?: string;
  actor?: string | null;
  notes?: string | null;
  created_at?: string;
  blocker_scope_item_id?: string;
  changed_items?: Array<{
    scope_item_id?: string;
    change_type?: string;
    previous_review_status?: string | null;
    new_review_status?: string | null;
    removed_blocker_codes?: string[];
  }>;
  before_snapshot?: RevisionRescopeSnapshot;
  after_snapshot?: RevisionRescopeSnapshot;
  readiness_snapshot?: {
    status?: string;
    open_scope_blocker_count?: number;
    customer_delivery_ready?: boolean;
  };
};

type CustomerRevisionRescopeVersionPacket = {
  items?: CustomerRevisionRescopeVersion[];
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

function asCustomerRevisionRescopeVersionPacket(data: unknown): CustomerRevisionRescopeVersionPacket | null {
  if (!data || typeof data !== "object") return null;
  const packet = data as CustomerRevisionRescopeVersionPacket;
  const items = Array.isArray(packet.items)
    ? packet.items.filter((item): item is CustomerRevisionRescopeVersion => Boolean(item) && typeof item === "object")
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
  const [revisionVersionPackets, setRevisionVersionPackets] = useState<Record<string, CustomerRevisionRescopeVersionPacket>>({});
  const [revisionText, setRevisionText] = useState("");
  const [revisionStatusFilter, setRevisionStatusFilter] = useState("all");
  const [revisionTradeFilter, setRevisionTradeFilter] = useState("all");
  const [revisionActionFilter, setRevisionActionFilter] = useState("all");
  const [revisionSearch, setRevisionSearch] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const busy = pending || actionBusy;
  const readinessPacket = asReadiness(result?.data);
  const inputNeeds = asInputNeeds(inputResult?.data);
  const ownerReviewPackage = asOwnerReviewPackage(ownerReviewResult?.data);
  const openQuantityRequirements = (inputNeeds?.quantityRequirements?.items ?? []).filter((item) => item.status === "open");
  const pricingNeeds = Array.isArray(inputNeeds?.pricingNeeds)
    ? inputNeeds.pricingNeeds
    : scopeItemsToPricingNeeds(inputNeeds?.scopeItems?.items);
  const revisions = revisionPacket?.items ?? [];
  const revisionSummary = summarizeRevisions(revisions);
  const revisionTrades = uniqueRevisionValues(revisions.map((req) => req.trade_code));
  const revisionActions = uniqueRevisionValues(revisions.map((req) => req.action));
  const filteredRevisions = filterRevisions(revisions, {
    status: revisionStatusFilter,
    trade: revisionTradeFilter,
    action: revisionActionFilter,
    search: revisionSearch,
  });

  function runLocked(action: () => Promise<void>) {
    if (actionBusy) return;
    setActionBusy(true);
    startTransition(() => {
      void action().finally(() => setActionBusy(false));
    });
  }

  function onRunDraftChain() {
    setResult(null);
    runLocked(async () => {
      setResult(await runAutomationDraftChain(projectId));
    });
  }

  function onLoadReadiness() {
    setResult(null);
    runLocked(async () => {
      setResult(await getAutomationReadiness(projectId));
    });
  }

  function onLoadInputs() {
    setInputResult(null);
    runLocked(async () => {
      setInputResult(await getAutomationInputNeeds(projectId));
    });
  }

  function onLoadOwnerReview() {
    setOwnerReviewResult(null);
    runLocked(async () => {
      setOwnerReviewResult(await getOwnerReviewPackage(projectId));
    });
  }

  function onApplyQuantity(requirement: QuantityRequirement) {
    const quantity = window.prompt(`Verified quantity for ${requirement.trade_code ?? "scope"}?`, "10");
    if (!quantity) return;
    const unit = window.prompt("Unit?", requirement.suggested_unit ?? "EA");
    if (!unit) return;
    runLocked(async () => {
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
    runLocked(async () => {
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
    runLocked(async () => {
      setRevisionResult(await reloadRevisions());
    });
  }

  function onParseRevisions() {
    if (!revisionText.trim()) {
      setRevisionResult({ ok: false, message: "Paste customer revision text before parsing." });
      return;
    }
    runLocked(async () => {
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
    runLocked(async () => {
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

  async function reloadRevisionVersions(requestId: string): Promise<AutomationActionResult> {
    const res = await getAutomationRevisionRescopeVersions(projectId, requestId);
    const packet = asCustomerRevisionRescopeVersionPacket(res.data);
    if (res.ok && packet) {
      setRevisionVersionPackets((current) => ({ ...current, [requestId]: packet }));
    }
    return res;
  }

  function onLoadRevisionVersions(request: CustomerRevisionRequest) {
    runLocked(async () => {
      setRevisionResult(await reloadRevisionVersions(request.id));
    });
  }

  function onResolveRevisionRescope(request: CustomerRevisionRequest) {
    const note = window.prompt(
      "Internal note for resolving this rescope blocker. Do not use this to approve or deliver a final estimate.",
      "",
    );
    if (note === null) return;
    runLocked(async () => {
      const resolved = await resolveAutomationRevisionRescope(projectId, request.id, note.trim() || undefined);
      await reloadRevisions();
      await reloadRevisionVersions(request.id);
      setResult(await getAutomationReadiness(projectId));
      setRevisionResult(resolved);
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
          disabled={busy || !engineProjectId}
          className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
        >
          {busy ? "Working…" : "Run automation draft chain"}
        </button>
        <button
          type="button"
          onClick={onLoadReadiness}
          disabled={busy || !engineProjectId}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          Load readiness
        </button>
        <button
          type="button"
          onClick={onLoadInputs}
          disabled={busy || !engineProjectId}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          Load quantity/pricing inputs
        </button>
        <button
          type="button"
          onClick={onLoadOwnerReview}
          disabled={busy || !engineProjectId}
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
                      disabled={busy}
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
                      disabled={busy}
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
            disabled={busy || !engineProjectId}
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
            disabled={busy || !engineProjectId}
            placeholder="Paste the customer's revision request text here…"
            className="w-full rounded-lg border border-slate-300 p-3 text-sm text-slate-700 disabled:opacity-60"
          />
          <div className="mt-2 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onParseRevisions}
              disabled={busy || !engineProjectId || !revisionText.trim()}
              className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
            >
              {busy ? "Working…" : "Parse into internal requests"}
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
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Parsed revision requests ({revisions.length} of {revisionPacket.total ?? revisions.length})
              </div>
              <div className="text-xs text-slate-500">
                Showing {filteredRevisions.length} after filters
              </div>
            </div>
            <RevisionWorkflowSummary summary={revisionSummary} />
            {revisions.length > 0 && (
              <div className="mt-3 grid gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 sm:grid-cols-2 lg:grid-cols-4">
                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Status
                  <select
                    value={revisionStatusFilter}
                    onChange={(event) => setRevisionStatusFilter(event.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal normal-case tracking-normal text-slate-700"
                  >
                    <option value="all">All statuses</option>
                    <option value="open">Needs decision</option>
                    <option value="accepted">Accepted</option>
                    <option value="accepted_for_rescope">Scope update needed</option>
                    <option value="rescope_resolved">Scope update resolved</option>
                    <option value="needs_customer_clarification">Needs customer clarification</option>
                    <option value="rejected">Rejected</option>
                  </select>
                </label>
                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Trade
                  <select
                    value={revisionTradeFilter}
                    onChange={(event) => setRevisionTradeFilter(event.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal normal-case tracking-normal text-slate-700"
                  >
                    <option value="all">All trades</option>
                    {revisionTrades.map((trade) => (
                      <option key={trade} value={trade}>{trade}</option>
                    ))}
                  </select>
                </label>
                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Action
                  <select
                    value={revisionActionFilter}
                    onChange={(event) => setRevisionActionFilter(event.target.value)}
                    className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal normal-case tracking-normal text-slate-700"
                  >
                    <option value="all">All actions</option>
                    {revisionActions.map((action) => (
                      <option key={action} value={action}>{action}</option>
                    ))}
                  </select>
                </label>
                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Search
                  <input
                    type="search"
                    value={revisionSearch}
                    onChange={(event) => setRevisionSearch(event.target.value)}
                    placeholder="Summary, sheet, trade…"
                    className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal normal-case tracking-normal text-slate-700"
                  />
                </label>
              </div>
            )}
            {revisions.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">No revision requests yet. Paste text above and parse.</p>
            ) : filteredRevisions.length === 0 ? (
              <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-500">
                No revision requests match the current filters.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {filteredRevisions.map((req) => {
                  const decision = req.payload?.review_decision;
                  const open = isRevisionOpen(req);
                  const nextAction = nextRevisionStaffAction(req);
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
                            {req.status ?? "unknown"}
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
                      <div className="mt-2 rounded-lg border border-blue-100 bg-blue-50 px-2 py-1.5 text-xs text-blue-800">
                        Next staff action: <span className="font-semibold">{nextAction}</span>
                      </div>
                      {open && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => onDecideRevision(req, "accepted")}
                            disabled={busy}
                            className="rounded-full bg-green-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                          >
                            Accept
                          </button>
                          <button
                            type="button"
                            onClick={() => onDecideRevision(req, "rejected")}
                            disabled={busy}
                            className="rounded-full bg-red-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                          >
                            Reject
                          </button>
                          <button
                            type="button"
                            onClick={() => onDecideRevision(req, "needs_clarification")}
                            disabled={busy}
                            className="rounded-full bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                          >
                            Needs clarification
                          </button>
                        </div>
                      )}
                      {isRevisionAcceptedForRescope(req) && (
                        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                              <div className="text-xs font-semibold uppercase tracking-wide text-amber-900">
                                Rescope / version history
                              </div>
                              <p className="mt-1 text-xs text-amber-800">
                                Internal only. Resolving records a durable version snapshot and reruns readiness; it does not approve,
                                send, publish, bill, or deliver a revised estimate.
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => onLoadRevisionVersions(req)}
                                disabled={busy}
                                className="rounded-full border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-800 disabled:opacity-60"
                              >
                                Load history
                              </button>
                              {req.status === "accepted_for_rescope" && (
                                <button
                                  type="button"
                                  onClick={() => onResolveRevisionRescope(req)}
                                  disabled={busy}
                                  className="rounded-full bg-amber-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                                >
                                  Resolve rescope blocker
                                </button>
                              )}
                            </div>
                          </div>
                          <RevisionVersionHistory packet={revisionVersionPackets[req.id]} />
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

type RevisionWorkflowSummary = {
  total: number;
  needsDecision: number;
  accepted: number;
  scopeUpdateNeeded: number;
  scopeUpdateResolved: number;
  needsCustomerClarification: number;
  rejected: number;
};

function uniqueRevisionValues(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.map((value) => value?.trim()).filter((value): value is string => Boolean(value)))).sort();
}

function summarizeRevisions(items: CustomerRevisionRequest[]): RevisionWorkflowSummary {
  return items.reduce<RevisionWorkflowSummary>(
    (summary, item) => {
      summary.total += 1;
      if (isRevisionOpen(item)) summary.needsDecision += 1;
      if (item.status === "accepted") summary.accepted += 1;
      if (item.status === "accepted_for_rescope") summary.scopeUpdateNeeded += 1;
      if (item.status === "rescope_resolved") summary.scopeUpdateResolved += 1;
      if (item.status === "needs_customer_clarification" || item.status === "needs_clarification") {
        summary.needsCustomerClarification += 1;
      }
      if (item.status === "rejected") summary.rejected += 1;
      return summary;
    },
    {
      total: 0,
      needsDecision: 0,
      accepted: 0,
      scopeUpdateNeeded: 0,
      scopeUpdateResolved: 0,
      needsCustomerClarification: 0,
      rejected: 0,
    },
  );
}

function revisionMatchesStatus(req: CustomerRevisionRequest, status: string): boolean {
  if (status === "all") return true;
  if (status === "open") return isRevisionOpen(req);
  if (status === "needs_customer_clarification") {
    return req.status === "needs_customer_clarification" || req.status === "needs_clarification";
  }
  return req.status === status;
}

function filterRevisions(
  items: CustomerRevisionRequest[],
  filters: { status: string; trade: string; action: string; search: string },
): CustomerRevisionRequest[] {
  const query = filters.search.trim().toLowerCase();
  return items.filter((item) => {
    if (!revisionMatchesStatus(item, filters.status)) return false;
    if (filters.trade !== "all" && item.trade_code !== filters.trade) return false;
    if (filters.action !== "all" && item.action !== filters.action) return false;
    if (!query) return true;
    const haystack = [
      item.summary,
      item.trade_code,
      item.action,
      item.status,
      ...(item.payload?.sheet_refs ?? []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
}

function RevisionWorkflowSummary({ summary }: { summary: RevisionWorkflowSummary }) {
  return (
    <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-3 lg:grid-cols-7">
      <Metric label="Total" value={summary.total} />
      <Metric label="Needs decision" value={summary.needsDecision} />
      <Metric label="Accepted" value={summary.accepted} />
      <Metric label="Scope updates" value={summary.scopeUpdateNeeded} />
      <Metric label="Resolved" value={summary.scopeUpdateResolved} />
      <Metric label="Clarification" value={summary.needsCustomerClarification} />
      <Metric label="Rejected" value={summary.rejected} />
    </dl>
  );
}

function nextRevisionStaffAction(req: CustomerRevisionRequest): string {
  if (req.status === "accepted") return "Confirm whether a scope update is needed before owner review.";
  if (req.status === "accepted_for_rescope") return "Resolve the internal rescope blocker after scope updates are applied.";
  if (req.status === "rescope_resolved") return "Review the version snapshot and reload readiness before owner review.";
  if (req.status === "needs_customer_clarification" || req.status === "needs_clarification") {
    return "Collect the missing clarification through the normal customer communication lane.";
  }
  if (req.status === "rejected") return "No revision work is needed unless new customer information arrives.";
  if (isRevisionOpen(req)) return "Decide whether to accept, reject, or request clarification.";
  return "Review this request status and choose the next internal step.";
}

/** A request is still open for a decision only when the engine marks it open and no review_decision is recorded. */
function isRevisionOpen(req: CustomerRevisionRequest): boolean {
  if (req.payload?.review_decision?.decision) return false;
  return req.status === "open" || req.status === "received";
}

function isRevisionAcceptedForRescope(req: CustomerRevisionRequest): boolean {
  return req.status === "accepted_for_rescope" || req.status === "rescope_resolved";
}

function formatVersionDate(value: string | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function RevisionVersionHistory({ packet }: { packet: CustomerRevisionRescopeVersionPacket | undefined }) {
  if (!packet) {
    return <p className="mt-3 text-xs text-amber-800">Load history to view durable rescope/version snapshots.</p>;
  }
  const items = packet.items ?? [];
  if (items.length === 0) {
    return <p className="mt-3 text-xs text-amber-800">No rescope version snapshots recorded yet.</p>;
  }
  return (
    <ol className="mt-3 space-y-2">
      {items.map((version) => (
        <li key={version.id} className="rounded-lg border border-amber-200 bg-white p-3 text-xs text-slate-700">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="font-semibold text-slate-800">
              Version {version.version_number ?? "—"} · {version.status ?? "unknown"}
            </div>
            <div className="text-slate-500">{formatVersionDate(version.created_at)}</div>
          </div>
          <dl className="mt-2 grid gap-2 sm:grid-cols-3">
            <Metric label="Actor" value={version.actor ?? "—"} />
            <Metric label="Readiness" value={version.readiness_snapshot?.status ?? "—"} />
            <Metric label="Open blockers" value={version.readiness_snapshot?.open_scope_blocker_count} />
          </dl>
          <SnapshotDelta before={version.before_snapshot} after={version.after_snapshot} />
          {version.notes && <p className="mt-2 whitespace-pre-wrap text-slate-600">Notes: {version.notes}</p>}
          {(version.changed_items ?? []).length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-600">
              {(version.changed_items ?? []).map((item, index) => (
                <li key={`${version.id}-${item.scope_item_id ?? index}`}>
                  {item.change_type ?? "change"}: {item.previous_review_status ?? "—"} → {item.new_review_status ?? "—"}
                  {item.removed_blocker_codes?.length ? ` · removed ${item.removed_blocker_codes.join(", ")}` : ""}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[11px] text-slate-400">
            Snapshot only — customer delivery remains {version.readiness_snapshot?.customer_delivery_ready ? "unexpectedly ready" : "locked"}.
          </p>
        </li>
      ))}
    </ol>
  );
}

function SnapshotDelta({
  before,
  after,
}: {
  before: RevisionRescopeSnapshot | undefined;
  after: RevisionRescopeSnapshot | undefined;
}) {
  if (!before && !after) return null;
  const beforeBlockers = before?.scope_item?.blocking_issues?.length ?? 0;
  const afterBlockers = after?.scope_item?.blocking_issues?.length ?? 0;
  return (
    <div className="mt-2 rounded-md border border-slate-100 bg-slate-50 p-2">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Durable before / after snapshot</div>
      <dl className="mt-2 grid gap-2 sm:grid-cols-2">
        <Metric label="Request status" value={`${before?.customer_revision_request?.status ?? "—"} → ${after?.customer_revision_request?.status ?? "—"}`} />
        <Metric label="Scope review" value={`${before?.scope_item?.review_status ?? "—"} → ${after?.scope_item?.review_status ?? "—"}`} />
        <Metric label="Conflict status" value={`${before?.scope_item?.conflict_status ?? "—"} → ${after?.scope_item?.conflict_status ?? "—"}`} />
        <Metric label="Blocker count" value={`${beforeBlockers} → ${afterBlockers}`} />
      </dl>
      {after?.scope_item?.id && <p className="mt-1 break-all text-[11px] text-slate-400">Scope item: {after.scope_item.id}</p>}
    </div>
  );
}

function statusTone(status: string | undefined): string {
  switch (status) {
    case "accepted":
    case "accepted_for_rescope":
      return "bg-green-100 text-green-700";
    case "rescope_resolved":
      return "bg-blue-100 text-blue-700";
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
