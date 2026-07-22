"use server";

import { persistLeadCapture } from "@/lib/lead-capture-server";

export interface LeadCaptureActionState {
  status: "idle" | "ok" | "error";
}

/**
 * Public homepage email capture. Stores the lead only—no confirmation, nurture,
 * email, or SMS is sent. Every outcome uses the same generic response so callers
 * cannot enumerate addresses or distinguish validation, honeypot, and DB state.
 */
export async function captureLead(
  _prev: LeadCaptureActionState,
  formData: FormData,
): Promise<LeadCaptureActionState> {
  try {
    await persistLeadCapture({
      email: formData.get("email"),
      source: formData.get("source"),
      utmSource: formData.get("utm_source"),
      utmMedium: formData.get("utm_medium"),
      utmCampaign: formData.get("utm_campaign"),
      utmContent: formData.get("utm_content"),
      utmTerm: formData.get("utm_term"),
      honeypot: formData.get("company_website"),
    });
  } catch {
    // Keep the public response generic and never expose raw storage errors.
  }
  return { status: "ok" };
}
