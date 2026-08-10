import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import {
  InvalidJsonBodyError,
  JsonBodyTooLargeError,
  readJsonBodyLimited,
} from "@/lib/request-body";
import { authorizeCapture } from "@/lib/scout-auth";
import {
  SCOUT_AUTHOR_FIELD_MAX,
  SCOUT_MAX_CAPTURE_ITEMS,
  SCOUT_SOURCE_TEXT_MAX,
  applyCapture,
} from "@/lib/scout";
import { readStore, updateStore } from "@/lib/store";
import { StoreConfigError } from "@/lib/store-mode";

export const dynamic = "force-dynamic";
const CAPTURE_BODY_MAX_BYTES = 192 * 1024;

class CaptureAuthChangedError extends Error {
  constructor(
    readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "CaptureAuthChangedError";
  }
}

/**
 * Capture endpoint for the iPhone Safari extension. Allowed THROUGH middleware
 * (self-authenticated), but independently requires the capture bearer token —
 * missing pairing or a wrong token fails closed here. Tokens are only accepted
 * in the Authorization header, never in the URL. No GET handler exists (a GET
 * would 405) so there is no read/side-effect surface.
 */

const itemSchema = z.object({
  postUrl: z.string().max(2048),
  sourceText: z.string().max(SCOUT_SOURCE_TEXT_MAX),
  authorName: z.string().max(SCOUT_AUTHOR_FIELD_MAX).optional(),
  authorHeadline: z.string().max(SCOUT_AUTHOR_FIELD_MAX).optional(),
  authorCompany: z.string().max(SCOUT_AUTHOR_FIELD_MAX).optional(),
});

const bodySchema = z.object({
  items: z.array(itemSchema).min(1).max(SCOUT_MAX_CAPTURE_ITEMS),
});

export async function POST(req: Request) {
  const authorization = req.headers.get("authorization");
  // Read the pairing state first so we can authenticate before doing any work.
  let paired;
  try {
    paired = await readStore();
  } catch (err) {
    if (err instanceof StoreConfigError) {
      return NextResponse.json({ error: err.message }, { status: 503 });
    }
    throw err;
  }

  const auth = authorizeCapture(authorization, paired.scout);
  if (!auth.ok) {
    return NextResponse.json({ error: auth.error }, { status: auth.status });
  }

  let raw: unknown;
  try {
    raw = await readJsonBodyLimited(req, CAPTURE_BODY_MAX_BYTES);
  } catch (err) {
    if (err instanceof JsonBodyTooLargeError) {
      return NextResponse.json({ error: "Capture payload is too large." }, { status: 413 });
    }
    if (err instanceof InvalidJsonBodyError) {
      return NextResponse.json({ error: "Invalid capture payload." }, { status: 400 });
    }
    throw err;
  }

  const parsed = bodySchema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid capture payload." },
      { status: 400 }
    );
  }

  const now = new Date().toISOString();
  try {
    let summary = {
      accepted: 0,
      duplicates: 0,
      invalid: 0,
      capacityRejected: 0,
    };
    await updateStore((store) => {
      // Re-authorize against every fresh CAS snapshot. If pairing was rotated or
      // revoked after the initial read, an old token must not write on retry.
      const freshAuth = authorizeCapture(authorization, store.scout);
      if (!freshAuth.ok) {
        throw new CaptureAuthChangedError(freshAuth.status, freshAuth.error);
      }
      const result = applyCapture(store, parsed.data.items, now);
      store.scoutCandidates = result.candidates;
      summary = result.summary;
      return store;
    });
    return NextResponse.json({ ok: true, ...summary });
  } catch (err) {
    if (err instanceof CaptureAuthChangedError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}
