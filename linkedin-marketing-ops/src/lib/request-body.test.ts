import assert from "node:assert/strict";
import { test } from "node:test";
import {
  InvalidJsonBodyError,
  JsonBodyTooLargeError,
  readJsonBodyLimited,
} from "./request-body";

test("readJsonBodyLimited parses JSON within the byte cap", async () => {
  const req = new Request("https://example.test", {
    method: "POST",
    body: JSON.stringify({ ok: true, value: "construction" }),
  });
  assert.deepEqual(await readJsonBodyLimited(req, 1024), {
    ok: true,
    value: "construction",
  });
});

test("readJsonBodyLimited rejects an oversized declared Content-Length", async () => {
  const req = new Request("https://example.test", {
    method: "POST",
    headers: { "Content-Length": "5000" },
    body: "{}",
  });

  await assert.rejects(
    () => readJsonBodyLimited(req, 100),
    JsonBodyTooLargeError
  );
});

test("readJsonBodyLimited cancels a streamed body once the running cap is crossed", async () => {
  const req = new Request("https://example.test", {
    method: "POST",
    body: "x".repeat(101),
  });
  await assert.rejects(
    () => readJsonBodyLimited(req, 100),
    JsonBodyTooLargeError
  );
});

test("readJsonBodyLimited distinguishes malformed JSON", async () => {
  const req = new Request("https://example.test", {
    method: "POST",
    body: "{not-json",
  });
  await assert.rejects(
    () => readJsonBodyLimited(req, 100),
    InvalidJsonBodyError
  );
});
