"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  applyWorkbenchAction,
  buildDraftMeasurementPreview,
  canRetryWorkerJob,
  defaultTrainingEligibility,
  distancePx,
  isSimpleInteractionWithinTarget,
  previewQuantityFromGeometry,
  svgClientPointToSheetPoint,
  TAKEOFF_PROVENANCE_LABELS,
  type SheetRasterSize,
  type TakeoffDocumentOption,
  type TakeoffMeasurementMode,
  type TakeoffProvenanceLabel,
  type TakeoffSheetOption,
  type WorkbenchInteractionTiming,
  type WorkbenchMeasurementPreview,
} from "@/lib/estimator-takeoff-workbench";
import {
  confirmLiveTakeoffScale,
  createLiveTakeoffJob,
  getLiveTakeoffArtifacts,
  getLiveTakeoffJob,
  measureLiveTakeoffCount,
  measureLiveTakeoffLine,
  measureLiveTakeoffPolygon,
  retryLiveTakeoffJob,
  type TakeoffWorkerActionResult,
} from "./takeoff-actions";

const PROVENANCE_STYLE: Record<TakeoffProvenanceLabel, string> = {
  "OpenTakeoff measured": "bg-sky-100 text-sky-800 border-sky-200",
  "Human verified": "bg-emerald-100 text-emerald-800 border-emerald-200",
  "Schedule extracted": "bg-violet-100 text-violet-800 border-violet-200",
  "Customer supplied": "bg-slate-100 text-slate-700 border-slate-200",
  "Model candidate": "border-dashed border-amber-400 bg-amber-50 text-amber-800",
};

