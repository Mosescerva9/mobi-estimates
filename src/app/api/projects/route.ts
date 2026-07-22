import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getPrimaryCompanyId } from "@/lib/company";
import {
  availablePayPerProjectCredits,
  hasActiveSubscription,
  introOfferEligible,
} from "@/lib/subscription";
import { PROJECT_TYPE_VALUES } from "@/lib/projects";
import { ensureEstimateJobForProject } from "@/lib/estimate-jobs";

export const runtime = "nodejs";

/** Empty string -> undefined, so optional fields don't fail validation. */
const optionalText = z
  .string()
  .trim()
  .max(5000)
  .optional()
  .transform((v) => (v ? v : undefined));

const optionalDate = z
  .string()
  .trim()
  .optional()
  .transform((v) => (v ? v : undefined))
  .refine((v) => v === undefined || !Number.isNaN(Date.parse(v)), "Invalid date.")
  .transform((v) => (v ? new Date(v).toISOString() : null));

const CreateProjectSchema = z.object({
  name: z.string().trim().min(2, "Please enter a project name.").max(200),
  projectType: z
    .string()
    .optional()
    .transform((v) => (v ? v : undefined))
    .refine((v) => v === undefined || PROJECT_TYPE_VALUES.includes(v), "Invalid project type.")
    .transform((v) => v ?? null),
  address: optionalText,
  bidDueAt: optionalDate,
  requestedCompletionAt: optionalDate,
  trades: optionalText,
  scopeNotes: optionalText,
  estimateType: optionalText,
  alternatesAllowances: optionalText,
  exclusions: optionalText,
  openQuestions: optionalText,
  sharedDocumentLink: optionalText,
  prevailingWage: z.boolean().optional().default(false),
  isPublicProject: z.boolean().optional().default(false),
});

/**
 * Create a project (status = 'submitted') for the caller's company. Metadata
 * only — file bytes are uploaded directly from the browser to private Storage
 * (avoids the serverless body-size limit). All inputs are validated server-side;
 * RLS guarantees the row is scoped to a company the user belongs to.
 */
