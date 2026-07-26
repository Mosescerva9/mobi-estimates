import assert from "node:assert/strict";
import { test } from "node:test";
import { needsAttention, statusLabel } from "./status";
import type { ItemStatus } from "./types";

test("status chips use exact plain-language labels", () => {
  assert.equal(statusLabel("pending_approval"), "Needs approval");
  assert.equal(statusLabel("approved"), "Approved");
  assert.equal(statusLabel("published"), "Published");
  assert.equal(statusLabel("sent"), "Sent");
  assert.equal(statusLabel("rejected"), "Rejected");
  assert.equal(statusLabel("skipped"), "Skipped");
  assert.equal(statusLabel("scheduled"), "Scheduled");
  assert.equal(statusLabel("draft"), "Draft");
});

test("every ItemStatus has a non-empty label", () => {
  const all: ItemStatus[] = [
    "draft",
    "pending_approval",
    "approved",
    "scheduled",
    "published",
    "sent",
    "rejected",
    "skipped",
  ];
  for (const s of all) {
    assert.ok(statusLabel(s).length > 0, `missing label for ${s}`);
  }
});

test("only pending_approval needs the owner's attention", () => {
  assert.equal(needsAttention("pending_approval"), true);
  assert.equal(needsAttention("approved"), false);
  assert.equal(needsAttention("published"), false);
});
