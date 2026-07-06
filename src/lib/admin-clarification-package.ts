export type AdminClarificationCandidate = {
  id?: string;
  source_entry_kind?: string;
  source_entry_code?: string;
  severity?: string;
  trade_code?: string | null;
  scope_item_id?: string | null;
  source?: string | null;
  internal_reason?: string;
  customer_safe_question?: string;
  required_response_type?: string;
  blocks_delivery?: boolean;
  customer_visible_candidate?: boolean;
  human_approval_required?: boolean;
};

export type AdminClarificationPackage = {
  package_type?: string;
  customer_delivery_ready?: boolean;
  customer_message_ready?: boolean;
  send_ready?: boolean;
  send_gate?: string;
  summary?: {
    candidate_count?: number;
    blocking_candidate_count?: number;
    critical_candidate_count?: number;
    customer_safe_candidate_count?: number;
  };
  candidates?: AdminClarificationCandidate[];
};

export const ADMIN_CLARIFICATION_VISIBLE_LIMIT = 5;

export type AdminClarificationWorkflowSummary = {
  candidateCount: number;
  blockingCandidateCount: number;
  criticalCandidateCount: number;
  customerSafeCandidateCount: number;
  customerDeliveryReady: boolean;
  customerMessageReady: boolean;
  sendReady: boolean;
  renderedCandidateCount: number;
  hiddenCandidateCount: number;
};

function numeric(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : 0;
}

function literalTrue(value: unknown): boolean {
  return value === true;
}

export function visibleAdminClarificationCandidates(
  clarificationPackage: AdminClarificationPackage | null | undefined,
): AdminClarificationCandidate[] {
  return Array.isArray(clarificationPackage?.candidates)
    ? clarificationPackage.candidates.slice(0, ADMIN_CLARIFICATION_VISIBLE_LIMIT)
    : [];
}

export function summarizeAdminClarificationWorkflow(
  clarificationPackage: AdminClarificationPackage | null | undefined,
): AdminClarificationWorkflowSummary {
  const allCandidates = Array.isArray(clarificationPackage?.candidates) ? clarificationPackage.candidates : [];
  const visibleCandidates = visibleAdminClarificationCandidates(clarificationPackage);
  return {
    candidateCount: numeric(clarificationPackage?.summary?.candidate_count),
    blockingCandidateCount: numeric(clarificationPackage?.summary?.blocking_candidate_count),
    criticalCandidateCount: numeric(clarificationPackage?.summary?.critical_candidate_count),
    customerSafeCandidateCount: numeric(clarificationPackage?.summary?.customer_safe_candidate_count),
    customerDeliveryReady: literalTrue(clarificationPackage?.customer_delivery_ready),
    customerMessageReady: literalTrue(clarificationPackage?.customer_message_ready),
    sendReady: literalTrue(clarificationPackage?.send_ready),
    renderedCandidateCount: visibleCandidates.length,
    hiddenCandidateCount: Math.max(allCandidates.length - visibleCandidates.length, 0),
  };
}

export function adminClarificationWorkflowIsDisplayOnly(
  clarificationPackage: AdminClarificationPackage | null | undefined,
): boolean {
  const summary = summarizeAdminClarificationWorkflow(clarificationPackage);
  return !summary.customerDeliveryReady && !summary.customerMessageReady && !summary.sendReady;
}
