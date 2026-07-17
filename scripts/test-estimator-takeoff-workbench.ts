import assert from "node:assert/strict";
import {
  applyWorkbenchAction,
  assertMeasurableRequest,
  assertWorkbenchPreviewProvenance,
  defaultTrainingEligibility,
  isHumanVerified,
  isModelCandidate,
  isSimpleInteractionWithinTarget,
  isValidTakeoffGeometry,
  nextEstimatorQueueState,
  nextWorkbenchJobStatus,
  previewFromRuntimePayload,
  svgClientPointToSheetPoint,
  totalInteractionSeconds,
  TAKEOFF_PROVENANCE_LABELS,
  TRAINING_ELIGIBILITY_VALUES,
  type RuntimeBridgePayload,
  type TakeoffGeometry,
  type WorkbenchInteractionTiming,
  type WorkbenchMeasurementPreview,
} from "../src/lib/estimator-takeoff-workbench";

// --- Provenance labels are preserved exactly ---
assert.deepEqual([...TAKEOFF_PROVENANCE_LABELS], [
  "OpenTakeoff measured",
  "Human verified",
  "Schedule extracted",
  "Customer supplied",
  "Model candidate",
]);

assert.deepEqual([...TRAINING_ELIGIBILITY_VALUES], [
  "project_verified",
  "company_preference_candidate",
  "general_training_candidate",
  "not_training_eligible",
]);

const openTakeoffPreview: WorkbenchMeasurementPreview = {
  measurementMode: "line",
  provenance: "OpenTakeoff measured",
  provider: "open_takeoff",
  evidenceClass: "measured",
  reviewStatus: "pending",
  sheetId: "C011",
  pageNumber: 4,
  scaleLabel: "units_per_px:0.08012820512820511",
  engineVersion: "opentakeoff-mcp@0.1.1",
  quantity: 37.5,
  unit: "LF",
  trade: "electrical",
  scopeCategory: "ev_charging",
  condition: "PROOF-LINE",
  markedGeometry: { mode: "line", points: [[3244.32, 1267.2], [3712.32, 1267.2]] },
  sourceRegion: [3244.32, 1267.2, 3712.32, 1267.2],
  reviewer: null,
  timestamp: null,
  confidence: null,
};

assertWorkbenchPreviewProvenance(openTakeoffPreview);

// --- Provenance guard: measured output cannot claim the model provider ---
assert.throws(
  () => assertWorkbenchPreviewProvenance({ ...openTakeoffPreview, provider: "model" }),
  /open_takeoff provider/,
);

// --- Model candidate stays distinct from human verified ---
const modelCandidate: WorkbenchMeasurementPreview = {
  ...openTakeoffPreview,
  provenance: "Model candidate",
  provider: "model",
  evidenceClass: "model_candidate",
  confidence: 0.62,
};
assertWorkbenchPreviewProvenance(modelCandidate);
assert.equal(isModelCandidate(modelCandidate), true);
assert.equal(isHumanVerified(modelCandidate), false);
assert.throws(
  () => assertWorkbenchPreviewProvenance({ ...modelCandidate, confidence: null }),
  /must include confidence/,
);
assert.throws(
  () => assertWorkbenchPreviewProvenance({ ...modelCandidate, provenance: "Human verified" }),
  /Human verified preview must carry human provider|must not be labelled Human verified/,
);
// A model candidate must never be presented as already approved/human-verified.
assert.throws(
  () => assertWorkbenchPreviewProvenance({ ...modelCandidate, reviewStatus: "approved" }),
  /cannot already be approved/,
);

// --- Default training eligibility: unreviewed/model => not_training_eligible ---
assert.equal(defaultTrainingEligibility("Model candidate", "pending"), "not_training_eligible");
assert.equal(defaultTrainingEligibility("OpenTakeoff measured", "pending"), "not_training_eligible");
assert.equal(defaultTrainingEligibility("OpenTakeoff measured", "rejected"), "not_training_eligible");
assert.equal(defaultTrainingEligibility("Human verified", "corrected"), "project_verified");

// --- Interaction timing (seconds) + targets ---
const timing: WorkbenchInteractionTiming = {
  sheet_selection_seconds: 8,
  scale_confirmation_seconds: 12,
  geometry_definition_seconds: 20,
  worker_wait_seconds: 6,
  review_seconds: 9,
  ai_suggestion_used: false,
  ai_suggestion_accepted: null,
};
assert.equal(totalInteractionSeconds(timing), 55);
assert.equal(isSimpleInteractionWithinTarget("line", timing), true);
assert.equal(
  isSimpleInteractionWithinTarget("line", { ...timing, review_seconds: 30 }),
  false,
);
// Polygon target is 120s.
assert.equal(
  isSimpleInteractionWithinTarget("polygon", { ...timing, geometry_definition_seconds: 80 }),
  true,
);

