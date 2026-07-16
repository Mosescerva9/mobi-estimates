"use client";

import { useState, useTransition } from "react";
import {
  confirmLiveTakeoffScale,
  createLiveTakeoffJob,
  getLiveTakeoffArtifacts,
  getLiveTakeoffJob,
  measureLiveTakeoffLine,
  type TakeoffWorkerActionResult,
} from "./takeoff-actions";

/**
 * Isolated staff-only wiring for the LIVE OpenTakeoff worker pathway.
 *
 * This panel never renders a fixture/demo measurement. Every value shown comes
 * from an actual worker API response for THIS project, so a fixture result is
 * never presented as if live customer measurement worked. All secrets and
 * tenant identity are added server-side by the takeoff-actions; the browser
 * only sends this project's id plus geometry/sheet/page/scale inputs.
 */
export function LiveTakeoffWorkerPanel({
  projectId,
  engineProjectId,
  configured,
}: {
  projectId: string;
  engineProjectId: string | null;
  configured: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<TakeoffWorkerActionResult | null>(null);
  const [jobId, setJobId] = useState("");
  const [page, setPage] = useState("4");
  const [sheetId, setSheetId] = useState("");
  const [unitsPerPx, setUnitsPerPx] = useState("");
  const [pointsText, setPointsText] = useState("");

  const ready = configured && Boolean(engineProjectId);

  function run(action: () => Promise<TakeoffWorkerActionResult>) {
    startTransition(async () => {
      try {
        const res = await action();
        setResult(res);
        if (res.ok && res.data && typeof res.data === "object" && "job_id" in res.data) {
          const id = (res.data as { job_id?: unknown }).job_id;
          if (typeof id === "string") setJobId(id);
        }
      } catch (e) {
        setResult({ ok: false, message: e instanceof Error ? e.message : "Action failed." });
      }
    });
  }

  function parsePoints(): Array<[number, number]> {
    return pointsText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => line.split(",").map((n) => Number(n.trim())) as [number, number]);
  }

  return (
    <section className="mt-5 rounded-xl border border-sky-200 bg-sky-50/60 p-4" data-project-id={projectId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-navy">Live worker pathway</h3>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            ready ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-500"
          }`}
        >
          {configured ? (engineProjectId ? "worker configured" : "send to engine first") : "worker not configured"}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">
        Calls the authenticated VPS worker server-side. The browser never holds the worker secret or chooses
        the tenant — identity is resolved from this project row on the server. Results below are live worker
        responses for this project only, never the demo fixture.
      </p>

      {!ready && (
        <p className="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
          {configured
            ? "This project has not been sent to the estimating engine yet, so it has no resolvable document. Send it to the engine before running live measurement."
            : "Configure the takeoff worker on the server to enable the live pathway."}
        </p>
      )}

      <fieldset disabled={!ready || pending} className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Page</span>
          <input
            value={page}
            onChange={(e) => setPage(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Job id (from create)</span>
          <input
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs"
            placeholder="created on demand"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Sheet id</span>
          <input
            value={sheetId}
            onChange={(e) => setSheetId(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Scale (units_per_px)</span>
          <input
            value={unitsPerPx}
            onChange={(e) => setUnitsPerPx(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="block sm:col-span-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Line geometry — one “x, y” per line
          </span>
          <textarea
            value={pointsText}
            onChange={(e) => setPointsText(e.target.value)}
            rows={2}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs"
          />
        </label>
      </fieldset>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          disabled={!ready || pending}
          onClick={() => run(() => createLiveTakeoffJob(projectId, { page: Number(page), operation: "measure_line" }))}
          className="rounded-full bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
        >
          Create job
        </button>
        <button
          disabled={!ready || pending || !jobId}
          onClick={() => run(() => getLiveTakeoffJob(projectId, jobId))}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-navy hover:border-brand hover:text-brand disabled:opacity-50"
        >
          Poll status
        </button>
        <button
          disabled={!ready || pending || !jobId}
          onClick={() =>
            run(() =>
              confirmLiveTakeoffScale(projectId, jobId, {
                sheetId,
                page: Number(page),
                unitsPerPx: Number(unitsPerPx),
              }),
            )
          }
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-navy hover:border-brand hover:text-brand disabled:opacity-50"
        >
          Confirm scale
        </button>
        <button
          disabled={!ready || pending || !jobId}
          onClick={() =>
            run(() =>
              measureLiveTakeoffLine(projectId, jobId, {
                sheetId,
                page: Number(page),
                points: parsePoints(),
              }),
            )
          }
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-navy hover:border-brand hover:text-brand disabled:opacity-50"
        >
          Measure line
        </button>
        <button
          disabled={!ready || pending || !jobId}
          onClick={() => run(() => getLiveTakeoffArtifacts(projectId, jobId))}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-navy hover:border-brand hover:text-brand disabled:opacity-50"
        >
          Artifacts
        </button>
      </div>

      {result && (
        <div
          className={`mt-4 rounded-lg border px-3 py-2 text-xs ${
            result.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-700"
          }`}
        >
          <div className="font-semibold">{result.message}</div>
          {result.data !== undefined && (
            <pre className="mt-2 overflow-x-auto whitespace-pre-wrap font-mono text-[11px] text-slate-600">
              {JSON.stringify(result.data, null, 2)}
            </pre>
          )}
        </div>
      )}
    </section>
  );
}