export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  }

  const companyId = await getPrimaryCompanyId();
  if (!companyId) {
    return NextResponse.json(
      { error: "Please finish setting up your company first.", redirect: "/onboarding" },
      { status: 400 },
    );
  }

  // Never trust the client for entitlement state — re-check server-side. A
  // company may submit with: an active subscription; a paid Pay Per Project
  // credit (exactly one estimate per $599 order); or, for a new company that
  // has not used it yet, the one free qualifying estimate (intro offer). After
  // the free claim, additional submissions require a paid entitlement.
  let needsFreeClaim = false;
  if (!(await hasActiveSubscription(companyId))) {
    const credits = await availablePayPerProjectCredits(companyId);
    if (credits < 1 && (await introOfferEligible(companyId))) {
      needsFreeClaim = true;
    } else if (credits < 1) {
      // No active subscription, no unused paid credit, and no genuine intro
      // eligibility. The one-free-project boundary is independent of whether
      // Stripe is configured — reject every time (never fail open in the
      // pre-Stripe preview). Portal viewing of an existing intro project stays
      // available elsewhere; only NEW submissions are gated here.
      return NextResponse.json(
        {
          error:
            "You've used your free estimate. Subscribe or purchase a Pay Per Project estimate to submit another project.",
          redirect: "/billing",
        },
        { status: 402 },
      );
    }
  }

  let parsed;
  try {
    parsed = CreateProjectSchema.parse(await request.json());
  } catch (e) {
    const message =
      e instanceof z.ZodError ? e.issues[0]?.message ?? "Invalid input." : "Invalid request body.";
    return NextResponse.json({ error: message }, { status: 400 });
  }

  let projectId: string;
  let projectNumber: string;

  if (needsFreeClaim) {
    // Free-offer path: create the submitted project AND its occupying claim in a
    // single DB transaction via a security-definer RPC. The RPC inserts the claim
    // FIRST, so the partial unique index makes a concurrent second first-submission
    // fail with 'already_claimed' and NO project is created for the loser — there
    // is no orphaned row and no hard-delete rollback here. Eligibility is
    // re-checked server-side inside the RPC, so a stale client preflight can't
    // bypass the one-free-project boundary.
    const { data: created, error: createErr } = await supabase.rpc("create_free_offer_project", {
      p_company: companyId,
      p_name: parsed.name,
      p_project_type: parsed.projectType,
      p_address: parsed.address ?? null,
      p_bid_due_at: parsed.bidDueAt,
      p_requested_completion_at: parsed.requestedCompletionAt,
      p_prevailing_wage: parsed.prevailingWage,
      p_is_public: parsed.isPublicProject,
    });
    const result = created as
      | { ok?: boolean; reason?: string; project_id?: string; project_number?: string }
      | null;
    if (createErr || !result?.ok || !result.project_id || !result.project_number) {
      return NextResponse.json(
        {
          error:
            "Your company's free estimate has already been requested. Subscribe or purchase a Pay Per Project estimate to submit another project.",
          redirect: "/billing",
        },
        { status: 402 },
      );
    }
    projectId = result.project_id;
    projectNumber = result.project_number;
  } else {
    // Paid/subscription path: entitlement decision, optional paid-credit
    // consumption, project-number assignment, and project insertion commit in one
    // serialized DB transaction. No customer project row is inserted directly.
    const { data: created, error: createErr } = await supabase.rpc("create_entitled_project", {
      p_company: companyId,
      p_name: parsed.name,
      p_project_type: parsed.projectType,
      p_address: parsed.address ?? null,
      p_bid_due_at: parsed.bidDueAt,
      p_requested_completion_at: parsed.requestedCompletionAt,
      p_prevailing_wage: parsed.prevailingWage,
      p_is_public: parsed.isPublicProject,
    });
    const result = created as
      | {
          ok?: boolean;
          reason?: string;
          project_id?: string;
          project_number?: string;
          entitlement?: "subscription" | "pay_per_project";
        }
      | null;

    if (createErr) {
      return NextResponse.json({ error: "Could not create the project." }, { status: 500 });
    }
    if (!result?.ok || !result.project_id || !result.project_number) {
      return NextResponse.json(
        {
          error:
            "No paid project entitlement is available. Purchase a Pay Per Project estimate or subscribe to submit again.",
          redirect: "/billing",
        },
        { status: 402 },
      );
    }
    projectId = result.project_id;
    projectNumber = result.project_number;
  }

  const admin = createAdminClient();

  // Fail-closed cleanup for a project whose downstream provisioning (scope write
  // or internal job creation) fails AFTER the project row exists.
  //   • Free-offer path: audit-preserving. Atomically release the occupying
  //     claim, cancel and soft-delete the incomplete project, and append an audit
  //     timeline event—never hard-delete an offer-provisioned project.
  //   • Paid/subscription path: hard-delete the partially-created project, which
  //     cascades to project_scopes/files and frees any spent Pay Per Project
  //     credit (consumed_project_id -> null) so the customer isn't double-charged.
  const rollbackProvisioning = async (): Promise<boolean> => {
    if (needsFreeClaim) {
      const { data, error } = await supabase.rpc("fail_free_offer_project_provisioning", {
        p_company: companyId,
        p_project: projectId,
      });
      const result = data as { ok?: boolean } | null;
      return !error && result?.ok === true;
    }
    const { error } = await admin.from("projects").delete().eq("id", projectId);
    return !error;
  };

  // Scope details. If this fails, roll back the project instead of creating an
  // EstimateJob with missing structured intake data.
  if (
    parsed.trades ||
    parsed.scopeNotes ||
    parsed.estimateType ||
    parsed.alternatesAllowances ||
    parsed.exclusions ||
    parsed.openQuestions ||
    parsed.sharedDocumentLink
  ) {
    const { error: scopeErr } = await supabase.from("project_scopes").upsert(
      {
        project_id: projectId,
        data: {
          trades: parsed.trades ?? null,
          notes: parsed.scopeNotes ?? null,
          estimateType: parsed.estimateType ?? null,
          alternatesAllowances: parsed.alternatesAllowances ?? null,
          exclusions: parsed.exclusions ?? null,
          openQuestions: parsed.openQuestions ?? null,
          sharedDocumentLink: parsed.sharedDocumentLink ?? null,
        },
      },
      { onConflict: "project_id" },
    );
    if (scopeErr) {
      const rolledBack = await rollbackProvisioning();
      return NextResponse.json(
        {
          error: rolledBack
            ? "Could not save the project scope. Your free estimate request was reset safely."
            : "Could not save the project scope or reset project setup. Contact support before retrying.",
        },
        { status: 500 },
      );
    }
  }

  // Paid/subscription path only: create the internal EstimateJob with the
  // service role (clients do not have direct RLS access to the internal
  // control-plane tables). If this fails, hard-delete the partially-created
  // project rather than leaving an orphan submitted project with no job behind it.
  //
  // Free-offer path: the claim is only 'requested' here — staff have not
  // reviewed it yet. Do NOT provision an EstimateJob. It is created
  // atomically by decide_intro_offer_claim only once staff accept the claim
  // (requested -> accepted); a database trigger on estimate_jobs enforces
  // this fail-closed even against service-role writes, so this is not merely
  // an application-layer convention.
  if (!needsFreeClaim) {
    try {
      await ensureEstimateJobForProject(admin, projectId);
    } catch {
      const rolledBack = await rollbackProvisioning();
      return NextResponse.json(
        {
          error: rolledBack
            ? "Could not prepare the project. Contact support before retrying."
            : "Could not prepare or reset the project. Contact support before retrying.",
        },
        { status: 500 },
      );
    }
  }

  return NextResponse.json({ id: projectId, projectNumber, companyId, pendingReview: needsFreeClaim });
}
