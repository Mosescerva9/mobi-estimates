import { NextResponse } from "next/server";
import { z } from "zod";
import { regenerateEngageDraft } from "@/lib/ai";
import { storeErrorResponse } from "@/lib/api-errors";
import { assistedSendMessage } from "@/lib/linkedin";
import { readStore, writeStore } from "@/lib/store";

export const dynamic = "force-dynamic";

const schema = z.object({
  action: z.enum(["approve", "reject", "skip", "edit", "regenerate"]),
  suggestedText: z.string().optional(),
  instruction: z.string().max(400).optional(),
});

type Params = { params: Promise<{ id: string }> };

export async function PATCH(req: Request, { params }: Params) {
  const { id } = await params;
  const parsed = schema.safeParse(await req.json());
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  try {
    const store = await readStore();
    const idx = store.engage.findIndex((e) => e.id === id);
    if (idx < 0) {
      return NextResponse.json({ error: "Engage item not found" }, { status: 404 });
    }

    const item = store.engage[idx];
    const now = new Date().toISOString();
    if (parsed.data.action === "regenerate") {
      store.engage[idx] = await regenerateEngageDraft(
        store.settings,
        item,
        parsed.data.instruction
      );
    } else if (
      parsed.data.action === "edit" &&
      parsed.data.suggestedText !== undefined
    ) {
      item.suggestedText = parsed.data.suggestedText;
      item.updatedAt = now;
    } else if (parsed.data.action === "approve") {
      item.status = "approved";
      item.updatedAt = now;
    } else if (parsed.data.action === "reject") {
      item.status = "rejected";
      item.updatedAt = now;
    } else if (parsed.data.action === "skip") {
      item.status = "skipped";
      item.updatedAt = now;
    }

    await writeStore(store);
    return NextResponse.json({
      item: store.engage[idx],
      sendHint:
        parsed.data.action === "approve"
          ? assistedSendMessage(store.engage[idx].kind)
          : undefined,
    });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}