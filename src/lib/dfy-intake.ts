import { normalizeEmail } from "@/lib/lead-capture";

/**
 * Pure parsing/validation for the DFY post-purchase intake form. Kept free of
 * Next.js and database plumbing so it can be unit-tested directly (see
 * scripts/test-dfy-offer.ts). The intake drives the 45-minute onboarding call,
 * so every field is bounded and nothing free-form is trusted.
 */

export const DFY_EXPERIENCE_RANGES = ["0-1", "1-3", "3-5", "5+"] as const;
export type DfyExperienceRange = (typeof DFY_EXPERIENCE_RANGES)[number];

export interface DfyIntake {
  name: string;
  email: string;
  trade_niche: string;
  years_experience: DfyExperienceRange;
  current_situation: string;
  goals: string;
  call_availability: string;
  /** Whether the buyer is already in the paid community (affects onboarding path). */
  community_member: boolean;
}

export type DfyIntakeRejectReason =
  | "honeypot"
  | "invalid_email"
  | "missing_field"
  | "invalid_experience";

export type DfyIntakeParseResult =
  | { ok: true; intake: DfyIntake }
  | { ok: false; reason: DfyIntakeRejectReason };

function boundedText(value: unknown, max: number): string | null {
  if (typeof value !== "string") return null;
  // eslint-disable-next-line no-control-regex
  const cleaned = value.replace(/[\u0000-\u001F\u007F]/g, "").trim();
  if (!cleaned) return null;
  return cleaned.slice(0, max);
}

function toBoolean(value: unknown): boolean {
  return value === true || value === "yes" || value === "true" || value === "on";
}

/**
 * Validate raw form/JSON input into a bounded DfyIntake. A filled honeypot is
 * reported separately so the caller can pretend success without storing spam.
 */
export function parseDfyIntake(raw: Record<string, unknown>): DfyIntakeParseResult {
  if (typeof raw.honeypot === "string" && raw.honeypot.trim() !== "") {
    return { ok: false, reason: "honeypot" };
  }

  const email = normalizeEmail(raw.email);
  if (!email) return { ok: false, reason: "invalid_email" };

  const name = boundedText(raw.name, 120);
  const tradeNiche = boundedText(raw.trade_niche ?? raw.tradeNiche, 120);
  const currentSituation = boundedText(raw.current_situation ?? raw.currentSituation, 1000);
  const goals = boundedText(raw.goals, 1000);
  const callAvailability = boundedText(raw.call_availability ?? raw.callAvailability, 200);
  if (!name || !tradeNiche || !currentSituation || !goals || !callAvailability) {
    return { ok: false, reason: "missing_field" };
  }

  const expRaw = typeof raw.years_experience === "string" ? raw.years_experience : raw.yearsExperience;
  const yearsExperience = (DFY_EXPERIENCE_RANGES as readonly string[]).includes(String(expRaw))
    ? (String(expRaw) as DfyExperienceRange)
    : null;
  if (!yearsExperience) return { ok: false, reason: "invalid_experience" };

  return {
    ok: true,
    intake: {
      name,
      email,
      trade_niche: tradeNiche,
      years_experience: yearsExperience,
      current_situation: currentSituation,
      goals,
      call_availability: callAvailability,
      community_member: toBoolean(raw.community_member ?? raw.communityMember),
    },
  };
}
