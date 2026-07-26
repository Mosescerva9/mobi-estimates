/**
 * Pure engage-queue rules, extracted from the API routes so they can be tested
 * without a running Next.js request or a browser. The routes stay thin wrappers
 * over these functions.
 */

import { linkedInPostKey, validateLinkedInPostUrl } from "./linkedin-url";
import { statusLabel } from "./status";
import type { EngageItem, EngageKind, ItemStatus } from "./types";

/**
 * An engage item is "active" while it still occupies the owner's queue: it is
 * either awaiting approval or approved-but-not-yet-completed. Rejected, skipped
 * and completed (sent) items are inactive and do not block a fresh capture.
 */
export function isActiveEngageStatus(status: ItemStatus): boolean {
  return status === "pending_approval" || status === "approved";
}

export type EngageCreateCheck =
  | { ok: true; sourcePostUrl?: string }
  | { ok: false; status: number; error: string };

/**
 * Validate a new engage capture and, for comments, enforce the post-URL rules:
 *  - a comment REQUIRES a valid LinkedIn post URL;
 *  - a duplicate active comment for the same normalized URL is rejected (409);
 *  - a connection note may optionally carry a URL and is otherwise unchanged.
 * Returns the normalized URL to persist on success.
 */
export function checkEngageCreate(
  input: { kind: EngageKind; sourcePostUrl?: string },
  existing: EngageItem[]
): EngageCreateCheck {
  if (input.kind === "comment") {
    const check = validateLinkedInPostUrl(input.sourcePostUrl);
    if (!check.ok) return { ok: false, status: 400, error: check.error };

    const key = linkedInPostKey(check.url);
    const duplicate = existing.some(
      (e) =>
        e.kind === "comment" &&
        isActiveEngageStatus(e.status) &&
        linkedInPostKey(e.sourcePostUrl) === key
    );
    if (duplicate) {
      return {
        ok: false,
        status: 409,
        error:
          "You already have an active comment saved for this post. Finish or remove it before adding another.",
      };
    }
    return { ok: true, sourcePostUrl: check.url };
  }

  // Connection notes: a URL is optional and only kept if it validates, so the
  // existing connect flow keeps working with or without one.
  if (typeof input.sourcePostUrl === "string" && input.sourcePostUrl.trim()) {
    const check = validateLinkedInPostUrl(input.sourcePostUrl);
    if (check.ok) return { ok: true, sourcePostUrl: check.url };
  }
  return { ok: true };
}

/**
 * Maximum length for an approved engage message, matching the composer limit in
 * the dashboard. LinkedIn comments and connection notes are both short-form.
 */
export const ENGAGE_TEXT_MAX_LEN = 300;

export type EngageGuard = { ok: true } | { ok: false; status: number; error: string };

/**
 * Edit and regenerate are only valid while an item is still `pending_approval`.
 * Once it is approved (or sent/rejected/skipped) the text is frozen — approving
 * copies that exact text to LinkedIn, so it must never change underneath the
 * owner afterwards. The route calls this before applying either mutation and
 * returns the 409 verbatim so the owner sees why the change was refused.
 */
export function checkEngageEditable(
  item: EngageItem,
  action: "edit" | "regenerate"
): EngageGuard {
  if (item.status === "pending_approval") return { ok: true };
  const noun = item.kind === "comment" ? "comment" : "note";
  const verb = action === "regenerate" ? "rewritten" : "edited";
  return {
    ok: false,
    status: 409,
    error: `This ${noun} can’t be ${verb} now (it is “${statusLabel(item.status)}”). Approved and sent text can’t be changed.`,
  };
}

export type SetSourceUrlResult =
  | { ok: true; item: EngageItem }
  | { ok: false; status: number; error: string };

/**
 * Attach or repair the LinkedIn post URL on a *pending comment*. This is the
 * owner-friendly way to fix a legacy comment that was captured before the URL
 * was required: instead of a dead end, they can paste the post link and try
 * approving again. It is deliberately narrow — comment-only, pending-only, and
 * server-validated by the strict post validator — so a URL can never be added
 * or changed after approval, keeping the approved target immutable.
 */
export function setEngageSourceUrl(
  item: EngageItem,
  url: unknown,
  now: string
): SetSourceUrlResult {
  if (item.kind !== "comment") {
    return { ok: false, status: 409, error: "Only comments have a post link." };
  }
  if (item.status !== "pending_approval") {
    return {
      ok: false,
      status: 409,
      error: `This comment’s post link can’t be changed now (it is “${statusLabel(item.status)}”).`,
    };
  }
  const check = validateLinkedInPostUrl(url);
  if (!check.ok) return { ok: false, status: 400, error: check.error };
  return { ok: true, item: { ...item, sourcePostUrl: check.url, updatedAt: now } };
}

/**
 * Bind a comment approval to the exact post the owner reviewed. The client sends
 * the post URL it is currently showing as `expectedSourcePostUrl`; we require it
 * to resolve to the *same* stored post target before approving. This closes a
 * stale-client / legacy URL-repair race: if the stored URL changed to a
 * different post since the page loaded (e.g. the owner repaired a legacy comment
 * in another tab), the owner would otherwise approve — and have the browser open
 * and copy against — a post they never actually saw. Comment-only; connection
 * notes carry no post target and are exempt.
 *
 * The expected URL must itself pass the strict post validator (so an omitted or
 * garbage value is rejected), and its normalized post key must match the stored
 * item's key. Both failures are owner-readable 409s asking them to reload.
 */
