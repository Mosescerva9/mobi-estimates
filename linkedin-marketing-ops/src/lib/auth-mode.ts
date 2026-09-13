/**
 * Access-control mode selection — pure and side-effect free so it can be unit
 * tested and safely imported into Edge middleware.
 *
 * Rules (in order):
 *  1. OPS_PASSWORD is set              → "enforce" (require a login).
 *  2. Otherwise, hosted/production env → "unconfigured-hosted" (fail closed).
 *     A hosted deployment with no password would expose the dashboard to
 *     anyone, so we refuse to treat callers as authenticated.
 *  3. Otherwise (local development)    → "open" (no login, dev convenience).
 */

import { isHostedEnvironment } from "./store-mode";

export type AuthState = "enforce" | "unconfigured-hosted" | "open";

/** Minimal shape of the environment we read — keeps the function easy to test. */
export type AuthEnv = {
  OPS_PASSWORD?: string;
  NODE_ENV?: string;
  VERCEL?: string;
};

export const AUTH_CONFIG_MESSAGE =
  "This dashboard is not configured for access. Set the OPS_PASSWORD environment " +
  "variable so a login is required before anyone can review or approve LinkedIn " +
  "drafts. Until then the dashboard is locked.";

/** Thrown/returned when a login is required but no password is configured. */
export class AuthConfigError extends Error {
  constructor(message = AUTH_CONFIG_MESSAGE) {
    super(message);
    this.name = "AuthConfigError";
  }
}

export function classifyAuth(env: AuthEnv = process.env): AuthState {
  if (env.OPS_PASSWORD?.trim()) return "enforce";
  if (isHostedEnvironment(env)) return "unconfigured-hosted";
  return "open";
}
