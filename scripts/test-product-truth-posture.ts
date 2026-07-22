import { readFileSync } from "node:fs";
import { join } from "node:path";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const files = [
  "src/app/page.tsx",
  "src/app/pricing/page.tsx",
  "src/components/PricingCards.tsx",
] as const;

// The retired 50%-off-first-month promotion (AFFIRMATIVE promo phrasings) and
// unsupported-capability/outcome claims must not appear on any public/pricing
// surface. Truthful negations ("no first-month discount") are intentionally NOT
// forbidden — only the promotional wording that advertises the retired offer.
const forbiddenClaims = [
  "50% off",
  "off your first month",
  "for your first month",
  "ai-audited",
  "ai-assisted construction estimates",
  // Affirmative win/turnaround promises only — truthful negations
  // ("we don't promise ... a guaranteed win") must remain allowed.
  "guarantee you win",
  "guaranteed to win",
  "we guarantee",
  "guaranteed turnaround",
  "win rate",
  "48 hours",
  "audit-reset",
];

// Truthful final-delivery gate language must still be present somewhere across
// the public/pricing surfaces.
const requiredTruthTerms = [
  "complete evidence",
  "supported scope",
  "required reviews",
  "owner approval",
];

const publicSurfaces = files.map((file) => ({
  file,
  source: readFileSync(join(process.cwd(), file), "utf8"),
  normalized: readFileSync(join(process.cwd(), file), "utf8").toLowerCase(),
}));

for (const { file, normalized } of publicSurfaces) {
  for (const claim of forbiddenClaims) {
    assert(
      !normalized.includes(claim),
      `${file} must not publish the retired/forbidden claim: "${claim}"`,
    );
  }
}

for (const term of requiredTruthTerms) {
  assert(
    publicSurfaces.some(({ normalized }) => normalized.includes(term)),
    `public/pricing copy must name the final-delivery gate term: ${term}`,
  );
}

// The homepage must carry the approved intro-offer truth: free per new company,
// no card, reviewed before acceptance, and no guaranteed win.
const home = publicSurfaces.find((s) => s.file === "src/app/page.tsx")!;
for (const phrase of [
  "no card required",
  "reviewed before acceptance",
  "track bid progress and follow-up steps",
]) {
  assert(
    home.normalized.includes(phrase),
    `home page must state the approved intro-offer phrase: "${phrase}"`,
  );
}

console.log(`PASS product truth posture: checked ${files.length} public/pricing source files`);
