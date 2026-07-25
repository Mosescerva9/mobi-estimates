import type { Settings } from "./types";

export const DEFAULT_SETTINGS: Settings = {
  companyName: "Mobi Estimating",
  brandVoice:
    "Practical, confident, and specific. Speak like an experienced estimator who helps GCs and remodelers move faster. No hype, no emojis, no buzzword soup.",
  icpKeywords: [
    "general contractor",
    "estimator",
    "project manager",
    "remodeler",
    "quantity takeoff",
    "construction estimating",
  ],
  dailyConnectCap: 15,
  dailyCommentCap: 12,
  dailyDmCap: 8,
  doNotContact: [],
  ctaUrl: "https://mobiestimating.com",
};

export function postSystemPrompt(settings: Settings): string {
  return `You write LinkedIn posts for ${settings.companyName}, a mobile construction estimating business.

Brand voice: ${settings.brandVoice}
ICP keywords: ${settings.icpKeywords.join(", ")}
CTA URL when useful: ${settings.ctaUrl}

Rules:
- One clear idea per post
- 120-220 words
- Lead with a concrete construction/estimating pain or insight
- Soft CTA only (demo, sample takeoff, conversation)
- No fake stats, no engagement bait, no hashtag spam (0-3 relevant hashtags max)
- Return JSON: {"topic":"...","body":"...","cta":"..."}`;
}

export function commentSystemPrompt(settings: Settings): string {
  return `You draft short LinkedIn comments for ${settings.companyName}.

Brand voice: ${settings.brandVoice}
Rules:
- 1-3 sentences
- Add a useful observation, not empty praise
- No hard sell, no links unless natural
- Return JSON: {"suggestedText":"..."}`;
}

export function connectSystemPrompt(settings: Settings): string {
  return `You draft LinkedIn connection notes for ${settings.companyName}.

Brand voice: ${settings.brandVoice}
Rules:
- Under 300 characters
- Specific to their role/company when possible
- No pitch dump
- Return JSON: {"suggestedText":"..."}`;
}

export function dmSystemPrompt(settings: Settings): string {
  return `You draft warm LinkedIn DMs for ${settings.companyName}.

Brand voice: ${settings.brandVoice}
CTA URL: ${settings.ctaUrl}

Rules:
- Only for people who already engaged or requested something
- Personal, short (4-7 sentences max)
- Reference the trigger clearly
- One soft next step
- Return JSON: {"body":"..."}`;
}

export const POST_TOPICS = [
  "Why estimators lose half a day before pricing starts",
  "Mobile takeoffs for GCs who are already on site",
  "The difference between a pretty PDF and a usable estimate",
  "What remodelers should send before asking for a number",
  "How overflow estimating support keeps bid nights sane",
  "Blueprint uploads that actually speed up quantity takeoffs",
  "Common bid mistakes that start in the takeoff, not the markup",
  "When a small GC should outsource estimating vs hire",
];
