import { NextResponse } from "next/server";
import { z } from "zod";
import { publishPost } from "@/lib/linkedin";
import { readStore, writeStore } from "@/lib/store";

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

  const store = await readStore();
  const idx = store.posts.findIndex((p) => p.id === id);
  if (idx < 0) {
    return NextResponse.json({ error: "Post not found" }, { status: 404 });
  }

  const post = store.posts[idx];
  const now = new Date().toISOString();
  const { action } = parsed.data;

  if (action === "edit") {
    if (parsed.data.body !== undefined) post.body = parsed.data.body;
    if (parsed.data.topic !== undefined) post.topic = parsed.data.topic;
    if (parsed.data.cta !== undefined) post.cta = parsed.data.cta;
    post.updatedAt = now;
    await writeStore(store);
    return NextResponse.json({ item: post });
  }

  if (action === "reject") {
    post.status = "rejected";
    post.updatedAt = now;
    await writeStore(store);
    return NextResponse.json({ item: post });
  }

  if (action === "schedule") {
    post.status = "scheduled";
    post.scheduledFor = parsed.data.scheduledFor ?? null;
    post.updatedAt = now;
    await writeStore(store);
    return NextResponse.json({ item: post });
  }

  // approve → attempt publish (or dry-run)
  const fullBody = [post.body, "", post.cta].filter(Boolean).join("\n");
  const result = await publishPost(fullBody);
  if (!result.ok) {
    return NextResponse.json({ error: result.message, item: post }, { status: 502 });
  }

  post.status = "published";
  post.updatedAt = now;
  post.notes = result.message;
  await writeStore(store);

  return NextResponse.json({
    item: post,
    publish: result,
  });
}
