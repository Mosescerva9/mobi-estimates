/**
 * Post approval with an atomic, CAS-protected claim so a post can never be
 * double-published — not by a repeated click and not by two concurrent
 * requests.
 *
 * Flow:
 *  1. The post must be `pending_approval` (precondition).
 *  2. Claim it: pending_approval → approved + a unique publishToken, written
 *     through the compare-and-swap store. Only ONE request can win this write;
 *     any other concurrent request either loses the CAS or reads a non-pending
 *     status and bails without publishing.
 *  3. Only the claim winner calls the publisher (LinkedIn / dry-run).
 *  4. On success → approved → published. On failure → back to pending_approval
 *     (retryable). Both are recorded against our own claim token via a
 *     CAS-safe retry so unrelated queue changes are never overwritten.
 */

import { createId } from "./id";
import { publishPost, type PublishResult } from "./linkedin";
import { readStore as defaultReadStore, writeStore as defaultWriteStore } from "./store";
import { StoreConflictError } from "./store-mode";
import type { PostItem, StoreData } from "./types";

export type ApproveDeps = {
  readStore: () => Promise<StoreData>;
  writeStore: (data: StoreData) => Promise<void>;
  publish: (body: string) => Promise<PublishResult>;
};

const defaultDeps: ApproveDeps = {
  readStore: defaultReadStore,
  writeStore: defaultWriteStore,
  publish: publishPost,
};

export type ApproveOutcome =
  | { ok: true; item: PostItem; publish: PublishResult }
  | { ok: false; status: number; error: string; item?: PostItem };

function postBody(post: PostItem): string {
  return [post.body, "", post.cta].filter(Boolean).join("\n");
}

/**
 * Re-read fresh data, find our claimed attempt (matched by publishToken), apply
 * a mutation, and write it back with CAS-safe retries. If another request has
 * already resolved our claim (token no longer matches), we leave it untouched.
 */
async function resolveClaim(
  deps: ApproveDeps,
  id: string,
  token: string,
  apply: (post: PostItem) => void
): Promise<PostItem | null> {
  const MAX_ATTEMPTS = 5;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const store = await deps.readStore();
    const post = store.posts.find((p) => p.id === id);
    if (!post) return null;
    // Our attempt was already resolved by someone else — don't overwrite it.
    if (post.publishToken !== token) return post;
    apply(post);
    post.updatedAt = new Date().toISOString();
    try {
      await deps.writeStore(store);
      return post;
    } catch (err) {
      if (err instanceof StoreConflictError && attempt < MAX_ATTEMPTS) continue;
      throw err;
    }
  }
  return null;
}

export async function approvePost(
  id: string,
  deps: ApproveDeps = defaultDeps
): Promise<ApproveOutcome> {
  const store = await deps.readStore();
  const post = store.posts.find((p) => p.id === id);
  if (!post) {
    return { ok: false, status: 404, error: "Post not found" };
  }

  // Precondition: only a post awaiting approval can be published. A repeated
  // approve (already approved/published/rejected) is rejected without publishing.
  if (post.status !== "pending_approval") {
    return {
      ok: false,
      status: 409,
      error: `This post is not awaiting approval (it is “${post.status}”). It was not published again.`,
      item: post,
    };
  }

  // Atomically claim the post before any LinkedIn call.
  const token = createId("pub");
  post.status = "approved";
  post.publishToken = token;
  post.updatedAt = new Date().toISOString();
  try {
    await deps.writeStore(store);
  } catch (err) {
    if (err instanceof StoreConflictError) {
      // Someone else claimed/changed this post first — we did not publish.
      return {
        ok: false,
        status: 409,
        error:
          "Another approval for this post is already in progress. It was not published twice.",
        item: post,
      };
    }
    throw err;
  }

  // Only the claim winner reaches here, so the publisher runs at most once.
  const result = await deps.publish(postBody(post));

  if (result.ok) {
    const finalItem = await resolveClaim(deps, id, token, (p) => {
      p.status = "published";
      p.notes = result.message;
      delete p.publishToken;
    });
    if (!finalItem) {
      return {
        ok: false,
        status: 409,
        error:
          "The post was published, but the queue changed before the status could be saved. Reload to confirm.",
      };
    }
    return { ok: true, item: finalItem, publish: result };
  }

  // Publish failed — return the claim to a retryable pending state.
  const reverted = await resolveClaim(deps, id, token, (p) => {
    p.status = "pending_approval";
    delete p.publishToken;
  });
  return {
    ok: false,
    status: 502,
    error: result.message,
    item: reverted ?? post,
  };
}
