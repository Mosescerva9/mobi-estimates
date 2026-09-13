import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import {
  InvalidJsonBodyError,
  JsonBodyTooLargeError,
  readJsonBodyLimited,
} from "@/lib/request-body";
import { authorizeCapture } from "@/lib/scout-auth";
import { draftOneComment } from "@/lib/scout-draft-one";
import { posterItemPayload } from "@/lib/scout-poster";
import {
  SCOUT_AUTHOR_FIELD_MAX,
  SCOUT_SOURCE_TEXT_MAX,
} from "@/lib/scout";
import { readStore, writeStore } from "@/lib/store";
import { StoreConfigError } from "@/lib/store-mode";

export const dynamic = "force-dynamic";
const BODY_MAX = 32 * 1024;

/**
 * Extension: capture one LinkedIn post the owner is looking at and draft a
 * comment for approval. Self-authenticated with the capture bearer token.
 * Never posts to LinkedIn.
 */

const bodySchema = z.object({
  postUrl: z.string().max(2048),
  sourceText: z.string().max(SCOUT_SOURCE_TEXT_MAX),
  authorName: z.string().max(SCOUT_AUTHOR_FIELD_MAX).optional(),
  authorHeadline: z.string().max(SCOUT_AUTHOR_FIELD_MAX).optional(),
  authorCompany: z.string().max(SCOUT_AUTHOR_FIELD_MAX).optional(),
});

export async function POST(req: Request) {
  const authorization = req.headers.get("authorization");
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
    raw = await readJsonBodyLimited(req, BODY_MAX);
  } catch (err) {
    if (err instanceof JsonBodyTooLargeError) {
      return NextResponse.json({ error: "Draft payload is too large." }, { status: 413 });
    }
    if (err instanceof InvalidJsonBodyError) {
      return NextResponse.json({ error: "Invalid draft payload." }, { status: 400 });
    }
    throw err;
  }

  const parsed = bodySchema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid draft payload." }, { status: 400 });
  }

  try {
    // Re-check auth against the store we will mutate.
    const store = await readStore();
    const freshAuth = authorizeCapture(authorization, store.scout);
    if (!freshAuth.ok) {
      return NextResponse.json({ error: freshAuth.error }, { status: freshAuth.status });
    }

    const result = await draftOneComment(store, parsed.data);
    if (!result.ok) {
      return NextResponse.json({ error: result.error }, { status: result.status });
    }

    if (!result.reused) {
      await writeStore(result.store);
    }

    return NextResponse.json({
      ok: true,
      reused: result.reused,
      item: posterItemPayload(result.item),
    });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}
