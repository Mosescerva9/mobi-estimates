import assert from "node:assert/strict";
import { test } from "node:test";
import {
  APPROVED_SERVER_URL,
  normalizeApprovedServerUrl,
} from "./server-url.mjs";

test("accepts only the exact production Scout origin", () => {
  assert.equal(normalizeApprovedServerUrl(APPROVED_SERVER_URL), APPROVED_SERVER_URL);
  assert.equal(normalizeApprovedServerUrl(`${APPROVED_SERVER_URL}/`), APPROVED_SERVER_URL);
});

test("rejects every alternate token destination", () => {
  for (const value of [
    "http://mobi-linkedin-ops.vercel.app",
    "https://mobi-linkedin-ops.vercel.app.evil.example",
    "https://evil.example",
    "https://mobi-linkedin-ops.vercel.app:443",
    "https://user:pass@mobi-linkedin-ops.vercel.app",
    "https://mobi-linkedin-ops.vercel.app/api/scout/capture",
    "https://mobi-linkedin-ops.vercel.app?next=https://evil.example",
    "https://mobi-linkedin-ops.vercel.app/#evil",
    "not a url",
    "",
  ]) {
    assert.equal(normalizeApprovedServerUrl(value), null, value);
  }
});
