import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  bearerFromHeader,
  constantTimeEqual,
  generateCaptureToken,
  hashCaptureToken,
  tokenLast4,
} from "./scout-token";

test("generateCaptureToken returns a high-entropy, unique, URL-safe token", () => {
  const a = generateCaptureToken();
  const b = generateCaptureToken();
  assert.notEqual(a, b);
  assert.ok(a.length >= 40);
  assert.match(a, /^[A-Za-z0-9_-]+$/);
});

test("hashCaptureToken is deterministic and hides the token", () => {
  const token = "example-token";
  const h1 = hashCaptureToken(token);
  const h2 = hashCaptureToken(token);
  assert.equal(h1, h2);
  assert.match(h1, /^[0-9a-f]{64}$/);
  assert.equal(h1.includes(token), false);
});

test("hashCaptureToken is domain-separated from a plain sha256 of the token", () => {
  // A different domain prefix must yield a different digest, so a capture-token
  // hash can never collide with another SHA-256 use in the app.
  const token = "example-token";
  const plain = createHash("sha256").update(token).digest("hex");
  assert.notEqual(hashCaptureToken(token), plain);
});

test("constantTimeEqual matches equal strings and rejects mismatches", () => {
  assert.equal(constantTimeEqual("abc123", "abc123"), true);
  assert.equal(constantTimeEqual("abc123", "abc124"), false);
  assert.equal(constantTimeEqual("abc", "abcd"), false);
});

test("tokenLast4 returns the last four characters", () => {
  assert.equal(tokenLast4("abcdef"), "cdef");
});

test("bearerFromHeader parses only a well-formed bearer header", () => {
  assert.equal(bearerFromHeader("Bearer tok123"), "tok123");
  assert.equal(bearerFromHeader("bearer tok123"), "tok123");
  assert.equal(bearerFromHeader("Basic tok123"), null);
  assert.equal(bearerFromHeader("Bearer   "), null);
  assert.equal(bearerFromHeader(null), null);
  assert.equal(bearerFromHeader(undefined), null);
});
