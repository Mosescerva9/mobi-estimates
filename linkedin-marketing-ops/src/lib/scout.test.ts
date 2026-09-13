import assert from "node:assert/strict";
import { test } from "node:test";
import { emptyStore } from "./store";
import {
  SCOUT_JOB_BATCH_CAP,
  SCOUT_MAX_PENDING,
  applyCapture,
  applyScoutOutcomes,
  isDoNotContact,
  normalizeCapturedItem,
  occupiedPostKeys,
  rejectScoutCandidate,
  sanitizeForJob,
  scoutCounts,
  selectScoutBatch,
} from "./scout";
import type { EngageItem, ScoutCandidate, StoreData } from "./types";

const NOW = "2026-07-26T00:00:00.000Z";
const URL_A =
  "https://www.linkedin.com/posts/jordan-hale_bid-night-activity-7100000000000000001-abcd";
const URL_B =
  "https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000002";
const URL_C =
  "https://www.linkedin.com/posts/casey-lane_takeoff-activity-7100000000000000003-wxyz";

function capture(over: Record<string, unknown> = {}) {
  return {
    postUrl: URL_A,
    sourceText: "We poured the deck this week and the crew held the schedule tight.",
    authorName: "Jordan Hale",
    authorHeadline: "Senior Estimator",
    authorCompany: "Northline Construction",
    ...over,
  };
}

/* --------------------------------------------------------- normalization */

test("normalizeCapturedItem accepts a valid post and trims fields", () => {
  const res = normalizeCapturedItem(capture({ authorName: "  Jordan Hale  " }));
  assert.ok(res.ok);
  if (res.ok) {
    assert.equal(res.value.authorName, "Jordan Hale");
    assert.ok(res.value.postKey.includes("linkedin.com"));
  }
});

test("normalizeCapturedItem rejects a non-post LinkedIn URL", () => {
  const res = normalizeCapturedItem(capture({ postUrl: "https://www.linkedin.com/feed/" }));
  assert.equal(res.ok, false);
});

test("normalizeCapturedItem rejects an arbitrary non-LinkedIn URL", () => {
  const res = normalizeCapturedItem(capture({ postUrl: "https://evil.example/posts/x" }));
  assert.equal(res.ok, false);
});

test("normalizeCapturedItem rejects too little visible text", () => {
  const res = normalizeCapturedItem(capture({ sourceText: "hi" }));
  assert.equal(res.ok, false);
});

/* --------------------------------------------------------------- capture */

test("applyCapture dedupes within a batch and against existing candidates", () => {
  const store = emptyStore();
  let id = 0;
  const first = applyCapture(
    store,
    [capture(), capture(), capture({ postUrl: URL_B })],
    NOW,
    () => `scout_${id++}`
  );
  assert.equal(first.summary.accepted, 2);
  assert.equal(first.summary.duplicates, 1);

  const store2 = { ...store, scoutCandidates: first.candidates };
  const second = applyCapture(store2, [capture()], NOW, () => `scout_${id++}`);
  assert.equal(second.summary.accepted, 0);
  assert.equal(second.summary.duplicates, 1);
});

test("applyCapture counts invalid items without adding them", () => {
  const store = emptyStore();
  const res = applyCapture(
    store,
    [capture({ postUrl: "not-a-url" }), capture()],
    NOW,
    () => "scout_x"
  );
  assert.equal(res.summary.invalid, 1);
  assert.equal(res.summary.accepted, 1);
});

test("applyCapture treats a post already active in engage as a duplicate", () => {
  const store = emptyStore();
  store.engage = [
    {
      id: "eng_live",
      type: "engage",
      kind: "comment",
      status: "pending_approval",
      targetName: "Jordan Hale",
      targetTitle: "",
      targetCompany: "",
      sourcePostSummary: "x",
      sourcePostUrl: URL_A,
      suggestedText: "hi",
      createdAt: NOW,
      updatedAt: NOW,
      aiModel: "mock",
    },
  ];
  const res = applyCapture(store, [capture()], NOW, () => "scout_x");
  assert.equal(res.summary.accepted, 0);
  assert.equal(res.summary.duplicates, 1);
});

test("applyCapture enforces the pending cap", () => {
  const store = emptyStore();
  store.scoutCandidates = Array.from({ length: SCOUT_MAX_PENDING }, (_, i) => ({
    id: `c${i}`,
    type: "scout",
    status: "collected",
    postUrl: `https://www.linkedin.com/posts/x_a-activity-71000000000000${String(i).padStart(5, "0")}-abcd`,
    postKey: `www.linkedin.com/posts/x_a-activity-71000000000000${String(i).padStart(5, "0")}-abcd`,
    sourceText: "some visible construction text here",
    capturedAt: NOW,
    updatedAt: NOW,
  })) as ScoutCandidate[];
  const res = applyCapture(store, [capture()], NOW, () => "scout_new");
  assert.equal(res.summary.accepted, 0);
  assert.equal(res.summary.capacityRejected, 1);
});

