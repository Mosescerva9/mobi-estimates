"use client";

import { useMemo, useState } from "react";
import {
  applyWorkbenchAction,
  defaultTrainingEligibility,
  isValidTakeoffGeometry,
  previewFromRuntimePayload,
  TAKEOFF_PROVENANCE_LABELS,
  WORKBENCH_JOB_STATUSES,
  type RuntimeBridgePayload,
  type TakeoffProvenanceLabel,
  type TakeoffWorkbenchAction,
  type WorkbenchJobStatus,
  type WorkbenchMeasurementPreview,
} from "@/lib/estimator-takeoff-workbench";

// Captured from the REAL merged OpenTakeoff MCP runtime via the local harness
// (`npm run harness:estimator-takeoff-workbench`), which drives the pinned
// opentakeoff-mcp subprocess against the PR #96 public Golden Set fixture.
// This is an actual runtime measurement result, not a fabricated frontend value.
// The browser cannot invoke the Node/pdfinfo subprocess in a deployed
// environment, so live measurement stays in the internal/local harness path.
const C011_RUNTIME_PROOF: RuntimeBridgePayload = {
  runtime: "real_opentakeoff_mcp_subprocess",
  engine_version: "opentakeoff-mcp@0.1.1",
  provider: "open_takeoff",
  provider_record_id: "shp-mrniodab-1",
  provenance_label: "OpenTakeoff measured",
  evidence_class: "measured",
  review_status: "pending",
  sheet_label: "C011",
  page_number: 4,
  scale: "units_per_px:0.08012820512820511",
  quantity: 37.5,
  unit: "LF",
  trade: "electrical",
  scope_category: "ev_charging",
  condition: "PROOF-LINE",
  region_coordinates: [0.6258333333333334, 0.3666666666666667, 0.7161111111111111, 0.3666666666666667],
  marked_geometry: { type: "line", pts: [[3244.32, 1267.2], [3712.32, 1267.2]] },
  source_region: { bounding_box: [3244.32, 1267.2, 3712.32, 1267.2] },
};

const PROVENANCE_STYLE: Record<TakeoffProvenanceLabel, string> = {
  "OpenTakeoff measured": "bg-sky-100 text-sky-800 border-sky-200",
  "Human verified": "bg-emerald-100 text-emerald-800 border-emerald-200",
  "Schedule extracted": "bg-violet-100 text-violet-800 border-violet-200",
  "Customer supplied": "bg-slate-100 text-slate-700 border-slate-200",
  // Model candidates are intentionally distinct (dashed, amber) from human-verified.
  "Model candidate": "border-dashed border-amber-400 bg-amber-50 text-amber-800",
};

const JOB_STATUS_STYLE: Record<WorkbenchJobStatus, string> = {
  queued: "bg-slate-100 text-slate-600",
  running: "bg-sky-100 text-sky-700",
  awaiting_scale_confirmation: "bg-amber-100 text-amber-800",
  awaiting_geometry_confirmation: "bg-amber-100 text-amber-800",
  completed: "bg-emerald-100 text-emerald-700",
  failed: "bg-rose-100 text-rose-700",
  cancelled: "bg-slate-200 text-slate-500",
};