function ProvenanceBadge({ label }: { label: TakeoffProvenanceLabel }) {
  return <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold ${PROVENANCE_STYLE[label]}`}>{label}</span>;
}

function safeStatus(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "unknown";
}

function formatSeconds(value: number): string {
  return `${Math.round(value * 10) / 10}s`;
}

function nowSeconds(): number {
  return performance.now() / 1000;
}

const CLIENT_WORKER_ACTION_TIMEOUT_MS = 40_000;

function clientWorkerTimeoutResult(): TakeoffWorkerActionResult {
  return {
    ok: false,
    message: `Worker action timed out in the browser after ${Math.round(CLIENT_WORKER_ACTION_TIMEOUT_MS / 1000)}s. Check worker runtime logs before retrying.`,
  };
}

function clientWorkerActionErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return "Worker action failed before the worker returned a response. Check staff session, worker config, and runtime logs before retrying.";
  const message = error.message?.trim();
  if (!message || message === "An unexpected error occurred") {
    return "Worker action failed before the worker returned a response. Check staff session, worker config, and runtime logs before retrying.";
  }
  return message;
}

function parseJobId(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const id = (data as { job_id?: unknown }).job_id;
  return typeof id === "string" ? id : null;
}

function parseStatus(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const status = (data as { status?: unknown }).status;
  return typeof status === "string" ? status : null;
}

function buildWorkbenchIdempotencyKey(input: {
  projectId: string;
  sheetId: string;
  page: number;
  mode: TakeoffMeasurementMode;
  unitsPerPx: number;
  condition: string;
  points: Array<[number, number]>;
}): string {
  const pointKey = input.points.map(([x, y]) => `${Math.round(x * 100) / 100},${Math.round(y * 100) / 100}`).join(";");
  return [
    "visual-workbench-v1",
    input.projectId,
    input.sheetId,
    String(input.page),
    input.mode,
    String(Math.round(input.unitsPerPx * 1_000_000) / 1_000_000),
    input.condition.trim() || "condition",
    pointKey,
  ].join(":");
}

function pointsPath(points: Array<[number, number]>, mode: TakeoffMeasurementMode): string {
  // Count markers are discrete points and are never connected by a path.
  if (points.length === 0 || mode === "count") return "";
  const d = points.map((p, index) => `${index === 0 ? "M" : "L"}${p[0]} ${p[1]}`).join(" ");
  return mode === "polygon" && points.length >= 3 ? `${d} Z` : d;
}

export function TakeoffWorkbenchPanel({
  projectId,
  engineProjectId = null,
  workerConfigured = false,
  documents = [],
  engineSheets = [],
}: {
  projectId: string;
  engineProjectId?: string | null;
  workerConfigured?: boolean;
  documents?: TakeoffDocumentOption[];
  engineSheets?: TakeoffSheetOption[];
}) {
  const [workerPending, setWorkerPending] = useState(false);
  const [selectedDocumentId, setSelectedDocumentId] = useState(documents[0]?.id ?? "");
  const [selectedSheetId, setSelectedSheetId] = useState(engineSheets[0]?.sheetId ?? "");
  const [page, setPage] = useState(String(engineSheets[0]?.pageNumber ?? documents[0]?.sheets[0]?.page ?? 1));
  const [mode, setMode] = useState<TakeoffMeasurementMode>("line");
  const [tool, setTool] = useState<"draw" | "calibrate" | "pan">("draw");
  const [points, setPoints] = useState<Array<[number, number]>>([]);
  const [calibrationPoints, setCalibrationPoints] = useState<Array<[number, number]>>([]);
  const [knownDimension, setKnownDimension] = useState("");
  const [unitsPerPx, setUnitsPerPx] = useState("");
  const [scaleConfirmed, setScaleConfirmed] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragVertex, setDragVertex] = useState<number | null>(null);
  const [panStart, setPanStart] = useState<{ pointer: [number, number]; pan: { x: number; y: number } } | null>(null);
  const [trade, setTrade] = useState("electrical");
  const [scopeCategory, setScopeCategory] = useState("ev_charging");
  const [condition, setCondition] = useState("RUNTIME-LINE");
  const [jobId, setJobId] = useState("");
  const [workerStatus, setWorkerStatus] = useState("not_started");
  const [workerResult, setWorkerResult] = useState<TakeoffWorkerActionResult | null>(null);
  // Retained lineage of the failed job a retry was launched from, so adopting the
  // linked retry attempt never hides the original failed job/error from staff.
  const [retriedFromJob, setRetriedFromJob] = useState<{ jobId: string; status: string; message: string } | null>(null);
  const [preview, setPreview] = useState<WorkbenchMeasurementPreview | null>(null);
  const [rasterSize, setRasterSize] = useState<SheetRasterSize | null>(null);
  const [decisionLog, setDecisionLog] = useState<string[]>([]);
  const [timing, setTiming] = useState<WorkbenchInteractionTiming>({
    sheet_selection_seconds: 0,
    scale_confirmation_seconds: 0,
    geometry_definition_seconds: 0,
    worker_wait_seconds: 0,
    review_seconds: 0,
    ai_suggestion_used: false,
    ai_suggestion_accepted: null,
  });
  const sheetSelectionStart = useRef(nowSeconds());
  const scaleStart = useRef(nowSeconds());
  const geometryStart = useRef(nowSeconds());
  const workerStart = useRef<number | null>(null);
  const reviewStart = useRef(nowSeconds());
  const svgRef = useRef<SVGSVGElement | null>(null);

  const selectedDocument = documents.find((d) => d.id === selectedDocumentId) ?? documents[0] ?? null;
  const selectedEngineSheet = engineSheets.find((s) => s.sheetId === selectedSheetId) ?? null;
  const pageNumber = Number(page) || selectedEngineSheet?.pageNumber || 1;
  const currentScale = Number(unitsPerPx);
  const quantityPreview = useMemo(() => previewQuantityFromGeometry(mode, points, currentScale), [mode, points, currentScale]);
  const targetMet = isSimpleInteractionWithinTarget(mode, timing);
  const sheetImageUrl = selectedEngineSheet
    ? `/admin/projects/${encodeURIComponent(projectId)}/takeoff-sheet-image?sheetId=${encodeURIComponent(selectedEngineSheet.sheetId)}`
    : null;
  const pdfUrl = selectedDocument?.signedUrl ? `${selectedDocument.signedUrl}#page=${pageNumber}&zoom=page-width` : null;
  const ready = workerConfigured && Boolean(engineProjectId) && Boolean(selectedEngineSheet);
  const sheetWidth = rasterSize?.width ?? 1;
  const sheetHeight = rasterSize?.height ?? 1;

  useEffect(() => {
    setRasterSize(null);
    if (!sheetImageUrl) return;
    let cancelled = false;
    const image = new Image();
    image.onload = () => {
      if (!cancelled && image.naturalWidth > 0 && image.naturalHeight > 0) {
        setRasterSize({ width: image.naturalWidth, height: image.naturalHeight });
      }
    };
    image.onerror = () => {
      if (!cancelled) setRasterSize(null);
    };
    image.src = sheetImageUrl;
    return () => {
      cancelled = true;
    };
  }, [sheetImageUrl]);

  function updateTiming(key: keyof WorkbenchInteractionTiming, value: number | boolean | null) {
    setTiming((current) => ({ ...current, [key]: value } as WorkbenchInteractionTiming));
  }

  function selectDocument(value: string) {
    updateTiming("sheet_selection_seconds", nowSeconds() - sheetSelectionStart.current);
    setSelectedDocumentId(value);
    const doc = documents.find((d) => d.id === value);
    const firstSheet = engineSheets[0];
    setSelectedSheetId(firstSheet?.sheetId ?? "");
    setPage(String(firstSheet?.pageNumber ?? doc?.sheets[0]?.page ?? 1));
    setPoints([]);
    setCalibrationPoints([]);
    sheetSelectionStart.current = nowSeconds();
  }

  function selectSheet(value: string) {
    updateTiming("sheet_selection_seconds", nowSeconds() - sheetSelectionStart.current);
    setSelectedSheetId(value);
    const sheet = engineSheets.find((s) => s.sheetId === value);
    if (sheet) setPage(String(sheet.pageNumber));
    setPoints([]);
    setCalibrationPoints([]);
    sheetSelectionStart.current = nowSeconds();
  }

  function fitPage() {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }

  function eventToSheetPoint(event: React.PointerEvent<SVGSVGElement>): [number, number] | null {
    if (!svgRef.current || !rasterSize) return null;
    return svgClientPointToSheetPoint({
      clientX: event.clientX,
      clientY: event.clientY,
      rect: svgRef.current.getBoundingClientRect(),
      raster: rasterSize,
      zoom,
      pan,
    });
  }

  function svgPointerDown(event: React.PointerEvent<SVGSVGElement>) {
    const point = eventToSheetPoint(event);
    if (!point) return;
    if (tool === "pan") {
      setPanStart({ pointer: [event.clientX, event.clientY], pan });
      return;
    }
    const vertexIndex = points.findIndex(([x, y]) => Math.hypot(x - point[0], y - point[1]) < 12 / zoom);
    if (vertexIndex >= 0 && tool === "draw") {
      setDragVertex(vertexIndex);
      return;
    }
    if (tool === "calibrate") {
      const next = [...calibrationPoints, point].slice(-2);
      setCalibrationPoints(next);
      if (next.length === 2) scaleStart.current = nowSeconds();
      return;
    }
    setPoints((current) => [...current, point]);
    updateTiming("geometry_definition_seconds", nowSeconds() - geometryStart.current);
  }

  function svgPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (!svgRef.current) return;
    if (panStart) {
      const dx = ((event.clientX - panStart.pointer[0]) / (svgRef.current.getBoundingClientRect().width || 1)) * sheetWidth;
      const dy = ((event.clientY - panStart.pointer[1]) / (svgRef.current.getBoundingClientRect().height || 1)) * sheetHeight;
      setPan({ x: panStart.pan.x + dx, y: panStart.pan.y + dy });
      return;
    }
    if (dragVertex === null) return;
    const point = eventToSheetPoint(event);
    if (!point) return;
    setPoints((current) => current.map((p, i) => (i === dragVertex ? point : p)));
    updateTiming("geometry_definition_seconds", nowSeconds() - geometryStart.current);
  }

  function pointerUp() {
    setDragVertex(null);
    setPanStart(null);
  }

  function applyCalibration() {
    const known = Number(knownDimension);
    if (calibrationPoints.length !== 2 || !Number.isFinite(known) || known <= 0) return;
    const px = distancePx(calibrationPoints[0], calibrationPoints[1]);
    if (px <= 0) return;
    setUnitsPerPx(String(known / px));
    setScaleConfirmed(true);
    updateTiming("scale_confirmation_seconds", nowSeconds() - scaleStart.current);
  }

  function buildPreview() {
    if (!selectedEngineSheet || !quantityPreview) return;
    const draft = buildDraftMeasurementPreview({
      mode,
      points,
      unitsPerPx: currentScale,
      scaleLabel: `units_per_px:${unitsPerPx}`,
      sheetId: selectedEngineSheet.sheetId,
      pageNumber,
      trade,
      scopeCategory,
      condition,
    });
    setPreview(draft);
  }

  function runWorker(action: () => Promise<TakeoffWorkerActionResult>) {
    workerStart.current = nowSeconds();
    let settled = false;
    setWorkerPending(true);
    setWorkerResult({ ok: false, message: "Worker action started. A browser timeout will appear if the worker submit does not return." });
    const timeout = setTimeout(() => {
      if (settled) return;
      setWorkerPending(false);
      setWorkerResult(clientWorkerTimeoutResult());
      updateTiming("worker_wait_seconds", workerStart.current ? nowSeconds() - workerStart.current : 0);
    }, CLIENT_WORKER_ACTION_TIMEOUT_MS);
    void action()
      .catch((error: unknown) => ({
        ok: false,
        message: clientWorkerActionErrorMessage(error),
      }))
      .then((res: TakeoffWorkerActionResult) => {
        settled = true;
        clearTimeout(timeout);
        setWorkerPending(false);
        updateTiming("worker_wait_seconds", workerStart.current ? nowSeconds() - workerStart.current : 0);
        setWorkerResult(res);
        const id = parseJobId(res.data);
        if (id) setJobId(id);
        const status = parseStatus(res.data);
        if (status) setWorkerStatus(status);
      });
  }

  async function submitToWorker() {
    if (!selectedEngineSheet || !scaleConfirmed || !quantityPreview || !rasterSize) {
      setWorkerResult({ ok: false, message: "Select a sheet, wait for the raster, confirm scale, and draw valid geometry before submitting." });
      return;
    }
    runWorker(async () => {
      const operation = mode === "polygon" ? "measure_polygon" : mode === "count" ? "measure_count" : "measure_line";
      const idempotencyKey = buildWorkbenchIdempotencyKey({
        projectId,
        sheetId: selectedEngineSheet.sheetId,
        page: pageNumber,
        mode,
        unitsPerPx: currentScale,
        condition,
        points,
      });
      const created = await createLiveTakeoffJob(projectId, { page: pageNumber, operation, trade, scopeCategory, condition, idempotencyKey });
      if (!created.ok) return created;
      const id = parseJobId(created.data);
      if (!id) return { ok: false, message: "Worker did not return a job id." };
      const scale = await confirmLiveTakeoffScale(projectId, id, {
        sheetId: selectedEngineSheet.sheetId,
        page: pageNumber,
        unitsPerPx: currentScale,
        scaleLabel: `units_per_px:${unitsPerPx}`,
      });
      if (!scale.ok) return scale;
      if (mode === "polygon") {
        return measureLiveTakeoffPolygon(projectId, id, { sheetId: selectedEngineSheet.sheetId, page: pageNumber, vertices: points, condition });
      }
      if (mode === "count") {
        return measureLiveTakeoffCount(projectId, id, { sheetId: selectedEngineSheet.sheetId, page: pageNumber, markers: points, condition });
      }
      return measureLiveTakeoffLine(projectId, id, { sheetId: selectedEngineSheet.sheetId, page: pageNumber, points, condition });
    });
  }

  const retryEligible = canRetryWorkerJob(workerStatus);

  function retryFailedJob() {
    // Guarded twice: the control only renders when the current job is exactly
    // `failed`, and re-checks here so a stale click cannot retry a non-failed job.
    if (!retryEligible || !jobId) return;
    const failedJobId = jobId;
    setRetriedFromJob({
      jobId: failedJobId,
      status: workerStatus,
      message: workerResult?.message ?? "The original job remains failed; poll it to review its retained safe error.",
    });
    // runWorker adopts the returned linked retry job_id/status on success so staff
    // continue the normal confirm-scale/measure flow on the new attempt. The
    // durable-retry backend never mutates the original failed job or its error.
    runWorker(() => retryLiveTakeoffJob(projectId, failedJobId));
  }

  function runReview(action: "approve" | "correct_geometry" | "reject" | "replace_with_human_verified_measurement") {
    if (!preview) return;
    try {
      const timestamp = new Date().toISOString();
      const decision =
        action === "correct_geometry"
          ? applyWorkbenchAction(preview, action, { reviewer: "staff:workbench-ui", timestamp, correctedGeometry: { mode, points }, correctedQuantity: preview.quantity, reason: "geometry corrected in visual workbench" })
          : action === "replace_with_human_verified_measurement"
            ? applyWorkbenchAction(preview, action, { reviewer: "staff:workbench-ui", timestamp, humanGeometry: { mode, points }, humanQuantity: preview.quantity })
            : applyWorkbenchAction(preview, action, { reviewer: "staff:workbench-ui", timestamp });
      setPreview(decision.preview);
      updateTiming("review_seconds", nowSeconds() - reviewStart.current);
      setDecisionLog((log) => [`${action} → ${timestamp}`, ...log].slice(0, 6));
    } catch (error) {
      setDecisionLog((log) => [`${action} rejected: ${error instanceof Error ? error.message : "unknown"}`, ...log].slice(0, 6));
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6" data-project-id={projectId}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-navy">Estimator visual takeoff workbench</h2>
          <p className="mt-1 text-sm text-slate-500">Staff-only visual measurement. Worker secrets and tenant identity stay server-side.</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${ready ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-500"}`}>
          {ready ? "worker configured" : "needs engine sheet"}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {TAKEOFF_PROVENANCE_LABELS.map((label) => <ProvenanceBadge key={label} label={label} />)}
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[280px_1fr]">
        <aside className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Document</span>
            <select value={selectedDocumentId} onChange={(e) => selectDocument(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
              {documents.length === 0 ? <option value="">No uploaded documents</option> : documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.fileName}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Sheet / page</span>
            <select value={selectedSheetId} onChange={(e) => selectSheet(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
              {engineSheets.length === 0 ? <option value="">No engine sheets</option> : engineSheets.map((sheet) => (
                <option key={sheet.sheetId} value={sheet.sheetId}>p{sheet.pageNumber} · {sheet.sheetNumber ?? "sheet"} {sheet.sheetTitle ? `— ${sheet.sheetTitle}` : ""}</option>
              ))}
            </select>
          </label>
          <div className="rounded-lg bg-white p-3 text-xs text-slate-600">
            <div><strong>Sheet:</strong> {selectedEngineSheet?.sheetNumber ?? "—"}</div>
            <div><strong>Title:</strong> {selectedEngineSheet?.sheetTitle ?? "—"}</div>
            <div><strong>Page:</strong> {pageNumber}</div>
            <div><strong>Vector/raster:</strong> {selectedEngineSheet?.vectorStatus ?? "unknown"}</div>
            <div><strong>Raster size:</strong> {rasterSize ? `${rasterSize.width} × ${rasterSize.height}px` : "loading"}</div>
            <div><strong>Saved scale:</strong> {scaleConfirmed ? `units_per_px:${unitsPerPx}` : "not confirmed"}</div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <button onClick={() => setMode("line")} className={`rounded-lg px-3 py-2 text-sm font-semibold ${mode === "line" ? "bg-brand text-white" : "border border-slate-300"}`}>Line</button>
            <button onClick={() => setMode("polygon")} className={`rounded-lg px-3 py-2 text-sm font-semibold ${mode === "polygon" ? "bg-brand text-white" : "border border-slate-300"}`}>Polygon</button>
            <button onClick={() => setMode("count")} className={`rounded-lg px-3 py-2 text-sm font-semibold ${mode === "count" ? "bg-brand text-white" : "border border-slate-300"}`}>Count</button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <button onClick={() => setTool("draw")} className={`rounded-lg px-2 py-2 text-xs font-semibold ${tool === "draw" ? "bg-navy text-white" : "border border-slate-300"}`}>Draw</button>
            <button onClick={() => setTool("calibrate")} className={`rounded-lg px-2 py-2 text-xs font-semibold ${tool === "calibrate" ? "bg-navy text-white" : "border border-slate-300"}`}>Calibrate</button>
            <button onClick={() => setTool("pan")} className={`rounded-lg px-2 py-2 text-xs font-semibold ${tool === "pan" ? "bg-navy text-white" : "border border-slate-300"}`}>Pan</button>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => setZoom((z) => Math.min(4, z + 0.25))} className="rounded border px-2 py-1 text-xs">Zoom +</button>
            <button onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} className="rounded border px-2 py-1 text-xs">Zoom -</button>
            <button onClick={fitPage} className="rounded border px-2 py-1 text-xs">Fit page</button>
          </div>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Known dimension for calibration</span>
            <input value={knownDimension} onChange={(e) => setKnownDimension(e.target.value)} placeholder="e.g. 15" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <button onClick={applyCalibration} disabled={calibrationPoints.length !== 2} className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Confirm calibrated scale</button>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Scale units_per_px</span>
            <input value={unitsPerPx} onChange={(e) => { setUnitsPerPx(e.target.value); setScaleConfirmed(false); }} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <button onClick={() => { if (Number(unitsPerPx) > 0) { setScaleConfirmed(true); updateTiming("scale_confirmation_seconds", nowSeconds() - scaleStart.current); } }} className="w-full rounded-lg border border-emerald-300 px-3 py-2 text-sm font-semibold text-emerald-700">Explicitly confirm scale</button>
        </aside>

        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
            <span>Zoom {Math.round(zoom * 100)}% · points {points.length} · tool {tool}</span>
            <span>Coordinates are natural rendered-sheet pixels, not display CSS pixels.</span>
          </div>
          <div className="relative overflow-hidden rounded-xl border border-slate-300 bg-slate-900">
            <svg
              ref={svgRef}
              viewBox={`0 0 ${sheetWidth} ${sheetHeight}`}
              preserveAspectRatio="none"
              className="h-[620px] w-full touch-none select-none bg-slate-800"
              onPointerDown={svgPointerDown}
              onPointerMove={svgPointerMove}
              onPointerUp={pointerUp}
              onPointerLeave={pointerUp}
            >
              <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
                <rect width={sheetWidth} height={sheetHeight} fill="#f8fafc" />
                {sheetImageUrl && rasterSize ? <image href={sheetImageUrl} x="0" y="0" width={sheetWidth} height={sheetHeight} preserveAspectRatio="none" /> : null}
                <path d={pointsPath(points, mode)} fill={mode === "polygon" && points.length >= 3 ? "rgba(14,165,233,0.18)" : "none"} stroke="#0ea5e9" strokeWidth={3 / zoom} />
                {points.map(([x, y], index) => <circle key={`${x}-${y}-${index}`} cx={x} cy={y} r={7 / zoom} fill="#f97316" stroke="white" strokeWidth={2 / zoom} />)}
                {calibrationPoints.map(([x, y], index) => <circle key={`c-${index}`} cx={x} cy={y} r={8 / zoom} fill="#10b981" stroke="white" strokeWidth={2 / zoom} />)}
                {calibrationPoints.length === 2 ? <line x1={calibrationPoints[0][0]} y1={calibrationPoints[0][1]} x2={calibrationPoints[1][0]} y2={calibrationPoints[1][1]} stroke="#10b981" strokeWidth={2 / zoom} strokeDasharray="8 6" /> : null}
              </g>
            </svg>
          </div>
          {pdfUrl ? <a href={pdfUrl} target="_blank" rel="noopener noreferrer" className="inline-block text-xs font-semibold text-brand hover:underline">Open signed PDF page in a new tab for reference</a> : null}
        </div>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-bold text-navy">Geometry controls</h3>
          <div className="mt-3 flex flex-wrap gap-2">
            <button onClick={() => setPoints((p) => p.slice(0, -1))} className="rounded-full border px-3 py-1.5 text-xs font-semibold">Undo latest point</button>
            <button onClick={() => { setPoints([]); setPreview(null); geometryStart.current = nowSeconds(); }} className="rounded-full border px-3 py-1.5 text-xs font-semibold">Clear draft geometry</button>
            <button onClick={buildPreview} disabled={!quantityPreview || !selectedEngineSheet} className="rounded-full bg-navy px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">Preview quantity</button>
          </div>
          <pre className="mt-3 max-h-32 overflow-auto rounded bg-slate-50 p-2 font-mono text-[11px] text-slate-600">{points.map((p) => `${Math.round(p[0] * 100) / 100}, ${Math.round(p[1] * 100) / 100}`).join("\n") || "No points yet."}</pre>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-bold text-navy">Quantity preview</h3>
          <div className="mt-2 text-2xl font-bold text-navy">{quantityPreview ? `${quantityPreview.quantity} ${quantityPreview.unit}` : "—"}</div>
          <div className="mt-1 text-xs text-slate-500">Formula: {mode === "line" ? "Σ segment length px × units_per_px = LF" : mode === "count" ? "count of placed markers = EA (scale-independent)" : "shoelace area px² × units_per_px² = SF"}</div>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            <input value={trade} onChange={(e) => setTrade(e.target.value)} aria-label="Trade" className="rounded border px-2 py-1 text-xs" />
            <input value={scopeCategory} onChange={(e) => setScopeCategory(e.target.value)} aria-label="Scope category" className="rounded border px-2 py-1 text-xs" />
            <input value={condition} onChange={(e) => setCondition(e.target.value)} aria-label="Condition" className="rounded border px-2 py-1 text-xs" />
          </div>
          {preview ? <div className="mt-3 rounded border border-emerald-200 bg-emerald-50 p-2 text-xs text-emerald-800"><ProvenanceBadge label={preview.provenance} /> <span className="ml-2">{preview.quantity} {preview.unit}; training: {defaultTrainingEligibility(preview.provenance, preview.reviewStatus)}</span></div> : null}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-bold text-navy">Interaction timing</h3>
          <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-600">
            <dt>Sheet selection</dt><dd>{formatSeconds(timing.sheet_selection_seconds)}</dd>
            <dt>Scale confirmation</dt><dd>{formatSeconds(timing.scale_confirmation_seconds)}</dd>
            <dt>Geometry definition</dt><dd>{formatSeconds(timing.geometry_definition_seconds)}</dd>
            <dt>Worker wait</dt><dd>{formatSeconds(timing.worker_wait_seconds)}</dd>
            <dt>Review</dt><dd>{formatSeconds(timing.review_seconds)}</dd>
          </dl>
          <div className={`mt-2 rounded px-2 py-1 text-xs font-semibold ${targetMet ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800"}`}>{targetMet ? "Within target" : "Over target or not measured"}</div>
          <div className="mt-1 text-xs text-slate-400">AI suggestion used: no; accepted: n/a.</div>
        </section>
      </div>

      <section className="mt-5 rounded-xl border border-sky-200 bg-sky-50/60 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-navy">Submit to real worker</h3>
          <span className="rounded-full bg-white px-2.5 py-0.5 text-xs font-semibold text-slate-600">status: {safeStatus(workerStatus)}</span>
        </div>
        <p className="mt-1 text-xs text-slate-500">The browser sends only selected sheet/page, scale, geometry, and classification fields. Worker identity, tenant headers, and API key stay server-side.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button disabled={!ready || workerPending || !scaleConfirmed || !quantityPreview || !rasterSize} onClick={submitToWorker} className="rounded-full bg-sky-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Create + confirm + measure</button>
          <input value={jobId} onChange={(e) => setJobId(e.target.value)} placeholder="existing job id" className="min-w-[260px] rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs" />
          <button disabled={!ready || workerPending || !jobId} onClick={() => runWorker(() => getLiveTakeoffJob(projectId, jobId))} className="rounded-full border px-4 py-2 text-sm font-semibold">Poll status</button>
          <button disabled={!ready || workerPending || !jobId} onClick={() => runWorker(() => getLiveTakeoffArtifacts(projectId, jobId))} className="rounded-full border px-4 py-2 text-sm font-semibold">Artifacts</button>
          {retryEligible && jobId ? <button disabled={!ready || workerPending} onClick={retryFailedJob} className="rounded-full border border-amber-400 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-800 disabled:opacity-50">Retry failed job</button> : null}
        </div>
        {retriedFromJob ? <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">Retry launched from failed job <span className="font-mono">{retriedFromJob.jobId}</span> (status {retriedFromJob.status}). Original result: {retriedFromJob.message} The original failed job and its error remain persisted unchanged; the linked retry attempt is shown below.</div> : null}
        {workerResult ? <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${workerResult.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-700"}`}><div className="font-semibold">{workerResult.message}</div>{workerResult.data !== undefined ? <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-slate-600">{JSON.stringify(workerResult.data, null, 2)}</pre> : null}</div> : null}
      </section>

      <section className="mt-5 rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-bold text-navy">Estimator review controls</h3>
        <p className="mt-1 text-xs text-slate-500">These record internal workbench review intent only. They do not deliver a final estimate.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={() => runReview("approve")} disabled={!preview} className="rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">Approve</button>
          <button onClick={() => runReview("correct_geometry")} disabled={!preview} className="rounded-full border px-4 py-2 text-sm font-semibold">Correct geometry</button>
          <button onClick={() => runReview("reject")} disabled={!preview} className="rounded-full border px-4 py-2 text-sm font-semibold">Reject</button>
          <button onClick={() => runReview("replace_with_human_verified_measurement")} disabled={!preview} className="rounded-full border px-4 py-2 text-sm font-semibold">Replace with human-verified</button>
        </div>
        {decisionLog.length > 0 ? <ul className="mt-3 space-y-1 text-xs text-slate-500">{decisionLog.map((entry) => <li key={entry}>{entry}</li>)}</ul> : null}
      </section>
    </section>
  );
}