/* --------------------------------------------------- do-not-contact / batch */

test("isDoNotContact matches case-insensitive substring", () => {
  assert.equal(isDoNotContact("Jordan Hale", ["hale"]), true);
  assert.equal(isDoNotContact("Jordan Hale", ["rival co"]), false);
  assert.equal(isDoNotContact(undefined, ["hale"]), false);
});

test("selectScoutBatch caps and includes do-not-contact so it can drain", () => {
  const base = emptyStore();
  base.settings.doNotContact = ["Rival"];
  base.scoutCandidates = [
    mkCandidate("a", "collected", "2026-07-26T00:00:01.000Z", "Ann"),
    mkCandidate("b", "queued", "2026-07-26T00:00:02.000Z", "Bob"),
    mkCandidate("c", "collected", "2026-07-26T00:00:00.000Z", "Rival Person"),
    mkCandidate("d", "collected", "2026-07-26T00:00:03.000Z", "Dan"),
  ];
  const batch = selectScoutBatch(base);
  assert.deepEqual(batch.map((c) => c.id), ["c", "a", "d"]);
});

test("sanitizeForJob omits internals and exposes only a do-not-contact boolean", () => {
  const c = mkCandidate("a", "collected", NOW, "Ann");
  c.model = "secret-model";
  c.postKey = "internal-key";
  const sanitized = sanitizeForJob(c, true);
  assert.equal("postKey" in sanitized, false);
  assert.equal("model" in sanitized, false);
  assert.equal(sanitized.postUrl, c.postUrl);
  assert.equal(sanitized.doNotContact, true);
});

/* --------------------------------------------------------- outcome apply */

function storeWithCandidates(cands: ScoutCandidate[]): StoreData {
  const s = emptyStore();
  s.scoutCandidates = cands;
  return s;
}

test("applyScoutOutcomes qualify creates exactly one bound EngageItem", () => {
  const c = mkCandidate("a", "collected", NOW, "Ann");
  const store = storeWithCandidates([c]);
  const { store: next, results } = applyScoutOutcomes(
    store,
    "batch1",
    [
      {
        candidateId: "a",
        decision: "qualify",
        suggestedComment: "Solid pour — holding that schedule is the hard part.",
        relevance: 80,
        reason: "construction relevance",
        safety: "safe",
      },
    ],
    "gpt-5.6-sol",
    NOW,
    () => "eng_1"
  );
  assert.equal(results[0].result, "queued");
  assert.equal(next.engage.length, 1);
  assert.equal(next.engage[0].sourcePostUrl, c.postUrl);
  assert.equal(next.engage[0].status, "pending_approval");
  assert.equal(next.scoutCandidates[0].status, "queued");
  assert.equal(next.scoutCandidates[0].engageItemId, "eng_1");
});

test("applyScoutOutcomes is idempotent on retry", () => {
  const c = mkCandidate("a", "collected", NOW, "Ann");
  const store = storeWithCandidates([c]);
  const first = applyScoutOutcomes(
    store,
    "batch1",
    [qualify("a")],
    "gpt-5.6-sol",
    NOW,
    () => "eng_1"
  );
  const second = applyScoutOutcomes(
    first.store,
    "batch1",
    [qualify("a")],
    "gpt-5.6-sol",
    NOW,
    () => "eng_2"
  );
  assert.equal(second.results[0].result, "already_processed");
  assert.equal(second.store.engage.length, 1);
});

test("applyScoutOutcomes skips with whitelisted reason", () => {
  const c = mkCandidate("a", "collected", NOW, "Ann");
  const { store: next, results } = applyScoutOutcomes(
    storeWithCandidates([c]),
    "b",
    [{ candidateId: "a", decision: "skip", reason: "sensitive" }],
    "gpt-5.6-sol",
    NOW
  );
  assert.equal(results[0].result, "skipped");
  assert.equal(next.scoutCandidates[0].status, "skipped");
  assert.equal(next.scoutCandidates[0].reason, "sensitive");
  assert.equal(next.engage.length, 0);
});

test("applyScoutOutcomes forces do-not-contact qualify to skip", () => {
  const c = mkCandidate("a", "collected", NOW, "Rival Person");
  const store = storeWithCandidates([c]);
  store.settings.doNotContact = ["Rival"];
  const { store: next, results } = applyScoutOutcomes(
    store,
    "b",
    [qualify("a")],
    "gpt-5.6-sol",
    NOW,
    () => "eng_1"
  );
  assert.equal(results[0].result, "skipped");
  assert.equal(next.engage.length, 0);
  assert.equal(next.scoutCandidates[0].reason, "do_not_contact");
});

