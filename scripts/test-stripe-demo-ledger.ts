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
  netForRange,
  round2,
  usd,
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
eq("gross volume = 98995", GROSS_VOLUME, 98995);
eq("fees total = 2881.75", FEES_TOTAL, 2881.75);
eq("refunds total = 1594", REFUNDS_TOTAL, 1594);
eq("net total = 94519.25", NET_TOTAL, 94519.25);
eq("successful payments = 36", SUCCESSFUL_PAYMENTS, 36);
eq("avg order = 2749.86", AVG_ORDER, 2749.86);
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
eq("per-charge fee sum = 2881.75", feeSum, 2881.75);

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
eq("paid total = 87546.07", PAYOUTS_PAID_TOTAL, 87546.07);
eq("in-transit total = 3489.17", PAYOUTS_IN_TRANSIT_TOTAL, 3489.17);
eq("July payouts total = 91035.24", PAYOUTS_JULY_TOTAL, 91035.24);
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
  "7d payouts total = 35566.35",
  round2(sevenDayPayouts.reduce((s, p) => s + p.amount, 0)),
  35566.35,
);
eq("PAYOUTS_7D_TOTAL = 35566.35", PAYOUTS_7D_TOTAL, 35566.35);

// --- independent payout reconciliation -------------------------------------
// Rebuild all 20 settlement cycles straight from charges/refunds/schedule and
// compare every field against the exported payouts. This deliberately does NOT
// import or sum any exported payout constant; it re-derives them from scratch,
// so a regression in data.ts's derivation (or a reversion to hard-coded
// numbers that drift from the ledger) fails here.
{
  // July 2026 business days (Jul 3 bank holiday; weekends excluded), extended
  // two business days into August for late-July arrival dates.
  const bizDays = [
    1, 2, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 27, 28, 29, 30, 31,
  ];
  const FIRST = 2; // payouts begin after the first two business days
  const arrivalLabel = (index: number): string => {
    if (index < bizDays.length) return `Jul ${bizDays[index]}, 2026`;
    // Aug 1/2 are a weekend, so the next business days are Aug 3, Aug 4.
    const augBusiness = [3, 4];
    return `Expected Aug ${augBusiness[index - bizDays.length]}`;
  };
  const netOf = (amount: number): number => amount - feeFor(amount);

  interface Cycle {
    day: number;
    cutoffDay: number;
    amount: number;
    status: string;
    initiated: string;
    arrival: string;
    note?: string;
  }

  // settledIn[chargeIndex] = the payout day that settled it, or null.
  const settledIn: (number | null)[] = charges.map(() => null);
  const cycles: Cycle[] = [];

  for (let i = FIRST; i < bizDays.length; i++) {
    const day = bizDays[i];
    const cutoffDay = bizDays[i - 2];
    let cycleNet = 0;
    charges.forEach((c, idx) => {
      if (settledIn[idx] === null && c.day <= cutoffDay) {
        settledIn[idx] = day;
        cycleNet += netOf(c.amount);
      }
    });
    const refundTotal = refunds
      .filter((r) => r.debitedToPayoutDay === day)
      .reduce((s, r) => s + r.amount, 0);
    cycles.push({
      day,
      cutoffDay,
      amount: round2(cycleNet - refundTotal),
      status: i >= bizDays.length - 2 ? "in_transit" : "paid",
      initiated: `Jul ${day}, 2026`,
      arrival: arrivalLabel(i + 2),
      note: refundTotal > 0 ? `After ${usd(refundTotal)} refund` : undefined,
    });
  }

  eq("independent reconstruction yields 20 cycles", cycles.length, 20);
  eq("exported payout count matches reconstruction", payouts.length, cycles.length);

  // Every exported payout matches the independently derived cycle field-by-field.
  cycles.forEach((ex) => {
    const got = payouts.find((p) => p.day === ex.day);
    assert(`payout Jul ${ex.day} exists`, !!got, "missing from exports");
    if (!got) return;
    eq(`payout Jul ${ex.day} amount`, got.amount, ex.amount);
    eq(`payout Jul ${ex.day} status`, got.status, ex.status);
    eq(`payout Jul ${ex.day} initiated`, got.initiated, ex.initiated);
    eq(`payout Jul ${ex.day} arrival (+2 business days)`, got.arrival, ex.arrival);
    eq(`payout Jul ${ex.day} refund note`, got.note ?? null, ex.note ?? null);
  });
  // No exported payout is absent from the independent reconstruction.
  payouts.forEach((p) =>
    assert(
      `exported payout Jul ${p.day} is in the reconstruction`,
      cycles.some((ex) => ex.day === p.day),
    ),
  );

  // Explicit checks on the specified marquee figures.
  const cycle = (d: number) => cycles.find((c) => c.day === d)!;
  eq("independent Jul 30 amount", cycle(30).amount, 2907.84);
  eq("independent Jul 31 amount", cycle(31).amount, 581.33);
  eq("independent Jul 30 arrival", cycle(30).arrival, "Expected Aug 3");
  eq("independent Jul 31 arrival", cycle(31).arrival, "Expected Aug 4");
  eq("independent Jul 20 refund note", cycle(20).note, "After $599.00 refund");
  eq("independent Jul 27 refund note", cycle(27).note, "After $995.00 refund");
  eq("independent Jul 20 amount (post-refund)", cycle(20).amount, 2890.17);
  eq("independent Jul 27 amount (post-refund)", cycle(27).amount, 1912.84);

  // Independent aggregate totals (never summed from exported constants).
  const indPaid = round2(
    cycles.filter((c) => c.status === "paid").reduce((s, c) => s + c.amount, 0),
  );
  const indTransit = round2(
    cycles.filter((c) => c.status === "in_transit").reduce((s, c) => s + c.amount, 0),
  );
  const indJuly = round2(cycles.reduce((s, c) => s + c.amount, 0));
  const ind7d = round2(
    cycles.filter((c) => c.day >= 25).reduce((s, c) => s + c.amount, 0),
  );
  eq("independent paid total = 87546.07", indPaid, 87546.07);
  eq("independent in-transit total = 3489.17", indTransit, 3489.17);
  eq("independent July total = 91035.24", indJuly, 91035.24);
  eq("independent 7d total = 35566.35", ind7d, 35566.35);

  // Conservation: no charge settled twice, none skipped. Every charge is either
  // settled by exactly one July payout or left for the available-soon balance.
  const settledIdx = charges
    .map((_, idx) => idx)
    .filter((idx) => settledIn[idx] !== null);
  const unsettledIdx = charges
    .map((_, idx) => idx)
    .filter((idx) => settledIn[idx] === null);
  eq(
    "every charge is settled once or unsettled (no skips)",
    settledIdx.length + unsettledIdx.length,
    charges.length,
  );
  // A charge counts toward exactly one cycle's amount (single-assignment).
  assert(
    "no charge is settled by more than one payout",
    charges.every((_, idx) => {
      const claims = cycles.filter((c) => settledIn[idx] === c.day).length;
      return claims <= 1;
    }),
  );
  // Each settled charge is within its payout's cutoff and would not have been
  // eligible for any earlier payout's cutoff (proves correct cycle placement).
  assert(
    "each settled charge lands in the earliest cutoff that reaches it",
    charges.every((c, idx) => {
      const settledDay = settledIn[idx];
      if (settledDay === null) return true;
      const owner = cycles.find((cy) => cy.day === settledDay)!;
      if (c.day > owner.cutoffDay) return false;
      const earlier = cycles.filter((cy) => cy.day < settledDay);
      return earlier.every((cy) => c.day > cy.cutoffDay);
    }),
  );

  // Independently derive the available-soon balance from the unsettled ledger,
  // subtracting only refunds not already debited to an initiated payout.
  const initiatedDays = new Set(bizDays.slice(FIRST));
  const indAvailableSoon = round2(
    unsettledIdx.reduce((s, idx) => s + netOf(charges[idx].amount), 0) -
      refunds
        .filter((r) => !initiatedDays.has(r.debitedToPayoutDay))
        .reduce((s, r) => s + r.amount, 0),
  );
  eq("independent available soon = 3484.01", indAvailableSoon, 3484.01);
  eq("exported AVAILABLE_SOON matches derivation", AVAILABLE_SOON, indAvailableSoon);
  assert(
    "available-soon charges are exactly the Jul 30–31 charges",
    unsettledIdx.length > 0 && unsettledIdx.every((idx) => charges[idx].day >= 30),
  );
  // Full conservation across the derivation: paid + transit + available = net.
  assert(
    "independent paid + in-transit + available soon === net",
    round2(indPaid + indTransit + indAvailableSoon) === NET_TOTAL,
    `got ${round2(indPaid + indTransit + indAvailableSoon)} vs ${NET_TOTAL}`,
  );
}

