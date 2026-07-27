import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ENGAGE_TEXT_MAX_LEN,
  approveEngageItem,
  checkApproveTargetBinding,
  checkEngageCreate,
  checkEngageEditable,
  engageStatusLabel,
  isActiveEngageStatus,
  markCommented,
  setEngageSourceUrl,
  transitionPendingEngage,
} from "./engage";
import type { EngageItem, ItemStatus } from "./types";

const POST_URL =
  "https://www.linkedin.com/posts/jordan-hale_bid-night-activity-7100000000000000000-abcd";

function engageItem(overrides: Partial<EngageItem> = {}): EngageItem {
  const now = "2024-01-01T00:00:00.000Z";
  return {
    id: "eng_1",
    type: "engage",
    kind: "comment",
    status: "pending_approval",
    targetName: "Jordan Hale",
    targetTitle: "Senior Estimator",
    targetCompany: "Northline Construction",
    sourcePostSummary: "Bid-night overtime and incomplete plan sets",
    suggestedText: "That tracks.",
    // Comments require a valid stored post URL to be approvable; default to one
    // so the general approve tests exercise the happy path.
    sourcePostUrl: POST_URL,
    createdAt: now,
    updatedAt: now,
    aiModel: "mock-local",
    ...overrides,
  };
}

/* ------------------------------------------------------------ checkEngageCreate */

test("a comment requires a valid LinkedIn post URL", () => {
  const missing = checkEngageCreate({ kind: "comment" }, []);
  assert.equal(missing.ok, false);
  if (!missing.ok) assert.equal(missing.status, 400);

  const bad = checkEngageCreate(
    { kind: "comment", sourcePostUrl: "http://evil.example/x" },
    []
  );
  assert.equal(bad.ok, false);
  if (!bad.ok) assert.equal(bad.status, 400);
});

test("a comment with a valid URL passes and returns the normalized URL", () => {
  const res = checkEngageCreate({ kind: "comment", sourcePostUrl: POST_URL }, []);
  assert.equal(res.ok, true);
  if (res.ok) assert.equal(res.sourcePostUrl, POST_URL);
});

test("a duplicate active comment for the same post is rejected 409", () => {
  const existing = [engageItem({ status: "pending_approval", sourcePostUrl: POST_URL })];
  const res = checkEngageCreate(
    { kind: "comment", sourcePostUrl: POST_URL + "?utm=share" },
    existing
  );
  assert.equal(res.ok, false);
  if (!res.ok) assert.equal(res.status, 409);
});

test("a completed or rejected comment does not block a fresh capture", () => {
  for (const status of ["sent", "rejected", "skipped"] as ItemStatus[]) {
    const existing = [engageItem({ status, sourcePostUrl: POST_URL })];
    const res = checkEngageCreate({ kind: "comment", sourcePostUrl: POST_URL }, existing);
    assert.equal(res.ok, true, `status ${status} should not block`);
  }
});

test("connection notes accept no URL, ignore an invalid one, keep a valid one", () => {
  assert.deepEqual(checkEngageCreate({ kind: "connect" }, []), { ok: true });

  const ignored = checkEngageCreate(
    { kind: "connect", sourcePostUrl: "http://evil.example/x" },
    []
  );
  assert.deepEqual(ignored, { ok: true });

  const kept = checkEngageCreate({ kind: "connect", sourcePostUrl: POST_URL }, []);
  assert.equal(kept.ok, true);
  if (kept.ok) assert.equal(kept.sourcePostUrl, POST_URL);
});

test("isActiveEngageStatus flags only pending/approved", () => {
  assert.equal(isActiveEngageStatus("pending_approval"), true);
  assert.equal(isActiveEngageStatus("approved"), true);
  assert.equal(isActiveEngageStatus("sent"), false);
  assert.equal(isActiveEngageStatus("rejected"), false);
});

/* --------------------------------------------------------------- approveEngageItem */

