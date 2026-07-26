import type { ItemStatus } from "./types";

/**
 * Plain-language labels for the owner-facing status chips.
 * These exact strings are what the dashboard shows — keep them human.
 */
const STATUS_LABELS: Record<ItemStatus, string> = {
  draft: "Draft",
  pending_approval: "Needs approval",
  approved: "Approved",
  scheduled: "Scheduled",
  published: "Published",
  sent: "Sent",
  rejected: "Rejected",
  skipped: "Skipped",
};

export function statusLabel(status: ItemStatus): string {
  return STATUS_LABELS[status] ?? status;
}

/** Statuses that still need the owner to act (used for the daily queue). */
export function needsAttention(status: ItemStatus): boolean {
  return status === "pending_approval";
}
