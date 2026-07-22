import "server-only";

import { parseLeadCapture, type LeadCaptureInput } from "@/lib/lead-capture";
import { createAdminClient } from "@/lib/supabase/admin";

/**
 * Narrow service-role boundary shared by the Next homepage server action and the
 * canonical marketing-site API. Only normalized fields can reach the database;
 * this helper never sends email/SMS or returns address-existence information.
 */
export async function persistLeadCapture(input: LeadCaptureInput): Promise<boolean> {
  const parsed = parseLeadCapture(input);
  if (!parsed.ok) return true; // generic no-op for invalid/honeypot submissions

  const admin = createAdminClient();
  const { error } = await admin.from("lead_captures").upsert(parsed.record, {
    onConflict: "email",
    ignoreDuplicates: true,
  });
  return !error;
}
