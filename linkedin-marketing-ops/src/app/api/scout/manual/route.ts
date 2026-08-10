import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import {
  SCOUT_AUTHOR_FIELD_MAX,
  SCOUT_SOURCE_TEXT_MAX,
  applyCapture,
} from "@/lib/scout";
import { readStore, updateStore } from "@/lib/store";
import { StoreConfigError } from "@/lib/store-mode";

export const dynamic = "force-dynamic";

/**
 * Owner paste capture — uses the logged-in dashboard session.
 * No Safari/Chrome extension required.
 */
const bodySchema = z.object({
  postUrl: z.string().min(8).max(2048),
  sourceText: z.string().min(8).max(SCOUT_SOURCE_TEXT_MAX),
  authorName: z.string().max(SCOUT_AUTHOR_FIELD_MAX).optional(),
  authorHeadline: z.string().max(SCOUT_AUTHOR_FIELD_MAX).optional(),
  authorCompany: z.string().max(SCOUT_AUTHOR_FIELD_MAX).optional(),
});

export async function POST(req: Request) {
  const parsed = bodySchema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json(
      {
        error:
          "Need a LinkedIn post URL and the post text (at least a couple of sentences).",
      },
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
      const result = applyCapture(store, [parsed.data], now);
      store.scoutCandidates = result.candidates;
      summary = result.summary;
      return store;
    });

    if (summary.invalid > 0) {
      return NextResponse.json(
        {
          error:
            "That LinkedIn URL or post text could not be saved. Use Share → Copy link on the post, and paste the visible post text.",
          ...summary,
        },
        { status: 400 }
      );
    }

    return NextResponse.json({
      ok: true,
      ...summary,
      message:
        summary.duplicates > 0
          ? "Already in Scout — skipped duplicate."
          : "Saved to Scout inbox.",
    });
  } catch (err) {
    if (err instanceof StoreConfigError) {
      return NextResponse.json({ error: err.message }, { status: 503 });
    }
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}