// --- Runtime bridge payload maps into an OpenTakeoff-measured preview ---
const runtimePayload: RuntimeBridgePayload = {
  runtime: "real_opentakeoff_mcp_subprocess",
  engine_version: "opentakeoff-mcp@0.1.1",
  provider: "open_takeoff",
  provider_record_id: "shp-abc-1",
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
  region_coordinates: [0.6258, 0.3666, 0.7161, 0.3666],
  marked_geometry: { type: "line", pts: [[3244.32, 1267.2], [3712.32, 1267.2]] },
  source_region: { bounding_box: [3244.32, 1267.2, 3712.32, 1267.2] },
};
const runtimePreview = previewFromRuntimePayload(runtimePayload);
assert.equal(runtimePreview.provenance, "OpenTakeoff measured");
assert.equal(runtimePreview.provider, "open_takeoff");
assert.equal(runtimePreview.quantity, 37.5);
assert.equal(runtimePreview.unit, "LF");
assert.equal(runtimePreview.pageNumber, 4);
assert.equal(runtimePreview.scaleLabel, "units_per_px:0.08012820512820511");
assert.deepEqual(runtimePreview.sourceRegion, [3244.32, 1267.2, 3712.32, 1267.2]);
assert.throws(
  () => previewFromRuntimePayload({ ...runtimePayload, provider: "model" }),
  /Unexpected runtime provider/,
);

// --- Geometry validity + missing scale / invalid geometry guards ---
assert.equal(isValidTakeoffGeometry({ mode: "line", points: [[0, 0], [1, 0]] }), true);
assert.equal(isValidTakeoffGeometry({ mode: "line", points: [[0, 0]] }), false);
assert.equal(
  isValidTakeoffGeometry({ mode: "polygon", points: [[0, 0], [1, 0], [1, 1]] }),
  true,
);
assert.equal(
  isValidTakeoffGeometry({ mode: "polygon", points: [[0, 0], [0, 0], [1, 0]] }),
  false,
);
assert.throws(
  () => assertMeasurableRequest({ geometry: { mode: "line", points: [[0, 0], [1, 0]] }, scaleConfirmed: false }),
  /scale_unconfirmed/,
);
assert.throws(
  () => assertMeasurableRequest({ geometry: { mode: "line", points: [[0, 0]] }, scaleConfirmed: true }),
  /invalid_geometry/,
);

// --- Visual workbench coordinate mapping: displayed SVG pixels map back to the
// natural rendered sheet raster, including non-1000x700 sheets and pan/zoom. ---
assert.deepEqual(
  svgClientPointToSheetPoint({
    clientX: 510,
    clientY: 255,
    rect: { left: 10, top: 5, width: 500, height: 250 },
    raster: { width: 2400, height: 1800 },
    zoom: 1,
    pan: { x: 0, y: 0 },
  }),
  [2400, 1800],
);
assert.deepEqual(
  svgClientPointToSheetPoint({
    clientX: 260,
    clientY: 130,
    rect: { left: 10, top: 5, width: 500, height: 250 },
    raster: { width: 2400, height: 1800 },
    zoom: 2,
    pan: { x: 100, y: 200 },
  }),
  [550, 350],
);
assert.throws(
  () => svgClientPointToSheetPoint({
    clientX: 0,
    clientY: 0,
    rect: { left: 0, top: 0, width: 0, height: 100 },
    raster: { width: 2400, height: 1800 },
    zoom: 1,
    pan: { x: 0, y: 0 },
  }),
  /invalid_viewport_rect/,
);

// --- Workbench review actions ---
const now = "2026-07-16T00:00:00.000Z";

// approve keeps provider provenance but records reviewer/timestamp
const approved = applyWorkbenchAction(runtimePreview, "approve", { reviewer: "staff:est", timestamp: now });
assert.equal(approved.preview.reviewStatus, "approved");
assert.equal(approved.preview.provenance, "OpenTakeoff measured");
assert.equal(approved.preview.reviewer, "staff:est");
assert.equal(approved.correction, undefined);

