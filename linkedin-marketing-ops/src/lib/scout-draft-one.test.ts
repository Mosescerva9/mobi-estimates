import assert from "node:assert/strict";
import { test } from "node:test";
import { draftOneComment } from "./scout-draft-one";
import { applyCapture } from "./scout";
import { emptyStore } from "./store";

const URL_GOOD =
  "https://www.linkedin.com/posts/jordan-hale_bid-night-activity-7100000000000000001-abcd";
const URL_OFFTOPIC =
  "https://www.linkedin.com/posts/sam-lee_weekend-activity-7100000000000000003-wxyz";
const URL_SENSITIVE =
  "https://www.linkedin.com/posts/sam-lee_politics-activity-7100000000000000002-wxyz";

test("draftOneComment drafts for an owner-selected construction post", async () => {
  delete process.env.OPENAI_API_KEY;
  const store = emptyStore();
  const result = await draftOneComment(store, {
    postUrl: URL_GOOD,
    sourceText:
      "Bid night is brutal when the takeoff is incomplete and addenda keep landing after 5pm.",
    authorName: "Jordan Hale",
    authorHeadline: "Senior Estimator",
  });
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.reused, false);
  assert.equal(result.item.kind, "comment");
  assert.equal(result.item.status, "pending_approval");
  assert.equal(result.item.sourcePostUrl, URL_GOOD);
  assert.ok(result.item.suggestedText.length >= 8);
});

test("draftOneComment reuses an active engage draft for the same post", async () => {
  delete process.env.OPENAI_API_KEY;
  let store = emptyStore();
  const first = await draftOneComment(store, {
    postUrl: URL_GOOD,
    sourceText:
      "We need cleaner quantity takeoffs before markup on remodel bids this week.",
    authorName: "Jordan Hale",
  });
  assert.equal(first.ok, true);
  if (!first.ok) return;
  store = first.store;

  const second = await draftOneComment(store, {
    postUrl: URL_GOOD,
    sourceText:
      "We need cleaner quantity takeoffs before markup on remodel bids this week.",
    authorName: "Jordan Hale",
  });
  assert.equal(second.ok, true);
  if (!second.ok) return;
  assert.equal(second.reused, true);
  assert.equal(second.item.id, first.item.id);
});

test("draftOneComment drafts intentionally even when off-topic for batch Scout", async () => {
  delete process.env.OPENAI_API_KEY;
  const result = await draftOneComment(emptyStore(), {
    postUrl: URL_OFFTOPIC,
    sourceText:
      "Beautiful sunset from the cabin this weekend. Feeling grateful for quiet mornings.",
    authorName: "Sam Lee",
    authorHeadline: "Homeowner",
  });
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.item.status, "pending_approval");
});

test("draftOneComment refuses sensitive posts", async () => {
  delete process.env.OPENAI_API_KEY;
  const result = await draftOneComment(emptyStore(), {
    postUrl: URL_SENSITIVE,
    sourceText:
      "Everyone in construction needs to vote carefully in this election season about contractors.",
    authorName: "Sam Lee",
  });
  assert.equal(result.ok, false);
  if (result.ok) return;
  assert.equal(result.status, 422);
});

test("draftOneComment can process an already-collected candidate", async () => {
  delete process.env.OPENAI_API_KEY;
  let store = emptyStore();
  const captured = applyCapture(
    store,
    [
      {
        postUrl: URL_GOOD,
        sourceText:
          "Change orders wreck margin when the RFI answers land after the bid is locked.",
        authorName: "Jordan Hale",
        authorHeadline: "Estimator",
      },
    ],
    new Date().toISOString()
  );
  store = { ...store, scoutCandidates: captured.candidates };
  const result = await draftOneComment(store, {
    postUrl: URL_GOOD,
    sourceText:
      "Change orders wreck margin when the RFI answers land after the bid is locked.",
    authorName: "Jordan Hale",
  });
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.reused, false);
  assert.equal(result.store.engage[0]?.sourcePostUrl, URL_GOOD);
});
