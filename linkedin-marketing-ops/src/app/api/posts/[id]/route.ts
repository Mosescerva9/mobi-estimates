import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import { approvePost } from "@/lib/post-approve";
import { readStore, writeStore } from "@/lib/store";

export const dynamic = "force-dynamic";

const patchSchema = z.object({
  action: z.enum(["approve", "reject", "edit", "schedule"]),
  body: z.string().optional(),
  topic: z.string().optional(),
  cta: z.string().optional(),
  scheduledFor: z.string().nullable().optional(),
});

type Params = { params: Promise<{ id: string }> };

export async function PATCH(req: Request, { params }: Params) {
  const { id } = await params;
  const parsed = patchSchema.safeParse(await req.json());
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  const { action } = parsed.data;

  // Approve runs through the CAS-protected claim so it can never double-publish.
  if (action === "approve") {
    try {
      const outcome = await approvePost(id);
      if (!outcome.ok) {
        return NextResponse.json(
          { error: outcome.error, item: outcome.item },
          { status: outcome.status }
        );
      }
      return NextResponse.json({ item: outcome.item, publish: outcome.publish });
    } catch (err) {
      const res = storeErrorResponse(err);
      if (res) return res;
      throw err;
    }
  }

  try {
    const store = await readStore();
    const idx = store.posts.findIndex((p) => p.id === id);
    if (idx < 0) {
      return NextResponse.json({ error: "Post not found" }, { status: 404 });
    }

    const post = store.posts[idx];
    const now = new Date().toISOString();

    if (action === "edit") {
      if (parsed.data.body !== undefined) post.body = parsed.data.body;
      if (parsed.data.topic !== undefined) post.topic = parsed.data.topic;
      if (parsed.data.cta !== undefined) post.cta = parsed.data.cta;
      post.updatedAt = now;
    } else if (action === "reject") {
      post.status = "rejected";
      post.updatedAt = now;
    } else if (action === "schedule") {
      post.status = "scheduled";
      post.scheduledFor = parsed.data.scheduledFor ?? null;
      post.updatedAt = now;
    }

    await writeStore(store);
    return NextResponse.json({ item: post });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}
