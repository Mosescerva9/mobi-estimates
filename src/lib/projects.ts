/**
 * Shared project-intake constants and helpers (safe for both client and server;
 * no server-only imports here).
 */

export const PROJECT_FILES_BUCKET = "project-files";
export const DELIVERABLES_BUCKET = "deliverables";

/** Deliverable categories for the staff upload form (deliverables.category). */
export const DELIVERABLE_CATEGORIES = [
  "Estimate summary",
  "Detailed takeoff",
  "Marked-up plans",
  "Proposal",
  "Other",
] as const;
export const DEFAULT_DELIVERABLE_CATEGORY = "Estimate summary";

/** All project_status values, in rough workflow order — used by the staff
 *  status-change dropdown (0001_schema.sql project_status enum). */
export const ALL_STATUSES = [
  "draft",
  "submitted",
  "needs_information",
  "under_internal_review",
  "accepted",
  "scheduled",
  "document_review",
  "takeoff_in_progress",
  "pricing_in_progress",
  "clarification_required",
  "qa_review",
  "ready_for_delivery",
  "delivered",
  "revision_requested",
  "revised",
  "approved",
  "closed",
  "canceled",
] as const;

/** Per-file size cap. Must match storage.buckets.file_size_limit (0004 migration). */
export const MAX_FILE_BYTES = 26214400; // 25 MB
export const MAX_FILES = 25;

/** Allowed upload extensions. CAD MIME types are unreliable, so we gate on
 *  extension in the app layer; the private bucket + size cap + RLS are the
 *  security boundary. Keep in sync with the marketing site's ACCEPTED_FILE_TYPES. */
export const ACCEPTED_EXTENSIONS = [
  ".pdf", ".dwg", ".dwf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls", ".csv", ".zip",
] as const;

/** `accept` attribute for the <input type="file">. */
export const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.join(",");

/** project_type enum (0001_schema.sql). */
export const PROJECT_TYPES: { value: string; label: string }[] = [
  { value: "residential", label: "Residential" },
  { value: "commercial", label: "Commercial" },
  { value: "industrial", label: "Industrial" },
  { value: "civil", label: "Civil" },
  { value: "infrastructure", label: "Infrastructure" },
  { value: "mixed", label: "Mixed-use" },
];
export const PROJECT_TYPE_VALUES = PROJECT_TYPES.map((t) => t.value);

/** Document categories for project_files.category (NOT NULL). */
export const FILE_CATEGORIES = [
  "Drawings",
  "Specifications",
  "Addenda",
  "Scope / Bid Docs",
  "Other",
] as const;
export const DEFAULT_FILE_CATEGORY = "Drawings";

export function lowerExt(fileName: string): string {
  const i = fileName.lastIndexOf(".");
  return i >= 0 ? fileName.slice(i).toLowerCase() : "";
}

export function isAllowedExtension(fileName: string): boolean {
  return (ACCEPTED_EXTENSIONS as readonly string[]).includes(lowerExt(fileName));
}

/**
 * Make a filename safe for a storage key: drop any path, replace unsafe chars
 * with "-", collapse repeats, and cap length (preserving the extension).
 */
export function sanitizeFilename(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? name;
  const ext = lowerExt(base);
  const stem = ext ? base.slice(0, base.length - ext.length) : base;
  const safeStem = stem
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "")
    .slice(0, 80) || "file";
  return safeStem + ext;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** Build the storage key for a project file: {company}/{project}/{ts}-{name}. */
export function buildStoragePath(companyId: string, projectId: string, fileName: string): string {
  return `${companyId}/${projectId}/${Date.now()}-${sanitizeFilename(fileName)}`;
}

// ---- status presentation --------------------------------------------------
type Tone = "slate" | "blue" | "amber" | "green" | "red";

const STATUS_META: Record<string, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "slate" },
  submitted: { label: "Submitted", tone: "blue" },
  needs_information: { label: "Needs information", tone: "amber" },
  under_internal_review: { label: "Under review", tone: "blue" },
  accepted: { label: "Accepted", tone: "blue" },
  scheduled: { label: "Scheduled", tone: "blue" },
  document_review: { label: "Document review", tone: "blue" },
  takeoff_in_progress: { label: "Takeoff in progress", tone: "blue" },
  pricing_in_progress: { label: "Pricing in progress", tone: "blue" },
  clarification_required: { label: "Clarification required", tone: "amber" },
  qa_review: { label: "Quality check", tone: "blue" },
  ready_for_delivery: { label: "Ready for delivery", tone: "green" },
  delivered: { label: "Delivered", tone: "green" },
  revision_requested: { label: "Revision requested", tone: "amber" },
  revised: { label: "Revised", tone: "blue" },
  approved: { label: "Approved", tone: "green" },
  closed: { label: "Closed", tone: "slate" },
  canceled: { label: "Canceled", tone: "slate" },
};

const TONE_CLASSES: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-600",
  blue: "bg-blue-50 text-blue-700",
  amber: "bg-amber-50 text-amber-700",
  green: "bg-green-50 text-green-700",
  red: "bg-red-50 text-red-700",
};

export function statusLabel(status: string): string {
  return STATUS_META[status]?.label ?? status;
}

export function statusBadgeClass(status: string): string {
  return TONE_CLASSES[STATUS_META[status]?.tone ?? "slate"];
}
