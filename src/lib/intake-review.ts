export interface IntakeReviewPacket {
  version: number;
  reviewed_at: string;
  completeness: Record<string, boolean>;
  detected_documents: Array<{
    file_name: string;
    category: string;
    document_type: string | null;
    page_count: number | null;
    processing_status: string;
  }>;
  missing_or_unclear: string[];
  risk_flags: string[];
  recommended_next_status: string;
  internal_notes: string[];
}

interface IntakeReviewProject {
  name: string | null;
  company_id: string | null;
  project_type: string | null;
  address: string | null;
  bid_due_at: string | null;
  requested_completion_at: string | null;
  prevailing_wage: boolean | null;
  is_public: boolean | null;
}

interface IntakeReviewScope {
  trades?: string | null;
  notes?: string | null;
  estimateType?: string | null;
  alternatesAllowances?: string | null;
  exclusions?: string | null;
  openQuestions?: string | null;
  sharedDocumentLink?: string | null;
}

interface IntakeReviewDocument {
  file_name: string;
  category: string;
  document_type: string | null;
  page_count: number | null;
  processing_status: string;
}

function hasText(value: string | null | undefined): boolean {
  return Boolean(value && value.trim().length > 0);
}

export function buildIntakeReviewPacket({
  project,
  scope,
  documents,
}: {
  project: IntakeReviewProject;
  scope: IntakeReviewScope;
  documents: IntakeReviewDocument[];
}): IntakeReviewPacket {
  const hasDrawings = documents.some((doc) => doc.category.toLowerCase().includes("drawing"));
  const hasSpecificationsOrScopeDocs = documents.some((doc) => {
    const category = doc.category.toLowerCase();
    return category.includes("spec") || category.includes("scope") || category.includes("bid");
  });
  const hasAddenda = documents.some((doc) => doc.category.toLowerCase().includes("addend"));

  const completeness = {
    has_project_name: hasText(project.name),
    has_company: hasText(project.company_id),
    has_project_type: hasText(project.project_type),
    has_location: hasText(project.address),
    has_bid_due_date: hasText(project.bid_due_at),
    has_requested_completion_date: hasText(project.requested_completion_at),
    has_trade_scope: hasText(scope.trades),
    has_scope_notes: hasText(scope.notes),
    has_estimate_type: hasText(scope.estimateType),
    has_exclusions_or_open_questions: hasText(scope.exclusions) || hasText(scope.openQuestions),
    has_drawings: hasDrawings,
    has_specifications_or_scope_docs: hasSpecificationsOrScopeDocs,
    has_addenda: hasAddenda,
  };

  const missingOrUnclear: string[] = [];
  if (!completeness.has_project_type) missingOrUnclear.push("NEEDS OWNER INPUT: Project type was not provided.");
  if (!completeness.has_location) missingOrUnclear.push("NEEDS OWNER INPUT: Project location/address was not provided.");
  if (!completeness.has_bid_due_date) missingOrUnclear.push("NEEDS OWNER INPUT: Bid due date was not provided.");
  if (!completeness.has_requested_completion_date) missingOrUnclear.push("Requested completion/turnaround date was not provided.");
  if (!completeness.has_trade_scope) missingOrUnclear.push("Trades/scopes requested were not provided.");
  if (!completeness.has_estimate_type) missingOrUnclear.push("Estimate type was not provided.");
  if (!completeness.has_exclusions_or_open_questions) {
    missingOrUnclear.push("Known exclusions/open questions were not provided; staff should confirm assumptions.");
  }
  if (!hasDrawings && !hasText(scope.sharedDocumentLink)) missingOrUnclear.push("No drawings uploaded or shared document link provided.");
  if (!hasSpecificationsOrScopeDocs) missingOrUnclear.push("No specifications or scope/bid documents uploaded.");

  const riskFlags: string[] = [];
  if (project.bid_due_at) {
    const bidDueMs = Date.parse(project.bid_due_at);
    if (!Number.isNaN(bidDueMs)) {
      const hoursUntilDue = (bidDueMs - Date.now()) / (1000 * 60 * 60);
      if (hoursUntilDue < 0) riskFlags.push("Bid due date has already passed.");
      else if (hoursUntilDue <= 48) riskFlags.push("Bid due date is within 48 hours.");
    }
  }
  if (project.prevailing_wage) riskFlags.push("Prevailing-wage project: verify labor assumptions before pricing.");
  if (project.is_public) riskFlags.push("Public project: verify bid instructions, addenda, and compliance requirements.");
  if (hasText(scope.sharedDocumentLink)) riskFlags.push("Shared document link provided; staff must manually retrieve/verify files.");

  return {
    version: 1,
    reviewed_at: new Date().toISOString(),
    completeness,
    detected_documents: documents.map((doc) => ({
      file_name: doc.file_name,
      category: doc.category,
      document_type: doc.document_type,
      page_count: doc.page_count,
      processing_status: doc.processing_status,
    })),
    missing_or_unclear: missingOrUnclear,
    risk_flags: riskFlags,
    recommended_next_status:
      missingOrUnclear.length > 0 ? "intake_needs_info" : "ready_for_document_processing",
    internal_notes: [
      "Deterministic Phase 1A intake review only; no pricing, quantities, or customer message was generated.",
    ],
  };
}
