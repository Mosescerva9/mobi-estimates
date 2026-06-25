import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { getPrimaryCompanyId } from "@/lib/company";
import { billingEnforced, hasActiveSubscription } from "@/lib/subscription";
import { PROJECT_TYPE_VALUES } from "@/lib/projects";

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

  // Never trust the client for subscription state — re-check server-side.
  if (billingEnforced() && !(await hasActiveSubscription(companyId))) {
    return NextResponse.json(
      { error: "An active subscription is required to submit a project.", redirect: "/billing" },
      { status: 402 },
    );
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

  // Scope details (best-effort; the project row above is the critical part).
  if (parsed.trades || parsed.scopeNotes) {
    await supabase.from("project_scopes").upsert(
      {
        project_id: project.id,
        data: {
          trades: parsed.trades ?? null,
          notes: parsed.scopeNotes ?? null,
        },
      },
      { onConflict: "project_id" },
    );
  }

  return NextResponse.json({ id: project.id, projectNumber, companyId });
}
