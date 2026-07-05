import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";
import { ensureEstimateJobForProject } from "@/lib/estimate-jobs";

export const runtime = "nodejs";

/**
 * Client-callable recovery/sync endpoint after browser-direct uploads.
 * The caller must be authenticated and allowed by project RLS; internal tables
 * are written server-side with the service role so clients never get direct
 * estimate_jobs access.
 */
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  }

  const { data: project, error: projectError } = await supabase
    .from("projects")
    .select("id")
    .eq("id", id)
    .is("deleted_at", null)
    .maybeSingle();

  if (projectError) {
    return NextResponse.json({ error: projectError.message }, { status: 500 });
  }
  if (!project) {
    return NextResponse.json({ error: "Project not found." }, { status: 404 });
  }

  try {
    const admin = createAdminClient();
    const job = await ensureEstimateJobForProject(admin, id);
    return NextResponse.json({ ok: true, estimateJobId: job.id });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Could not sync estimate job." },
      { status: 500 },
    );
  }
}
