import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { seedStore } from "./seed-data";
import { emptyStore } from "./store";
import type { StoreData } from "./types";

const savedKey = process.env.OPENAI_API_KEY;

beforeEach(() => {
  // Force offline mock drafts so the test never calls a real API.
  delete process.env.OPENAI_API_KEY;
});

afterEach(() => {
  if (savedKey === undefined) delete process.env.OPENAI_API_KEY;
  else process.env.OPENAI_API_KEY = savedKey;
});

function existingStore(): StoreData {
  const store = emptyStore();
  store.settings.companyName = "Acme Estimating";
  store.settings.ctaUrl = "https://acme.example.com";
  store.posts = [
    {
      id: "existing_post",
      type: "post",
      status: "published",
      topic: "Real production post",
      body: "This is real owner data.",
      cta: "https://acme.example.com",
      scheduledFor: null,
      createdAt: "2024-01-01T00:00:00Z",
      updatedAt: "2024-01-01T00:00:00Z",
      aiModel: "mock-local",
    },
  ];
  store.dms = [
    {
      id: "existing_dm",
      type: "dm",
      status: "sent",
      leadName: "Real Lead",
      leadTitle: "Owner",
      leadCompany: "Real Co",
      trigger: "demo_request",
      body: "Real DM.",
      createdAt: "2024-01-01T00:00:00Z",
      updatedAt: "2024-01-01T00:00:00Z",
      aiModel: "mock-local",
    },
  ];
  return store;
}

test("seed appends demo items while preserving existing records and settings", async () => {
  const before = existingStore();
  let written: StoreData | null = null;
  const deps = {
    readStore: async () => structuredClone(before),
    writeStore: async (data: StoreData) => {
      written = data;
    },
  };

  const result = await seedStore(deps);

  // Existing settings survive untouched.
  assert.equal(result.settings.companyName, "Acme Estimating");
  assert.equal(result.settings.ctaUrl, "https://acme.example.com");

  // Existing records survive.
  assert.ok(
    result.posts.some((p) => p.id === "existing_post"),
    "existing post must survive seed append"
  );
  assert.ok(
    result.dms.some((d) => d.id === "existing_dm"),
    "existing DM must survive seed append"
  );

  // Demo items were added on top.
  assert.ok(result.posts.length > before.posts.length, "demo posts were appended");
  assert.ok(result.engage.length > before.engage.length, "demo engage items were appended");
  assert.ok(result.dms.length > before.dms.length, "demo DMs were appended");

  // The written store is exactly what was returned (no separate replace path).
  assert.equal(written, result);
});
