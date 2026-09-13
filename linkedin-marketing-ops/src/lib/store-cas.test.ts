import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { StoreConflictError, readStore, writeStore } from "./store";
import { getStoreVersion } from "./store-version";

/**
 * Exercises the Supabase compare-and-swap adapter with a mocked fetch — no real
 * Supabase. Read attaches the row's updated_at as version metadata; write calls
 * the CAS RPC with that expected version and surfaces a StoreConflictError when
 * the RPC reports a mismatch.
 */

const realFetch = globalThis.fetch;
const saved = {
  SUPABASE_URL: process.env.SUPABASE_URL,
  SUPABASE_SERVICE_ROLE_KEY: process.env.SUPABASE_SERVICE_ROLE_KEY,
  NODE_ENV: process.env.NODE_ENV,
  VERCEL: process.env.VERCEL,
};

beforeEach(() => {
  const mut = process.env as Record<string, string | undefined>;
  mut.SUPABASE_URL = "https://example.supabase.co";
  mut.SUPABASE_SERVICE_ROLE_KEY = "service-role-test-key";
  delete mut.VERCEL;
  mut.NODE_ENV = "production";
});

afterEach(() => {
  globalThis.fetch = realFetch;
  for (const [k, v] of Object.entries(saved)) {
    if (v === undefined) delete (process.env as Record<string, string | undefined>)[k];
    else (process.env as Record<string, string>)[k] = v;
  }
});

function jsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 500,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

test("read attaches the row updated_at as version metadata", async () => {
  globalThis.fetch = (async (url: string) => {
    assert.ok(String(url).includes("select=data,updated_at"));
    return jsonResponse([
      { data: { posts: [], engage: [], dms: [] }, updated_at: "2024-01-01T00:00:00+00:00" },
    ]);
  }) as typeof fetch;

  const store = await readStore();
  assert.equal(getStoreVersion(store), "2024-01-01T00:00:00+00:00");
});

test("a missing row reads as an empty store with a null (insert-allowed) version", async () => {
  globalThis.fetch = (async () => jsonResponse([])) as typeof fetch;
  const store = await readStore();
  assert.equal(getStoreVersion(store), null);
  assert.deepEqual(store.posts, []);
});

test("write sends the expected version to the CAS RPC and adopts the new version", async () => {
  const calls: Array<{ url: string; body: unknown }> = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    if (String(url).includes("/rest/v1/rpc/linkedin_ops_state_cas")) {
      calls.push({ url: String(url), body: JSON.parse(String(init?.body)) });
      return jsonResponse("2024-01-02T00:00:00+00:00");
    }
    return jsonResponse([
      { data: { posts: [], engage: [], dms: [] }, updated_at: "2024-01-01T00:00:00+00:00" },
    ]);
  }) as typeof fetch;

  const store = await readStore();
  await writeStore(store);

  assert.equal(calls.length, 1);
  const body = calls[0].body as { p_expected_updated_at: string; p_data: unknown };
  assert.equal(body.p_expected_updated_at, "2024-01-01T00:00:00+00:00");
  // The service-role key must never appear in the serialized payload.
  assert.ok(!JSON.stringify(body).includes("service-role-test-key"));
  // The snapshot adopts the new version for any subsequent write.
  assert.equal(getStoreVersion(store), "2024-01-02T00:00:00+00:00");
});

test("a CAS conflict (RPC returns null) throws StoreConflictError", async () => {
  globalThis.fetch = (async (url: string) => {
    if (String(url).includes("/rest/v1/rpc/linkedin_ops_state_cas")) {
      return jsonResponse(null);
    }
    return jsonResponse([
      { data: { posts: [], engage: [], dms: [] }, updated_at: "2024-01-01T00:00:00+00:00" },
    ]);
  }) as typeof fetch;

  const store = await readStore();
  await assert.rejects(() => writeStore(store), StoreConflictError);
});
