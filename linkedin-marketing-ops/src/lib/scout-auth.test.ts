import assert from "node:assert/strict";
import { test } from "node:test";
import { authorizeCapture, authorizeJob, jobTokenConfigured } from "./scout-auth";
import { hashCaptureToken } from "./scout-token";
import type { ScoutState } from "./types";

/* --------------------------------------------------------------- job token */

test("authorizeJob fails closed (503) when SCOUT_JOB_TOKEN is unset", () => {
  const res = authorizeJob("Bearer anything", {});
  assert.equal(res.ok, false);
  if (!res.ok) assert.equal(res.status, 503);
});

test("authorizeJob 401s a missing or wrong bearer token", () => {
  const env = { SCOUT_JOB_TOKEN: "job-secret" };
  assert.equal(authorizeJob(undefined, env).ok, false);
  const wrong = authorizeJob("Bearer nope", env);
  assert.equal(wrong.ok, false);
  if (!wrong.ok) assert.equal(wrong.status, 401);
});

test("authorizeJob accepts the exact configured token", () => {
  const env = { SCOUT_JOB_TOKEN: "job-secret" };
  assert.equal(authorizeJob("Bearer job-secret", env).ok, true);
});

test("jobTokenConfigured reflects the environment", () => {
  assert.equal(jobTokenConfigured({}), false);
  assert.equal(jobTokenConfigured({ SCOUT_JOB_TOKEN: "  " }), false);
  assert.equal(jobTokenConfigured({ SCOUT_JOB_TOKEN: "x" }), true);
});

/* ----------------------------------------------------------- capture token */

test("authorizeCapture fails closed (503) when no pairing code exists", () => {
  const res = authorizeCapture("Bearer whatever", {});
  assert.equal(res.ok, false);
  if (!res.ok) assert.equal(res.status, 503);
});

test("authorizeCapture accepts a token whose hash matches the stored hash", () => {
  const token = "capture-token-value";
  const scout: ScoutState = { captureTokenHash: hashCaptureToken(token) };
  assert.equal(authorizeCapture(`Bearer ${token}`, scout).ok, true);
});

test("authorizeCapture 401s a wrong token", () => {
  const scout: ScoutState = { captureTokenHash: hashCaptureToken("right") };
  const res = authorizeCapture("Bearer wrong", scout);
  assert.equal(res.ok, false);
  if (!res.ok) assert.equal(res.status, 401);
});

test("an initially valid capture token fails against fresh rotated or revoked state", () => {
  const oldToken = "old-capture-token";
  const oldState: ScoutState = { captureTokenHash: hashCaptureToken(oldToken) };
  assert.equal(authorizeCapture(`Bearer ${oldToken}`, oldState).ok, true);

  const rotated: ScoutState = { captureTokenHash: hashCaptureToken("new-capture-token") };
  const afterRotate = authorizeCapture(`Bearer ${oldToken}`, rotated);
  assert.equal(afterRotate.ok, false);
  if (!afterRotate.ok) assert.equal(afterRotate.status, 401);

  const afterRevoke = authorizeCapture(`Bearer ${oldToken}`, {});
  assert.equal(afterRevoke.ok, false);
  if (!afterRevoke.ok) assert.equal(afterRevoke.status, 503);
});

test("a capture token cannot satisfy the job endpoint", () => {
  // The job endpoint compares the raw token against SCOUT_JOB_TOKEN; a capture
  // token (only ever a hash preimage) is not the job secret.
  const captureToken = "capture-token-value";
  const env = { SCOUT_JOB_TOKEN: "job-secret" };
  assert.equal(authorizeJob(`Bearer ${captureToken}`, env).ok, false);
});
