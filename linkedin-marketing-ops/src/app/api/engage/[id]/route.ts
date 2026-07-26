import { NextResponse } from "next/server";
import { z } from "zod";
import { regenerateEngageDraft } from "@/lib/ai";
import { storeErrorResponse } from "@/lib/api-errors";
import {
  approveEngageItem,
  checkEngageEditable,
  markCommented,
  setEngageSourceUrl,
  transitionPendingEngage,
} from "@/lib/engage";
import { assistedSendMessage } from "@/lib/linkedin";
import { readStore, writeStore } from "@/lib/store";

export const dynamic = "force-dynamic";

const schema = z.object({
  action: z.enum([
    "approve",
    "reject",
    "skip",
    "edit",
    "regenerate",
    "mark_commented",
    "set_source_url",
  ]),
  suggestedText: z.string().optional(),
  instruction: z.string().max(400).optional(),
  sourcePostUrl: z.string().max(2048).optional(),
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
      // Rewriting is only valid while pending — approved/sent text is immutable.
      const guard = checkEngageEditable(item, "regenerate");
      if (!guard.ok) {
        return NextResponse.json({ error: guard.error }, { status: guard.status });
      }
      store.engage[idx] = await regenerateEngageDraft(
        store.settings,
        item,
        parsed.data.instruction
      );
    } else if (
      parsed.data.action === "edit" &&
      parsed.data.suggestedText !== undefined
    ) {
      // Editing is only valid while pending — approved/sent text is immutable.
      const guard = checkEngageEditable(item, "edit");
      if (!guard.ok) {
        return NextResponse.json({ error: guard.error }, { status: guard.status });
      }
      item.suggestedText = parsed.data.suggestedText;
      item.updatedAt = now;
    } else if (parsed.data.action === "set_source_url") {
      // Owner repairs a pending legacy comment by attaching a valid post URL.
      const result = setEngageSourceUrl(item, parsed.data.sourcePostUrl, now);
      if (!result.ok) {
        return NextResponse.json({ error: result.error }, { status: result.status });
      }
      store.engage[idx] = result.item;
    } else if (parsed.data.action === "approve") {
      // Atomically approve the exact text supplied in this request (falling back
      // to the item's current text when omitted) so the copied text can never
      // drift from what was approved by a concurrent edit. For comments the
      // client's expected post URL is bound to the stored target here, so it can
      // never approve-and-open a post that changed underneath it.
      const result = approveEngageItem(
        item,
        parsed.data.suggestedText,
        now,
        parsed.data.sourcePostUrl
      );
      if (!result.ok) {
        return NextResponse.json({ error: result.error }, { status: result.status });
      }
      store.engage[idx] = result.item;
    } else if (parsed.data.action === "mark_commented") {
      // Owner confirms they posted the comment on LinkedIn. Persist state only —
      // no autonomous send. Valid only for an approved comment.
      const result = markCommented(item, now);
      if (!result.ok) {
        return NextResponse.json({ error: result.error }, { status: result.status });
      }
      store.engage[idx] = result.item;
    } else if (parsed.data.action === "reject") {
      // Reject/skip are terminal and only valid from pending_approval — the
      // server enforces this so a stale tab can't clobber a decided item.
      const result = transitionPendingEngage(item, "rejected", now);
      if (!result.ok) {
        return NextResponse.json({ error: result.error }, { status: result.status });
      }
      store.engage[idx] = result.item;
    } else if (parsed.data.action === "skip") {
      const result = transitionPendingEngage(item, "skipped", now);
      if (!result.ok) {
        return NextResponse.json({ error: result.error }, { status: result.status });
      }
      store.engage[idx] = result.item;
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