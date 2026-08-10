import assert from "node:assert/strict";
import { test } from "node:test";
import { linkedInPostKey, validateLinkedInPostUrl } from "./linkedin-url";

test("accepts real LinkedIn post URL variants", () => {
  const valid = [
    "https://www.linkedin.com/posts/jordan-hale_bid-night-activity-7100000000000000000-abcd",
    "https://linkedin.com/feed/update/urn:li:activity:7100000000000000000",
    "https://de.linkedin.com/posts/someone_thing-activity-7200000000000000000-wxyz/",
    "https://www.linkedin.com/posts/x?utm_source=share&utm_medium=member_desktop",
    // share and ugcPost URNs, and a trailing slash on a feed permalink
    "https://www.linkedin.com/feed/update/urn:li:share:7100000000000000000",
    "https://www.linkedin.com/feed/update/urn:li:ugcPost:7100000000000000000/",
    // case-insensitive urn kind
    "https://www.linkedin.com/feed/update/urn:li:UGCPOST:7100000000000000000",
  ];
  for (const url of valid) {
    const check = validateLinkedInPostUrl(url);
    assert.equal(check.ok, true, `expected ${url} to be accepted`);
  }
});

test("rejects non-post LinkedIn paths, including redirect-style URLs", () => {
  const rejected = [
    // Auth / account flows on the real host.
    "https://www.linkedin.com/login",
    "https://www.linkedin.com/uas/login?session_redirect=/posts/x",
    "https://www.linkedin.com/checkpoint/lg/login-submit",
    "https://www.linkedin.com/oauth/v2/authorization?redirect_uri=https://evil.example",
    // Open-redirect / safety bounce endpoints — the whole reason host isn't enough.
    "https://www.linkedin.com/safety/go?url=https://evil.example",
    "https://www.linkedin.com/redir/redirect?url=https://evil.example",
    // Root feed, profile-only, company, and search paths are not posts.
    "https://www.linkedin.com/feed/",
    "https://www.linkedin.com/feed",
    "https://www.linkedin.com/in/jordan-hale",
    "https://www.linkedin.com/company/acme",
    "https://www.linkedin.com/search/results/all/?keywords=x",
    // Post-lookalike paths that don't match the strict shapes.
    "https://www.linkedin.com/posts/", // empty slug
    "https://www.linkedin.com/posts", // no slug at all
    "https://www.linkedin.com/posts/slug/extra", // extra segment
    "https://www.linkedin.com/feed/update/urn:li:activity:", // empty id
    "https://www.linkedin.com/feed/update/urn:li:comment:7100000000000000000", // wrong urn kind
    "https://www.linkedin.com/feed/update/urn:li:activity:abc", // non-numeric id
  ];
  for (const url of rejected) {
    assert.equal(validateLinkedInPostUrl(url).ok, false, `expected ${url} rejected`);
  }
});

test("normalizes host casing without changing the target path/query", () => {
  const check = validateLinkedInPostUrl(
    "https://WWW.LinkedIn.com/posts/abc-activity-7100000000000000000-defg?x=1"
  );
  assert.equal(check.ok, true);
  if (check.ok) {
    assert.equal(
      check.url,
      "https://www.linkedin.com/posts/abc-activity-7100000000000000000-defg?x=1"
    );
  }
});

test("rejects non-HTTPS and non-http schemes", () => {
  for (const url of [
    "http://www.linkedin.com/posts/x",
    "ftp://www.linkedin.com/posts/x",
    "javascript:alert(1)//www.linkedin.com/posts/x",
  ]) {
    assert.equal(validateLinkedInPostUrl(url).ok, false, `expected ${url} rejected`);
  }
});

test("rejects lookalike and non-LinkedIn hosts", () => {
  for (const url of [
    "https://linkedin.com.evil.example/posts/x",
    "https://notlinkedin.com/posts/x",
    "https://linkedin.evil.com/posts/x",
    "https://linkedin.com./posts/x", // trailing-dot FQDN
    "https://www.linkedln.com/posts/x", // typo lookalike
  ]) {
    assert.equal(validateLinkedInPostUrl(url).ok, false, `expected ${url} rejected`);
  }
});

test("rejects embedded credentials and credential-lookalike hosts", () => {
  for (const url of [
    "https://user:pass@www.linkedin.com/posts/x",
    "https://linkedin.com@evil.example/posts/x",
  ]) {
    assert.equal(validateLinkedInPostUrl(url).ok, false, `expected ${url} rejected`);
  }
});

test("rejects the bare LinkedIn home page (not a post)", () => {
  assert.equal(validateLinkedInPostUrl("https://linkedin.com").ok, false);
  assert.equal(validateLinkedInPostUrl("https://www.linkedin.com/").ok, false);
});

test("rejects empty, non-string, malformed, and overlong values", () => {
  assert.equal(validateLinkedInPostUrl("").ok, false);
  assert.equal(validateLinkedInPostUrl("   ").ok, false);
  assert.equal(validateLinkedInPostUrl(undefined).ok, false);
  assert.equal(validateLinkedInPostUrl(null).ok, false);
  assert.equal(validateLinkedInPostUrl(42 as unknown).ok, false);
  assert.equal(validateLinkedInPostUrl("not a url").ok, false);
  assert.equal(validateLinkedInPostUrl("//www.linkedin.com/posts/x").ok, false);
  const overlong = "https://www.linkedin.com/posts/" + "a".repeat(3000);
  assert.equal(validateLinkedInPostUrl(overlong).ok, false);
});

test("linkedInPostKey collapses trailing slash, query, fragment, and host casing", () => {
  const a = linkedInPostKey("https://www.linkedin.com/posts/abc-activity-7100/");
  const b = linkedInPostKey(
    "https://WWW.linkedin.com/posts/abc-activity-7100?utm=x#comment"
  );
  assert.ok(a);
  assert.equal(a, b);
});

test("linkedInPostKey distinguishes different posts and tolerates junk", () => {
  const a = linkedInPostKey("https://www.linkedin.com/posts/abc-activity-7100");
  const b = linkedInPostKey("https://www.linkedin.com/posts/def-activity-7200");
  assert.notEqual(a, b);
  assert.equal(linkedInPostKey(undefined), null);
  assert.equal(linkedInPostKey("not a url"), null);
});
