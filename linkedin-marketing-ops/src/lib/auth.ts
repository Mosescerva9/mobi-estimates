import { timingSafeEqual } from "crypto";
import { cookies } from "next/headers";
import { AuthConfigError, classifyAuth } from "./auth-mode";
import { hashSessionToken } from "./session-token";

export const OPS_COOKIE = "mobi_linkedin_ops_session";

function safeEqualHex(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  if (left.length !== right.length) return false;
  return timingSafeEqual(left, right);
}

/** True when a login is required (a password is configured). */
export function passwordConfigured(): boolean {
  return classifyAuth(process.env) === "enforce";
}

/**
 * Returns an AuthConfigError when the app is hosted but no OPS_PASSWORD is set.
 * Callers use this to fail closed with an owner-readable configuration message
 * instead of exposing the dashboard.
 */
export function authConfigError(): AuthConfigError | null {
  return classifyAuth(process.env) === "unconfigured-hosted" ? new AuthConfigError() : null;
}

export async function makeSessionToken(password: string): Promise<string> {
  return hashSessionToken(password);
}

export async function verifyPassword(password: string): Promise<boolean> {
  // A login can only succeed when a password is actually configured. In a
  // misconfigured hosted deployment (no password) there is nothing to match,
  // so we refuse rather than fail open.
  if (classifyAuth(process.env) !== "enforce") return false;
  const configured = process.env.OPS_PASSWORD!.trim();
  const a = await hashSessionToken(password);
  const b = await hashSessionToken(configured);
  return safeEqualHex(a, b);
}

export async function isAuthenticated(): Promise<boolean> {
  const state = classifyAuth(process.env);
  // Hosted with no password → fail closed. Local dev with no password → open.
  if (state === "unconfigured-hosted") return false;
  if (state === "open") return true;

  const configured = process.env.OPS_PASSWORD!.trim();
  const jar = await cookies();
  const token = jar.get(OPS_COOKIE)?.value;
  if (!token) return false;
  const expected = await hashSessionToken(configured);
  return safeEqualHex(token, expected);
}
