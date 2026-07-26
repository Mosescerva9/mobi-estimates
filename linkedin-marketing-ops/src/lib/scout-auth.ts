/**
 * Route-level bearer authorization for the two Scout integration endpoints.
 * Pure and side-effect free so the fail-closed rules can be unit tested without
 * a live request.
 *
 * Two secrets, never interchangeable:
 *  - capture token: validated against the domain-separated hash stored in app state.
 *  - job token: validated against the SCOUT_JOB_TOKEN environment variable.
 *
 * Both use constant-time comparison. Missing configuration fails CLOSED: a
 * missing SCOUT_JOB_TOKEN yields 503, an app with no pairing code yields 503.
 * A capture token can never satisfy the job endpoint and vice-versa because the
 * comparison targets are different values reached only from different routes.
 */

import { bearerFromHeader, constantTimeEqual, hashCaptureToken } from "./scout-token";
import type { ScoutState } from "./types";

export type ScoutAuthOutcome = { ok: true } | { ok: false; status: number; error: string };

export type ScoutJobEnv = { SCOUT_JOB_TOKEN?: string; [key: string]: string | undefined };

/** True when the Hermes job token is configured in the environment. */
export function jobTokenConfigured(env: ScoutJobEnv = process.env): boolean {
  return Boolean(env.SCOUT_JOB_TOKEN?.trim());
}

/**
 * Authorize a Hermes job request. Fails closed with 503 when SCOUT_JOB_TOKEN is
 * unset, 401 when the bearer token is missing or does not match.
 */
export function authorizeJob(
  authorizationHeader: string | null | undefined,
  env: ScoutJobEnv = process.env
): ScoutAuthOutcome {
  const configured = env.SCOUT_JOB_TOKEN?.trim();
  if (!configured) {
    return {
      ok: false,
      status: 503,
      error: "The Scout job token is not configured on the server.",
    };
  }
  const presented = bearerFromHeader(authorizationHeader);
  if (!presented) {
    return { ok: false, status: 401, error: "A bearer job token is required." };
  }
  if (!constantTimeEqual(presented, configured)) {
    return { ok: false, status: 401, error: "Unauthorized." };
  }
  return { ok: true };
}

/**
 * Authorize a capture request from the Safari extension. Fails closed with 503
 * when no pairing code has been created (no stored hash), 401 when the bearer
 * token is missing or its hash does not match the stored hash.
 */
export function authorizeCapture(
  authorizationHeader: string | null | undefined,
  scout: ScoutState
): ScoutAuthOutcome {
  const storedHash = scout.captureTokenHash;
  if (!storedHash) {
    return {
      ok: false,
      status: 503,
      error: "No pairing code exists yet. Create one in the Scout tab first.",
    };
  }
  const presented = bearerFromHeader(authorizationHeader);
  if (!presented) {
    return { ok: false, status: 401, error: "A bearer capture token is required." };
  }
  if (!constantTimeEqual(hashCaptureToken(presented), storedHash)) {
    return { ok: false, status: 401, error: "Unauthorized." };
  }
  return { ok: true };
}
