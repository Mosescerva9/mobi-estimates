// Customer-safe revision history normalization.
//
// The estimating engine's customer-history endpoint already returns
// human-readable, customer-safe *label values*, but under its own field names
// (`action`, `status`, `trade`, `sheet_refs[]`, `follow_up`,
// `latest_version_at`). The portal view model uses different, explicit
// `*_label` field names and a scalar `sheet_ref`. This module maps between the
// two with an explicit whitelist so raw engine fields (parser text, internal
// notes, reviewers, snapshots, readiness/pricing internals, payloads, unknown
// enums) can never pass through to the customer UI.

export type CustomerRevisionHistoryItem = {
  id: string;
  status_label: string;
  requested_action_label: string;
  trade_label?: string | null;
  sheet_ref?: string | null;
  summary: string;
  follow_up_label?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  version_count?: number;
  latest_version_created_at?: string | null;
};

export type CustomerRevisionHistoryResult = {
  available: boolean;
  reason?: "engine_unavailable" | "project_unlinked" | "failed";
  items: CustomerRevisionHistoryItem[];
};

/** Shape the engine's customer-history endpoint emits (all optional/defensive). */
export type EngineRevisionHistoryItem = {
  id?: unknown;
  action?: unknown;
  status?: unknown;
  trade?: unknown;
  summary?: unknown;
  sheet_refs?: unknown;
  follow_up?: unknown;
  version_count?: unknown;
  latest_version_at?: unknown;
  created_at?: unknown;
  updated_at?: unknown;
};

function optLabel(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/** Collapse the engine's safe `sheet_refs[]` to the first non-empty scalar ref. */
function firstSheetRef(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  for (const ref of value) {
    if (typeof ref !== "string") continue;
    const trimmed = ref.trim();
    if (trimmed.length > 0) return trimmed;
  }
  return null;
}

function optCount(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return undefined;
}

/**
 * Map one engine-shaped history item to the customer-safe portal view model.
 *
 * Only known, already-safe label fields are read; every other engine field is
 * dropped. The engine supplies display labels (e.g. "Received", "Include"),
 * never raw enums, so no additional label lookup is performed here.
 */
export function normalizeCustomerRevisionHistoryItem(
  raw: EngineRevisionHistoryItem,
): CustomerRevisionHistoryItem {
  return {
    id: typeof raw.id === "string" ? raw.id : String(raw.id ?? ""),
    requested_action_label: optLabel(raw.action) ?? "Review",
    status_label: optLabel(raw.status) ?? "In review",
    trade_label: optLabel(raw.trade),
    sheet_ref: firstSheetRef(raw.sheet_refs),
    summary: optLabel(raw.summary) ?? "Revision request received.",
    follow_up_label: optLabel(raw.follow_up),
    version_count: optCount(raw.version_count),
    latest_version_created_at: optLabel(raw.latest_version_at),
    created_at: optLabel(raw.created_at),
    updated_at: optLabel(raw.updated_at),
  };
}

export function normalizeCustomerRevisionHistory(
  items: EngineRevisionHistoryItem[] | undefined | null,
): CustomerRevisionHistoryItem[] {
  if (!Array.isArray(items)) return [];
  return items.map(normalizeCustomerRevisionHistoryItem);
}