function ProvenanceBadge({ label }: { label: TakeoffProvenanceLabel }) {
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold ${PROVENANCE_STYLE[label]}`}>
      {label}
    </span>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-700">{value}</dd>
    </div>
  );
}

export function TakeoffWorkbenchPanel({ projectId }: { projectId: string }) {
  const runtimePreview = useMemo(() => previewFromRuntimePayload(C011_RUNTIME_PROOF), []);
  const [preview, setPreview] = useState<WorkbenchMeasurementPreview>(runtimePreview);
  const [jobStatus, setJobStatus] = useState<WorkbenchJobStatus>("completed");
  const [decisionLog, setDecisionLog] = useState<string[]>([]);

  // Deterministic coordinate form model (full interactive PDF drawing is a TODO).
  const [scaleUpp, setScaleUpp] = useState(String(C011_RUNTIME_PROOF.scale));
  const [pointsText, setPointsText] = useState(
    C011_RUNTIME_PROOF.marked_geometry.pts.map((p) => p.join(", ")).join("\n"),
  );

  const parsedGeometry = useMemo(() => {
    const points = pointsText
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => line.split(",").map((n) => Number(n.trim())) as [number, number]);
    return { mode: preview.measurementMode, points };
  }, [pointsText, preview.measurementMode]);

  const geometryValid = isValidTakeoffGeometry(parsedGeometry);
  const scaleConfirmed = scaleUpp.trim().length > 0;

  function runAction(action: TakeoffWorkbenchAction) {
    const timestamp = new Date().toISOString();
    const reviewer = "staff:workbench-ui";
    try {
      if (action === "correct_geometry") {
        if (!geometryValid) throw new Error("invalid_geometry");
        const decision = applyWorkbenchAction(preview, action, {
          reviewer,
          timestamp,
          reason: "geometry adjusted in workbench",
          correctedGeometry: parsedGeometry,
          correctedQuantity: preview.quantity, // recomputed by runtime in the live path
        });
        setPreview(decision.preview);
      } else if (action === "replace_with_human_verified_measurement") {
        if (!geometryValid) throw new Error("invalid_geometry");
        const decision = applyWorkbenchAction(preview, action, {
          reviewer,
          timestamp,
          humanGeometry: parsedGeometry,
          humanQuantity: preview.quantity,
        });
        setPreview(decision.preview);
      } else {
        const decision = applyWorkbenchAction(preview, action, { reviewer, timestamp });
        setPreview(decision.preview);
      }
      setDecisionLog((log) => [`${action} → ${timestamp}`, ...log].slice(0, 8));
    } catch (err) {
      setDecisionLog((log) => [`${action} rejected: ${(err as Error).message}`, ...log].slice(0, 8));
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6" data-project-id={projectId}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-navy">Estimator takeoff workbench</h2>
          <p className="mt-1 text-sm text-slate-500">Internal staff-only. Measurements carry provenance and require human review.</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${JOB_STATUS_STYLE[jobStatus]}`}>
          job: {jobStatus}
        </span>
      </div>

      <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        <strong>Local runtime only.</strong> Live measurement runs the pinned OpenTakeoff MCP subprocess
        (Node + pdfinfo) via <code>npm run harness:estimator-takeoff-workbench</code>. The browser cannot
        launch that subprocess in a deployed environment, so this panel previews the actual runtime result
        and the review state model. Full interactive PDF drawing is a TODO — use the deterministic
        coordinate form below.
      </div>

      {/* Provenance legend — model candidate is visually distinct from human-verified. */}
      <div className="mt-4 flex flex-wrap gap-2">
        {TAKEOFF_PROVENANCE_LABELS.map((label) => (
          <ProvenanceBadge key={label} label={label} />
        ))}
      </div>

      {/* Runtime measurement result */}
      <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ProvenanceBadge label={preview.provenance} />
            <span className="rounded bg-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-600">
              review: {preview.reviewStatus}
            </span>
          </div>
          <div className="text-right">
            <div className="text-lg font-bold text-navy">{preview.quantity} {preview.unit}</div>
            <div className="text-xs text-slate-400">confidence: {preview.confidence ?? "n/a"}</div>
          </div>
        </div>
        <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-3">
          <Field label="Provider" value={preview.provider} />
          <Field label="Engine version" value={preview.engineVersion} />
          <Field label="Sheet / page" value={`${preview.sheetId} · p${preview.pageNumber}`} />
          <Field label="Scale" value={preview.scaleLabel} />
          <Field label="Trade" value={preview.trade} />
          <Field label="Scope category" value={preview.scopeCategory} />
          <Field label="Condition" value={preview.condition} />
          <Field label="Evidence class" value={preview.evidenceClass} />
          <Field
            label="Training eligibility"
            value={defaultTrainingEligibility(preview.provenance, preview.reviewStatus)}
          />
          <Field
            label="Source region (px bbox)"
            value={preview.sourceRegion ? preview.sourceRegion.map((n) => Math.round(n)).join(", ") : "—"}
          />
          <Field
            label="Marked geometry"
            value={preview.markedGeometry.points.map((p) => `(${p.join(",")})`).join(" → ")}
          />
        </dl>
      </div>

      {/* Deterministic coordinate form (drawing TODO) + trade/scope assignment */}
      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Scale confirmation (units_per_px)</span>
          <input
            value={scaleUpp}
            onChange={(e) => setScaleUpp(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <span className={`mt-1 block text-xs ${scaleConfirmed ? "text-emerald-600" : "text-rose-600"}`}>
            {scaleConfirmed ? "scale confirmed" : "scale required before measurement"}
          </span>
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            {preview.measurementMode} geometry — one “x, y” per line
          </span>
          <textarea
            value={pointsText}
            onChange={(e) => setPointsText(e.target.value)}
            rows={3}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs"
          />
          <span className={`mt-1 block text-xs ${geometryValid ? "text-emerald-600" : "text-rose-600"}`}>
            {geometryValid ? "geometry valid" : "invalid geometry"}
          </span>
        </label>
      </div>

      {/* Review controls */}
      <div className="mt-5 flex flex-wrap gap-2">
        <button
          onClick={() => runAction("approve")}
          className="rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
        >
          Approve
        </button>
        <button
          onClick={() => runAction("correct_geometry")}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-navy hover:border-brand hover:text-brand"
        >
          Correct geometry
        </button>
        <button
          onClick={() => runAction("replace_with_human_verified_measurement")}
          className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-navy hover:border-brand hover:text-brand"
        >
          Replace with human-verified
        </button>
        <button
          onClick={() => runAction("reject")}
          className="rounded-full border border-rose-300 px-4 py-2 text-sm font-semibold text-rose-700 hover:bg-rose-50"
        >
          Reject
        </button>
      </div>

      {/* Job status state model (queued/running/completed/failed/cancelled) */}
      <div className="mt-5">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Simulate worker job state</span>
        <div className="mt-2 flex flex-wrap gap-2">
          {WORKBENCH_JOB_STATUSES.map((status) => (
            <button
              key={status}
              onClick={() => setJobStatus(status)}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                status === jobStatus ? JOB_STATUS_STYLE[status] : "bg-white text-slate-500 border border-slate-200"
              }`}
            >
              {status}
            </button>
          ))}
        </div>
      </div>

      {decisionLog.length > 0 && (
        <ul className="mt-4 space-y-1 text-xs text-slate-500">
          {decisionLog.map((entry, i) => (
            <li key={i}>• {entry}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