// correct_geometry produces a full correction record + human-verified preview
const correctedGeometry: TakeoffGeometry = { mode: "line", points: [[3244.32, 1267.2], [3720, 1267.2]] };
const corrected = applyWorkbenchAction(runtimePreview, "correct_geometry", {
  reviewer: "staff:est",
  timestamp: now,
  correctedGeometry,
  correctedQuantity: 38.1,
  reason: "endpoint snapped to wrong grid line",
  scope: "ev_charging_conduit",
});
assert.ok(corrected.correction);
const corr = corrected.correction!;
assert.deepEqual(corr.originalGeometry, runtimePreview.markedGeometry);
assert.deepEqual(corr.correctedGeometry, correctedGeometry);
assert.equal(corr.originalQuantity, 37.5);
assert.equal(corr.correctedQuantity, 38.1);
assert.equal(corr.originalProviderResult.provider, "open_takeoff");
assert.equal(corr.finalEvidenceClass, "human_verified");
assert.equal(corr.pageNumber, 4);
assert.equal(corr.scale, "units_per_px:0.08012820512820511");
assert.equal(corr.trade, "electrical");
assert.equal(corr.scope, "ev_charging_conduit");
assert.equal(corr.condition, "PROOF-LINE");
assert.equal(corr.reviewer, "staff:est");
assert.equal(corr.trainingEligibility, "project_verified");
assert.equal(corrected.preview.provenance, "Human verified");
assert.equal(corrected.preview.provider, "human");
assert.equal(corrected.preview.reviewStatus, "corrected");
assert.equal(isHumanVerified(corrected.preview), true);

// correct_geometry requires geometry + quantity
assert.throws(
  () => applyWorkbenchAction(runtimePreview, "correct_geometry", { reviewer: "s", timestamp: now }),
  /requires corrected geometry/,
);

// reject leaves it non-training-eligible and NOT human verified
const rejected = applyWorkbenchAction(runtimePreview, "reject", {
  reviewer: "staff:est",
  timestamp: now,
  reason: "wrong sheet",
});
assert.equal(rejected.preview.reviewStatus, "rejected");
assert.notEqual(rejected.preview.provenance, "Human verified");
assert.equal(defaultTrainingEligibility(rejected.preview.provenance, rejected.preview.reviewStatus), "not_training_eligible");

// human replacement substitutes a human-verified measurement
const replaced = applyWorkbenchAction(runtimePreview, "replace_with_human_verified_measurement", {
  reviewer: "staff:est",
  timestamp: now,
  humanQuantity: 41.0,
  humanGeometry: { mode: "line", points: [[3200, 1260], [3720, 1260]] },
});
assert.equal(replaced.preview.reviewStatus, "replaced_by_human");
assert.equal(replaced.preview.provenance, "Human verified");
assert.equal(replaced.preview.provider, "human");
assert.equal(replaced.preview.quantity, 41.0);
assert.equal(isHumanVerified(replaced.preview), true);
assert.throws(
  () => applyWorkbenchAction(runtimePreview, "replace_with_human_verified_measurement", { reviewer: "s", timestamp: now }),
  /human replacement requires/,
);

// --- Worker job status model incl. failed + cancellation ---
assert.equal(nextWorkbenchJobStatus("queued", "start"), "running");
assert.equal(nextWorkbenchJobStatus("running", "await_scale"), "awaiting_scale_confirmation");
assert.equal(nextWorkbenchJobStatus("awaiting_scale_confirmation", "resume"), "running");
assert.equal(nextWorkbenchJobStatus("running", "complete"), "completed");
assert.equal(nextWorkbenchJobStatus("running", "fail"), "failed");
assert.equal(nextWorkbenchJobStatus("queued", "cancel"), "cancelled");
assert.equal(nextWorkbenchJobStatus("running", "cancel"), "cancelled");
assert.throws(() => nextWorkbenchJobStatus("completed", "start"), /terminal state/);
assert.throws(() => nextWorkbenchJobStatus("cancelled", "resume"), /terminal state/);
assert.throws(() => nextWorkbenchJobStatus("queued", "complete"), /Invalid job transition/);

// --- Estimator queue transitions ---
assert.equal(nextEstimatorQueueState("new_project", "documents_done"), "documents_processing");
assert.equal(nextEstimatorQueueState("documents_processing", "documents_done"), "ready_for_takeoff");
assert.equal(nextEstimatorQueueState("ready_for_takeoff", "takeoff_started"), "takeoff_in_progress");
assert.equal(nextEstimatorQueueState("takeoff_in_progress", "takeoff_ready_for_review"), "takeoff_review");
assert.equal(nextEstimatorQueueState("takeoff_review", "takeoff_approved"), "pricing_required");
assert.equal(nextEstimatorQueueState("pricing_required", "pricing_done"), "estimate_qa");
assert.equal(nextEstimatorQueueState("estimate_qa", "qa_done"), "ready_for_customer");
assert.equal(nextEstimatorQueueState("ready_for_customer", "revision_requested"), "revision_requested");
assert.equal(nextEstimatorQueueState("revision_requested", "takeoff_started"), "takeoff_in_progress");
assert.throws(() => nextEstimatorQueueState("new_project", "qa_done"), /Invalid queue transition/);

console.log("estimator workbench contract checks passed");
