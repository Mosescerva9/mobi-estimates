import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import {
  aiMode,
  buildMockComment,
  generateEngageDraft,
  generatePostDrafts,
  modelLabel,
} from "./ai";
import { ENGAGE_TEXT_MAX_LEN } from "./engage";
import { DEFAULT_SETTINGS } from "./prompts";

const savedKey = process.env.OPENAI_API_KEY;
const savedModel = process.env.OPENAI_MODEL;

afterEach(() => {
  if (savedKey === undefined) delete process.env.OPENAI_API_KEY;
  else process.env.OPENAI_API_KEY = savedKey;
  if (savedModel === undefined) delete process.env.OPENAI_MODEL;
  else process.env.OPENAI_MODEL = savedModel;
});

test("mock mode when no OpenAI key is set", () => {
  delete process.env.OPENAI_API_KEY;
  assert.equal(aiMode(), "mock");
  assert.equal(modelLabel(), "mock-local");
});

test("openai mode and default model gpt-4o-mini when key is set", () => {
  process.env.OPENAI_API_KEY = "sk-test";
  delete process.env.OPENAI_MODEL;
  assert.equal(aiMode(), "openai");
  assert.equal(modelLabel(), "gpt-4o-mini");
});

test("OPENAI_MODEL overrides the default label", () => {
  process.env.OPENAI_API_KEY = "sk-test";
  process.env.OPENAI_MODEL = "gpt-4o";
  assert.equal(modelLabel(), "gpt-4o");
});

test("mock drafts are usable: pending approval with non-empty body", async () => {
  delete process.env.OPENAI_API_KEY;
  const items = await generatePostDrafts(DEFAULT_SETTINGS, 2);
  assert.equal(items.length, 2);
  for (const item of items) {
    assert.equal(item.status, "pending_approval");
    assert.equal(item.aiModel, "mock-local");
    assert.ok(item.body.trim().length > 0);
    assert.ok(item.topic.trim().length > 0);
    assert.ok(!/\p{Extended_Pictographic}/u.test(item.body));
    assert.ok(!/game-changer/i.test(item.body));
  }
});

test("mock drafts can target a specific angle", async () => {
  delete process.env.OPENAI_API_KEY;
  const items = await generatePostDrafts(DEFAULT_SETTINGS, 1, "overflow_capacity");
  assert.equal(items.length, 1);
  assert.match(items[0].body.toLowerCase(), /overflow|capacity|bid/);
});

/* --------------------------------------------------------------- buildMockComment */

// Every mock comment must be owner-ready: uses the first name, is a complete
// sentence (no mid-word slicing), stays under the limit, and carries no links,
// hashtags, emojis or hard sell.
function assertOwnerReady(comment: string, first: string) {
  assert.ok(comment.startsWith(`${first}, `), `starts with first name: ${comment}`);
  assert.match(comment, /[.!?]$/, `ends on a complete sentence: ${comment}`);
  assert.ok(comment.length < ENGAGE_TEXT_MAX_LEN, `under limit: ${comment.length}`);
  assert.ok(comment.length < 300, `under 300 chars: ${comment.length}`);
  assert.ok(!comment.includes("http"), "no links");
  assert.ok(!comment.includes("#"), "no hashtags");
  assert.ok(!/\p{Extended_Pictographic}/u.test(comment), "no emojis");
  // No mid-word fragment artifact from the old slicing bug.
  assert.ok(!/\bf slips\b/.test(comment), "no mid-word slice artifact");
  // No dangling single-letter word (a sign of a truncated word).
  assert.ok(!/\s[b-hj-z]\s/i.test(comment), `no orphaned partial word: ${comment}`);
}

test("mock comment for estimating/bid context is complete and on-topic", () => {
  const comment = buildMockComment("Jordan Hale", "Bid-night overtime and incomplete plan sets");
  assertOwnerReady(comment, "Jordan");
  assert.match(comment, /bid|scope|pricing|quantities/i);
});

test("mock comment for a completed-project context is complete and on-topic", () => {
  const comment = buildMockComment(
    "Priya Nair",
    "Completed hospital fit-out, photos of the crew and subcontractors on a tight schedule"
  );
  assertOwnerReady(comment, "Priya");
  assert.match(comment, /finish|schedule|subs|crew/i);
});

test("mock comment for a generic construction context is complete", () => {
  const comment = buildMockComment("Sam Okoye", "Reflections on running work in the field");
  assertOwnerReady(comment, "Sam");
  assert.match(comment, /project|work/i);
});

test("mock comment falls back to a friendly address when no name is given", () => {
  const comment = buildMockComment("", "bid scope questions");
  assertOwnerReady(comment, "there");
});

test("engage mock comment draft is pending, non-empty and under the limit", async () => {
  delete process.env.OPENAI_API_KEY;
  const item = await generateEngageDraft(DEFAULT_SETTINGS, {
    kind: "comment",
    targetName: "Jordan Hale",
    targetTitle: "Senior Estimator",
    targetCompany: "Northline Construction",
    sourcePostSummary: "Bid-night overtime and incomplete plan sets",
  });
  assert.equal(item.status, "pending_approval");
  assert.ok(item.suggestedText.trim().length > 0);
  assert.ok(item.suggestedText.length <= ENGAGE_TEXT_MAX_LEN);
  assert.ok(item.suggestedText.startsWith("Jordan, "));
});
