import { NextRequest, NextResponse } from "next/server";
import { requireStaff } from "@/lib/auth";
import { createAdminClient } from "@/lib/supabase/admin";
import { engineConfigured, engineFetchSheetImage } from "@/lib/engine";

/**
 * Staff-only proxy for a single engine-rendered sheet raster.
 *
 * The browser cannot call the engine directly (that requires the engine API
 * key, which must never reach a client component). This route resolves the
 * project's tenant/engine identity server-side from the Supabase row, fetches
 * the PNG from the engine using the server-only credential, and streams back
 * only image bytes — no path, no key, no tenant identifier.
 */

const OPAQUE_ID = /^[A-Za-z0-9_-]+$/;

export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  await requireStaff();
  const { id: projectId } = await params;

  const sheetId = request.nextUrl.searchParams.get("sheetId") ?? "";
  const variant = request.nextUrl.searchParams.get("variant") === "thumbnail" ? "thumbnail" : "image";
  if (!OPAQUE_ID.test(sheetId)) {
    return NextResponse.json({ error: "Invalid sheet id." }, { status: 400 });
  }
  if (!engineConfigured()) {
    return NextResponse.json({ error: "Estimating engine is not configured on this deployment." }, { status: 404 });
  }

  const admin = createAdminClient();
  const { data: project } = await admin
    .from("projects")
    .select("id, company_id, engine_project_id")
    .eq("id", projectId)
    .maybeSingle();
  if (!project?.company_id || !project.engine_project_id) {
    return NextResponse.json({ error: "Project has not been synced to the estimating engine." }, { status: 404 });
  }

  try {
    const result = await engineFetchSheetImage(project.engine_project_id, sheetId, variant, {
      tenantId: project.company_id,
      companyId: project.company_id,
    });
    if (!result) {
      return NextResponse.json({ error: "Sheet image is not available yet." }, { status: 404 });
    }
    return new NextResponse(result.bytes, {
      status: 200,
      headers: {
        "Content-Type": result.contentType,
        "Cache-Control": "private, max-age=60",
      },
    });
  } catch {
    return NextResponse.json({ error: "Could not load the sheet image." }, { status: 502 });
  }
}
