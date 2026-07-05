import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { getPrimaryCompanyId } from "@/lib/company";
import {
  availablePayPerProjectCredits,
  billingEnforced,
  hasActiveSubscription,
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
  // company may submit either with an active subscription, or by spending one
  // paid Pay Per Project credit (exactly one estimate per $599 order).
  let needsPppCredit = false;
  if (billingEnforced() && !(await hasActiveSubscription(companyId))) {
    const credits = await availablePayPerProjectCredits(companyId);
    if (credits < 1) {
      return NextResponse.json(
        {
          error:
            "You need an active subscription or a Pay Per Project purchase to submit a project.",
          redirect: "/billing",
        },
        { status: 402 },
      );
    }
    needsPppCredit = true;
  }

  let parsed;
  try {
    parsed = CreateProjectSchema.parse(await request.json());
  } catch (e) {
    const message =
      e instanceof z.ZodError ? e.issues[0]?.message ?? "Invalid input." : "Invalid request body.";
    return NextResponse.json({ error: message }, { status: 400 });
  }

  // Assign a unique, sequential project number (MOBI-YYYY-NNNN).
  const { data: numberData, error: numberErr } = await supabase.rpc("next_project_number");
  if (numberErr) {
    return NextResponse.json({ error: "Could not assign a project number." }, { status: 500 });
  }
  const projectNumber = numberData as unknown as string;

  const { data: project, error: insertErr } = await supabase
    .from("projects")
    .insert({
      company_id: companyId,
      project_number: projectNumber,
      name: parsed.name,
      status: "submitted",
      project_type: parsed.projectType,
      address: parsed.address ?? null,
      bid_due_at: parsed.bidDueAt,
      requested_completion_at: parsed.requestedCompletionAt,
      prevailing_wage: parsed.prevailingWage,
      is_public: parsed.isPublicProject,
      created_by: user.id,
    })
    .select("id")
    .single();

  if (insertErr || !project) {
    return NextResponse.json(
      { error: insertErr?.message ?? "Could not create the project." },
      { status: 500 },
    );
  }

  // Spend exactly one Pay Per Project credit for this project. Atomic claim;
  // if a concurrent submission took the last credit, roll back the project.
  if (needsPppCredit) {
    const { data: claimed, error: claimErr } = await supabase.rpc("consume_ppp_credit", {
      p_company: companyId,
      p_project: project.id,
    });
    if (claimErr || claimed !== true) {
      // RLS has no client delete policy on projects; remove via service role.
      await createAdminClient().from("projects").delete().eq("id", project.id);
      return NextResponse.json(
        {
          error:
            "Your Pay Per Project estimate has already been used. Purchase another estimate or subscribe to submit again.",
          redirect: "/billing",
        },
        { status: 402 },
      );
    }
  }

  const admin = createAdminClient();

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
        project_id: project.id,
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
      await admin.from("projects").delete().eq("id", project.id);
      return NextResponse.json({ error: "Could not save the project scope." }, { status: 500 });
    }
  }

  // Create the internal EstimateJob with the service role: clients do not have
  // direct RLS access to the internal control-plane tables. If this fails, roll
  // back the project rather than leaving an orphan submitted project with no
  // job behind it — deleting cascades to project_scopes/files and frees any
  // spent Pay Per Project credit (consumed_project_id -> null) so the customer
  // isn't charged a second credit when they resubmit.
  try {
    await ensureEstimateJobForProject(admin, project.id);
  } catch (jobErr) {
    await admin.from("projects").delete().eq("id", project.id);
    return NextResponse.json(
      {
        error:
          jobErr instanceof Error
            ? `Could not prepare the internal job for this project: ${jobErr.message}`
            : "Could not prepare the internal job for this project.",
      },
      { status: 500 },
    );
  }

  return NextResponse.json({ id: project.id, projectNumber, companyId });
}
