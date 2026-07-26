import { NextResponse } from "next/server";
import { z } from "zod";
import { aiMode, generateEngageDraft } from "@/lib/ai";
import { readStore, writeStore } from "@/lib/store";

export const dynamic = "force-dynamic";

const createSchema = z.object({
  kind: z.enum(["comment", "connect"]),
  targetName: z.string().min(2),
  targetTitle: z.string().min(2),
  targetCompany: z.string().min(2),
  sourcePostSummary: z.string().min(5),
});

export async function GET() {
  const store = await readStore();
  return NextResponse.json({ items: store.engage });
}

export async function POST(req: Request) {
  const parsed = createSchema.safeParse(await req.json());
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const store = await readStore();
  const blocked = store.settings.doNotContact.some((name) =>
    parsed.data.targetName.toLowerCase().includes(name.toLowerCase())
  );
  if (blocked) {
    return NextResponse.json(
      { error: "Target is on the do-not-contact list." },
      { status: 400 }
    );
  }

  const item = await generateEngageDraft(store.settings, parsed.data);
  store.engage = [item, ...store.engage];
  await writeStore(store);

  return NextResponse.json({ item, aiMode: aiMode() });
}