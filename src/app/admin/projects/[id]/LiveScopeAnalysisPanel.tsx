"use client";

import { useState, useTransition } from "react";
import {
  LIVE_SCOPE_COPY,
  type EnabledTrade,
  type LiveExtractionRunSummary,
  type LiveReadinessPacket,
} from "@/lib/live-scope-extraction";
import {
  getLiveScopeExtractionReadiness,
  startLiveScopeExtraction,
  type AutomationActionResult,
} from "./actions";

type LiveScopeAnalysisPanelProps = {
  projectId: string;
  engineProjectId: string | null;
};

function asReadiness(data: unknown): LiveReadinessPacket | null {
  if (!data || typeof data !== "object") return null;
  const packet = data as LiveReadinessPacket;
  if (!packet.live || !Array.isArray(packet.enabledTrades)) return null;
  return packet;
}

function asRunSummary(data: unknown): LiveExtractionRunSummary | null {
  if (!data || typeof data !== "object") return null;
  return data as LiveExtractionRunSummary;
}

export function LiveScopeAnalysisPanel({ projectId, engineProjectId }: LiveScopeAnalysisPanelProps) {
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [readiness, setReadiness] = useState<LiveReadinessPacket | null>(null);
  const [checked, setChecked] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState("");
  const [result, setResult] = useState<AutomationActionResult | null>(null);
  const [run, setRun] = useState<LiveExtractionRunSummary | null>(null);

  const working = pending || busy;
  const enabledTrades: EnabledTrade[] = readiness?.enabledTrades ?? [];
  const liveReady = readiness?.live.ready_for_live_call === true;

  // Guard against duplicate submissions while a run is in flight.
  function runLocked(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    startTransition(() => {
      void action().finally(() => setBusy(false));
    });
  }

  function onCheckAvailability() {
    setResult(null);
    setRun(null);
    runLocked(async () => {
      const res = await getLiveScopeExtractionReadiness(projectId);
      setChecked(true);
      const packet = res.ok ? asReadiness(res.data) : null;
      setReadiness(packet);
      if (packet && packet.enabledTrades.length > 0 && !selectedTrade) {
        setSelectedTrade(packet.enabledTrades[0].trade_code);
      }
      setResult(res);
    });
  }

  function onRun() {
    if (!selectedTrade) {
      setResult({ ok: false, message: LIVE_SCOPE_COPY.chooseTrade });
      return;
    }
    setResult(null);
    setRun(null);
    runLocked(async () => {
      const res = await startLiveScopeExtraction(projectId, selectedTrade);
      setResult(res);
      setRun(res.ok ? asRunSummary(res.data) : null);
    });
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-navy">Live GPT-5.6 scope analysis</h2>
          <p className="mt-1 text-sm text-slate-500">
            Staff-only. Explicitly runs one exact GPT-5.6 Medium scope analysis on this project&apos;s
            already-processed sheets. It never authors quantities, prices, approvals, or deliveries — every
            resulting scope item and quote stays pending human review.
          </p>
        </div>
        <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
          {engineProjectId ? "Engine synced" : "Not synced"}
        </span>
      </div>

      {!engineProjectId && (
        <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Send this project to the estimating engine before running live scope analysis.
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <button
          type="button"
          onClick={onCheckAvailability}
          disabled={working || !engineProjectId}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          {working ? "Checking…" : "Check live availability"}
        </button>

        <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Enabled trade
          <select
            value={selectedTrade}
            onChange={(event) => setSelectedTrade(event.target.value)}
            disabled={working || !liveReady || enabledTrades.length === 0}
            className="mt-1 block w-56 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm font-normal normal-case tracking-normal text-slate-700 disabled:opacity-60"
          >
            <option value="">Select a trade…</option>
            {enabledTrades.map((trade) => (
              <option key={trade.trade_code} value={trade.trade_code}>
                {trade.trade_name} ({trade.trade_code})
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={onRun}
          disabled={working || !engineProjectId || !liveReady || !selectedTrade}
          className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-dark disabled:opacity-60"
        >
          {working ? "Working…" : "Run GPT-5.6 scope analysis"}
        </button>
      </div>

      {checked && readiness && !liveReady && (
        <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {LIVE_SCOPE_COPY.notEnabled}. Ask the owner to arm live extraction on the engine before running.
        </p>
      )}

      {readiness?.live && (
        <dl className="mt-4 grid gap-x-6 gap-y-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Model</dt>
            <dd className="mt-0.5 text-slate-700">{readiness.live.model ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Reasoning effort</dt>
            <dd className="mt-0.5 text-slate-700">{readiness.live.reasoning_effort ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Live call</dt>
            <dd className="mt-0.5 text-slate-700">{liveReady ? "available" : "not enabled"}</dd>
          </div>
        </dl>
      )}

      {result && (
        <div className={`mt-4 rounded-lg px-3 py-2 text-sm ${result.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>
          {result.message}
        </div>
      )}

      {run && (
        <dl className="mt-4 grid gap-x-6 gap-y-2 rounded-lg border border-slate-200 p-3 text-sm sm:grid-cols-2">
          <div className="sm:col-span-2">
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Run id</dt>
            <dd className="mt-0.5 break-all font-mono text-xs text-slate-600">{run.runId ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Status</dt>
            <dd className="mt-0.5 text-slate-700">{run.status ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Trade</dt>
            <dd className="mt-0.5 text-slate-700">{run.tradeCode ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Provider / model</dt>
            <dd className="mt-0.5 text-slate-700">{run.provider ?? "—"} · {run.model ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">Candidates</dt>
            <dd className="mt-0.5 text-slate-700">{run.candidateCount ?? "—"}</dd>
          </div>
        </dl>
      )}

      <p className="mt-4 text-xs text-slate-400">
        Results feed internal review only. Customer delivery, pricing, approval, and messaging stay locked.
      </p>
    </section>
  );
}
