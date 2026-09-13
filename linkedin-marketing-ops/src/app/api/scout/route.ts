import { NextResponse } from "next/server";
import { storeErrorResponse } from "@/lib/api-errors";
import { jobTokenConfigured } from "@/lib/scout-auth";
import { scoutCounts } from "@/lib/scout";
import { readStore } from "@/lib/store";
import { StoreConfigError } from "@/lib/store-mode";
import type { ScoutCandidate } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Owner-authenticated Scout list/status for the dashboard. Reached only behind
 * the owner session cookie (this path is NOT in the middleware integration
 * allow-list). Returns candidates, counts and pairing STATUS — never the token
 * hash. Read-only: no side effects.
 */
export async function GET() {
  let store;
  try {
    store = await readStore();
  } catch (err) {
    if (err instanceof StoreConfigError) {
      return NextResponse.json({ error: err.message }, { status: 503 });
    }
    const mapped = storeErrorResponse(err);
    if (mapped) return mapped;
    throw err;
  }

  // Strip any secret/internal-only fields from what we hand the browser. postKey
  // is an internal dedupe key; it is safe but unnecessary, so we drop it too.
  const candidates = store.scoutCandidates.map((c: ScoutCandidate) => ({
    id: c.id,
    status: c.status,
    postUrl: c.postUrl,
    sourceText: c.sourceText,
    authorName: c.authorName,
    authorHeadline: c.authorHeadline,
    authorCompany: c.authorCompany,
    capturedAt: c.capturedAt,
    updatedAt: c.updatedAt,
    relevance: c.relevance,
    reason: c.reason,
    safety: c.safety,
    suggestedComment: c.suggestedComment,
    engageItemId: c.engageItemId,
  }));

  return NextResponse.json({
    counts: scoutCounts(store.scoutCandidates),
    candidates,
    pairing: {
      // Non-secret pairing status. The token hash is intentionally omitted.
      paired: Boolean(store.scout.captureTokenHash),
      last4: store.scout.captureTokenLast4 ?? null,
      updatedAt: store.scout.captureTokenUpdatedAt ?? null,
    },
    jobConfigured: jobTokenConfigured(),
  });
}