export function checkApproveTargetBinding(
  item: EngageItem,
  expectedSourcePostUrl: string | undefined
): EngageGuard {
  if (item.kind !== "comment") return { ok: true };

  const expected = validateLinkedInPostUrl(expectedSourcePostUrl);
  if (!expected.ok) {
    return {
      ok: false,
      status: 409,
      error:
        "Reload this page and approve again — we couldn’t confirm which LinkedIn post this comment is for.",
    };
  }
  if (linkedInPostKey(expected.url) !== linkedInPostKey(item.sourcePostUrl)) {
    return {
      ok: false,
      status: 409,
      error:
        "This comment’s post link changed since you opened it. Reload the page, re-check the post, and approve again.",
    };
  }
  return { ok: true };
}

export type ApproveEngageResult =
  | { ok: true; item: EngageItem }
  | { ok: false; status: number; error: string };

/**
 * Atomically validate and apply an approval. The text that becomes approved is
 * the exact `suggestedText` supplied in the approve request, so the copy the
 * owner takes matches what was persisted even if a concurrent edit lands between
 * the click and the write. When `suggestedText` is omitted we fall back to the
 * item's current text, preserving the older edit-then-approve call path.
 *
 * For comments, `expectedSourcePostUrl` (the URL the client is about to open)
 * must be supplied and must resolve to the same stored post target — see
 * checkApproveTargetBinding. The route returns the fresh stored item so the
 * client navigates and copies from server truth, not its pre-request values.
 *
 * Enforces the pending_approval -> approved transition and rejects empty or
 * over-limit text with an owner-readable message. The supplied text is stored
 * verbatim (no trimming) so the approved text and the copied text are identical.
 */
export function approveEngageItem(
  item: EngageItem,
  suggestedText: string | undefined,
  now: string,
  expectedSourcePostUrl?: string
): ApproveEngageResult {
  const noun = item.kind === "comment" ? "comment" : "note";

  if (item.status !== "pending_approval") {
    return {
      ok: false,
      status: 409,
      error: `This ${noun} can’t be approved right now (it is “${statusLabel(item.status)}”).`,
    };
  }

  // A comment must never be approved without a stored URL that passes the strict
  // post validator. "Approve & open post" navigates to this URL, and legacy
  // records captured before the URL was required can reach here without one — so
  // we re-validate the persisted value at the moment of approval, not just at
  // capture time. The owner repairs it via setEngageSourceUrl.
  if (item.kind === "comment") {
    const urlCheck = validateLinkedInPostUrl(item.sourcePostUrl);
    if (!urlCheck.ok) {
      return {
        ok: false,
        status: 422,
        error:
          "Add a valid LinkedIn post URL to this comment before approving it, so the correct post opens.",
      };
    }
  }

  // Bind the approval to the exact post the client is showing so the tab that
  // opens and the text that is copied match what the owner reviewed.
  const binding = checkApproveTargetBinding(item, expectedSourcePostUrl);
  if (!binding.ok) return binding;

  const text = suggestedText === undefined ? item.suggestedText : suggestedText;

  if (text.trim().length === 0) {
    return {
      ok: false,
      status: 400,
      error: `Add some text before approving — an empty ${noun} can’t be approved.`,
    };
  }
  if (text.length > ENGAGE_TEXT_MAX_LEN) {
    return {
      ok: false,
      status: 400,
      error: `Trim this ${noun} to ${ENGAGE_TEXT_MAX_LEN} characters or fewer before approving (it is ${text.length} now).`,
    };
  }

  return {
    ok: true,
    item: { ...item, suggestedText: text, status: "approved", updatedAt: now },
  };
}

export type EngageTransitionResult =
  | { ok: true; item: EngageItem }
  | { ok: false; status: number; error: string };

/**
 * Reject or skip an engage item. Both are terminal and are valid ONLY from
 * pending_approval: an approved item may already have copy the owner has pasted
 * on LinkedIn, and sent/rejected/skipped items are already final. The UI only
 * shows Reject/Skip on pending items, but the server enforces it too so a stale
 * tab or a direct API call can't clobber an already-decided item. Returns an
 * owner-readable 409 for any non-pending state.
 */
export function transitionPendingEngage(
  item: EngageItem,
  target: "rejected" | "skipped",
  now: string
): EngageTransitionResult {
  if (item.status !== "pending_approval") {
    const noun = item.kind === "comment" ? "comment" : "note";
    const verb = target === "rejected" ? "rejected" : "skipped";
    return {
      ok: false,
      status: 409,
      error: `This ${noun} can’t be ${verb} now (it is “${statusLabel(item.status)}”). Only items waiting for approval can be ${verb}.`,
    };
  }
  return { ok: true, item: { ...item, status: target, updatedAt: now } };
}

export type MarkCommentedResult =
  | { ok: true; item: EngageItem }
  | { ok: false; status: number; error: string };

/**
 * Owner confirms they pasted and posted the comment on LinkedIn. Valid only for
 * an approved comment; it moves to the existing `sent` status and records when
 * it was completed. This never sends anything — it only records human action.
 */
export function markCommented(item: EngageItem, now: string): MarkCommentedResult {
  if (item.kind !== "comment") {
    return {
      ok: false,
      status: 409,
      error: "Only comments can be marked as commented.",
    };
  }
  if (item.status !== "approved") {
    return {
      ok: false,
      status: 409,
      error: `This comment is not approved yet (it is “${statusLabel(item.status)}”).`,
    };
  }
  return {
    ok: true,
    item: { ...item, status: "sent", completedAt: now, updatedAt: now },
  };
}

/**
 * Owner-facing label. A completed comment uses the existing `sent` status
 * internally but reads as "Commented"; everything else uses the shared labels.
 */
export function engageStatusLabel(item: Pick<EngageItem, "kind" | "status">): string {
  if (item.kind === "comment" && item.status === "sent") return "Commented";
  return statusLabel(item.status);
}
