/**
 * Owner-triggered local Scout processing (no Hermes required).
 * Drafts comment recommendations into Engage for human approval.
 */

import { generateEngageDraft, modelLabel } from "./ai";
import {
  SCOUT_COMMENT_MAX,
  SCOUT_JOB_BATCH_CAP,
  applyScoutOutcomes,
  createBatchId,
  isDoNotContact,
  selectScoutBatch,
  type ScoutOutcome,
} from "./scout";
import type { ScoutCandidate, StoreData } from "./types";

const SENSITIVE =
  /\b(election|democrat|republican|trump|biden|war|killed|shooting|funeral|passed away|\brip\b|harassment|lawsuit)\b/i;

const CONSTRUCTION =
  /\b(estimat|takeoff|bid|contractor|gc\b|remodel|construction|subcontractor|quantity|blueprint|addend|rfi|jobsite|concrete|framing|hvac|plumbing|electrical|scope|markup|change order|project manager|\bpm\b)\b/i;

function decideSkip(candidate: ScoutCandidate, store: StoreData): ScoutOutcome | null {
  if (isDoNotContact(candidate.authorName, store.settings.doNotContact)) {
    return {
      candidateId: candidate.id,
      decision: "skip",
      reason: "do_not_contact",
    };
  }
  if (SENSITIVE.test(candidate.sourceText) || SENSITIVE.test(candidate.authorName || "")) {
    return {
      candidateId: candidate.id,
      decision: "skip",
      reason: "sensitive",
    };
  }
  if (candidate.sourceText.trim().length < 40) {
    return {
      candidateId: candidate.id,
      decision: "skip",
      reason: "insufficient_text",
    };
  }
  if (!CONSTRUCTION.test(candidate.sourceText + " " + (candidate.authorHeadline || ""))) {
    return {
      candidateId: candidate.id,
      decision: "skip",
      reason: "off_topic",
    };
  }
  return null;
}

export async function processScoutLocally(
  store: StoreData,
  limit = SCOUT_JOB_BATCH_CAP
): Promise<{
  store: StoreData;
  batchId: string;
  queued: number;
  skipped: number;
}> {
  const batch = selectScoutBatch(store, limit);
  const batchId = createBatchId();
  const outcomes: ScoutOutcome[] = [];

  for (const candidate of batch) {
    const skip = decideSkip(candidate, store);
    if (skip) {
      outcomes.push(skip);
      continue;
    }

    const draft = await generateEngageDraft(store.settings, {
      kind: "comment",
      targetName: candidate.authorName || "LinkedIn member",
      targetTitle: candidate.authorHeadline || "Construction professional",
      targetCompany: candidate.authorCompany || "their company",
      sourcePostSummary: candidate.sourceText.slice(0, 700),
    });

    const comment = draft.suggestedText.slice(0, SCOUT_COMMENT_MAX).trim();
    if (comment.length < 8) {
      outcomes.push({
        candidateId: candidate.id,
        decision: "skip",
        reason: "low_information",
      });
      continue;
    }

    outcomes.push({
      candidateId: candidate.id,
      decision: "qualify",
      suggestedComment: comment,
      relevance: 70,
      reason: "Construction/estimating relevance matched for a grounded comment.",
      safety: "No sensitive/political markers detected in local pre-check.",
    });
  }

  const applied = applyScoutOutcomes(
    store,
    batchId,
    outcomes,
    modelLabel(),
    new Date().toISOString()
  );

  const queued = applied.results.filter((r) => r.result === "queued").length;
  const skipped = applied.results.filter((r) => r.result === "skipped").length;

  return {
    store: applied.store,
    batchId,
    queued,
    skipped,
  };
}
