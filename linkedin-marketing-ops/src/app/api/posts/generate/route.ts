import { NextResponse } from "next/server";
import { z } from "zod";
import { aiMode, generatePostDrafts } from "@/lib/ai";
import { storeErrorResponse } from "@/lib/api-errors";
import { readStore, writeStore } from "@/lib/store";

export const dynamic = "force-dynamic";

const schema = z.object({
  count: z.number().int().min(1).max(10).optional(),
});

export async function POST(req: Request) {
  const json = await req.json().catch(() => ({}));
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const current = await readStore();
  const items = await generatePostDrafts(current.settings, parsed.data.count ?? 3);
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