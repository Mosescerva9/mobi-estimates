/**
 * Pure Scout domain logic, extracted from the API routes so it can be unit
 * tested without a running Next.js request, a browser, or a network. The routes
 * stay thin wrappers over these functions.
 *
 * Nothing here calls LinkedIn, sends anything, or performs I/O. Every mutation
 * is expressed as a pure transform over the in-memory store snapshot; the route
 * persists the result through the existing singleton compare-and-swap store.
 */

import { isActiveEngageStatus } from "./engage";
import { createId } from "./id";
import { linkedInPostKey, validateLinkedInPostUrl } from "./linkedin-url";
import type {
  EngageItem,
  ScoutCandidate,
  ScoutCandidateStatus,
  Settings,
  StoreData,
} from "./types";

/* --------------------------------------------------------------- constants */

/** Max captured items accepted in a single capture request from Safari. */
export const SCOUT_MAX_CAPTURE_ITEMS = 25;

/** Max candidates returned to (and outcomes accepted from) one Hermes job run. */
export const SCOUT_JOB_BATCH_CAP = 20;

/** Upper bound on collected (unprocessed) candidates, to bound store growth. */
export const SCOUT_MAX_PENDING = 200;

/** Field length caps applied server-side, independent of the Zod body limits. */
export const SCOUT_SOURCE_TEXT_MAX = 4000;
export const SCOUT_AUTHOR_FIELD_MAX = 400;

/** Comment length must match the Engage composer / approval limit. */
export const SCOUT_COMMENT_MAX = 300;

/** The only reasons the Hermes job may use to skip a candidate. */
export const SCOUT_SKIP_REASONS = [
  "off_topic",
  "sensitive",
  "low_information",
  "duplicate",
  "do_not_contact",
  "insufficient_text",
  "other",
] as const;

export type ScoutSkipReason = (typeof SCOUT_SKIP_REASONS)[number];

/* -------------------------------------------------------- capture validation */

export type CapturedInput = {
  postUrl?: unknown;
  sourceText?: unknown;
  authorName?: unknown;
  authorHeadline?: unknown;
  authorCompany?: unknown;
};

export type NormalizedCapture = {
  postUrl: string;
  postKey: string;
  sourceText: string;
  authorName?: string;
  authorHeadline?: string;
  authorCompany?: string;
};

export type CaptureValidation =
  | { ok: true; value: NormalizedCapture }
  | { ok: false; error: string };

function cleanField(value: unknown, max: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.slice(0, max);
}

/**
 * Validate and normalize one captured feed item. The URL must pass the strict
 * LinkedIn post validator (same guard the owner-facing flow uses), and there
 * must be enough visible text to ground a recommendation. Author fields are
 * optional and bounded. Never throws.
 */
export function normalizeCapturedItem(input: CapturedInput): CaptureValidation {
  const urlCheck = validateLinkedInPostUrl(input.postUrl);
  if (!urlCheck.ok) return { ok: false, error: urlCheck.error };

  const key = linkedInPostKey(urlCheck.url);
  if (!key) return { ok: false, error: "Could not derive a post key." };

  const sourceText = cleanField(input.sourceText, SCOUT_SOURCE_TEXT_MAX);
  if (!sourceText || sourceText.length < 8) {
    return {
      ok: false,
      error: "The captured post has too little visible text to be useful.",
    };
  }

  return {
    ok: true,
    value: {
      postUrl: urlCheck.url,
      postKey: key,
      sourceText,
      authorName: cleanField(input.authorName, SCOUT_AUTHOR_FIELD_MAX),
      authorHeadline: cleanField(input.authorHeadline, SCOUT_AUTHOR_FIELD_MAX),
      authorCompany: cleanField(input.authorCompany, SCOUT_AUTHOR_FIELD_MAX),
    },
  };
}

/* ------------------------------------------------------------------- dedupe */

/**
 * A candidate is "active" (occupies a Scout slot for its post) while it is
 * collected or already queued. Skipped/rejected/failed candidates are inactive
 * and do not block a fresh capture of the same post.
 */
export function isActiveCandidateStatus(status: ScoutCandidateStatus): boolean {
  return status === "collected" || status === "queued";
}

