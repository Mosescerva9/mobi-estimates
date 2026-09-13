import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import {
  InvalidJsonBodyError,
  JsonBodyTooLargeError,
  readJsonBodyLimited,
} from "@/lib/request-body";
import { authorizeJob } from "@/lib/scout-auth";
import {
  SCOUT_COMMENT_MAX,
  SCOUT_JOB_BATCH_CAP,
  SCOUT_SKIP_REASONS,
  applyScoutOutcomes,
  createBatchId,
  isDoNotContact,
  sanitizeForJob,
  selectScoutBatch,
  type ScoutOutcome,
} from "@/lib/scout";
import { readStore, updateStore } from "@/lib/store";
import { StoreConfigError } from "@/lib/store-mode";

export const dynamic = "force-dynamic";
const JOB_BODY_MAX_BYTES = 64 * 1024;

/**
 * Hermes worker endpoint. Self-authenticated through middleware; independently
 * requires the SCOUT_JOB_TOKEN bearer (missing env → 503, wrong token → 401).
 * The capture token can never authorise this endpoint. Tokens are only accepted
 * in the Authorization header. Never calls LinkedIn.
 *
 *  GET  → up to SCOUT_JOB_BATCH_CAP unprocessed, sanitized candidates + batchId.
 *  POST → apply outcomes for a batch: each qualified outcome atomically creates
 *         exactly one pending EngageItem bound to its source post; idempotent on
 *         retry. Skips record a whitelisted reason. No autonomous send.
 */

function ensureConfigured(req: Request): NextResponse | null {
  const auth = authorizeJob(req.headers.get("authorization"));
  if (!auth.ok) {
    return NextResponse.json({ error: auth.error }, { status: auth.status });
  }
  return null;
}

export async function GET(req: Request) {
  const unauthorized = ensureConfigured(req);
  if (unauthorized) return unauthorized;

  let store;
  try {
    store = await readStore();
  } catch (err) {
    if (err instanceof StoreConfigError) {
      return NextResponse.json({ error: err.message }, { status: 503 });
    }
    throw err;
  }

  const batch = selectScoutBatch(store);
  return NextResponse.json({
    batchId: createBatchId(),
    cap: SCOUT_JOB_BATCH_CAP,
    commentMaxLength: SCOUT_COMMENT_MAX,
    skipReasons: SCOUT_SKIP_REASONS,
    candidates: batch.map((candidate) =>
      sanitizeForJob(
        candidate,
        isDoNotContact(candidate.authorName, store.settings.doNotContact)
      )
    ),
  });
}

const qualifySchema = z.object({
  candidateId: z.string().min(1).max(200),
  decision: z.literal("qualify"),
  suggestedComment: z.string().min(1).max(SCOUT_COMMENT_MAX),
  relevance: z.number().min(0).max(100),
  reason: z.string().min(1).max(500),
  safety: z.string().min(1).max(200),
});

const skipSchema = z.object({
  candidateId: z.string().min(1).max(200),
  decision: z.literal("skip"),
  reason: z.enum(SCOUT_SKIP_REASONS),
});

const bodySchema = z.object({
  batchId: z.string().min(1).max(200),
  provider: z.literal("openai-codex"),
  model: z.literal("gpt-5.6-sol"),
  outcomes: z.array(z.union([qualifySchema, skipSchema])).max(SCOUT_JOB_BATCH_CAP),
});

export async function POST(req: Request) {
  const unauthorized = ensureConfigured(req);
  if (unauthorized) return unauthorized;

  let raw: unknown;
  try {
    raw = await readJsonBodyLimited(req, JOB_BODY_MAX_BYTES);
  } catch (err) {
    if (err instanceof JsonBodyTooLargeError) {
      return NextResponse.json({ error: "Job payload is too large." }, { status: 413 });
    }
    if (err instanceof InvalidJsonBodyError) {
      return NextResponse.json({ error: "Invalid job payload." }, { status: 400 });
    }
    throw err;
  }

  const parsed = bodySchema.safeParse(raw);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid job payload." }, { status: 400 });
  }

  const modelProvenance = `${parsed.data.provider}/${parsed.data.model}`;
  const outcomes = parsed.data.outcomes as ScoutOutcome[];
  const now = new Date().toISOString();

  try {
    let results: ReturnType<typeof applyScoutOutcomes>["results"] = [];
    await updateStore((store) => {
      const applied = applyScoutOutcomes(
        store,
        parsed.data.batchId,
        outcomes,
        modelProvenance,
        now
      );
      results = applied.results;
      return applied.store;
    });

    const queued = results.filter((r) => r.result === "queued").length;
    const skipped = results.filter(
      (r) => r.result === "skipped" || r.result === "duplicate"
    ).length;
    return NextResponse.json({ ok: true, queued, skipped, results });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}
