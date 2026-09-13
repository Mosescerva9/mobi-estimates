import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import { rejectScoutCandidate } from "@/lib/scout";
import { updateStore } from "@/lib/store";

export const dynamic = "force-dynamic";

/**
 * Owner action on a single Scout candidate (behind the session cookie — this
 * dynamic path is NOT in the middleware integration allow-list, and the static
 * `/api/scout/capture` and `/api/scout/job` segments take precedence over it).
 * The only action is `reject`, which dismisses a candidate from the list. A
 * queued candidate is refused because it owns a live pending EngageItem.
 */

const schema = z.object({ action: z.literal("reject") });

type Params = { params: Promise<{ id: string }> };

export async function PATCH(req: Request, { params }: Params) {
  const { id } = await params;
  const parsed = schema.safeParse(await req.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  const now = new Date().toISOString();
  try {
    let outcome: { status: number; error: string } | null = null;
    let found = false;
    await updateStore((store) => {
      const idx = store.scoutCandidates.findIndex((c) => c.id === id);
      if (idx < 0) return store;
      found = true;
      const res = rejectScoutCandidate(store.scoutCandidates[idx], now);
      if (!res.ok) {
        outcome = { status: res.status, error: res.error };
        return store;
      }
      store.scoutCandidates[idx] = res.candidate;
      return store;
    });

    if (!found) {
      return NextResponse.json({ error: "Candidate not found." }, { status: 404 });
    }
    if (outcome) {
      return NextResponse.json(
        { error: (outcome as { error: string }).error },
        { status: (outcome as { status: number }).status }
      );
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}
