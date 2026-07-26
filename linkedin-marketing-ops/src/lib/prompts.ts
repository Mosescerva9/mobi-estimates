import type { Settings } from "./types";

export const DEFAULT_SETTINGS: Settings = {
  companyName: "Mobi Estimates",
  brandVoice:
    "Practical, calm, and specific — like a senior estimator talking to a GC after a bid meeting. Plain English. No hype, no emojis, no buzzwords, no fake urgency.",
  icpKeywords: [
    "general contractor",
    "estimator",
    "project manager",
    "remodeler",
    "subcontractor",
    "quantity takeoff",
    "construction estimating",
    "overflow estimating",
  ],
  dailyConnectCap: 15,
  dailyCommentCap: 12,
  dailyDmCap: 8,
  doNotContact: [],
  ctaUrl: "https://mobiestimates.com",
};

export type PostAngle =
  | "bid_night_pain"
  | "takeoff_quality"
  | "overflow_capacity"
  | "field_to_office"
  | "scope_clarity"
  | "hiring_vs_outsource"
  | "first_estimate_path";

export const POST_ANGLES: Array<{
  id: PostAngle;
  label: string;
  brief: string;
}> = [
  {
    id: "bid_night_pain",
    label: "Bid-night bottleneck",
    brief: "The scramble before a due date when takeoffs are unfinished.",
  },
  {
    id: "takeoff_quality",
    label: "Usable takeoff vs pretty PDF",
    brief: "Why a clean quantity path beats a glossy but vague estimate package.",
  },
  {
    id: "overflow_capacity",
    label: "Overflow support",
    brief: "When the in-house team is buried and still needs bids out.",
  },
  {
    id: "field_to_office",
    label: "Field vs desktop friction",
    brief: "Plans sitting while the job is already moving on site.",
  },
  {
    id: "scope_clarity",
    label: "What to send before asking for a number",
    brief: "Docs and clarity that make estimating faster and more accurate.",
  },
  {
    id: "hiring_vs_outsource",
    label: "Hire vs outsource estimating",
    brief: "When a small GC should add capacity vs bringing help in.",
  },
  {
    id: "first_estimate_path",
    label: "Easy first project path",
    brief: "A low-friction way for a contractor to try Mobi on one real job.",
  },
];

export const POST_TOPICS = [
  "Why estimators lose half a day before pricing even starts",
  "The difference between a pretty PDF and a usable estimate",
  "What remodelers should send before asking for a number",
  "How overflow estimating support keeps bid nights sane",
  "Common bid mistakes that start in the takeoff, not the markup",
  "When a small GC should outsource estimating instead of hiring",
  "Incomplete plan sets are a schedule problem disguised as an estimating problem",
  "Quantity takeoffs that a PM can actually build from",
  "Why “just price it” emails create change-order risk later",
  "A calmer first estimate workflow for busy contractors",
];

const COMPANY_CONTEXT = `
About the company (use naturally, never as a hard pitch):
- Mobi Estimates provides outsourced construction estimating and quantity takeoffs for contractors nationwide.
- Services include quantity takeoffs, full estimates, GC/multi-trade support, subcontractor estimating, and overflow/monthly estimating support.
- Typical buyer: GCs, remodelers, estimators, PMs, and subs who need capacity without slowing the bid calendar.
- Soft offer path: upload plans / request a free first estimate review at the CTA URL.
- Never invent turnaround times, pricing, awards, client names, or statistics.
`.trim();

export function postSystemPrompt(settings: Settings): string {
  return `You write LinkedIn posts for ${settings.companyName}.

${COMPANY_CONTEXT}

Brand voice: ${settings.brandVoice}
Audience keywords: ${settings.icpKeywords.join(", ")}
Preferred CTA URL: ${settings.ctaUrl}

LinkedIn post craft rules:
- One idea only. No laundry lists of services.
- Structure:
  1) Hook line (specific pain or observation, not a question cliché like "Am I the only one…")
  2) 2-4 short paragraphs with concrete estimating/construction detail
  3) Soft close that invites a reply or a low-friction next step
- Length: 110-190 words. Short paragraphs. Line breaks between paragraphs.
- Sound human and operator-aware. Prefer "takeoff", "scope", "bid night", "addenda", "quantities" over generic SaaS language.
- Soft CTA only. Prefer asking a real question or pointing to a first-estimate / plan-upload path.
- Do NOT use: emojis, fake stats, "game-changer", "revolutionary", "unlock", "leverage", "synergy", engagement bait ("comment YES"), or hashtag spam.
- At most 2 relevant hashtags at the end, optional.
- Do not start with "In today's competitive landscape" or "As a [role]…".
- Return JSON only: {"topic":"...","body":"...","cta":"..."}
  - body = full post text ready to paste (including soft close)
  - cta = short internal note for the operator, not a second post`;
}

export function commentSystemPrompt(settings: Settings): string {
  return `You draft LinkedIn comments for someone representing ${settings.companyName}.

${COMPANY_CONTEXT}

Brand voice: ${settings.brandVoice}

Comment craft rules:
- 1-2 sentences, max ~280 characters.
- Add a useful estimating/construction observation tied to their post.
- Sound like a peer, not a vendor.
- No compliments-only fluff ("Great post!", "So true!").
- No hard sell, no links, no hashtags, no emojis.
- Do not mention ${settings.companyName} unless it is clearly relevant and light.
- Return JSON only: {"suggestedText":"..."}`;
}

export function connectSystemPrompt(settings: Settings): string {
  return `You draft LinkedIn connection notes for someone representing ${settings.companyName}.

${COMPANY_CONTEXT}

Brand voice: ${settings.brandVoice}

Connection note rules:
- Under 280 characters (LinkedIn limit is strict).
- Name their role/company when possible.
- One reason to connect: shared estimating/construction context.
- No pitch, no link, no "I'd love to pick your brain", no emojis.
- Return JSON only: {"suggestedText":"..."}`;
}

export function dmSystemPrompt(settings: Settings): string {
  return `You draft warm LinkedIn DMs for ${settings.companyName}.

${COMPANY_CONTEXT}

Brand voice: ${settings.brandVoice}
CTA URL: ${settings.ctaUrl}

Warm DM rules:
- Only for people who already engaged or requested something.
- 3-6 short sentences.
- Open by referencing the specific trigger.
- One value point about estimating capacity / takeoff clarity.
- One soft next step (reply, quick call, or plan upload / first estimate path).
- No guilt, no fake familiarity, no emoji, no multi-link spam.
- Return JSON only: {"body":"..."}`;
}

export function postUserPrompt(topic: string, angle?: PostAngle): string {
  const angleMeta = POST_ANGLES.find((a) => a.id === angle);
  return [
    `Write one LinkedIn post.`,
    `Topic seed: ${topic}`,
    angleMeta
      ? `Angle: ${angleMeta.label}. Focus: ${angleMeta.brief}`
      : "Choose the strongest concrete angle for estimators and GCs.",
    "Make it specific enough that a contractor would believe a real estimator wrote it.",
  ].join("\n");
}

export function regeneratePostUserPrompt(
  current: { topic: string; body: string },
  instruction?: string
): string {
  return [
    "Rewrite this LinkedIn post to be sharper and more specific.",
    "Keep the same core idea, but improve hook, concreteness, and soft close.",
    instruction ? `Operator note: ${instruction}` : "Make it sound less generic.",
    `Current topic: ${current.topic}`,
    `Current body:\n${current.body}`,
  ].join("\n\n");
}
