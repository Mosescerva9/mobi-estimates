import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import { SCOUT_JOB_BATCH_CAP } from "@/lib/scout";
import { processScoutLocally } from "@/lib/scout-local";
import { readStore, writeStore } from "@/lib/store";
import { StoreConfigError } from "@/lib/store-mode";

export const dynamic = "force-dynamic";

const schema = z.object({
  limit: z.number().int().min(1).max(SCOUT_JOB_BATCH_CAP).optional(),
});

/**
 * Draft comment recommendations for collected Scout posts using the app's
 * normal AI layer. Owner-session only. Does not require Hermes or SCOUT_JOB_TOKEN.
 * Never posts to LinkedIn.
 */
export async function POST(req: Request) {
  const parsed = schema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  try {
    const store = await readStore();
    const result = await processScoutLocally(
      store,
      parsed.data.limit ?? SCOUT_JOB_BATCH_CAP
    );
    await writeStore(result.store);
    return NextResponse.json({
      ok: true,
      batchId: result.batchId,
      queued: result.queued,
      skipped: result.skipped,
      message:
        result.queued > 0
          ? `Drafted ${result.queued} comment${result.queued === 1 ? "" : "s"} into Engage for approval.`
          : result.skipped > 0
            ? `No comments drafted. Skipped ${result.skipped} post${result.skipped === 1 ? "" : "s"} (off-topic, sensitive, or too little text).`
            : "No waiting Scout posts to process. Paste a LinkedIn post into Scout first.",
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