test("approve applies the exact supplied text and moves to approved", () => {
  const item = engageItem({ status: "pending_approval", suggestedText: "old draft" });
  const now = "2024-03-03T09:00:00.000Z";
  const supplied = "Jordan, this is the edited text I want approved.";
  const res = approveEngageItem(item, supplied, now, POST_URL);
  assert.equal(res.ok, true);
  if (res.ok) {
    assert.equal(res.item.status, "approved");
    assert.equal(res.item.updatedAt, now);
    // Exact-text correctness: what is approved is exactly what was supplied.
    assert.equal(res.item.suggestedText, supplied);
  }
});

test("approve stores supplied text verbatim (no trimming) so copy matches", () => {
  const item = engageItem({ status: "pending_approval" });
  const supplied = "  spaced text with edges  ";
  const res = approveEngageItem(item, supplied, "2024-03-03T09:00:00.000Z", POST_URL);
  assert.equal(res.ok, true);
  if (res.ok) assert.equal(res.item.suggestedText, supplied);
});

test("approve falls back to the item text when suggestedText is omitted", () => {
  const item = engageItem({ status: "pending_approval", suggestedText: "current item text" });
  const res = approveEngageItem(item, undefined, "2024-03-03T09:00:00.000Z", POST_URL);
  assert.equal(res.ok, true);
  if (res.ok) {
    assert.equal(res.item.status, "approved");
    assert.equal(res.item.suggestedText, "current item text");
  }
});

test("approve enforces pending_approval -> approved and rejects other states 409", () => {
  for (const status of ["approved", "sent", "rejected", "skipped"] as ItemStatus[]) {
    const res = approveEngageItem(
      engageItem({ status }),
      "some text",
      "2024-03-03T09:00:00.000Z"
    );
    assert.equal(res.ok, false, `status ${status} must not be approvable`);
    if (!res.ok) assert.equal(res.status, 409);
  }
});

test("approve rejects empty or whitespace-only text 400", () => {
  const item = engageItem({ status: "pending_approval" });
  for (const text of ["", "   ", "\n\t "]) {
    const res = approveEngageItem(item, text, "2024-03-03T09:00:00.000Z", POST_URL);
    assert.equal(res.ok, false, `text ${JSON.stringify(text)} must be rejected`);
    if (!res.ok) assert.equal(res.status, 400);
  }
});

test("approve rejects over-limit text 400 and allows text at the limit", () => {
  const item = engageItem({ status: "pending_approval" });
  const over = "x".repeat(ENGAGE_TEXT_MAX_LEN + 1);
  const overRes = approveEngageItem(item, over, "2024-03-03T09:00:00.000Z", POST_URL);
  assert.equal(overRes.ok, false);
  if (!overRes.ok) assert.equal(overRes.status, 400);

  const atLimit = "x".repeat(ENGAGE_TEXT_MAX_LEN);
  const okRes = approveEngageItem(item, atLimit, "2024-03-03T09:00:00.000Z", POST_URL);
  assert.equal(okRes.ok, true);
  if (okRes.ok) assert.equal(okRes.item.suggestedText, atLimit);
});

test("a comment cannot be approved without a valid stored post URL (422)", () => {
  for (const badUrl of [undefined, "", "http://evil.example/x", "https://www.linkedin.com/login"]) {
    const item = engageItem({ status: "pending_approval", sourcePostUrl: badUrl });
    const res = approveEngageItem(item, "looks fine", "2024-03-03T09:00:00.000Z");
    assert.equal(res.ok, false, `url ${JSON.stringify(badUrl)} must block approval`);
    if (!res.ok) assert.equal(res.status, 422);
  }
});

test("a connection note is approvable with no URL (URL rule is comment-only)", () => {
  const item = engageItem({ kind: "connect", status: "pending_approval", sourcePostUrl: undefined });
  const res = approveEngageItem(item, "Nice to connect.", "2024-03-03T09:00:00.000Z");
  assert.equal(res.ok, true);
  if (res.ok) assert.equal(res.item.status, "approved");
});