/** Set of post keys already spoken for — by an active candidate OR an active
 * engage comment. Capturing a post already in either queue is a no-op dedupe. */
export function occupiedPostKeys(store: {
  scoutCandidates: ScoutCandidate[];
  engage: EngageItem[];
}): Set<string> {
  const keys = new Set<string>();
  for (const c of store.scoutCandidates) {
    if (isActiveCandidateStatus(c.status)) keys.add(c.postKey);
  }
  for (const e of store.engage) {
    if (e.kind === "comment" && isActiveEngageStatus(e.status)) {
      const k = linkedInPostKey(e.sourcePostUrl);
      if (k) keys.add(k);
    }
  }
  return keys;
}

export type CaptureSummary = {
  accepted: number;
  duplicates: number;
  invalid: number;
  capacityRejected: number;
};

export type ApplyCaptureResult = {
  candidates: ScoutCandidate[];
  summary: CaptureSummary;
};

/**
 * Apply a batch of raw captured items to the current candidate list. Pure:
 * returns the NEW candidate array plus a count summary; the caller persists it.
 *
 *  - invalid items (bad URL, too little text) are counted and dropped;
 *  - items whose post key is already active (candidate or engage) are counted
 *    as duplicates and dropped, including duplicates within the same batch;
 *  - once the collected backlog reaches SCOUT_MAX_PENDING, further new items are
 *    counted as capacityRejected and dropped so the store cannot grow unbounded.
 */
export function applyCapture(
  store: { scoutCandidates: ScoutCandidate[]; engage: EngageItem[] },
  rawItems: CapturedInput[],
  now: string,
  makeId: () => string = () => createId("scout")
): ApplyCaptureResult {
  const occupied = occupiedPostKeys(store);
  const collectedCount = store.scoutCandidates.filter(
    (c) => c.status === "collected"
  ).length;

  const summary: CaptureSummary = {
    accepted: 0,
    duplicates: 0,
    invalid: 0,
    capacityRejected: 0,
  };
  const additions: ScoutCandidate[] = [];
  let pending = collectedCount;

  for (const raw of rawItems) {
    const check = normalizeCapturedItem(raw);
    if (!check.ok) {
      summary.invalid += 1;
      continue;
    }
    if (occupied.has(check.value.postKey)) {
      summary.duplicates += 1;
      continue;
    }
    if (pending >= SCOUT_MAX_PENDING) {
      summary.capacityRejected += 1;
      continue;
    }
    occupied.add(check.value.postKey);
    pending += 1;
    summary.accepted += 1;
    additions.push({
      id: makeId(),
      type: "scout",
      status: "collected",
      postUrl: check.value.postUrl,
      postKey: check.value.postKey,
      sourceText: check.value.sourceText,
      authorName: check.value.authorName,
      authorHeadline: check.value.authorHeadline,
      authorCompany: check.value.authorCompany,
      capturedAt: now,
      updatedAt: now,
    });
  }

  // Newest first, matching the rest of the queues.
  return { candidates: [...additions, ...store.scoutCandidates], summary };
}

/* ---------------------------------------------------- do-not-contact filter */

/** True when an author name matches any do-not-contact entry (case-insensitive
 * substring, same rule the Engage create flow uses). */
export function isDoNotContact(
  authorName: string | undefined,
  doNotContact: string[]
): boolean {
  if (!authorName) return false;
  const name = authorName.toLowerCase();
  return doNotContact.some((entry) => {
    const e = entry.trim().toLowerCase();
    return e.length > 0 && name.includes(e);
  });
}

/* -------------------------------------------------------- batch selection */

/**
 * Select collected candidates a Hermes job run should process, capped at
 * SCOUT_JOB_BATCH_CAP. Oldest first so the backlog drains fairly. Do-not-contact
 * candidates remain in the batch and are flagged by sanitizeForJob so the job
 * can durably skip them instead of leaving them collected forever.
 */
export function selectScoutBatch(
  store: { scoutCandidates: ScoutCandidate[]; settings: Settings },
  cap: number = SCOUT_JOB_BATCH_CAP
): ScoutCandidate[] {
  return store.scoutCandidates
    .filter((c) => c.status === "collected")
    .slice()
    .sort((a, b) => a.capturedAt.localeCompare(b.capturedAt))
    .slice(0, Math.max(0, cap));
}

