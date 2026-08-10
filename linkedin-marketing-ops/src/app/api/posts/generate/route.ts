import { NextResponse } from "next/server";
import { z } from "zod";
import { aiMode, generatePostDrafts } from "@/lib/ai";
import { storeErrorResponse } from "@/lib/api-errors";
import type { PostAngle } from "@/lib/prompts";
import { readStore, writeStore } from "@/lib/store";

export const dynamic = "force-dynamic";

const schema = z.object({
  count: z.number().int().min(1).max(10).optional(),
  angle: z
    .enum([
      "bid_night_pain",
      "takeoff_quality",
      "overflow_capacity",
      "field_to_office",
      "scope_clarity",
      "hiring_vs_outsource",
      "first_estimate_path",
    ])
    .optional(),
});

export async function POST(req: Request) {
  const json = await req.json().catch(() => ({}));
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const current = await readStore();
  const items = await generatePostDrafts(
    current.settings,
    parsed.data.count ?? 3,
    parsed.data.angle as PostAngle | undefined
  );
  current.posts = [...items, ...current.posts];
  try {
    await writeStore(current);
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }

  return NextResponse.json({ items, aiMode: aiMode() });
}
