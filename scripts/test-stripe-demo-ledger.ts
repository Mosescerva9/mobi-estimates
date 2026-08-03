// Reconciliation tests for the Stripe Dashboard demonstration ledger.
// Everything is derived from `charges` in src/components/stripe-dashboard/data.ts;
// these assertions lock the derivation to the published figures.
//
// Run: npm run test:stripe-demo-ledger

import {
  charges,
  refunds,
  payouts,
  ranges,
  recentPayments,
  planCounts,
  feeFor,
  round2,
  GROSS_VOLUME,
  FEES_TOTAL,
  REFUNDS_TOTAL,
  NET_TOTAL,
  SUCCESSFUL_PAYMENTS,
  AVG_ORDER,
  MRR,
  SUBSCRIPTIONS,
  NEW_CUSTOMERS_JULY,
  PAYOUTS_PAID_TOTAL,
  PAYOUTS_IN_TRANSIT_TOTAL,
  PAYOUTS_JULY_TOTAL,
  PAYOUTS_7D_TOTAL,
  AVAILABLE_SOON,
  type PlanCode,
} from "../src/components/stripe-dashboard/data";

let failures = 0;
function assert(name: string, cond: boolean, detail?: string) {
  if (cond) {
    console.log(`  ✓ ${name}`);
  } else {
    failures += 1;
    console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}
function eq(name: string, actual: unknown, expected: unknown) {
  assert(name, actual === expected, `expected ${expected}, got ${actual}`);
}

console.log("Stripe demo ledger reconciliation\n");

// --- headline totals -------------------------------------------------------
eq("gross volume = 48995", GROSS_VOLUME, 48995);
eq("fees total = 1431.75", FEES_TOTAL, 1431.75);
eq("refunds total = 1594", REFUNDS_TOTAL, 1594);
eq("net total = 45969.25", NET_TOTAL, 45969.25);
eq("successful payments = 36", SUCCESSFUL_PAYMENTS, 36);
eq("avg order = 1360.97", AVG_ORDER, 1360.97);
eq("MRR = 39890", MRR, 39890);
eq("active subscriptions = 22", SUBSCRIPTIONS, 22);
eq("new customers July = 16", NEW_CUSTOMERS_JULY, 16);

// gross = fees + refunds + net (internal consistency)
eq(
  "gross === fees + refunds + net",
  round2(FEES_TOTAL + REFUNDS_TOTAL + NET_TOTAL),
  GROSS_VOLUME,
);

// --- fee formula spot check ------------------------------------------------
const feeSum = round2(charges.reduce((s, c) => s + feeFor(c.amount), 0));
eq("per-charge fee sum = 1431.75", feeSum, 1431.75);

// --- plan counts -----------------------------------------------------------
// ope 12 / starter 9 / growth 8 / ed 5 + 2 prorations
const expectedCounts: Record<PlanCode, number> = {
  ope: 12,
  starter: 9,
  growth: 8,
  ed: 5,
  proration: 2,
};
(Object.keys(expectedCounts) as PlanCode[]).forEach((p) =>
  eq(`plan count ${p} = ${expectedCounts[p]}`, planCounts[p], expectedCounts[p]),
);
eq("two refunds recorded", refunds.length, 2);

// --- payouts ---------------------------------------------------------------
eq("20 payouts", payouts.length, 20);
eq("paid total = 38996.07", PAYOUTS_PAID_TOTAL, 38996.07);
eq("in-transit total = 3489.17", PAYOUTS_IN_TRANSIT_TOTAL, 3489.17);
eq("July payouts total = 42485.24", PAYOUTS_JULY_TOTAL, 42485.24);
eq("available soon = 3484.01", AVAILABLE_SOON, 3484.01);
assert(
  "paid + in transit + available soon === net",
  round2(PAYOUTS_PAID_TOTAL + PAYOUTS_IN_TRANSIT_TOTAL + AVAILABLE_SOON) === NET_TOTAL,
  `got ${round2(PAYOUTS_PAID_TOTAL + PAYOUTS_IN_TRANSIT_TOTAL + AVAILABLE_SOON)}`,
);
assert(
  "no non-positive payouts",
  payouts.every((p) => p.amount > 0),
);
const sevenDayPayouts = payouts.filter((p) => p.day >= 25);
eq("5 payouts in 7d window", sevenDayPayouts.length, 5);
eq(
  "7d payouts total = 11291.35",
  round2(sevenDayPayouts.reduce((s, p) => s + p.amount, 0)),
  11291.35,
);
eq("PAYOUTS_7D_TOTAL = 11291.35", PAYOUTS_7D_TOTAL, 11291.35);

// --- ranges ----------------------------------------------------------------
const month = ranges.month;
const seven = ranges["7d"];

eq(
  "month chart days sum to gross",
  round2(month.days.reduce((s, d) => s + d.gross, 0)),
  GROSS_VOLUME,
);
eq("month new customers = 16", month.newCustomers, 16);
eq("month successful = 36", month.successful, 36);

eq("7d gross = 12366", seven.gross, 12366);
eq("7d prev gross = 8067.1", seven.prevGross, 8067.1);
eq("7d successful = 10", seven.successful, 10);
eq("7d prev successful = 6", seven.prevSuccessful, 6);
eq("7d new customers = 4", seven.newCustomers, 4);
eq(
  "7d chart days sum to 12366",
  round2(seven.days.reduce((s, d) => s + d.gross, 0)),
  12366,
);

// --- recent transactions all map to a ledger charge ------------------------
const descToPlan: Record<string, PlanCode> = {
  "One Project Estimate": "ope",
  Starter: "starter",
  Growth: "growth",
  "Estimating Department": "ed",
};
recentPayments.forEach((row) => {
  const plan = descToPlan[row.description];
  const match = charges.some(
    (c) => c.day === row.chargeDay && c.amount === row.amount && c.plan === plan,
  );
  assert(
    `recent txn "${row.name}" matches a ledger charge`,
    match,
    `day ${row.chargeDay} / ${row.amount} / ${plan}`,
  );
});

console.log(
  failures === 0
    ? "\nAll ledger reconciliation checks passed."
    : `\n${failures} check(s) FAILED.`,
);
process.exit(failures === 0 ? 0 : 1);
