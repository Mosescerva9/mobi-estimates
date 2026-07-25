/**
 * Pure resolution of the EXACT document set that may be packaged for the
 * estimating engine.
 *
 * The internal estimate-job register (`estimate_job_documents`) records a review
 * decision per document, but it is NOT authoritative about which files exist:
 * a register row can outlive the file it names (soft-deleted), point at another
 * project's or another company's file, or drift from that file's storage path or
 * name. Trusting `review_status = 'accepted'` alone would therefore let a stale,
 * cross-tenant, or identity-divergent row be downloaded with the service role and
 * shipped into an engine packet.
 *
 * The authority is ACTIVE `project_files`. Every accepted register row must
 * resolve to exactly one non-soft-deleted `project_files` row belonging to the
 * SAME portal project and company, with an identical id, storage path, and file
 * name. Anything else fails the whole send closed rather than packaging a
 * best-effort subset.
 *
 * This module is deliberately pure (no Supabase client, no I/O) so the identity
 * rules are directly unit-testable; the server action supplies server-owned rows
 * and never browser input.
 */

import { estimateDocumentRegisterHealth } from "@/lib/estimate-jobs";

/** One non-soft-deleted `project_files` row (server-read). */
export interface ActiveProjectFileRow {
  id: string | null;
  project_id: string | null;
  company_id: string | null;
  storage_path: string | null;
  file_name: string | null;
}

/** One `estimate_job_documents` register row (server-read). */
export interface RegisterDocumentRow {
  project_file_id: string | null;
  project_id: string | null;
  company_id: string | null;
  storage_path: string | null;
  file_name: string | null;
  review_status: string | null;
}

/** A resolved source, carrying the ACTIVE file's identity — never the register's copy. */
export interface AcceptedEngineSource {
  project_file_id: string;
  file_name: string;
  storage_path: string;
}

export type AcceptedPacketSourcesResult =
  | { ok: true; acceptedDocs: AcceptedEngineSource[] }
  | { ok: false; message: string };

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

/**
 * Resolve the accepted set through exact active-`project_files` membership.
 *
 * Fails closed on:
 *  - a stale register (an active file that was never registered);
 *  - any undecided document (pending / needs_replacement);
 *  - an accepted row missing a resolvable identity;
 *  - an accepted row whose project or company is not this project/company;
 *  - an accepted row whose `project_file_id` names no ACTIVE file (deleted or
 *    never existed — the "stale extra accepted row" case);
 *  - an active file that belongs to a different project or company;
 *  - a storage path or file name that differs between the register row and the
 *    active file;
 *  - two accepted rows claiming the same file;
 *  - a non-PDF accepted file (the engine ingests PDF only);
 *  - an empty accepted set.
 */
export function resolveAcceptedPacketSources(args: {
  projectId: string;
  companyId: string;
  activeFiles: ActiveProjectFileRow[];
  register: RegisterDocumentRow[];
}): AcceptedPacketSourcesResult {
  const { projectId, companyId, activeFiles, register } = args;
  if (!projectId || !companyId) {
    return { ok: false, message: "Missing project or company identity; cannot resolve the accepted set." };
  }

  // Index only files that are genuinely active AND belong to this project and
  // company. Because the caller is a server-owned exact-project query, any row
  // outside that scope indicates corrupted or confused-deputy input and fails the
  // entire resolution closed rather than being silently filtered.
  const activeById = new Map<string, ActiveProjectFileRow>();
  for (const file of activeFiles) {
    if (!isNonEmptyString(file.id)) {
      return { ok: false, message: "An active project file is missing its server-owned identity. No documents were sent." };
    }
    if (file.project_id !== projectId || file.company_id !== companyId) {
      return {
        ok: false,
        message: "An active project file belongs to a different project or company. No documents were sent.",
      };
    }
    if (!isNonEmptyString(file.storage_path) || !isNonEmptyString(file.file_name)) {
      return { ok: false, message: "An active project file is missing its storage path or file name. No documents were sent." };
    }
    if (activeById.has(file.id)) {
      return { ok: false, message: "The active project-file set contains a duplicate identity. No documents were sent." };
    }
    activeById.set(file.id, file);
  }

  // Stale register: every active uploaded file must be registered before the
  // accepted set can be trusted as the whole picture.
  const health = estimateDocumentRegisterHealth(
    [...activeById.keys()],
    register.map((d) => d.project_file_id ?? null),
  );
  if (health.missingCount > 0) {
    return {
      ok: false,
      message: `The document register is stale: ${health.missingCount} uploaded file(s) are not yet registered. Re-run intake before sending.`,
    };
  }

  const undecided = register.filter(
    (d) => d.review_status === "pending" || d.review_status === "needs_replacement",
  );
  if (undecided.length > 0) {
    return {
      ok: false,
      message: `${undecided.length} document(s) are still pending review or need replacement. Resolve every document before sending the accepted set.`,
    };
  }

  const acceptedAll = register.filter((d) => d.review_status === "accepted");
  const unresolvable = acceptedAll.filter(
    (d) => !isNonEmptyString(d.project_file_id) || !isNonEmptyString(d.storage_path) || !isNonEmptyString(d.file_name),
  );
  if (unresolvable.length > 0) {
    return {
      ok: false,
      message: `${unresolvable.length} accepted document(s) are missing a file identity (project_file_id/storage_path). Re-register them before sending.`,
    };
  }
  if (acceptedAll.length === 0) {
    return { ok: false, message: "No accepted documents to send. Accept the plan/spec set first." };
  }

  const resolved: AcceptedEngineSource[] = [];
  const seenFileIds = new Set<string>();
  for (const doc of acceptedAll) {
    const fileId = doc.project_file_id as string;

    if (doc.project_id !== projectId || doc.company_id !== companyId) {
      return {
        ok: false,
        message:
          `Accepted document "${doc.file_name}" is registered under a different project or company. ` +
          "No documents were sent.",
      };
    }
    if (seenFileIds.has(fileId)) {
      return {
        ok: false,
        message: `Accepted document "${doc.file_name}" is registered twice against the same uploaded file. No documents were sent.`,
      };
    }
    seenFileIds.add(fileId);

    const file = activeById.get(fileId);
    if (!file) {
      return {
        ok: false,
        message:
          `Accepted document "${doc.file_name}" does not reference an active uploaded file for this project ` +
          "(it was deleted, or belongs to another project/company). Re-run intake before sending.",
      };
    }
    if (file.storage_path !== doc.storage_path || file.file_name !== doc.file_name) {
      return {
        ok: false,
        message:
          `Accepted document "${doc.file_name}" no longer matches its uploaded file's name/path. ` +
          "Re-register it before sending.",
      };
    }

    resolved.push({
      // Server-owned identity, taken from the ACTIVE file row.
      project_file_id: file.id as string,
      file_name: file.file_name as string,
      storage_path: file.storage_path as string,
    });
  }

  const nonPdf = resolved.filter((d) => !d.file_name.toLowerCase().endsWith(".pdf"));
  if (nonPdf.length > 0) {
    return {
      ok: false,
      message: `The accepted set includes unsupported non-PDF file(s): ${nonPdf
        .map((d) => d.file_name)
        .join(", ")}. The engine packet accepts only PDF documents.`,
    };
  }

  return { ok: true, acceptedDocs: resolved };
}