test("applyScoutOutcomes does not create a duplicate engage draft for a live post", () => {
  const c = mkCandidate("a", "collected", NOW, "Ann");
  const store = storeWithCandidates([c]);
  store.engage = [
    {
      id: "eng_live",
      type: "engage",
      kind: "comment",
      status: "pending_approval",
      targetName: "Ann",
      targetTitle: "",
      targetCompany: "",
      sourcePostSummary: "x",
      sourcePostUrl: c.postUrl,
      suggestedText: "hi",
      createdAt: NOW,
      updatedAt: NOW,
      aiModel: "mock",
    } as EngageItem,
  ];
  const { store: next, results } = applyScoutOutcomes(
    store,
    "b",
    [qualify("a")],
    "gpt-5.6-sol",
    NOW,
    () => "eng_1"
  );
  assert.equal(results[0].result, "duplicate");
  assert.equal(next.engage.length, 1);
});

test("applyScoutOutcomes reports not_found for an unknown id and rejects a duplicate id in a batch", () => {
  const c = mkCandidate("a", "collected", NOW, "Ann");
  const { results } = applyScoutOutcomes(
    storeWithCandidates([c]),
    "b",
    [qualify("a"), qualify("a"), qualify("zzz")],
    "gpt-5.6-sol",
    NOW,
    () => "eng_1"
  );
  assert.equal(results[0].result, "queued");
  assert.equal(results[1].result, "already_processed");
  assert.equal(results[2].result, "not_found");
});

test("applyScoutOutcomes marks an over-limit comment as failed, not queued", () => {
  const c = mkCandidate("a", "collected", NOW, "Ann");
  const { store: next, results } = applyScoutOutcomes(
    storeWithCandidates([c]),
    "b",
    [
      {
        candidateId: "a",
        decision: "qualify",
        suggestedComment: "x".repeat(400),
        relevance: 50,
        reason: "r",
        safety: "safe",
      },
    ],
    "gpt-5.6-sol",
    NOW,
    () => "eng_1"
  );
  assert.equal(results[0].result, "invalid");
  assert.equal(next.scoutCandidates[0].status, "failed");
  assert.equal(next.engage.length, 0);
});

/* ------------------------------------------------------------ misc */

test("rejectScoutCandidate refuses a queued candidate but dismisses collected", () => {
  const collected = mkCandidate("a", "collected", NOW, "Ann");
  const okRes = rejectScoutCandidate(collected, NOW);
  assert.ok(okRes.ok);

  const queued = mkCandidate("b", "queued", NOW, "Bob");
  const bad = rejectScoutCandidate(queued, NOW);
  assert.equal(bad.ok, false);
});

test("scoutCounts tallies by status", () => {
  const counts = scoutCounts([
    mkCandidate("a", "collected", NOW, "A"),
    mkCandidate("b", "queued", NOW, "B"),
    mkCandidate("c", "skipped", NOW, "C"),
  ]);
  assert.equal(counts.collected, 1);
  assert.equal(counts.queued, 1);
  assert.equal(counts.skipped, 1);
  assert.equal(counts.total, 3);
});

test("occupiedPostKeys includes active candidates and engage comments", () => {
  const store = emptyStore();
  store.scoutCandidates = [mkCandidate("a", "collected", NOW, "Ann")];
  const keys = occupiedPostKeys(store);
  assert.equal(keys.has(store.scoutCandidates[0].postKey), true);
});

test("SCOUT_JOB_BATCH_CAP is 20", () => {
  assert.equal(SCOUT_JOB_BATCH_CAP, 20);
});

/* --------------------------------------------------------------- helpers */

function mkCandidate(
  id: string,
  status: ScoutCandidate["status"],
  capturedAt: string,
  authorName: string
): ScoutCandidate {
  const url = id === "a" ? URL_A : id === "b" ? URL_B : URL_C;
  return {
    id,
    type: "scout",
    status,
    postUrl: url,
    postKey: url.replace(/^https:\/\//, "").replace(/\/+$/, "").split("?")[0],
    sourceText: "Visible construction post text used for grounding a reply.",
    authorName,
    capturedAt,
    updatedAt: capturedAt,
  };
}

function qualify(candidateId: string) {
  return {
    candidateId,
    decision: "qualify" as const,
    suggestedComment: "Grounded, specific reply about the schedule.",
    relevance: 75,
    reason: "construction relevance",
    safety: "safe",
  };
}
