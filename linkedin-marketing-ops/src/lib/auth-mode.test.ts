import assert from "node:assert/strict";
import { test } from "node:test";
import { AUTH_CONFIG_MESSAGE, classifyAuth } from "./auth-mode";

test("enforce when OPS_PASSWORD is set, even on a hosted deployment", () => {
  assert.equal(
    classifyAuth({ OPS_PASSWORD: "hunter2", NODE_ENV: "production", VERCEL: "1" }),
    "enforce"
  );
  assert.equal(classifyAuth({ OPS_PASSWORD: "hunter2" }), "enforce");
});

test("open in local development when no password is set", () => {
  assert.equal(classifyAuth({ NODE_ENV: "development" }), "open");
  assert.equal(classifyAuth({}), "open");
});

test("fails closed (unconfigured-hosted) in production without a password", () => {
  assert.equal(classifyAuth({ NODE_ENV: "production" }), "unconfigured-hosted");
});

test("fails closed (unconfigured-hosted) on Vercel without a password", () => {
  assert.equal(classifyAuth({ VERCEL: "1" }), "unconfigured-hosted");
});

test("blank/whitespace OPS_PASSWORD does not count as configured", () => {
  assert.equal(classifyAuth({ OPS_PASSWORD: "   ", VERCEL: "1" }), "unconfigured-hosted");
  assert.equal(classifyAuth({ OPS_PASSWORD: "" }), "open");
});

test("the configuration message is owner-readable and mentions OPS_PASSWORD", () => {
  assert.ok(AUTH_CONFIG_MESSAGE.includes("OPS_PASSWORD"));
  assert.ok(AUTH_CONFIG_MESSAGE.length > 20);
});