/** Shape returned to the Hermes worker — no token/config, no internal keys the
 * worker does not need. */
export type ScoutJobCandidate = {
  id: string;
  postUrl: string;
  sourceText: string;
  authorName?: string;
  authorHeadline?: string;
  authorCompany?: string;
  capturedAt: string;
  doNotContact: boolean;
};

/** Fresh batch run id handed to the Hermes worker on GET and echoed back on
 * POST for audit. Not a security boundary — idempotency is enforced by
 * candidate status, not by the batch id. */
export function createBatchId(): string {
  return createId("batch");
}

export function sanitizeForJob(
  candidate: ScoutCandidate,
  doNotContact = false
): ScoutJobCandidate {
  return {
    id: candidate.id,
    postUrl: candidate.postUrl,
    sourceText: candidate.sourceText,
    authorName: candidate.authorName,
    authorHeadline: candidate.authorHeadline,
    authorCompany: candidate.authorCompany,
    capturedAt: candidate.capturedAt,
    doNotContact,
  };
}

/* ------------------------------------------------------ outcome application */

export type ScoutQualifyOutcome = {
  candidateId: string;
  decision: "qualify";
  suggestedComment: string;
  relevance: number;
  reason: string;
  safety: string;
};

export type ScoutSkipOutcome = {
  candidateId: string;
  decision: "skip";
  reason: ScoutSkipReason;
};

export type ScoutOutcome = ScoutQualifyOutcome | ScoutSkipOutcome;

export type OutcomeResult = {
  candidateId: string;
  result: "queued" | "skipped" | "already_processed" | "not_found" | "duplicate" | "invalid";
  engageItemId?: string;
  detail?: string;
};

export type ApplyOutcomesResult = {
  store: StoreData;
  results: OutcomeResult[];
};

/**
 * Apply a batch of Hermes outcomes to the store. Pure and idempotent:
 *
 *  - A qualify outcome atomically creates exactly ONE EngageItem (a pending
 *    comment bound to the candidate's exact source post), marks the candidate
 *    `queued`, and records the link. Re-applying the same batch is a no-op
 *    (`already_processed`) because the candidate is no longer `collected`.
 *  - If an active engage comment already exists for the post (race with a manual
 *    capture), the candidate is marked `skipped`/duplicate and NO second
 *    EngageItem is created.
 *  - A skip outcome marks the candidate `skipped` with the whitelisted reason.
 *  - Unknown ids are reported `not_found`; do-not-contact qualifies are demoted
 *    to a `skipped` do_not_contact result.
 *
 * Never calls LinkedIn and never sets any status past `pending_approval` — the
 * human approve/copy/post boundary is untouched.
 */
