// Staff-only estimator takeoff workbench domain model.
//
// This module is the typed contract between the internal takeoff workbench UI
// and the REAL merged OpenTakeoff runtime (see
// mobi-estimating-phase1/scripts/opentakeoff_workbench_bridge.py). It carries
// provenance, review status, correction records, and interaction timing.
//
// Provenance labels are preserved EXACTLY and must never be mutated:
//   OpenTakeoff measured, Human verified, Schedule extracted,
//   Customer supplied, Model candidate.

export const TAKEOFF_PROVENANCE_LABELS = [
  "OpenTakeoff measured",
  "Human verified",
  "Schedule extracted",
  "Customer supplied",
  "Model candidate",
] as const;

export type TakeoffProvenanceLabel = (typeof TAKEOFF_PROVENANCE_LABELS)[number];

// Model candidates are AI suggestions that have NOT been human verified. They
// must remain visually and semantically distinct from "Human verified".
export const MODEL_CANDIDATE_LABEL: TakeoffProvenanceLabel = "Model candidate";
export const HUMAN_VERIFIED_LABEL: TakeoffProvenanceLabel = "Human verified";

export const ESTIMATOR_QUEUE_STATES = [
  "new_project",
  "documents_processing",
  "needs_clarification",
  "ready_for_takeoff",
  "takeoff_in_progress",
  "takeoff_review",
  "pricing_required",
  "estimate_qa",
  "ready_for_customer",
  "revision_requested",
] as const;

export type EstimatorQueueState = (typeof ESTIMATOR_QUEUE_STATES)[number];

export const TAKEOFF_WORKBENCH_ACTIONS = [
  "approve",
  "correct_geometry",
  "reject",
  "replace_with_human_verified_measurement",
] as const;

export type TakeoffWorkbenchAction = (typeof TAKEOFF_WORKBENCH_ACTIONS)[number];

// Mirrors the merged worker job lifecycle (queued/running/... /completed/failed
// /cancelled) at the granularity the workbench surface needs.
export const WORKBENCH_JOB_STATUSES = [
  "queued",
  "running",
  "awaiting_scale_confirmation",
  "awaiting_geometry_confirmation",
  "completed",
  "failed",
  "cancelled",
] as const;

export type WorkbenchJobStatus = (typeof WORKBENCH_JOB_STATUSES)[number];

export const WORKBENCH_TERMINAL_JOB_STATUSES: readonly WorkbenchJobStatus[] = [
  "completed",
  "failed",
  "cancelled",
];

export type TakeoffMeasurementMode = "line" | "polygon";

export type TakeoffProvider = "open_takeoff" | "human" | "schedule" | "customer" | "model";

// Evidence classes align with the Python EvidenceClass enum values.
export type EvidenceClass =
  | "measured"
  | "human_verified"
  | "schedule_extracted"
  | "customer_supplied"
  | "model_candidate";

export type ReviewStatus =
  | "pending"
  | "approved"
  | "corrected"
  | "rejected"
  | "replaced_by_human";

export const TRAINING_ELIGIBILITY_VALUES = [
  "project_verified",
  "company_preference_candidate",
  "general_training_candidate",
  "not_training_eligible",
] as const;

export type TrainingEligibility = (typeof TRAINING_ELIGIBILITY_VALUES)[number];

export type TakeoffUnit = "LF" | "SF" | "EA";

export interface TakeoffGeometry {
  mode: TakeoffMeasurementMode;
  // Pixel-space coordinates as marked on the sheet.
  points: Array<[number, number]>;
}

// Bounding box in the coordinate space used by the source (px) or normalized
// sheet space, mirroring CanonicalEvidence.region_coordinates.
export type RegionBox = [number, number, number, number];

// Required quantity display metadata for a single workbench measurement row.
export interface WorkbenchMeasurementPreview {
  measurementMode: TakeoffMeasurementMode;
  provenance: TakeoffProvenanceLabel;
  provider: TakeoffProvider;
  evidenceClass: EvidenceClass;
  reviewStatus: ReviewStatus;
  sheetId: string;
  pageNumber: number;
  scaleLabel: string;
  // Engine/provider version string, e.g. "opentakeoff-mcp@0.1.1".
  engineVersion: string;
  quantity: number;
  unit: TakeoffUnit;
  trade: string;
  scopeCategory: string;
  condition: string;
  // Geometry the estimator marked, plus the derived source region box.
  markedGeometry: TakeoffGeometry;
  sourceRegion: RegionBox | null;
  reviewer: string | null;
  timestamp: string | null;
  confidence: number | null;
  warning?: string;
}

