"use strict";
/*
 * Deterministic unit tests for the Scout extractor. Run with:
 *   node --test safari-extension/extract.test.js
 *
 * Uses tiny hand-rolled fake DOM nodes so no jsdom / heavy runtime dependency
 * is required.
 */
const assert = require("node:assert/strict");
const { test } = require("node:test");
const {
  normalizePostUrl,
  postKey,
  cleanText,
  buildCandidates,
  extractVisiblePosts,
  MAX_ITEMS,
} = require("./extract.js");

/* ------------------------------------------------------------- URL rules */

test("normalizePostUrl accepts canonical post and activity permalinks", () => {
  assert.equal(
    normalizePostUrl("https://www.linkedin.com/posts/jordan_bid-activity-7100000000000000001-abcd?utm=x"),
    "https://www.linkedin.com/posts/jordan_bid-activity-7100000000000000001-abcd"
  );
  assert.equal(
    normalizePostUrl("https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000002/"),
    "https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000002"
  );
});

test("normalizePostUrl rejects non-post, non-LinkedIn, and credentialed URLs", () => {
  assert.equal(normalizePostUrl("https://www.linkedin.com/feed/"), null);
  assert.equal(normalizePostUrl("https://www.linkedin.com/in/someone"), null);
  assert.equal(normalizePostUrl("https://evil.example/posts/x"), null);
  assert.equal(normalizePostUrl("http://www.linkedin.com/posts/x"), null);
  assert.equal(normalizePostUrl("https://user:pw@www.linkedin.com/posts/x"), null);
  assert.equal(normalizePostUrl(""), null);
  assert.equal(normalizePostUrl(null), null);
});

test("postKey collapses host casing and trailing slash", () => {
  const a = postKey("https://WWW.linkedin.com/posts/x_a-activity-7100000000000000001-ab/");
  const b = postKey("https://www.linkedin.com/posts/x_a-activity-7100000000000000001-ab");
  assert.equal(a, b);
});

test("cleanText collapses whitespace and caps length", () => {
  assert.equal(cleanText("  a\n\n b  ", 100), "a b");
  assert.equal(cleanText("x".repeat(50), 10).length, 10);
});

/* ------------------------------------------------------- build candidates */

test("buildCandidates dedupes, drops invalid, and caps", () => {
  const url1 = "https://www.linkedin.com/posts/a_x-activity-7100000000000000001-ab";
  const url2 = "https://www.linkedin.com/posts/b_x-activity-7100000000000000002-cd";
  const records = [
    { postUrl: url1, sourceText: "Solid pour on the deck this week." },
    { postUrl: url1 + "?utm=1", sourceText: "duplicate of the same post here" },
    { postUrl: "https://www.linkedin.com/feed/", sourceText: "not a post at all here" },
    { postUrl: url2, sourceText: "short", authorName: "Ann" },
    { postUrl: url2, sourceText: "hi" },
  ];
  const out = buildCandidates(records, MAX_ITEMS);
  assert.equal(out.length, 1);
  assert.equal(out[0].postUrl, url1);
});

test("buildCandidates respects an explicit cap", () => {
  const records = [];
  for (let i = 0; i < 30; i++) {
    records.push({
      postUrl:
        "https://www.linkedin.com/posts/a_x-activity-71000000000000" +
        String(i).padStart(5, "0") +
        "-ab",
      sourceText: "Some visible construction post text number " + i,
    });
  }
  assert.equal(buildCandidates(records, MAX_ITEMS).length, MAX_ITEMS);
  assert.equal(buildCandidates(records, 5).length, 5);
});

/* ------------------------------------------------------------ DOM extract */

// Minimal fake element: querySelector by a flat map of selector -> {text, href}.
function fakeNode(map) {
  return {
    querySelector(sel) {
      const hit = map[sel];
      if (!hit) return null;
      return {
        textContent: hit.text || "",
        getAttribute: (name) => (name === "href" ? hit.href || null : null),
        getBoundingClientRect: hit.rect ? () => hit.rect : undefined,
      };
    },
  };
}

function fakeDoc(pathname, containers) {
  return {
    location: { pathname },
    querySelectorAll(sel) {
      return sel === "div.feed-shared-update-v2" ? containers : [];
    },
  };
}

test("extractVisiblePosts reads a feed container into a candidate", () => {
  const node = fakeNode({
    "a[href*='/feed/update/urn:li:']": {
      href: "https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000009",
    },
    ".feed-shared-update-v2__description": {
      text: "We wrapped the concrete pour ahead of schedule this week.",
    },
    ".update-components-actor__title span[aria-hidden='true']": { text: "Jordan Hale" },
    ".update-components-actor__description": { text: "Senior Estimator" },
  });
  const doc = fakeDoc("/feed/", [node]);
  const out = extractVisiblePosts(doc, null);
  assert.equal(out.length, 1);
  assert.equal(out[0].authorName, "Jordan Hale");
  assert.equal(out[0].authorHeadline, "Senior Estimator");
  assert.match(out[0].postUrl, /urn:li:activity:7100000000000000009$/);
});

test("extractVisiblePosts returns nothing outside the exact main feed", () => {
  const node = fakeNode({});
  assert.deepEqual(extractVisiblePosts(fakeDoc("/messaging/thread/1", [node]), null), []);
  assert.deepEqual(extractVisiblePosts(fakeDoc("/feed/comments/1", [node]), null), []);
  assert.deepEqual(extractVisiblePosts(fakeDoc("/in/moses-cervantes", [node]), null), []);
  assert.deepEqual(extractVisiblePosts(fakeDoc("/search/results/content/", [node]), null), []);
  assert.deepEqual(extractVisiblePosts(fakeDoc("/groups/123/", [node]), null), []);
  assert.deepEqual(
    extractVisiblePosts(
      fakeDoc("/feed/update/urn:li:activity:7100000000000000009", [node]),
      null
    ),
    []
  );
});

test("extractVisiblePosts drops a container without a valid permalink", () => {
  const node = fakeNode({
    ".feed-shared-update-v2__description": { text: "Plenty of visible text here." },
  });
  assert.deepEqual(extractVisiblePosts(fakeDoc("/feed/", [node]), null), []);
});

test("extractVisiblePosts rejects off-screen permalink descendants", () => {
  const offscreen = { top: 900, bottom: 950, left: 0, right: 300, width: 300, height: 50 };
  const visible = { top: 20, bottom: 100, left: 0, right: 300, width: 300, height: 80 };
  const node = fakeNode({
    "a[href*='/feed/update/urn:li:']": {
      href: "https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000010",
      rect: offscreen,
    },
    ".feed-shared-update-v2__description": {
      text: "A construction post whose permalink is not currently visible.",
      rect: visible,
    },
  });
  assert.deepEqual(
    extractVisiblePosts(fakeDoc("/feed/", [node]), { innerHeight: 800, innerWidth: 390 }),
    []
  );
});
