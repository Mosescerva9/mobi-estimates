import {
  LEAD_CONSENT_VERSION,
  normalizeEmail,
  normalizeSource,
  parseLeadCapture,
  sanitizeUtmFreeText,
} from "../src/lib/lead-capture";

/**
 * Lead-capture normalization + abuse controls. Pure; never touches the network.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

test("email is trimmed + lowercased and shape/length bounded", () => {
  assert(normalizeEmail("  Foo@Bar.COM ") === "foo@bar.com", "must trim + lowercase");
  assert(normalizeEmail("not-an-email") === null, "must reject malformed email");
  assert(normalizeEmail("a@b") === null, "must require a dotted domain");
  assert(normalizeEmail("x".repeat(400) + "@a.com") === null, "must bound length");
  assert(normalizeEmail(123) === null, "non-strings rejected");
});

test("source is constrained to the allowlist (unknown -> 'unknown')", () => {
  assert(normalizeSource("homepage_hero") === "homepage_hero", "allowlisted source kept");
  assert(normalizeSource("evil'; drop table") === "unknown", "unknown source coerced");
  assert(normalizeSource(undefined) === "unknown", "missing source coerced");
});

test("free-text UTM values strip control chars and bound length", () => {
  assert(sanitizeUtmFreeText("spring\u0000\u0007sale") === "springsale", "control chars stripped");
  assert(sanitizeUtmFreeText("x".repeat(500))!.length === 120, "length bounded to 120");
  assert(sanitizeUtmFreeText("   ") === null, "whitespace-only -> null");
});

test("honeypot submissions are rejected as a silent no-op", () => {
  const res = parseLeadCapture({ email: "real@company.com", honeypot: "http://spam" });
  assert(res.ok === false && res.reason === "honeypot", "filled honeypot must be rejected");
});

test("invalid email is rejected (caller responds generically)", () => {
  const res = parseLeadCapture({ email: "nope" });
  assert(res.ok === false && res.reason === "invalid_email", "invalid email rejected");
});

test("valid submission builds a normalized, allowlisted record with consent", () => {
  const now = new Date("2026-07-22T00:00:00.000Z");
  const res = parseLeadCapture(
    {
      email: "  Lead@Company.com ",
      source: "homepage_hero",
      utmSource: "GOOGLE",
      utmMedium: "not_in_allowlist",
      utmCampaign: "summer\u0007-2026",
      honeypot: "",
    },
    now,
  );
  assert(res.ok === true, "valid submission should parse");
  if (!res.ok) return;
  assert(res.record.email === "lead@company.com", "email normalized");
  assert(res.record.source === "homepage_hero", "source allowlisted");
  assert(res.record.utm_source === "google", "utm_source allowlisted + lowercased");
  assert(res.record.utm_medium === null, "unknown utm_medium dropped to null");
  assert(res.record.utm_campaign === "summer-2026", "utm_campaign control-char stripped");
  assert(res.record.consent_version === LEAD_CONSENT_VERSION, "consent version stamped");
  assert(res.record.consent_at === now.toISOString(), "consent timestamp stamped");
});

function main(): void {
  let failures = 0;
  for (const t of tests) {
    try {
      t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      console.error(`  FAIL  ${t.name}`);
      console.error(`        ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  console.log(`\n${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) process.exit(1);
}

main();