export interface WorkbenchCorrectionRecord {
  originalGeometry: TakeoffGeometry | null;
  correctedGeometry: TakeoffGeometry;
  originalQuantity: number | null;
  correctedQuantity: number;
  // The raw provider result that was corrected (provider + record id + engine).
  originalProviderResult: {
    provider: TakeoffProvider;
    providerRecordId: string;
    engineVersion: string;
  };
  finalEvidenceClass: EvidenceClass;
  sheetId: string;
  pageNumber: number;
  scale: string;
  trade: string;
  scopeCategory: string;
  condition: string;
  scope: string;
  reason: string;
  reviewer: string;
  timestamp: string;
  providerVersion: string;
  trainingEligibility: TrainingEligibility;
}

// Interaction timing, in SECONDS, matching the workbench measurement targets.
export interface WorkbenchInteractionTiming {
  sheet_selection_seconds: number;
  scale_confirmation_seconds: number;
  geometry_definition_seconds: number;
  worker_wait_seconds: number;
  review_seconds: number;
  ai_suggestion_used: boolean;
  ai_suggestion_accepted: boolean | null;
}

export function totalInteractionSeconds(timing: WorkbenchInteractionTiming): number {
  const total =
    timing.sheet_selection_seconds +
    timing.scale_confirmation_seconds +
    timing.geometry_definition_seconds +
    timing.worker_wait_seconds +
    timing.review_seconds;
  return Math.round(total * 100) / 100;
}

// Simple line target: <= 60s. Simple polygon target: <= 120s.
export const SIMPLE_LINE_TARGET_SECONDS = 60;
export const SIMPLE_POLYGON_TARGET_SECONDS = 120;

export function isSimpleInteractionWithinTarget(
  mode: TakeoffMeasurementMode,
  timing: WorkbenchInteractionTiming,
): boolean {
  const seconds = totalInteractionSeconds(timing);
  return mode === "line"
    ? seconds <= SIMPLE_LINE_TARGET_SECONDS
    : seconds <= SIMPLE_POLYGON_TARGET_SECONDS;
}

// Unreviewed provider output and any model candidate default to
// not_training_eligible. Only a human decision can promote eligibility.
export function defaultTrainingEligibility(
  provenance: TakeoffProvenanceLabel,
  reviewStatus: ReviewStatus,
): TrainingEligibility {
  // Model candidates and any un-decided/rejected record are never eligible.
  if (provenance === MODEL_CANDIDATE_LABEL) return "not_training_eligible";
  if (reviewStatus === "pending" || reviewStatus === "rejected") {
    return "not_training_eligible";
  }
  // A human-decided record (approved/corrected/replaced) defaults to
  // project_verified; promotion beyond that is an explicit reviewer choice.
  return "project_verified";
}

export function isModelCandidate(preview: WorkbenchMeasurementPreview): boolean {
  return preview.provenance === MODEL_CANDIDATE_LABEL || preview.provider === "model";
}

export function isHumanVerified(preview: WorkbenchMeasurementPreview): boolean {
  return preview.provenance === HUMAN_VERIFIED_LABEL && preview.provider === "human";
}

export function assertWorkbenchPreviewProvenance(preview: WorkbenchMeasurementPreview): void {
  if (!TAKEOFF_PROVENANCE_LABELS.includes(preview.provenance)) {
    throw new Error("Unsupported takeoff provenance label");
  }
  if (preview.provenance === "OpenTakeoff measured" && preview.provider !== "open_takeoff") {
    throw new Error("OpenTakeoff measured preview must carry open_takeoff provider");
  }
  if (preview.provenance === "Human verified" && preview.provider !== "human") {
    throw new Error("Human verified preview must carry human provider");
  }
  if (preview.provenance === "Schedule extracted" && preview.provider !== "schedule") {
    throw new Error("Schedule extracted preview must carry schedule provider");
  }
  if (preview.provenance === "Customer supplied" && preview.provider !== "customer") {
    throw new Error("Customer supplied preview must carry customer provider");
  }
  // A model candidate is never presented as human verified and must expose a
  // confidence so reviewers can triage it.
  if (isModelCandidate(preview) && preview.provenance === HUMAN_VERIFIED_LABEL) {
    throw new Error("Model candidate must not be labelled Human verified");
  }
  if (preview.provenance === "Model candidate") {
    if (preview.provider !== "model") {
      throw new Error("Model candidate preview must carry model provider");
    }
    if (preview.confidence === null) {
      throw new Error("Model candidate preview must include confidence for review");
    }
    if (preview.reviewStatus === "approved" || preview.reviewStatus === "replaced_by_human") {
      throw new Error("Model candidate cannot already be approved/human-verified");
    }
  }
}

