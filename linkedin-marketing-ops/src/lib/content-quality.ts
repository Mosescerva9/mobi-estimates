/**
 * Light cleanup so drafts stay LinkedIn-native and on-brand even when the model drifts.
 */

const BANNED_PHRASES = [
  /game[-\s]?changer/gi,
  /revolutionary/gi,
  /unlock(ing)?\s+your\s+potential/gi,
  /in today'?s competitive landscape/gi,
  /leverage\s+synergies/gi,
  /comment\s+YES/gi,
  /like\s+if\s+you\s+agree/gi,
];

export function stripEmojis(text: string): string {
  return text
    .replace(/\p{Extended_Pictographic}/gu, "")
    .replace(/\uFE0F/g, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function cleanupMarketingSpeak(text: string): string {
  let next = stripEmojis(text);
  for (const pattern of BANNED_PHRASES) {
    next = next.replace(pattern, "").replace(/[ ]{2,}/g, " ");
  }
  return next.replace(/\n{3,}/g, "\n\n").trim();
}

export function clampHashtags(text: string, max = 2): string {
  const lines = text.split("\n");
  const body: string[] = [];
  const tags: string[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (/^(#[\w-]+\s*)+$/.test(trimmed)) {
      const found = trimmed.match(/#[\w-]+/g) || [];
      tags.push(...found);
    } else {
      body.push(line);
    }
  }

  const unique = [...new Set(tags)].slice(0, max);
  if (unique.length === 0) return body.join("\n").trim();
  return `${body.join("\n").trim()}\n\n${unique.join(" ")}`.trim();
}

export function polishPostBody(body: string): string {
  return clampHashtags(cleanupMarketingSpeak(body));
}

export function polishShortText(text: string): string {
  return stripEmojis(text).replace(/\s+/g, " ").trim();
}

export function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

export function charCount(text: string): number {
  return text.length;
}
