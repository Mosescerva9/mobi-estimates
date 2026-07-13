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

const forbiddenBroadClaims = [
  "ai-assisted construction estimates",
  "ai-audited construction estimates",
  "independently audited, contractor-ready estimate",
  "estimates and takeoffs generated with ai",
  "one professional construction estimate",
  "single construction estimate",
  "professional construction estimates in as little as 48 hours",
  "most standard-scope estimates are delivered within 48 hours",
];

const requiredTruthTerms = [
  "complete evidence",
  "supported scope",
  "required reviews",
  "owner approval",
];

for (const file of files) {
  const source = readFileSync(join(process.cwd(), file), "utf8");
  const normalized = source.toLowerCase();

  for (const claim of forbiddenBroadClaims) {
    assert(
      !normalized.includes(claim),
      `${file} must not publish the paused broad capability claim: ${claim}`,
    );
  }
}

const publicSurfaces = files.map((file) => ({
  file,
  source: readFileSync(join(process.cwd(), file), "utf8").toLowerCase(),
}));

for (const term of requiredTruthTerms) {
  assert(
    publicSurfaces.some(({ source }) => source.includes(term)),
    `public/pricing copy must name the P0 final-delivery gate term: ${term}`,
  );
}

assert(
  readFileSync(join(process.cwd(), "src/app/page.tsx"), "utf8").includes("Unsupported\n            scopes abstain, test-only evidence cannot unlock delivery"),
  "home page must state unsupported-scope abstention and test-only evidence blocking",
);

console.log(`PASS product truth posture: checked ${files.length} public/pricing source files`);
