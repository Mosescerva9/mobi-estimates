import { readFileSync } from "node:fs";
import { join } from "node:path";
import { OFFERS, getOffer } from "../src/lib/pricing";
import { INTRO_OFFER } from "../src/lib/intro-offer";

/**
 * Offer-truth guard: the retired 50%-off-first-month promotion (coupon,
 * discounted first-month price, readiness gate) must be fully gone from the
 * runtime pricing/checkout paths, regular prices must be preserved, and the
 * centralized intro-offer contract must keep its approved commitments.
 */

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
const test = (name: string, fn: () => void) => tests.push({ name, fn });

const read = (p: string) => readFileSync(join(process.cwd(), p), "utf8");

test("pricing.ts has no first-month / coupon code symbols", () => {
  const src = read("src/lib/pricing.ts").toLowerCase();
  // Code-level symbols only — a comment noting the coupon is *retired* is fine.
  for (const forbidden of ["firstmonth", "first_month_coupon", "discountapplies", "couponid"]) {
    assert(!src.includes(forbidden), `pricing.ts still references "${forbidden}"`);
  }
});

test("regular prices are preserved exactly", () => {
  assert(getOffer("starter").regularAmountCents === 99_500, "starter must be $995/mo");
  assert(getOffer("growth").regularAmountCents === 199_500, "growth must be $1,995/mo");
  assert(getOffer("estimating_department").regularAmountCents === 299_500, "est. dept must be $2,995/mo");
  assert(getOffer("pay_per_project").regularAmountCents === 59_900, "PPP must be $599 one-time");
});

test("Offer objects carry no first-month fields", () => {
  for (const offer of OFFERS) {
    assert(!("firstMonthAmountCents" in offer), `${offer.id} still has firstMonthAmountCents`);
    assert(!("firstMonthDiscountApplies" in offer), `${offer.id} still has firstMonthDiscountApplies`);
  }
});

test("checkout/start/stripe runtime paths carry no coupon logic", () => {
  for (const p of [
    "src/lib/stripe.ts",
    "src/app/api/stripe/checkout/route.ts",
    "src/app/start/route.ts",
  ]) {
    const src = read(p);
    assert(!src.includes("couponId"), `${p} still references couponId`);
    assert(!src.includes("FIRST_MONTH_COUPON_ENV"), `${p} still references FIRST_MONTH_COUPON_ENV`);
  }
});

test("intro offer keeps its approved commitments", () => {
  const blob = [
    INTRO_OFFER.summary,
    INTRO_OFFER.qualifyingRule,
    INTRO_OFFER.afterOffer,
    INTRO_OFFER.noGuarantee,
    INTRO_OFFER.reviewNote,
  ]
    .join(" ")
    .toLowerCase();
  assert(blob.includes("no card"), "intro offer must state no card required");
  assert(blob.includes("qualifying estimate"), "intro offer must reference a qualifying estimate");
  assert(blob.includes("reviewed before acceptance"), "intro offer must state scope reviewed before acceptance");
  assert(
    blob.includes("don't promise a turnaround") || blob.includes("guaranteed win"),
    "intro offer must disclaim guaranteed turnaround/win",
  );
});

test("FAQ replacement migration is deterministic on rerun", () => {
  const migration = read("supabase/migrations/0033_retire_first_month_promo_faq.sql");
  const insertAt = migration.indexOf("insert into public.faq_entries");
  assert(insertAt > 0, "FAQ replacement insert is missing");
  for (const question of [
    "Is there a free trial?",
    "Do new monthly subscribers get a first-month discount?",
    "Does the free estimate mean you will win my bid?",
  ]) {
    assert(
      migration.indexOf(`'${question}'`) > -1 && migration.indexOf(`'${question}'`) < insertAt,
      `replacement FAQ '${question}' must be deleted before reinsertion`,
    );
  }
  assert(!migration.includes("on conflict do nothing"), "FAQ migration must not rely on a missing unique constraint");
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
