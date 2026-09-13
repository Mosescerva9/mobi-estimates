import { readFileSync } from "fs";
import { DFY_EXPERIENCE_RANGES, parseDfyIntake } from "../src/lib/dfy-intake";
import { DFY_OFFER } from "../src/lib/dfy-offer";

/**
 * DFY "Estimator Business Setup" offer + intake invariants. Pure and static;
 * never touches the network, Stripe, or Supabase.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

// ── Offer config invariants ────────────────────────────────────────────────

test("offer is a $997 one-time product with the expected identifiers", () => {
  assert(DFY_OFFER.amountCents === 99_700, "$997 must be 99_700 cents");
  assert(DFY_OFFER.code === "dfy_setup", "offer code is dfy_setup");
  assert(DFY_OFFER.stripePriceEnvVar === "STRIPE_PRICE_DFY_SETUP", "env var name documented");
});

test("offer copy carries the truth-in-marketing posture (no income hype)", () => {
  const copy = [
    DFY_OFFER.name,
    DFY_OFFER.disclaimer,
    ...DFY_OFFER.deliverables,
    ...DFY_OFFER.boundaries,
  ].join(" ").toLowerCase();
  assert(copy.includes("no income"), "disclaimer must disavow income promises");
  assert(copy.includes("not an estimating service"), "boundaries must exclude estimating work");
  assert(!/guarantee[ds]?\b/.test(copy.replace("no income or revenue outcome is promised or implied", "")), "no guarantee language");
  assert(DFY_OFFER.deliverables.length >= 5, "fixed-scope deliverables listed");
  assert(DFY_OFFER.boundaries.length >= 3, "explicit boundaries listed");
});

// ── Intake parsing ─────────────────────────────────────────────────────────

const VALID = {
  name: "Sam Builder",
  email: "sam@example.com",
  trade_niche: "concrete",
  years_experience: "3-5",
  current_situation: "Employed estimator doing side work.",
  goals: "Freelance full-time.",
  call_availability: "weekday evenings CT",
};

test("valid intake parses and bounds fields", () => {
  const res = parseDfyIntake({ ...VALID, community_member: "yes" });
  assert(res.ok === true, "valid submission should parse");
  if (!res.ok) return;
  assert(res.intake.email === "sam@example.com", "email normalized");
  assert(res.intake.years_experience === "3-5", "experience enum kept");
  assert(res.intake.community_member === true, "checkbox coerced");
});

test("camelCase aliases from the form payload are accepted", () => {
  const res = parseDfyIntake({
    name: "Sam Builder",
    email: "sam@example.com",
    tradeNiche: "concrete",
    yearsExperience: "1-3",
    currentSituation: "Side hustle.",
    goals: "Grow.",
    callAvailability: "Sat mornings",
  });
  assert(res.ok === true, "camelCase payload should parse");
});

test("honeypot submissions are rejected as a silent no-op", () => {
  const res = parseDfyIntake({ ...VALID, honeypot: "http://spam" });
  assert(res.ok === false && res.reason === "honeypot", "filled honeypot rejected");
});

test("invalid email / missing fields / bad experience are rejected", () => {
  assert(parseDfyIntake({ ...VALID, email: "nope" }).ok === false, "bad email rejected");
  assert(parseDfyIntake({ ...VALID, goals: "   " }).ok === false, "blank goals rejected");
  assert(
    parseDfyIntake({ ...VALID, years_experience: "100+" }).ok === false,
    "experience outside the enum rejected",
  );
});

test("free-text fields strip control chars and bound length", () => {
  const res = parseDfyIntake({ ...VALID, goals: "grow\u0000\u0007", name: "x".repeat(500) });
  assert(res.ok === true, "should still parse");
  if (!res.ok) return;
  assert(res.intake.goals === "grow", "control chars stripped");
  assert(res.intake.name.length === 120, "name bounded to 120");
});

test("experience range enum stays the expected four buckets", () => {
  assert(DFY_EXPERIENCE_RANGES.join(",") === "0-1,1-3,3-5,5+", "enum drifted");
});

// ── Static wiring checks ───────────────────────────────────────────────────

test("webhook routes the dfy branch BEFORE the generic claim branch", () => {
  const webhook = readFileSync("src/app/api/stripe/webhook/route.ts", "utf8");
  const dfyIdx = webhook.indexOf("meta.plan_code === DFY_OFFER.code");
  const claimIdx = webhook.indexOf("await recordPendingClaim(");
  assert(dfyIdx > 0, "dfy branch missing from webhook");
  assert(claimIdx > dfyIdx, "dfy branch must run before the generic claim handler");
});

test("migration exists with default-deny RLS and the status check", () => {
  const sql = readFileSync("supabase/migrations/0038_dfy_orders.sql", "utf8");
  assert(sql.includes("enable row level security"), "RLS must be enabled");
  assert(!/create policy/i.test(sql), "no policies — service-role only");
  assert(sql.includes("'intake_submitted'") && sql.includes("'refunded'"), "status enum present");
});

test(".env.example documents the dfy price env var", () => {
  const env = readFileSync(".env.example", "utf8");
  assert(env.includes("STRIPE_PRICE_DFY_SETUP"), "env template missing STRIPE_PRICE_DFY_SETUP");
});

function main(): void {
  let failures = 0;
  for (const t of tests) {
    try {
      t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      console.error(`  FAIL  ${t.name}: ${e instanceof Error ? e.message : e}`);
    }
  }
  if (failures > 0) {
    console.error(`\n${failures} test(s) failed`);
    process.exit(1);
  }
  console.log(`\nAll ${tests.length} tests passed`);
}

main();
