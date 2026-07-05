import { checkoutReadiness, OFFERS, FIRST_MONTH_COUPON_ENV } from "../src/lib/pricing";

/**
 * Offline guard: checkoutReadiness() must require the Stripe secret key AND
 * every configured offer's price id AND the first-month coupon id, not just
 * the secret key alone. Never reads real env values -- only ever sets/deletes
 * placeholder strings on process.env for the duration of this process.
 */

const ENV_KEYS = ["STRIPE_SECRET_KEY", FIRST_MONTH_COUPON_ENV, ...OFFERS.map((o) => o.stripePriceEnvVar)];
const savedEnv = new Map(ENV_KEYS.map((k) => [k, process.env[k]]));

function clearEnv(): void {
  for (const key of ENV_KEYS) delete process.env[key];
}

function restoreEnv(): void {
  for (const [key, value] of savedEnv) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function fullyConfigure(): void {
  process.env.STRIPE_SECRET_KEY = "sk_test_placeholder";
  process.env[FIRST_MONTH_COUPON_ENV] = "coupon_placeholder";
  for (const offer of OFFERS) {
    process.env[offer.stripePriceEnvVar] = `price_placeholder_${offer.id}`;
  }
}

type Test = { name: string; fn: () => void };
const tests: Test[] = [];
function test(name: string, fn: () => void) {
  tests.push({ name, fn });
}

test("not ready with no env configured at all", () => {
  clearEnv();
  assert(checkoutReadiness() === false, "expected checkoutReadiness() to be false");
});

test("not ready with only STRIPE_SECRET_KEY set (the bug this guards against)", () => {
  clearEnv();
  process.env.STRIPE_SECRET_KEY = "sk_test_placeholder";
  assert(
    checkoutReadiness() === false,
    "checkoutReadiness() must not return true from STRIPE_SECRET_KEY alone",
  );
});

test("not ready when a monthly offer's price id is missing", () => {
  clearEnv();
  fullyConfigure();
  const monthlyOffer = OFFERS.find((o) => o.billingType === "monthly");
  assert(monthlyOffer, "expected at least one monthly offer");
  delete process.env[monthlyOffer!.stripePriceEnvVar];
  assert(checkoutReadiness() === false, "expected checkoutReadiness() to be false");
});

test("not ready when the first-month coupon is missing but a monthly offer needs it", () => {
  clearEnv();
  fullyConfigure();
  delete process.env[FIRST_MONTH_COUPON_ENV];
  assert(checkoutReadiness() === false, "expected checkoutReadiness() to be false");
});

test("not ready when the one-time offer's price id is missing", () => {
  clearEnv();
  fullyConfigure();
  const onceOffer = OFFERS.find((o) => o.billingType === "one_time");
  assert(onceOffer, "expected at least one one-time offer");
  delete process.env[onceOffer!.stripePriceEnvVar];
  assert(checkoutReadiness() === false, "expected checkoutReadiness() to be false");
});

test("ready when every required env var for the current offers is present", () => {
  clearEnv();
  fullyConfigure();
  assert(checkoutReadiness() === true, "expected checkoutReadiness() to be true");
});

function main(): void {
  let failures = 0;
  for (const t of tests) {
    try {
      t.fn();
      console.log(`  PASS  ${t.name}`);
    } catch (e) {
      failures += 1;
      const message = e instanceof Error ? e.message : String(e);
      console.error(`  FAIL  ${t.name}`);
      console.error(`        ${message}`);
    }
  }
  restoreEnv();

  console.log("");
  console.log(`${tests.length - failures}/${tests.length} passed`);
  if (failures > 0) {
    process.exit(1);
  }
}

main();
