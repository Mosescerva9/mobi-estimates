import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { buildStoragePath, DEFAULT_FILE_CATEGORY, PROJECT_FILES_BUCKET } from "@/lib/projects";

export const runtime = "nodejs";

const AttachSchema = z.object({
  messageId: z.string().uuid("Invalid forwarded-bid id."),
});

interface IntakeAttachment {
  id: string;
  file_name: string;
  content_type: string | null;
  size_bytes: number | null;
  storage_path: string;
  project_file_id: string | null;
}

/**
 * Attach the documents from a captured forwarded bid to a project the caller has
 * already created through the normal entitlement-checked path.
 *
 * Ordering: the intake is claimed FIRST via claim_inbound_intake_for_project,
 * which is atomic and single-use, so two concurrent confirmations can't attach
 * the same forward to two projects. File registration then runs per-attachment
 * and skips anything already registered, which makes a repeat call after a
 * partial failure finish the remaining files instead of duplicating them.
 */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id: projectId } = await params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Not authenticated." }, { status: 401 });
  }

  let parsed;
  try {
    parsed = AttachSchema.parse(await request.json());
  } catch (e) {
    const message =
      e instanceof z.ZodError ? e.issues[0]?.message ?? "Invalid input." : "Invalid request body.";
    return NextResponse.json({ error: message }, { status: 400 });
  }

  // RLS scopes this read to a project in a company the caller belongs to.
  const { data: project } = await supabase
    .from("projects")
    .select("id, company_id")
    .eq("id", projectId)
    .is("deleted_at", null)
    .maybeSingle();
  if (!project) {
    return NextResponse.json({ error: "Project not found." }, { status: 404 });
  }
  const companyId = (project as { company_id: string }).company_id;

  const { data: message } = await supabase
    .from("inbound_intake_messages")
    .select("id, status, project_id, company_id")
    .eq("id", parsed.messageId)
    .maybeSingle();
  if (!message) {
    return NextResponse.json({ error: "Forwarded bid not found." }, { status: 404 });
  }
  const intake = message as {
    id: string;
    status: string;
    project_id: string | null;
    company_id: string;
  };

  const alreadyBoundToThisProject =
    intake.status === "converted" && intake.project_id === projectId;

  if (!alreadyBoundToThisProject) {
    const { data: claimed, error: claimError } = await supabase.rpc(
      "claim_inbound_intake_for_project",
      { p_message: parsed.messageId, p_project: projectId },
    );
    const result = claimed as { ok?: boolean; reason?: string } | null;
    if (claimError || !result?.ok) {
      return NextResponse.json(
        {
          error:
            result?.reason === "not_convertible"
              ? "This forwarded bid has already been submitted or dismissed."
              : "Could not attach the forwarded bid to this project.",
        },
        { status: 409 },
      );
    }
  }

  // Service role from here: project_files rows and Storage objects for a
  // customer's own documents are written server-side, the same way the rest of
  // the internal register is maintained.
  const admin = createAdminClient();

  const { data: attachmentRows, error: attachmentsError } = await admin
    .from("inbound_intake_attachments")
    .select("id, file_name, content_type, size_bytes, storage_path, project_file_id")
    .eq("message_id", parsed.messageId)
    .eq("company_id", companyId)
    .order("created_at");
  if (attachmentsError) {
    return NextResponse.json({ error: "Could not read the forwarded documents." }, { status: 500 });
  }

  const attachments = (attachmentRows ?? []) as IntakeAttachment[];
  let attached = 0;
  const failed: string[] = [];

  for (const attachment of attachments) {
    if (attachment.project_file_id) continue; // already registered by an earlier call

    // Move the object under the project so every project document follows the
    // documented {company_id}/{project_id}/{file} convention. If the move fails
    // the original key is still inside the same company folder, so the tenant
    // can read it — register that path rather than losing the document.
    const targetPath = buildStoragePath(companyId, projectId, attachment.file_name);
    const { error: moveError } = await admin.storage
      .from(PROJECT_FILES_BUCKET)
      .move(attachment.storage_path, targetPath);
    const storagePath = moveError ? attachment.storage_path : targetPath;

    const { data: file, error: fileError } = await admin
      .from("project_files")
      .insert({
        project_id: projectId,
        company_id: companyId,
        category: DEFAULT_FILE_CATEGORY,
        storage_path: storagePath,
        file_name: attachment.file_name,
        mime_type: attachment.content_type,
        size_bytes: attachment.size_bytes,
        uploaded_by: user.id,
      })
      .select("id")
      .single();

    if (fileError || !file) {
      failed.push(attachment.file_name);
      continue;
    }

    await admin
      .from("inbound_intake_attachments")
      .update({ project_file_id: (file as { id: string }).id, storage_path: storagePath })
      .eq("id", attachment.id);

    attached += 1;
  }

  return NextResponse.json({ ok: true, attached, failed });
}