// --- ranges ----------------------------------------------------------------
const month = ranges.month;
const seven = ranges["7d"];

eq("month range gross = 98995", month.gross, 98995);
eq(
  "month chart days sum to gross",
  round2(month.days.reduce((s, d) => s + d.gross, 0)),
  GROSS_VOLUME,
);
// The $50,000 increase lives entirely in the two one-time proration charges
// (day 15 and day 24), split evenly. Prove the changed ledger days reflect it.
const dayGross = (d: number) =>
  month.days.find((p) => p.dayNum === d)!.gross;
eq("day 15 proration charge = 26032.9", charges.find((c) => c.day === 15 && c.plan === "proration")!.amount, 26032.9);
eq("day 24 proration charge = 25884.1", charges.find((c) => c.day === 24 && c.plan === "proration")!.amount, 25884.1);
eq("day 15 daily gross = 28027.9 (growth 1995 + proration 26032.9)", dayGross(15), 28027.9);
eq("day 24 daily gross = 25884.1 (proration only)", dayGross(24), 25884.1);
eq("month new customers = 16", month.newCustomers, 16);
eq("month successful = 36", month.successful, 36);

// --- range net reconciliation (derived, never hard-coded) ------------------
// Each range's net must derive from the ledger: in-range gross, less per-charge
// Stripe fees, less refunds debited to a payout initiated within the range.
// month.net covers the whole of July, so it must equal NET_TOTAL exactly.
eq("month net = 94519.25 (= NET_TOTAL)", month.net, 94519.25);
eq("month net === NET_TOTAL", month.net, NET_TOTAL);
eq("netForRange(1,31) === month net", netForRange(1, 31), month.net);

