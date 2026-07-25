import { NextResponse } from "next/server";
import { z } from "zod";
import { aiMode, generateDmDraft } from "@/lib/ai";
import { readStore, writeStore } from "@/lib/store";

const createSchema = z.object({
  leadName: z.string().min(2),
  leadTitle: z.string().min(2),
  leadCompany: z.string().min(2),
  trigger: z.enum([
    "liked_post",
    "commented",
    "accepted_connect",
    "demo_request",
    "site_visit",
  ]),
});

export async function GET() {
  const store = await readStore();
  return NextResponse.json({ items: store.dms });
}

export async function POST(req: Request) {
  const parsed = createSchema.safeParse(await req.json());
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const store = await readStore();
  const blocked = store.settings.doNotContact.some((name) =>
    parsed.data.leadName.toLowerCase().includes(name.toLowerCase())
  );
  if (blocked) {
    return NextResponse.json(
      { error: "Lead is on the do-not-contact list." },
      { status: 400 }
    );
  }

  const item = await generateDmDraft(store.settings, parsed.data);
  store.dms = [item, ...store.dms];
  await writeStore(store);

  return NextResponse.json({ item, aiMode: aiMode() });
}
