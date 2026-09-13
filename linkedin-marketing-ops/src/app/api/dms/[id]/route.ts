import { NextResponse } from "next/server";
import { z } from "zod";
import { regenerateDmDraft } from "@/lib/ai";
import { storeErrorResponse } from "@/lib/api-errors";
import { assistedSendMessage } from "@/lib/linkedin";
import { readStore, writeStore } from "@/lib/store";

export const dynamic = "force-dynamic";

const schema = z.object({
  action: z.enum(["approve", "reject", "edit", "mark_sent", "regenerate"]),
  body: z.string().optional(),
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
    const idx = store.dms.findIndex((d) => d.id === id);
    if (idx < 0) {
      return NextResponse.json({ error: "DM not found" }, { status: 404 });
    }

    const item = store.dms[idx];
    const now = new Date().toISOString();
    if (parsed.data.action === "regenerate") {
      store.dms[idx] = await regenerateDmDraft(
        store.settings,
        item,
        parsed.data.instruction
      );
    } else if (parsed.data.action === "edit" && parsed.data.body !== undefined) {
      item.body = parsed.data.body;
      item.updatedAt = now;
    } else if (parsed.data.action === "approve") {
      item.status = "approved";
      item.updatedAt = now;
    } else if (parsed.data.action === "mark_sent") {
      item.status = "sent";
      item.updatedAt = now;
    } else if (parsed.data.action === "reject") {
      item.status = "rejected";
      item.updatedAt = now;
    }

    await writeStore(store);
    return NextResponse.json({
      item: store.dms[idx],
      sendHint:
        parsed.data.action === "approve"
          ? assistedSendMessage("dm")
          : undefined,
    });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}