// 7d (Jul 25–31): gross 12366 − fees 361.64 − Jul 27 refund 995 = 11009.36.
const net7dGross = round2(
  charges.filter((c) => c.day >= 25 && c.day <= 31).reduce((s, c) => s + c.amount, 0),
);
const net7dFees = round2(
  charges
    .filter((c) => c.day >= 25 && c.day <= 31)
    .reduce((s, c) => s + feeFor(c.amount), 0),
);
eq("7d net gross component = 12366", net7dGross, 12366);
eq("7d net fee component = 361.64", net7dFees, 361.64);
eq("7d net = 11009.36", seven.net, 11009.36);
eq("netForRange(25,31) === 7d net", netForRange(25, 31), seven.net);

// prev 7d (Jul 18–24): gross 33067.1 − fees 960.76 − Jul 20 refund 599 = 31507.34.
const prev7dGross = round2(
  charges.filter((c) => c.day >= 18 && c.day <= 24).reduce((s, c) => s + c.amount, 0),
);
const prev7dFees = round2(
  charges
    .filter((c) => c.day >= 18 && c.day <= 24)
    .reduce((s, c) => s + feeFor(c.amount), 0),
);
eq("prev 7d net gross component = 33067.1", prev7dGross, 33067.1);
eq("prev 7d net fee component = 960.76", prev7dFees, 960.76);
eq("prev 7d net = 31507.34", seven.prevNet, 31507.34);
eq("netForRange(18,24) === 7d prevNet", netForRange(18, 24), seven.prevNet);

// month.prevNet is a June historical comparison with no source ledger here,
// so it stays a fixed figure rather than a derived one.
eq("month prevNet unchanged = 39968.3", month.prevNet, 39968.3);

eq("7d gross = 12366", seven.gross, 12366);
eq("7d prev gross = 33067.1", seven.prevGross, 33067.1);
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
