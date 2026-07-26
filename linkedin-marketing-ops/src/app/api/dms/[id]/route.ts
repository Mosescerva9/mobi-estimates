import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import { assistedSendMessage } from "@/lib/linkedin";
import { readStore, writeStore } from "@/lib/store";

export const dynamic = "force-dynamic";

const schema = z.object({
  action: z.enum(["approve", "reject", "edit", "mark_sent"]),
  body: z.string().optional(),
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
    const item = store.dms.find((d) => d.id === id);
    if (!item) {
      return NextResponse.json({ error: "DM not found" }, { status: 404 });
    }

    const now = new Date().toISOString();
    if (parsed.data.action === "edit" && parsed.data.body !== undefined) {
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
      item,
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