// Shape of the JSON emitted by the real runtime bridge script.
export interface RuntimeBridgePayload {
  runtime: string;
  engine_version: string;
  provider: string;
  provider_record_id: string;
  provenance_label: string;
  evidence_class: string;
  review_status: string;
  sheet_label: string;
  page_number: number;
  scale: string;
  quantity: number | null;
  unit: string;
  trade: string;
  scope_category: string;
  condition: string | null;
  region_coordinates: RegionBox | null;
  marked_geometry: { type: TakeoffMeasurementMode; pts: Array<[number, number]> };
  source_region: { bounding_box: RegionBox } | null;
}

// Connect the real merged runtime output to the workbench preview. This never
// fabricates a measurement; it maps actual runtime evidence into the UI model.
export function previewFromRuntimePayload(
  payload: RuntimeBridgePayload,
): WorkbenchMeasurementPreview {
  if (payload.provider !== "open_takeoff") {
    throw new Error(`Unexpected runtime provider: ${payload.provider}`);
  }
  if (payload.quantity === null) {
    throw new Error("Runtime payload is missing a measured quantity");
  }
  const preview: WorkbenchMeasurementPreview = {
    measurementMode: payload.marked_geometry.type,
    provenance: "OpenTakeoff measured",
    provider: "open_takeoff",
    evidenceClass: "measured",
    reviewStatus: "pending",
    sheetId: payload.sheet_label,
    pageNumber: payload.page_number,
    scaleLabel: payload.scale,
    engineVersion: payload.engine_version,
    quantity: payload.quantity,
    unit: payload.unit as TakeoffUnit,
    trade: payload.trade,
    scopeCategory: payload.scope_category,
    condition: payload.condition ?? "MEASURED",
    markedGeometry: {
      mode: payload.marked_geometry.type,
      points: payload.marked_geometry.pts,
    },
    sourceRegion: payload.source_region?.bounding_box ?? payload.region_coordinates,
    reviewer: null,
    timestamp: null,
    confidence: null,
  };
  assertWorkbenchPreviewProvenance(preview);
  return preview;
}

export interface WorkbenchReviewDecision {
  preview: WorkbenchMeasurementPreview;
  correction?: WorkbenchCorrectionRecord;
}

// Apply a staff review action, returning the resulting preview state (and a
// correction record where one is produced). Rejecting or replacing a provider
// result never keeps it flagged as human verified unless a human measurement
// is substituted.
export function applyWorkbenchAction(
  preview: WorkbenchMeasurementPreview,
  action: TakeoffWorkbenchAction,
  input: {
    reviewer: string;
    timestamp: string;
    reason?: string;
    correctedGeometry?: TakeoffGeometry;
    correctedQuantity?: number;
    humanQuantity?: number;
    humanGeometry?: TakeoffGeometry;
    scope?: string;
    trainingEligibility?: TrainingEligibility;
  },
): WorkbenchReviewDecision {
  const base = { ...preview, reviewer: input.reviewer, timestamp: input.timestamp };

  switch (action) {
    case "approve": {
      const evidenceClass: EvidenceClass =
        preview.provider === "open_takeoff" ? "measured" : preview.evidenceClass;
      return {
        preview: { ...base, reviewStatus: "approved", evidenceClass },
      };
    }
    case "correct_geometry": {
      if (!input.correctedGeometry || input.correctedQuantity === undefined) {
        throw new Error("correct_geometry requires corrected geometry and quantity");
      }
      const correction: WorkbenchCorrectionRecord = {
        originalGeometry: preview.markedGeometry,
        correctedGeometry: input.correctedGeometry,
        originalQuantity: preview.quantity,
        correctedQuantity: input.correctedQuantity,
        originalProviderResult: {
          provider: preview.provider,
          providerRecordId: `${preview.sheetId}:${preview.provenance}`,
          engineVersion: preview.engineVersion,
        },
        finalEvidenceClass: "human_verified",
        sheetId: preview.sheetId,
        pageNumber: preview.pageNumber,
        scale: preview.scaleLabel,
        trade: preview.trade,
        scopeCategory: preview.scopeCategory,
        condition: preview.condition,
        scope: input.scope ?? preview.scopeCategory,
        reason: input.reason ?? "geometry corrected by estimator",
        reviewer: input.reviewer,
        timestamp: input.timestamp,
        providerVersion: preview.engineVersion,
        trainingEligibility: input.trainingEligibility ?? "project_verified",
      };
      return {
        preview: {
          ...base,
          reviewStatus: "corrected",
          provenance: HUMAN_VERIFIED_LABEL,
          provider: "human",
          evidenceClass: "human_verified",
          quantity: input.correctedQuantity,
          markedGeometry: input.correctedGeometry,
          confidence: null,
        },
        correction,
      };
    }
    case "reject": {
      return {
        preview: { ...base, reviewStatus: "rejected" },
      };
    }
    case "replace_with_human_verified_measurement": {
      if (input.humanQuantity === undefined || !input.humanGeometry) {
        throw new Error("human replacement requires a human quantity and geometry");
      }
      return {
        preview: {
          ...base,
          reviewStatus: "replaced_by_human",
          provenance: HUMAN_VERIFIED_LABEL,
          provider: "human",
          evidenceClass: "human_verified",
          quantity: input.humanQuantity,
          markedGeometry: input.humanGeometry,
          confidence: null,
        },
      };
    }
    default: {
      const exhaustive: never = action;
      throw new Error(`Unsupported workbench action: ${exhaustive as string}`);
    }
  }
}

