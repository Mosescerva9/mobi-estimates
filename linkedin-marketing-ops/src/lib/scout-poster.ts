/**
 * Extension poster helpers: claim an approved comment for a LinkedIn post and
 * complete it after the owner-approved submit succeeds on the page.
 *
 * These never call LinkedIn themselves — they only manage Engage state for the
 * browser extension that fills the comment box after human approval.
 */

import { approveEngageItem, markCommented } from "./engage";
import { linkedInPostKey, validateLinkedInPostUrl } from "./linkedin-url";
import type { EngageItem, StoreData } from "./types";

export type PosterClaimResult =
  | { ok: true; item: EngageItem }
  | { ok: false; status: number; error: string };

/**
 * Find the next approved comment ready for the extension to submit.
 * When `postUrl` is supplied, only a matching post is returned.
 */
export function claimApprovedComment(
  store: StoreData,
  postUrl?: string
): PosterClaimResult {
  let approved = store.engage.filter(
    (e) => e.kind === "comment" && e.status === "approved"
  );

  if (typeof postUrl === "string" && postUrl.trim()) {
    const check = validateLinkedInPostUrl(postUrl);
    if (!check.ok) {
      return { ok: false, status: 400, error: check.error };
    }
    const key = linkedInPostKey(check.url);
    approved = approved.filter((e) => linkedInPostKey(e.sourcePostUrl) === key);
  }

  // Oldest approval first so a backlog drains fairly.
  approved.sort((a, b) => a.updatedAt.localeCompare(b.updatedAt));
  const item = approved[0];
  if (!item) {
    return {
      ok: false,
      status: 404,
      error: postUrl
        ? "No approved comment is waiting for this LinkedIn post."
        : "No approved comments are waiting to be posted.",
    };
  }
  return { ok: true, item };
}

export type PosterApproveResult =
  | { ok: true; store: StoreData; item: EngageItem }
  | { ok: false; status: number; error: string };

export function approveForPoster(
  store: StoreData,
  engageId: string,
  suggestedText: string | undefined,
  sourcePostUrl: string | undefined,
  now: string
): PosterApproveResult {
  const idx = store.engage.findIndex((e) => e.id === engageId);
  if (idx < 0) {
    return { ok: false, status: 404, error: "Engage item not found." };
  }
  const result = approveEngageItem(
    store.engage[idx],
    suggestedText,
    now,
    sourcePostUrl
  );
  if (!result.ok) {
    return { ok: false, status: result.status, error: result.error };
  }
  const engage = [...store.engage];
  engage[idx] = result.item;
  return { ok: true, store: { ...store, engage }, item: result.item };
}

export type PosterCompleteResult =
  | { ok: true; store: StoreData; item: EngageItem }
  | { ok: false; status: number; error: string };

export function completePostedComment(
  store: StoreData,
  engageId: string,
  now: string
): PosterCompleteResult {
  const idx = store.engage.findIndex((e) => e.id === engageId);
  if (idx < 0) {
    return { ok: false, status: 404, error: "Engage item not found." };
  }
  const result = markCommented(store.engage[idx], now);
  if (!result.ok) {
    return { ok: false, status: result.status, error: result.error };
  }
  const engage = [...store.engage];
  engage[idx] = result.item;
  return { ok: true, store: { ...store, engage }, item: result.item };
}

/** Public shape returned to the extension (no internal-only fields required). */
export function posterItemPayload(item: EngageItem) {
  return {
    id: item.id,
    status: item.status,
    suggestedText: item.suggestedText,
    sourcePostUrl: item.sourcePostUrl ?? null,
    targetName: item.targetName,
    sourcePostSummary: item.sourcePostSummary,
  };
}