/* ------------------------------------------------- approve target binding (blocker 1) */

const OTHER_POST_URL =
  "https://www.linkedin.com/feed/update/urn:li:activity:7200000000000000000";

test("approve binds to the exact post: matching expected target succeeds", () => {
  const item = engageItem({ status: "pending_approval", sourcePostUrl: POST_URL });
  // Same post, different query string — normalizes to the same target, so it is
  // accepted and the copied/opened target comes from server truth.
  const res = approveEngageItem(item, "looks good", "2024-05-05T00:00:00.000Z", POST_URL + "?utm=share");
  assert.equal(res.ok, true);
  if (res.ok) {
    assert.equal(res.item.status, "approved");
    assert.equal(res.item.sourcePostUrl, POST_URL);
  }
});

test("approve rejects a comment with no expected post URL (409 binding)", () => {
  const item = engageItem({ status: "pending_approval", sourcePostUrl: POST_URL });
  const res = approveEngageItem(item, "looks good", "2024-05-05T00:00:00.000Z", undefined);
  assert.equal(res.ok, false);
  if (!res.ok) assert.equal(res.status, 409);
});

test("approve rejects a stale/mismatched expected target (409 binding)", () => {
  const item = engageItem({ status: "pending_approval", sourcePostUrl: POST_URL });
  const res = approveEngageItem(item, "looks good", "2024-05-05T00:00:00.000Z", OTHER_POST_URL);
  assert.equal(res.ok, false);
  if (!res.ok) assert.equal(res.status, 409);
});

test("checkApproveTargetBinding: match ok, mismatch/omitted 409, notes exempt", () => {
  const comment = engageItem({ kind: "comment", sourcePostUrl: POST_URL });
  assert.equal(checkApproveTargetBinding(comment, POST_URL).ok, true);

  const omitted = checkApproveTargetBinding(comment, undefined);
  assert.equal(omitted.ok, false);
  if (!omitted.ok) assert.equal(omitted.status, 409);

  const mismatch = checkApproveTargetBinding(comment, OTHER_POST_URL);
  assert.equal(mismatch.ok, false);
  if (!mismatch.ok) assert.equal(mismatch.status, 409);

  // Connection notes carry no post target and are URL-exempt.
  const note = checkApproveTargetBinding(
    engageItem({ kind: "connect", sourcePostUrl: undefined }),
    undefined
  );
  assert.equal(note.ok, true);
});

/* ------------------------------------------- reject/skip terminal gating (blocker 2) */

test("reject and skip are allowed only from pending_approval", () => {
  for (const target of ["rejected", "skipped"] as const) {
    const ok = transitionPendingEngage(
      engageItem({ status: "pending_approval" }),
      target,
      "2024-06-06T00:00:00.000Z"
    );
    assert.equal(ok.ok, true, `${target} from pending must succeed`);
    if (ok.ok) {
      assert.equal(ok.item.status, target);
      assert.equal(ok.item.updatedAt, "2024-06-06T00:00:00.000Z");
    }
  }
});

test("reject and skip are rejected 409 from any terminal/approved state", () => {
  for (const target of ["rejected", "skipped"] as const) {
    for (const status of ["approved", "sent", "rejected", "skipped"] as ItemStatus[]) {
      const res = transitionPendingEngage(
        engageItem({ status }),
        target,
        "2024-06-06T00:00:00.000Z"
      );
      assert.equal(res.ok, false, `${target} from ${status} must be blocked`);
      if (!res.ok) assert.equal(res.status, 409);
    }
  }
});

/* --------------------------------------------------------------- checkEngageEditable */

