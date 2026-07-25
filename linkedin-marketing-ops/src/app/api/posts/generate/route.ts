import { NextResponse } from "next/server";
import { z } from "zod";
import { aiMode, generatePostDrafts } from "@/lib/ai";
import { readStore, writeStore } from "@/lib/store";

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
  await writeStore(current);

  return NextResponse.json({ items, aiMode: aiMode() });
}
