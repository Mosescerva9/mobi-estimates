import assert from "node:assert/strict";
import { test } from "node:test";
import { StoreConfigError, StoreConflictError, selectStoreMode } from "./store-mode";

test("uses supabase when both durable-store vars are set", () => {
  assert.equal(
    selectStoreMode({
      SUPABASE_URL: "https://x.supabase.co",
      SUPABASE_SERVICE_ROLE_KEY: "service-role-key",
      NODE_ENV: "production",
      VERCEL: "1",
    }),
    "supabase"
  );
});

test("uses file store in local development when supabase is absent", () => {
  assert.equal(selectStoreMode({ NODE_ENV: "development" }), "file");
  assert.equal(selectStoreMode({}), "file");
});

test("fails closed in production without durable storage", () => {
  assert.throws(
    () => selectStoreMode({ NODE_ENV: "production" }),
    StoreConfigError
  );
});

test("fails closed on Vercel without durable storage", () => {
  assert.throws(() => selectStoreMode({ VERCEL: "1" }), StoreConfigError);
});

test("blank/whitespace supabase vars do not count as configured", () => {
  assert.throws(
    () =>
      selectStoreMode({
        SUPABASE_URL: "  ",
        SUPABASE_SERVICE_ROLE_KEY: "",
        VERCEL: "1",
      }),
    StoreConfigError
  );
});

test("StoreConflictError is a typed error with an owner-readable default message", () => {
  const err = new StoreConflictError();
  assert.equal(err.name, "StoreConflictError");
  assert.ok(err instanceof Error);
  assert.ok(/reload/i.test(err.message));
});