test("edit and regenerate are allowed only while pending_approval", () => {
  for (const action of ["edit", "regenerate"] as const) {
    assert.equal(
      checkEngageEditable(engageItem({ status: "pending_approval" }), action).ok,
      true
    );
    for (const status of ["approved", "sent", "rejected", "skipped"] as ItemStatus[]) {
      const res = checkEngageEditable(engageItem({ status }), action);
      assert.equal(res.ok, false, `${action} on ${status} must be blocked`);
      if (!res.ok) assert.equal(res.status, 409);
    }
  }
});

/* --------------------------------------------------------------- setEngageSourceUrl */

test("setEngageSourceUrl attaches a valid URL to a pending legacy comment", () => {
  const item = engageItem({ status: "pending_approval", sourcePostUrl: undefined });
  const now = "2024-04-04T10:00:00.000Z";
  const res = setEngageSourceUrl(item, POST_URL, now);
  assert.equal(res.ok, true);
  if (res.ok) {
    assert.equal(res.item.sourcePostUrl, POST_URL);
    assert.equal(res.item.updatedAt, now);
    // Repaired item is now approvable, bound to the URL just attached.
    const approved = approveEngageItem(res.item, "ok", now, POST_URL);
    assert.equal(approved.ok, true);
  }
});

test("setEngageSourceUrl rejects an invalid URL (400)", () => {
  const item = engageItem({ status: "pending_approval", sourcePostUrl: undefined });
  const res = setEngageSourceUrl(item, "https://www.linkedin.com/login", "now");
  assert.equal(res.ok, false);
  if (!res.ok) assert.equal(res.status, 400);
});

test("setEngageSourceUrl is comment-only and pending-only (409)", () => {
  const note = setEngageSourceUrl(
    engageItem({ kind: "connect", status: "pending_approval" }),
    POST_URL,
    "now"
  );
  assert.equal(note.ok, false);
  if (!note.ok) assert.equal(note.status, 409);

  for (const status of ["approved", "sent", "rejected"] as ItemStatus[]) {
    const res = setEngageSourceUrl(engageItem({ status }), POST_URL, "now");
    assert.equal(res.ok, false, `url edit on ${status} must be blocked`);
    if (!res.ok) assert.equal(res.status, 409);
  }
});

/* ------------------------------------------------------------------ markCommented */

test("mark_commented moves an approved comment to sent and records completedAt", () => {
  const item = engageItem({ status: "approved" });
  const now = "2024-02-02T12:00:00.000Z";
  const res = markCommented(item, now);
  assert.equal(res.ok, true);
  if (res.ok) {
    assert.equal(res.item.status, "sent");
    assert.equal(res.item.completedAt, now);
    assert.equal(res.item.updatedAt, now);
  }
});

test("mark_commented is rejected unless the comment is approved", () => {
  for (const status of ["pending_approval", "sent", "rejected"] as ItemStatus[]) {
    const res = markCommented(engageItem({ status }), "2024-01-01T00:00:00.000Z");
    assert.equal(res.ok, false, `status ${status} must not be markable`);
    if (!res.ok) assert.equal(res.status, 409);
  }
});

test("mark_commented is rejected for a connection note", () => {
  const res = markCommented(
    engageItem({ kind: "connect", status: "approved" }),
    "2024-01-01T00:00:00.000Z"
  );
  assert.equal(res.ok, false);
  if (!res.ok) assert.equal(res.status, 409);
});

/* --------------------------------------------------------------- engageStatusLabel */

test("a completed comment reads Commented; approved comments are Ready to post", () => {
  assert.equal(engageStatusLabel({ kind: "comment", status: "sent" }), "Commented");
  assert.equal(engageStatusLabel({ kind: "comment", status: "approved" }), "Ready to post");
  assert.equal(
    engageStatusLabel({ kind: "comment", status: "pending_approval" }),
    "Needs approval"
  );
  // A connection note keeps the shared label even at `sent`.
  assert.equal(engageStatusLabel({ kind: "connect", status: "sent" }), "Sent");
});
