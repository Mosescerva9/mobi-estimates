import assert from "node:assert/strict";
import { test } from "node:test";
import { approveEngageItem } from "./engage";
import {
  approveForPoster,
  claimApprovedComment,
  completePostedComment,
  posterItemPayload,
} from "./scout-poster";
import { emptyStore } from "./store";
import type { EngageItem } from "./types";

const POST_URL =
  "https://www.linkedin.com/posts/jordan-hale_bid-night-activity-7100000000000000001-abcd";
const OTHER_URL =
  "https://www.linkedin.com/posts/sam-lee_scope-activity-7100000000000000002-wxyz";

function comment(over: Partial<EngageItem> = {}): EngageItem {
  return {
    id: "eng_1",
    type: "engage",
    kind: "comment",
    status: "approved",
    targetName: "Jordan",
    targetTitle: "Estimator",
    targetCompany: "Northline",
    sourcePostSummary: "Bid night is hard.",
    sourcePostUrl: POST_URL,
    suggestedText: "Jordan, clean takeoffs before markup save the night.",
    createdAt: "2024-01-01T00:00:00.000Z",
    updatedAt: "2024-01-02T00:00:00.000Z",
    aiModel: "mock",
    ...over,
  };
}

test("claimApprovedComment returns the oldest approved comment", () => {
  const store = emptyStore();
  store.engage = [
    comment({ id: "eng_new", updatedAt: "2024-01-03T00:00:00.000Z" }),
    comment({
      id: "eng_old",
      updatedAt: "2024-01-01T00:00:00.000Z",
      sourcePostUrl: OTHER_URL,
      suggestedText: "Older approval",
    }),
  ];
  const claim = claimApprovedComment(store);
  assert.equal(claim.ok, true);
  if (!claim.ok) return;
  assert.equal(claim.item.id, "eng_old");
});

test("claimApprovedComment can filter by post URL", () => {
  const store = emptyStore();
  store.engage = [
    comment({ id: "eng_a", sourcePostUrl: POST_URL }),
    comment({ id: "eng_b", sourcePostUrl: OTHER_URL }),
  ];
  const claim = claimApprovedComment(store, POST_URL);
  assert.equal(claim.ok, true);
  if (!claim.ok) return;
  assert.equal(claim.item.id, "eng_a");
});

test("claimApprovedComment 404s when nothing matches", () => {
  const store = emptyStore();
  store.engage = [comment({ status: "pending_approval" })];
  const claim = claimApprovedComment(store);
  assert.equal(claim.ok, false);
  if (claim.ok) return;
  assert.equal(claim.status, 404);
});

test("approveForPoster and completePostedComment move statuses", () => {
  const store = emptyStore();
  store.engage = [comment({ status: "pending_approval" })];
  const approved = approveForPoster(
    store,
    "eng_1",
    "Final wording for LinkedIn.",
    POST_URL,
    "2024-01-04T00:00:00.000Z"
  );
  assert.equal(approved.ok, true);
  if (!approved.ok) return;
  assert.equal(approved.item.status, "approved");
  assert.equal(approved.item.suggestedText, "Final wording for LinkedIn.");

  const done = completePostedComment(
    approved.store,
    "eng_1",
    "2024-01-04T00:01:00.000Z"
  );
  assert.equal(done.ok, true);
  if (!done.ok) return;
  assert.equal(done.item.status, "sent");
});

test("posterItemPayload exposes the fields the extension needs", () => {
  const item = comment();
  const payload = posterItemPayload(item);
  assert.equal(payload.id, item.id);
  assert.equal(payload.suggestedText, item.suggestedText);
  assert.equal(payload.sourcePostUrl, item.sourcePostUrl);
  assert.equal(payload.status, "approved");
});

test("approveEngageItem still powers the poster approve path", () => {
  const item = comment({ status: "pending_approval" });
  const res = approveEngageItem(item, "x", "2024-01-04T00:00:00.000Z", POST_URL);
  assert.equal(res.ok, true);
});
