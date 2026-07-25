import { timingSafeEqual } from "crypto";
import { cookies } from "next/headers";
import { hashSessionToken } from "./session-token";

export const OPS_COOKIE = "mobi_linkedin_ops_session";

function safeEqualHex(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  if (left.length !== right.length) return false;
  return timingSafeEqual(left, right);
}

export function passwordConfigured(): boolean {
  return Boolean(process.env.OPS_PASSWORD?.trim());
}

export async function makeSessionToken(password: string): Promise<string> {
  return hashSessionToken(password);
}

export async function verifyPassword(password: string): Promise<boolean> {
  const configured = process.env.OPS_PASSWORD?.trim();
  if (!configured) return true;
  const a = await hashSessionToken(password);
  const b = await hashSessionToken(configured);
  return safeEqualHex(a, b);
}

export async function isAuthenticated(): Promise<boolean> {
  const configured = process.env.OPS_PASSWORD?.trim();
  if (!configured) return true;
  const jar = await cookies();
  const token = jar.get(OPS_COOKIE)?.value;
  if (!token) return false;
  const expected = await hashSessionToken(configured);
  return safeEqualHex(token, expected);
}