export function isValidTakeoffGeometry(geometry: TakeoffGeometry): boolean {
  if (geometry.mode === "line") {
    return geometry.points.length >= 2;
  }
  // A polygon needs at least three distinct vertices.
  if (geometry.points.length < 3) return false;
  const unique = new Set(geometry.points.map((p) => `${p[0]},${p[1]}`));
  return unique.size >= 3;
}

export function assertMeasurableRequest(input: {
  geometry: TakeoffGeometry;
  scaleConfirmed: boolean;
}): void {
  if (!input.scaleConfirmed) {
    throw new Error("scale_unconfirmed: explicit scale confirmation is required");
  }
  if (!isValidTakeoffGeometry(input.geometry)) {
    throw new Error("invalid_geometry: measurement geometry is degenerate");
  }
}

export function nextWorkbenchJobStatus(
  current: WorkbenchJobStatus,
  event:
    | "start"
    | "await_scale"
    | "await_geometry"
    | "resume"
    | "complete"
    | "fail"
    | "cancel",
): WorkbenchJobStatus {
  if (WORKBENCH_TERMINAL_JOB_STATUSES.includes(current)) {
    throw new Error(`Invalid job transition from terminal state: ${current}`);
  }
  const transitions: Record<WorkbenchJobStatus, Partial<Record<typeof event, WorkbenchJobStatus>>> = {
    queued: { start: "running", cancel: "cancelled", fail: "failed" },
    running: {
      await_scale: "awaiting_scale_confirmation",
      await_geometry: "awaiting_geometry_confirmation",
      complete: "completed",
      fail: "failed",
      cancel: "cancelled",
    },
    awaiting_scale_confirmation: { resume: "running", fail: "failed", cancel: "cancelled" },
    awaiting_geometry_confirmation: { resume: "running", fail: "failed", cancel: "cancelled" },
    completed: {},
    failed: {},
    cancelled: {},
  };
  const next = transitions[current][event];
  if (!next) throw new Error(`Invalid job transition: ${current} -> ${event}`);
  return next;
}

export function nextEstimatorQueueState(
  current: EstimatorQueueState,
  event:
    | "documents_done"
    | "clarification_needed"
    | "takeoff_started"
    | "takeoff_ready_for_review"
    | "takeoff_approved"
    | "pricing_done"
    | "qa_done"
    | "revision_requested",
): EstimatorQueueState {
  const transitions: Record<EstimatorQueueState, Partial<Record<typeof event, EstimatorQueueState>>> = {
    new_project: { documents_done: "documents_processing" },
    documents_processing: { documents_done: "ready_for_takeoff", clarification_needed: "needs_clarification" },
    needs_clarification: { documents_done: "ready_for_takeoff" },
    ready_for_takeoff: { takeoff_started: "takeoff_in_progress" },
    takeoff_in_progress: { takeoff_ready_for_review: "takeoff_review" },
    takeoff_review: { takeoff_approved: "pricing_required", clarification_needed: "needs_clarification" },
    pricing_required: { pricing_done: "estimate_qa" },
    estimate_qa: { qa_done: "ready_for_customer" },
    ready_for_customer: { revision_requested: "revision_requested" },
    revision_requested: { takeoff_started: "takeoff_in_progress" },
  };
  const next = transitions[current][event];
  if (!next) throw new Error(`Invalid queue transition: ${current} -> ${event}`);
  return next;
}
