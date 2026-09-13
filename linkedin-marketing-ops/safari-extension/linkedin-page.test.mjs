import assert from "node:assert/strict";
import { test } from "node:test";
import { isLinkedInMainFeedUrl, isLinkedInScoutableUrl } from "./linkedin-page.mjs";

test("accepts only the exact LinkedIn main-feed pathname", () => {
  assert.equal(isLinkedInMainFeedUrl("https://www.linkedin.com/feed"), true);
  assert.equal(isLinkedInMainFeedUrl("https://www.linkedin.com/feed/?trk=nav"), true);
  assert.equal(isLinkedInMainFeedUrl("https://linkedin.com/feed/"), true);
});

test("rejects non-feed LinkedIn pages and non-LinkedIn origins", () => {
  const rejected = [
    "https://www.linkedin.com/in/moses-cervantes",
    "https://www.linkedin.com/search/results/content/",
    "https://www.linkedin.com/groups/123/",
    "https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000009",
    "https://www.linkedin.com/messaging/thread/1",
    "https://evil.example/feed/",
    "http://www.linkedin.com/feed/",
    "not-a-url",
  ];
  for (const value of rejected) {
    assert.equal(isLinkedInMainFeedUrl(value), false, value);
  }
});

test("scoutable URLs include feed and post permalinks", () => {
  assert.equal(isLinkedInScoutableUrl("https://www.linkedin.com/feed"), true);
  assert.equal(
    isLinkedInScoutableUrl(
      "https://www.linkedin.com/posts/jordan_bid-activity-7100000000000000001-abcd"
    ),
    true
  );
  assert.equal(
    isLinkedInScoutableUrl(
      "https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000009"
    ),
    true
  );
  assert.equal(isLinkedInScoutableUrl("https://www.linkedin.com/in/someone"), false);
  assert.equal(isLinkedInScoutableUrl("https://www.linkedin.com/messaging/"), false);
});
