import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import {
  generateCaptureToken,
  hashCaptureToken,
  tokenLast4,
} from "@/lib/scout-token";
import { updateStore } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * Owner-authenticated pairing manager (behind the session cookie — NOT in the
 * middleware integration allow-list). Creating or rotating generates a fresh
 * high-entropy capture token, stores ONLY its domain-separated hash + last4, and returns
 * the plaintext EXACTLY once. There is no way to read a stored token back.
 */

const bodySchema = z.object({ action: z.enum(["create", "rotate"]) }).optional();

export async function POST(req: Request) {
  // Body is optional; both create and rotate do the same thing (replace the
  // active token). We accept either so the UI can label the action clearly.
  const raw = await req.json().catch(() => ({}));
  const parsed = bodySchema.safeParse(raw ?? {});
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  const token = generateCaptureToken();
  const now = new Date().toISOString();
  try {
    await updateStore((store) => {
      store.scout = {
        captureTokenHash: hashCaptureToken(token),
        captureTokenLast4: tokenLast4(token),
        captureTokenUpdatedAt: now,
      };
      return store;
    });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }

  // The ONLY time the plaintext token is ever returned. It is not persisted.
  return NextResponse.json({
    token,
    last4: tokenLast4(token),
    updatedAt: now,
    warning:
      "Copy this pairing code now — it is shown only once and cannot be retrieved later.",
  });
}

/** Revoke the pairing: clears the stored hash so no capture token works until a
 * new one is created. */
export async function DELETE() {
  try {
    await updateStore((store) => {
      store.scout = {};
      return store;
    });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
  return NextResponse.json({ revoked: true });
}
