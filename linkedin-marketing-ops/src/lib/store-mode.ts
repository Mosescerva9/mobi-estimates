/**
 * Durable-store mode selection — pure and side-effect free so it can be unit
 * tested without touching the filesystem, network, or real environment.
 *
 * Rules (in order):
 *  1. If both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set → "supabase".
 *  2. Otherwise, in a production/hosted environment → fail closed (throw).
 *     We never silently fall back to ephemeral /tmp JSON on Vercel, because
 *     that data would vanish between requests.
 *  3. Otherwise (local development) → "file" JSON store.
 */

export type StoreMode = "supabase" | "file";

/** Thrown when durable storage is required but not configured. */
export class StoreConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StoreConfigError";
  }
}

/**
 * Thrown when a durable write loses an optimistic compare-and-swap: the row
 * changed since it was read, so applying this write would silently clobber
 * another request. Callers should surface HTTP 409 and ask the owner to reload.
 */
export class StoreConflictError extends Error {
  constructor(
    message = "The queue changed while you were working on it. Reload and try again."
  ) {
    super(message);
    this.name = "StoreConflictError";
  }
}

/** Minimal shape of the environment we read — keeps the function easy to test. */
export type StoreEnv = {
  SUPABASE_URL?: string;
  SUPABASE_SERVICE_ROLE_KEY?: string;
  NODE_ENV?: string;
  VERCEL?: string;
};

export function hasSupabaseConfig(env: StoreEnv): boolean {
  return Boolean(env.SUPABASE_URL?.trim() && env.SUPABASE_SERVICE_ROLE_KEY?.trim());
}

export function isHostedEnvironment(env: StoreEnv): boolean {
  return env.NODE_ENV === "production" || Boolean(env.VERCEL?.trim());
}

export function selectStoreMode(env: StoreEnv = process.env): StoreMode {
  if (hasSupabaseConfig(env)) return "supabase";

  if (isHostedEnvironment(env)) {
    throw new StoreConfigError(
      "Durable storage is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY " +
        "so the LinkedIn Ops queue is saved permanently. Refusing to use temporary storage " +
        "that would be lost between requests."
    );
  }

  return "file";
}
