export interface PlanContextPacket {
  version: 1;
  generated_at: string;
  source: "deterministic_plan_context_intake_v1";
  project: {
    name: string | null;
    project_type: string | null;
    address: string | null;
    bid_due_at: string | null;
    requested_completion_at: string | null;
    prevailing_wage: boolean | null;
    is_public: boolean | null;
  };
  requested_scope: {
    trades: string | null;
    notes: string | null;
    estimateType: string | null;
    alternatesAllowances: string | null;
    exclusions: string | null;
    openQuestions: string | null;
    sharedDocumentLink: string | null;
  };
  estimate_job_status: string;
  document_summary: {
    total: number;
    accepted: number;
    ignored: number;
    needs_replacement: number;
    pending: number;
    plan_set: number;
    spec: number;
    other: number;
  };
  accepted_documents: Array<{
    id: string;
    file_name: string;
    category: string;
    document_type: string | null;
    page_count: number | null;
    processing_status: string;
    review_status: string;
    sheet_index: unknown;
  }>;
  source_gaps: string[];
  internal_notes: string[];
}

interface PlanContextProject {
  name: string | null;
  project_type: string | null;
  address: string | null;
  bid_due_at: string | null;
  requested_completion_at: string | null;
  prevailing_wage: boolean | null;
  is_public: boolean | null;
}

interface PlanContextScope {
  trades?: string | null;
  notes?: string | null;
  estimateType?: string | null;
  alternatesAllowances?: string | null;
  exclusions?: string | null;
  openQuestions?: string | null;
  sharedDocumentLink?: string | null;
}

interface PlanContextDocument {
  id: string;
  file_name: string;
  category: string;
  document_type: string | null;
  page_count: number | null;
  processing_status: string;
  review_status: string;
  sheet_index: unknown;
}

function isPlanSetDoc(doc: PlanContextDocument): boolean {
  const documentType = (doc.document_type ?? "").toLowerCase();
  const category = doc.category.toLowerCase();
  return documentType === "plan_set" || category.includes("drawing") || category.includes("plan");
}

function isSpecDoc(doc: PlanContextDocument): boolean {
  const documentType = (doc.document_type ?? "").toLowerCase();
  const category = doc.category.toLowerCase();
  return (
    documentType === "spec_book" ||
    documentType === "scope_sheet" ||
    category.includes("spec") ||
    category.includes("scope") ||
    category.includes("bid")
  );
}

export function buildPlanContextPacket({
  project,
  scope,
  estimateJobStatus,
  documents,
}: {
  project: PlanContextProject;
  scope: PlanContextScope;
  estimateJobStatus: string;
  documents: PlanContextDocument[];
}): PlanContextPacket {
  const accepted = documents.filter((doc) => doc.review_status === "accepted");
  const ignored = documents.filter((doc) => doc.review_status === "ignored");
  const needsReplacement = documents.filter((doc) => doc.review_status === "needs_replacement");
  const pending = documents.filter((doc) => doc.review_status === "pending");
  const planSetDocs = documents.filter(isPlanSetDoc);
  const specDocs = documents.filter(isSpecDoc);
  const otherDocs = documents.filter((doc) => !isPlanSetDoc(doc) && !isSpecDoc(doc));

  const acceptedPlanSet = accepted.filter(isPlanSetDoc);
  const acceptedSpec = accepted.filter(isSpecDoc);

  const sourceGaps: string[] = [];
  if (accepted.length === 0) sourceGaps.push("No documents have been accepted yet.");
  if (pending.length > 0) sourceGaps.push(`${pending.length} document(s) are still pending review.`);
  if (needsReplacement.length > 0) sourceGaps.push(`${needsReplacement.length} document(s) need replacement before takeoff.`);
  if (acceptedPlanSet.length === 0) sourceGaps.push("No plan set has been accepted yet.");
  if (acceptedSpec.length === 0) sourceGaps.push("No specification or scope document has been accepted yet.");

  return {
    version: 1,
    generated_at: new Date().toISOString(),
    source: "deterministic_plan_context_intake_v1",
    project: {
      name: project.name,
      project_type: project.project_type,
      address: project.address,
      bid_due_at: project.bid_due_at,
      requested_completion_at: project.requested_completion_at,
      prevailing_wage: project.prevailing_wage,
      is_public: project.is_public,
    },
    requested_scope: {
      trades: scope.trades ?? null,
      notes: scope.notes ?? null,
      estimateType: scope.estimateType ?? null,
      alternatesAllowances: scope.alternatesAllowances ?? null,
      exclusions: scope.exclusions ?? null,
      openQuestions: scope.openQuestions ?? null,
      sharedDocumentLink: scope.sharedDocumentLink ?? null,
    },
    estimate_job_status: estimateJobStatus,
    document_summary: {
      total: documents.length,
      accepted: accepted.length,
      ignored: ignored.length,
      needs_replacement: needsReplacement.length,
      pending: pending.length,
      plan_set: planSetDocs.length,
      spec: specDocs.length,
      other: otherDocs.length,
    },
    accepted_documents: accepted.map((doc) => ({
      id: doc.id,
      file_name: doc.file_name,
      category: doc.category,
      document_type: doc.document_type,
      page_count: doc.page_count,
      processing_status: doc.processing_status,
      review_status: doc.review_status,
      sheet_index: doc.sheet_index,
    })),
    source_gaps: sourceGaps,
    internal_notes: [
      "Deterministic Plan Context Intake v1 packet only; no quantities, pricing, final estimate, or customer deliverable was generated.",
    ],
  };
}
