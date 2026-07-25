import { NextResponse } from "next/server";
import { z } from "zod";
import { assistedSendMessage } from "@/lib/linkedin";
import { readStore, writeStore } from "@/lib/store";

const schema = z.object({
  action: z.enum(["approve", "reject", "skip", "edit"]),
  suggestedText: z.string().optional(),
});

type Params = { params: Promise<{ id: string }> };

export async function PATCH(req: Request, { params }: Params) {
  const { id } = await params;
  const parsed = schema.safeParse(await req.json());
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const store = await readStore();
  const item = store.engage.find((e) => e.id === id);
  if (!item) {
    return NextResponse.json({ error: "Engage item not found" }, { status: 404 });
  }

  const now = new Date().toISOString();
  if (parsed.data.action === "edit" && parsed.data.suggestedText !== undefined) {
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
    item,
    sendHint:
      parsed.data.action === "approve"
        ? assistedSendMessage(item.kind)
        : undefined,
  });
}