export function applyScoutOutcomes(
  store: StoreData,
  batchId: string,
  outcomes: ScoutOutcome[],
  model: string,
  now: string,
  makeEngageId: () => string = () => createId("eng")
): ApplyOutcomesResult {
  const candidates = store.scoutCandidates.map((c) => ({ ...c }));
  const engage = [...store.engage];
  const results: OutcomeResult[] = [];

  // Active engage comment keys, kept current as we add within this batch so two
  // outcomes for the same post in one run can't both create an EngageItem.
  const engageKeys = new Set<string>();
  for (const e of engage) {
    if (e.kind === "comment" && isActiveEngageStatus(e.status)) {
      const k = linkedInPostKey(e.sourcePostUrl);
      if (k) engageKeys.add(k);
    }
  }

  const seen = new Set<string>();
  for (const outcome of outcomes) {
    // Guard against a batch that lists the same candidate twice.
    if (seen.has(outcome.candidateId)) {
      results.push({ candidateId: outcome.candidateId, result: "already_processed" });
      continue;
    }
    seen.add(outcome.candidateId);

    const idx = candidates.findIndex((c) => c.id === outcome.candidateId);
    if (idx < 0) {
      results.push({ candidateId: outcome.candidateId, result: "not_found" });
      continue;
    }
    const candidate = candidates[idx];

    // Idempotency: only collected candidates are processable. A retry of an
    // already-queued/skipped candidate is a no-op.
    if (candidate.status !== "collected") {
      results.push({
        candidateId: candidate.id,
        result: "already_processed",
        engageItemId: candidate.engageItemId,
      });
      continue;
    }

    if (outcome.decision === "skip") {
      candidates[idx] = {
        ...candidate,
        status: "skipped",
        reason: outcome.reason,
        model,
        batchId,
        updatedAt: now,
      };
      results.push({ candidateId: candidate.id, result: "skipped", detail: outcome.reason });
      continue;
    }

    // decision === "qualify"
    if (isDoNotContact(candidate.authorName, store.settings.doNotContact)) {
      candidates[idx] = {
        ...candidate,
        status: "skipped",
        reason: "do_not_contact",
        model,
        batchId,
        updatedAt: now,
      };
      results.push({
        candidateId: candidate.id,
        result: "skipped",
        detail: "do_not_contact",
      });
      continue;
    }

    const comment = outcome.suggestedComment.trim();
    if (!comment || comment.length > SCOUT_COMMENT_MAX) {
      candidates[idx] = {
        ...candidate,
        status: "failed",
        reason: "invalid_comment",
        model,
        batchId,
        updatedAt: now,
      };
      results.push({ candidateId: candidate.id, result: "invalid", detail: "invalid_comment" });
      continue;
    }

    // Prevent a duplicate active engage draft for the same post.
    if (engageKeys.has(candidate.postKey)) {
      candidates[idx] = {
        ...candidate,
        status: "skipped",
        reason: "duplicate",
        model,
        batchId,
        updatedAt: now,
      };
      results.push({ candidateId: candidate.id, result: "duplicate", detail: "duplicate" });
      continue;
    }

    const engageId = makeEngageId();
    const engageItem: EngageItem = {
      id: engageId,
      type: "engage",
      kind: "comment",
      status: "pending_approval",
      targetName: candidate.authorName ?? "LinkedIn author",
      targetTitle: candidate.authorHeadline ?? "",
      targetCompany: candidate.authorCompany ?? "",
      sourcePostSummary: candidate.sourceText.slice(0, 600),
      sourcePostUrl: candidate.postUrl,
      suggestedText: comment,
      createdAt: now,
      updatedAt: now,
      aiModel: model,
    };
    engage.unshift(engageItem);
    engageKeys.add(candidate.postKey);

    candidates[idx] = {
      ...candidate,
      status: "queued",
      suggestedComment: comment,
      relevance: outcome.relevance,
      reason: outcome.reason,
      safety: outcome.safety,
      model,
      batchId,
      engageItemId: engageId,
      updatedAt: now,
    };
    results.push({ candidateId: candidate.id, result: "queued", engageItemId: engageId });
  }

  return {
    store: { ...store, engage, scoutCandidates: candidates },
    results,
  };
}

/* -------------------------------------------------------- owner dismissal */

export type RejectResult =
  | { ok: true; candidate: ScoutCandidate }
  | { ok: false; status: number; error: string };

/**
 * Owner dismisses a candidate from the Scout list. Allowed from any state that
 * has NOT already produced a live engage draft — a `queued` candidate is bound
 * to a pending EngageItem the owner reviews in Engage, so dismissing it here
 * would orphan that draft; refuse and point them at Engage instead.
 */
export function rejectScoutCandidate(
  candidate: ScoutCandidate,
  now: string
): RejectResult {
  if (candidate.status === "queued") {
    return {
      ok: false,
      status: 409,
      error:
        "This one already created a comment waiting for you in Engage. Handle it there.",
    };
  }
  if (candidate.status === "rejected") {
    return { ok: true, candidate };
  }
  return {
    ok: true,
    candidate: { ...candidate, status: "rejected", updatedAt: now },
  };
}

/* ------------------------------------------------------------------ counts */

export type ScoutCounts = {
  collected: number;
  queued: number;
  skipped: number;
  rejected: number;
  failed: number;
  total: number;
};

export function scoutCounts(candidates: ScoutCandidate[]): ScoutCounts {
  const counts: ScoutCounts = {
    collected: 0,
    queued: 0,
    skipped: 0,
    rejected: 0,
    failed: 0,
    total: candidates.length,
  };
  for (const c of candidates) counts[c.status] += 1;
  return counts;
}
