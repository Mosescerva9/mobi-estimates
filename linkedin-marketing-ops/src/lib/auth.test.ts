import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { authConfigError, isAuthenticated, passwordConfigured, verifyPassword } from "./auth";

const saved = {
  OPS_PASSWORD: process.env.OPS_PASSWORD,
  NODE_ENV: process.env.NODE_ENV,
  VERCEL: process.env.VERCEL,
};

function setEnv(env: { OPS_PASSWORD?: string; NODE_ENV?: string; VERCEL?: string }) {
  const mut = process.env as Record<string, string | undefined>;
  for (const key of ["OPS_PASSWORD", "NODE_ENV", "VERCEL"] as const) {
    if (env[key] === undefined) delete mut[key];
    else mut[key] = env[key];
  }
}

afterEach(() => setEnv(saved));

test("hosted with no OPS_PASSWORD fails closed: not authenticated", async () => {
  setEnv({ NODE_ENV: "production", VERCEL: "1" });
  assert.equal(passwordConfigured(), false);
  assert.notEqual(authConfigError(), null);
  assert.equal(await isAuthenticated(), false);
});

test("hosted with no OPS_PASSWORD cannot log in: verifyPassword is always false", async () => {
  setEnv({ VERCEL: "1" });
  assert.equal(await verifyPassword("anything"), false);
  assert.equal(await verifyPassword(""), false);
});

test("local development with no password is open (dev-only) and reports no config error", async () => {
  setEnv({ NODE_ENV: "development" });
  assert.equal(authConfigError(), null);
  assert.equal(passwordConfigured(), false);
  assert.equal(await isAuthenticated(), true);
});

test("with OPS_PASSWORD set, login gate is enforced and no config error is reported", async () => {
  setEnv({ OPS_PASSWORD: "hunter2", VERCEL: "1" });
  assert.equal(passwordConfigured(), true);
  assert.equal(authConfigError(), null);
  assert.equal(await verifyPassword("hunter2"), true);
  assert.equal(await verifyPassword("wrong"), false);
});
