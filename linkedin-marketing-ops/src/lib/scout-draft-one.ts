/**
 * Intentional one-post comment drafting for the owner-triggered extension flow.
 *
 * Unlike batch Scout processing, this path does NOT skip for “off topic”: the
 * owner already chose the specific LinkedIn post. It still refuses do-not-contact
 * and sensitive content, and never posts to LinkedIn.
 */

import { generateEngageDraft, modelLabel } from "./ai";
import { isActiveEngageStatus } from "./engage";
import { linkedInPostKey } from "./linkedin-url";
import {
  SCOUT_COMMENT_MAX,
  applyCapture,
  applyScoutOutcomes,
  createBatchId,
  isDoNotContact,
  normalizeCapturedItem,
  type CapturedInput,
} from "./scout";
import type { EngageItem, ScoutCandidate, StoreData } from "./types";

const SENSITIVE =
  /\b(election|democrat|republican|trump|biden|war|killed|shooting|funeral|passed away|\brip\b|harassment|lawsuit)\b/i;

export type DraftOneResult =
  | { ok: true; store: StoreData; item: EngageItem; reused: boolean }
  | { ok: false; status: number; error: string };

function findActiveComment(
  store: StoreData,
  postKey: string
): EngageItem | undefined {
  return store.engage.find(
    (e) =>
      e.kind === "comment" &&
      isActiveEngageStatus(e.status) &&
      linkedInPostKey(e.sourcePostUrl) === postKey
  );
}

function findCandidateByKey(
  store: StoreData,
  postKey: string
): ScoutCandidate | undefined {
  return store.scoutCandidates.find((c) => c.postKey === postKey);
}

/**
 * Capture (if needed) and draft a pending comment for exactly one LinkedIn post.
 * Idempotent: if an active engage comment already exists for the post, returns it.
 */
export async function draftOneComment(
  store: StoreData,
  raw: CapturedInput,
  now: string = new Date().toISOString()
): Promise<DraftOneResult> {
  const normalized = normalizeCapturedItem(raw);
  if (!normalized.ok) {
    return { ok: false, status: 400, error: normalized.error };
  }

  const { postKey } = normalized.value;
  const existing = findActiveComment(store, postKey);
  if (existing) {
    return { ok: true, store, item: existing, reused: true };
  }

  // A queued candidate may already point at an engage item that was completed
  // or rejected; only reuse when that engage is still active (handled above).
  // Otherwise ensure we have a collected candidate to process.
  let working: StoreData = store;
  let candidate = findCandidateByKey(working, postKey);

  if (!candidate || candidate.status !== "collected") {
    // If it was previously skipped/failed/queued without an active engage,
    // re-capture by clearing that key from the occupied set is not possible
    // while the candidate still exists. For queued-without-active-engage we
    // treat as a fresh draft path by creating via applyCapture only when the
    // key is not occupied by an active candidate/engage.
    if (!candidate || candidate.status === "skipped" || candidate.status === "failed") {
      // Soft-reset: remove terminal candidates for this key so applyCapture can
      // accept the intentional re-draft.
      working = {
        ...working,
        scoutCandidates: working.scoutCandidates.filter(
          (c) => !(c.postKey === postKey && (c.status === "skipped" || c.status === "failed"))
        ),
      };
    }

    const captured = applyCapture(working, [raw], now);
    working = { ...working, scoutCandidates: captured.candidates };
    candidate = findCandidateByKey(working, postKey);

    if (!candidate || candidate.status !== "collected") {
      // Duplicates of collected/queued with no active engage — rare. Try the
      // collected candidate again; if still missing, explain.
      if (captured.summary.duplicates > 0 && candidate?.status === "queued") {
        return {
          ok: false,
          status: 409,
          error:
            "This post was already processed. Finish or reject the Engage draft first.",
        };
      }
      if (!candidate || candidate.status !== "collected") {
        return {
          ok: false,
          status: 400,
          error:
            captured.summary.invalid > 0
              ? "That LinkedIn post URL or text was not accepted."
              : "Could not save this post for drafting.",
        };
      }
    }
  }

  if (isDoNotContact(candidate.authorName, working.settings.doNotContact)) {
    return {
      ok: false,
      status: 422,
      error: "This author is on your do-not-contact list.",
    };
  }
  if (
    SENSITIVE.test(candidate.sourceText) ||
    SENSITIVE.test(candidate.authorName || "")
  ) {
    return {
      ok: false,
      status: 422,
      error: "This post looks sensitive — draft a comment yourself instead.",
    };
  }

  const draft = await generateEngageDraft(working.settings, {
    kind: "comment",
    targetName: candidate.authorName || "LinkedIn member",
    targetTitle: candidate.authorHeadline || "Construction professional",
    targetCompany: candidate.authorCompany || "their company",
    sourcePostSummary: candidate.sourceText.slice(0, 700),
  });

  const comment = draft.suggestedText.slice(0, SCOUT_COMMENT_MAX).trim();
  if (comment.length < 8) {
    return {
      ok: false,
      status: 502,
      error: "The draft came back empty. Try again in a moment.",
    };
  }

  const batchId = createBatchId();
  const applied = applyScoutOutcomes(
    working,
    batchId,
    [
      {
        candidateId: candidate.id,
        decision: "qualify",
        suggestedComment: comment,
        relevance: 90,
        reason: "Owner selected this exact post for a comment draft.",
        safety: "Sensitive/DNC pre-check passed for intentional draft.",
      },
    ],
    modelLabel(),
    now
  );

  const queued = applied.results.find((r) => r.result === "queued");
  if (!queued?.engageItemId) {
    const detail = applied.results[0]?.detail || applied.results[0]?.result;
    return {
      ok: false,
      status: 409,
      error:
        detail === "duplicate"
          ? "You already have an active comment for this post."
          : "Could not queue a comment draft for this post.",
    };
  }

  const item = applied.store.engage.find((e) => e.id === queued.engageItemId);
  if (!item) {
    return { ok: false, status: 500, error: "Draft was created but could not be loaded." };
  }

  return { ok: true, store: applied.store, item, reused: false };
}
