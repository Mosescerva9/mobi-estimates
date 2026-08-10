import assert from "node:assert/strict";
import { test } from "node:test";
import { approvePost, type ApproveDeps } from "./post-approve";
import { emptyStore } from "./store";
import { StoreConflictError } from "./store-mode";
import { attachVersion, getStoreVersion } from "./store-version";
import type { PublishResult } from "./linkedin";
import type { PostItem, StoreData } from "./types";

function pendingPost(id: string): PostItem {
  const now = new Date().toISOString();
  return {
    id,
    type: "post",
    status: "pending_approval",
    topic: "Bid-night overtime",
    body: "Estimators lose nights to incomplete plan sets.",
    cta: "https://mobiestimates.com",
    scheduledFor: null,
    createdAt: now,
    updatedAt: now,
    aiModel: "mock-local",
  };
}

/** In-memory store that enforces the same compare-and-swap contract as Supabase. */
function makeFakeStore(initial: StoreData) {
  let current: StoreData = structuredClone(initial);
  let counter = 1;
  let version = "v1";

  const readStore = async (): Promise<StoreData> =>
    attachVersion(structuredClone(current), version);

  const writeStore = async (data: StoreData): Promise<void> => {
    if (getStoreVersion(data) !== version) throw new StoreConflictError();
    counter += 1;
    version = `v${counter}`;
    current = structuredClone(data);
    attachVersion(data, version);
  };

  return {
    readStore,
    writeStore,
    post: (id: string) => current.posts.find((p) => p.id === id),
  };
}

function baseStore(): StoreData {
  const store = emptyStore();
  store.posts = [pendingPost("post_1")];
  return store;
}

test("sequential double approve publishes exactly once", async () => {
  const fake = makeFakeStore(baseStore());
  let publishCalls = 0;
  const deps: ApproveDeps = {
    readStore: fake.readStore,
    writeStore: fake.writeStore,
    publish: async () => {
      publishCalls += 1;
      return { ok: true, mode: "dry_run", message: "dry run" } as PublishResult;
    },
  };

  const first = await approvePost("post_1", deps);
  assert.equal(first.ok, true);
  assert.equal(publishCalls, 1);
  assert.equal(fake.post("post_1")?.status, "published");
  assert.equal(fake.post("post_1")?.publishToken, undefined);

  const second = await approvePost("post_1", deps);
  assert.equal(second.ok, false);
  assert.equal((second as { status: number }).status, 409);
  assert.equal(publishCalls, 1, "already-published post must not publish again");
});

test("concurrent approve requests publish exactly once", async () => {
  const fake = makeFakeStore(baseStore());
  let publishCalls = 0;
  const deps: ApproveDeps = {
    readStore: fake.readStore,
    writeStore: fake.writeStore,
    publish: async () => {
      publishCalls += 1;
      // Yield so both claim attempts have a chance to interleave.
      await Promise.resolve();
      return { ok: true, mode: "dry_run", message: "dry run" } as PublishResult;
    },
  };

  const [a, b] = await Promise.all([
    approvePost("post_1", deps),
    approvePost("post_1", deps),
  ]);

  const okCount = [a, b].filter((r) => r.ok).length;
  assert.equal(okCount, 1, "exactly one request may win the claim");
  assert.equal(publishCalls, 1, "the publisher is invoked at most once");
  assert.equal(fake.post("post_1")?.status, "published");
});

test("a failed publish returns the post to a retryable pending state", async () => {
  const fake = makeFakeStore(baseStore());
  let publishCalls = 0;
  const deps: ApproveDeps = {
    readStore: fake.readStore,
    writeStore: fake.writeStore,
    publish: async () => {
      publishCalls += 1;
      return { ok: false, message: "LinkedIn publish failed (502)" } as PublishResult;
    },
  };

  const failed = await approvePost("post_1", deps);
  assert.equal(failed.ok, false);
  assert.equal((failed as { status: number }).status, 502);
  assert.equal(fake.post("post_1")?.status, "pending_approval");
  assert.equal(fake.post("post_1")?.publishToken, undefined);
  assert.equal(publishCalls, 1);

  // The post is retryable: a later successful approve publishes it.
  deps.publish = async () => {
    publishCalls += 1;
    return { ok: true, mode: "dry_run", message: "dry run" } as PublishResult;
  };
  const retried = await approvePost("post_1", deps);
  assert.equal(retried.ok, true);
  assert.equal(fake.post("post_1")?.status, "published");
});

test("approving a missing post returns 404 without publishing", async () => {
  const fake = makeFakeStore(baseStore());
  let publishCalls = 0;
  const deps: ApproveDeps = {
    readStore: fake.readStore,
    writeStore: fake.writeStore,
    publish: async () => {
      publishCalls += 1;
      return { ok: true, mode: "dry_run", message: "dry run" } as PublishResult;
    },
  };
  const outcome = await approvePost("nope", deps);
  assert.equal(outcome.ok, false);
  assert.equal((outcome as { status: number }).status, 404);
  assert.equal(publishCalls, 0);
});
