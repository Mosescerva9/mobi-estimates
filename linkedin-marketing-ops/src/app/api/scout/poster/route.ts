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
  approveForPoster,
  claimApprovedComment,
  completePostedComment,
  posterItemPayload,
} from "@/lib/scout-poster";
import { readStore, writeStore } from "@/lib/store";
import { StoreConfigError } from "@/lib/store-mode";

export const dynamic = "force-dynamic";
const BODY_MAX = 16 * 1024;

/**
 * Extension poster control plane (capture bearer token).
 *  - next: claim the next approved comment (optionally for a post URL)
 *  - approve: move a pending draft to approved after the owner confirms text
 *  - complete: mark an approved comment as posted after the page submit succeeds
 *
 * Never calls LinkedIn itself.
 */

const schema = z.discriminatedUnion("action", [
  z.object({
    action: z.literal("next"),
    postUrl: z.string().max(2048).optional(),
  }),
  z.object({
    action: z.literal("approve"),
    engageId: z.string().min(1).max(120),
    suggestedText: z.string().max(400).optional(),
    sourcePostUrl: z.string().max(2048),
  }),
  z.object({
    action: z.literal("complete"),
    engageId: z.string().min(1).max(120),
  }),
]);

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
      return NextResponse.json({ error: "Poster payload is too large." }, { status: 413 });
    }
    if (err instanceof InvalidJsonBodyError) {
      return NextResponse.json({ error: "Invalid poster payload." }, { status: 400 });
    }
    throw err;
  }

  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid poster payload." }, { status: 400 });
  }

  const now = new Date().toISOString();

  try {
    const store = await readStore();
    const freshAuth = authorizeCapture(authorization, store.scout);
    if (!freshAuth.ok) {
      return NextResponse.json({ error: freshAuth.error }, { status: freshAuth.status });
    }

    if (parsed.data.action === "next") {
      const claim = claimApprovedComment(store, parsed.data.postUrl);
      if (!claim.ok) {
        return NextResponse.json({ error: claim.error }, { status: claim.status });
      }
      return NextResponse.json({ ok: true, item: posterItemPayload(claim.item) });
    }

    if (parsed.data.action === "approve") {
      const result = approveForPoster(
        store,
        parsed.data.engageId,
        parsed.data.suggestedText,
        parsed.data.sourcePostUrl,
        now
      );
      if (!result.ok) {
        return NextResponse.json({ error: result.error }, { status: result.status });
      }
      await writeStore(result.store);
      return NextResponse.json({ ok: true, item: posterItemPayload(result.item) });
    }

    // complete
    const result = completePostedComment(store, parsed.data.engageId, now);
    if (!result.ok) {
      return NextResponse.json({ error: result.error }, { status: result.status });
    }
    await writeStore(result.store);
    return NextResponse.json({ ok: true, item: posterItemPayload(result.item) });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}
