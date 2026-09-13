import assert from "node:assert/strict";
import { test } from "node:test";
import { applyCapture } from "./scout";
import { processScoutLocally } from "./scout-local";
import { emptyStore } from "./store";

const URL_GOOD =
  "https://www.linkedin.com/posts/jordan-hale_bid-night-activity-7100000000000000001-abcd";
const URL_SENSITIVE =
  "https://www.linkedin.com/posts/sam-lee_politics-activity-7100000000000000002-wxyz";

test("processScoutLocally drafts a comment for a construction post", async () => {
  delete process.env.OPENAI_API_KEY;
  let store = emptyStore();
  const now = new Date().toISOString();
  const captured = applyCapture(
    store,
    [
      {
        postUrl: URL_GOOD,
        sourceText:
          "Bid night is brutal when the takeoff is incomplete and addenda keep landing after 5pm. We need cleaner quantity takeoffs before markup.",
        authorName: "Jordan Hale",
        authorHeadline: "Senior Estimator",
        authorCompany: "Northline Construction",
      },
    ],
    now
  );
  store = { ...store, scoutCandidates: captured.candidates };

  const result = await processScoutLocally(store, 5);
  assert.ok(result.queued >= 1);
  assert.equal(result.store.engage[0]?.kind, "comment");
  assert.ok(result.store.engage[0]?.sourcePostUrl?.includes("linkedin.com"));
});

test("processScoutLocally skips sensitive posts", async () => {
  delete process.env.OPENAI_API_KEY;
  let store = emptyStore();
  const now = new Date().toISOString();
  const captured = applyCapture(
    store,
    [
      {
        postUrl: URL_SENSITIVE,
        sourceText:
          "Everyone in construction needs to vote carefully in this election season about contractors.",
        authorName: "Sam Lee",
        authorHeadline: "Estimator",
      },
    ],
    now
  );
  store = { ...store, scoutCandidates: captured.candidates };
  const result = await processScoutLocally(store, 5);
  assert.equal(result.queued, 0);
  assert.ok(result.skipped >= 1);
});
