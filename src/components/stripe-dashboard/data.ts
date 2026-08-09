// ---------------------------------------------------------------------------
// SYNTHETIC LEDGER — source of truth for the Stripe Dashboard DEMONSTRATION.
//
// Every headline figure on the demo is DERIVED from the `charges` array below.
// This is SAMPLE DATA for a visual demonstration only. It is NOT a live Stripe
// account and has NO connection to Stripe or any real financial data.
//
// Plan codes / list prices:
//   ope     One Project Estimate      $599   (one-time)
//   starter Starter — monthly         $995   (subscription)
//   growth  Growth — monthly          $1,995 (subscription)
//   ed      Estimating Department     $2,995 (subscription)
//   proration  mid-cycle upgrade charge (one-time)
//
// Non-proration charge amounts are DERIVED from the authoritative pricing config
// (src/lib/pricing.ts) via `priceOf`, so the demo can never drift from Mobi's
// real business prices. The two prorations are legitimate mid-cycle upgrade
// deltas that never exceed the upgrade's full price difference.
//
// Reconciles to:
//   gross $98,995.00 · refunds $1,594.00 · 51 successful payments
//   MRR $91,795 (41 subs) · 16 new customers · 20 payouts
//   (fees, net, avg order, and payout totals are all derived below; every
//    July settlement cycle initiates a payout, one per business day)
// ---------------------------------------------------------------------------

import { getOffer, type OfferId } from "../../lib/pricing";

export const BUSINESS_NAME = "Mobi Estimates";
export const BANK_NAME = "Chase Bank";
export const BANK_LAST4 = "6789";

export type RangeKey = "month" | "7d";

export type PlanCode = "ope" | "starter" | "growth" | "ed" | "proration";

export interface Charge {
  /** Day-of-month in July 2026. */
  day: number;
  amount: number;
  plan: PlanCode;
  /** True when this charge is a first-time (new) customer. */
  isNew?: boolean;
  /** Human label for prorated upgrades. */
  note?: string;
}

// Map each subscription/one-time plan code to its authoritative offer id so the
// ledger amount is the real Mobi price, never a duplicated literal.
const PLAN_OFFER: Record<Exclude<PlanCode, "proration">, OfferId> = {
  ope: "pay_per_project",
  starter: "starter",
  growth: "growth",
  ed: "estimating_department",
};

/** The authoritative price (in dollars) for a non-proration plan. */
const priceOf = (plan: Exclude<PlanCode, "proration">): number =>
  getOffer(PLAN_OFFER[plan]).regularAmountCents / 100;

/** A plan charge whose amount is the authoritative price. */
const sub = (day: number, plan: Exclude<PlanCode, "proration">, isNew = false): Charge =>
  isNew
    ? { day, amount: priceOf(plan), plan, isNew: true }
    : { day, amount: priceOf(plan), plan };

/** A legitimate mid-cycle upgrade proration (a one-time delta charge). */
const prorate = (day: number, amount: number, note: string): Charge => ({
  day,
  amount,
  plan: "proration",
  note,
});

// The ledger. Day = July 2026 day-of-month. Revenue is spread realistically
// across the month with several zero-revenue days; the daily distribution is
// intentional and auditable (see the per-day schedule below). All amounts are
// derived: plan charges from priceOf(), prorations from the named upgrade delta.
export const charges: Charge[] = [
  // Jul 1 — 5589
  sub(1, "growth"),
  sub(1, "ope", true),
  sub(1, "ed"),
  // Jul 2 — 4990
  sub(2, "growth", true),
  sub(2, "ed"),
  // Jul 6 — 6589
  sub(6, "ed"),
  sub(6, "ope", true),
  sub(6, "ed"),
  // Jul 7 — 5990
  sub(7, "ed"),
  sub(7, "ed"),
  // Jul 8 — 3990
  sub(8, "growth", true),
  sub(8, "growth"),
  // Jul 9 — 4985
  sub(9, "growth"),
  sub(9, "starter", true),
  sub(9, "growth"),
  // Jul 10 — 4990
  sub(10, "ed"),
  sub(10, "growth", true),
  // Jul 13 — 5985
  sub(13, "growth", true),
  sub(13, "growth"),
  sub(13, "growth"),
  // Jul 14 — 5990
  sub(14, "ed"),
  sub(14, "ed"),
  // Jul 15 — 3903
  prorate(15, 908, "Growth → ED upgrade"),
  sub(15, "ed", true),
  // Jul 16 — 6985
  sub(16, "ed"),
  sub(16, "growth", true),
  sub(16, "growth"),
  // Jul 17 — 3594
  sub(17, "ed"),
  sub(17, "ope"),
  // Jul 20 — 3985
  sub(20, "starter", true),
  sub(20, "starter"),
  sub(20, "growth"),
  // Jul 21 — 4495
  sub(21, "ed"),
  prorate(21, 1500, "Starter → ED upgrade"),
  // Jul 22 — 5990
  sub(22, "ed", true),
  sub(22, "ed"),
  // Jul 23 — 4589
  sub(23, "ope", true),
  sub(23, "ed"),
  sub(23, "starter"),
  // Jul 24 — 3990
  sub(24, "starter"),
  sub(24, "ed"),
  // Jul 25 – 31 — unchanged so Last 7 Days, recent transactions, and recent
  // rows stay exactly the same.
  sub(25, "starter"),
  sub(25, "ope", true),
  sub(27, "growth"),
  sub(27, "starter"),
  sub(27, "ope", true),
  sub(28, "ed"),
  sub(29, "ope", true),
  sub(30, "growth"),
  sub(30, "ope", true),
  sub(31, "starter"),
];

// Refunds (debited to the payout initiated on the given day).
export interface Refund {
  chargeDay: number;
  amount: number;
  debitedToPayoutDay: number;
}
export const refunds: Refund[] = [
  { chargeDay: 17, amount: 599, debitedToPayoutDay: 20 },
  { chargeDay: 23, amount: 995, debitedToPayoutDay: 27 },
];

// --- money helpers ---------------------------------------------------------

/** Round to cents, nudging past binary-float error so .155 → .16. */
export const round2 = (n: number): number => Math.round((n + 1e-9) * 100) / 100;

/** Stripe standard US card fee: 2.9% + $0.30, rounded to the cent. */
export const feeFor = (amount: number): number => round2(amount * 0.029 + 0.3);

export const usd = (n: number): string =>
  n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export const usd0 = (n: number): string =>
  n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });

export const pctDelta = (current: number, previous: number): number =>
  ((current - previous) / previous) * 100;

export const pctDeltaLabel = (current: number, previous: number): string => {
  const d = pctDelta(current, previous);
  return `${d >= 0 ? "+" : ""}${d.toFixed(1)}%`;
};

const SUBSCRIPTION_PLANS: PlanCode[] = ["starter", "growth", "ed"];

// --- derived headline figures ---------------------------------------------

export const GROSS_VOLUME = round2(charges.reduce((s, c) => s + c.amount, 0));
export const FEES_TOTAL = round2(charges.reduce((s, c) => s + feeFor(c.amount), 0));
export const REFUNDS_TOTAL = round2(refunds.reduce((s, r) => s + r.amount, 0));
export const NET_TOTAL = round2(GROSS_VOLUME - FEES_TOTAL - REFUNDS_TOTAL);
export const SUCCESSFUL_PAYMENTS = charges.length;
export const AVG_ORDER = round2(GROSS_VOLUME / SUCCESSFUL_PAYMENTS);
export const NEW_CUSTOMERS_JULY = charges.filter((c) => c.isNew).length;

export const SUBSCRIPTIONS = charges.filter((c) =>
  SUBSCRIPTION_PLANS.includes(c.plan),
).length;
export const MRR = round2(
  charges
    .filter((c) => SUBSCRIPTION_PLANS.includes(c.plan))
    .reduce((s, c) => s + c.amount, 0),
);

export const planCounts: Record<PlanCode, number> = charges.reduce(
  (acc, c) => {
    acc[c.plan] = (acc[c.plan] ?? 0) + 1;
    return acc;
  },
  { ope: 0, starter: 0, growth: 0, ed: 0, proration: 0 } as Record<PlanCode, number>,
);

// --- daily series (derived) ------------------------------------------------

export interface DayPoint {
  day: string; // "Jul 1"
  dayNum: number;
  gross: number;
  customers: number;
}

const DAYS_IN_JULY = 31;
const allDays: DayPoint[] = Array.from({ length: DAYS_IN_JULY }, (_, i) => {
  const dayNum = i + 1;
  const dayCharges = charges.filter((c) => c.day === dayNum);
  return {
    day: `Jul ${dayNum}`,
    dayNum,
    gross: round2(dayCharges.reduce((s, c) => s + c.amount, 0)),
    customers: dayCharges.filter((c) => c.isNew).length,
  };
});

const sumGross = (days: DayPoint[]) => round2(days.reduce((s, d) => s + d.gross, 0));
const sumNew = (days: DayPoint[]) => days.reduce((s, d) => s + d.customers, 0);
const countCharges = (from: number, to: number) =>
  charges.filter((c) => c.day >= from && c.day <= to).length;

/**
 * Net proceeds for an inclusive July day range, derived from the ledger: the
 * gross of every charge in [from, to], less each charge's own independently
 * rounded Stripe fee, less any refunds debited to a payout initiated within the
 * same range. Nothing here is hard-coded, so on-page range figures reconcile to
 * the ledger the same way NET_TOTAL does.
 */
export const netForRange = (from: number, to: number): number => {
  const inRange = charges.filter((c) => c.day >= from && c.day <= to);
  const gross = inRange.reduce((s, c) => s + c.amount, 0);
  const fees = inRange.reduce((s, c) => s + feeFor(c.amount), 0);
  const refundsDebited = refunds
    .filter((r) => r.debitedToPayoutDay >= from && r.debitedToPayoutDay <= to)
    .reduce((s, r) => s + r.amount, 0);
  return round2(gross - fees - refundsDebited);
};

export interface RangeData {
  key: RangeKey;
  label: string;
  shortLabel: string;
  compareLabel: string;
  gross: number;
  prevGross: number;
  net: number;
  prevNet: number;
  newCustomers: number;
  prevNewCustomers: number;
  successful: number;
  prevSuccessful: number;
  freeEstimates: number;
  prevFreeEstimates: number;
  days: DayPoint[];
  /** Recharts tick interval for the x-axis. */
  tickInterval: number;
}

const last7 = allDays.slice(24); // Jul 25 – 31

export const ranges: Record<RangeKey, RangeData> = {
  month: {
    key: "month",
    label: "Jul 1 – Jul 31, 2026",
    shortLabel: "Jul 1 – Jul 31",
    compareLabel: "Compared to Jun 1 – Jun 30",
    gross: sumGross(allDays),
    prevGross: 41206.3,
    net: netForRange(1, DAYS_IN_JULY), // = NET_TOTAL 94514.65
    prevNet: 39968.3, // June historical comparison — no source ledger here
    newCustomers: sumNew(allDays),
    prevNewCustomers: 13,
    successful: SUCCESSFUL_PAYMENTS,
    prevSuccessful: 31,
    freeEstimates: 23,
    prevFreeEstimates: 19,
    days: allDays,
    tickInterval: 6, // every 7th label
  },
  "7d": {
    key: "7d",
    label: "Jul 25 – Jul 31, 2026",
    shortLabel: "Jul 25 – Jul 31",
    compareLabel: "Compared to Jul 18 – Jul 24",
    gross: sumGross(last7),
    prevGross: sumGross(allDays.slice(17, 24)), // Jul 18 – 24
    net: netForRange(25, 31), // = 11009.36
    prevNet: netForRange(18, 24), // Jul 18 – 24 = 21777.93
    newCustomers: sumNew(last7),
    prevNewCustomers: sumNew(allDays.slice(17, 24)),
    successful: countCharges(25, 31),
    prevSuccessful: countCharges(18, 24),
    freeEstimates: 6,
    prevFreeEstimates: 5,
    days: last7,
    tickInterval: 0, // every label
  },
};

// --- payouts (2-business-day rolling; Jul 3 bank holiday) ------------------

export type PayoutStatus = "paid" | "in_transit";

export interface Payout {
  day: number;
  amount: number;
  status: PayoutStatus;
  initiated: string;
  arrival: string;
  note?: string;
}

// July 2026 business days (weekends excluded; Jul 3 is a bank holiday for the
// Jul 4 Independence Day observance). This is the settlement calendar.
const JULY_BUSINESS_DAYS = [
  1, 2, 6, 7, 8, 9, 10, 13, 14, 15, 16, 17, 20, 21, 22, 23, 24, 27, 28, 29, 30, 31,
];

// The same calendar extended two business days into August, so payouts
// initiated late in July can resolve their arrival dates.
interface BusinessDay {
  month: "Jul" | "Aug";
  day: number;
}
const BUSINESS_DAYS: BusinessDay[] = [
  ...JULY_BUSINESS_DAYS.map((day) => ({ month: "Jul" as const, day })),
  { month: "Aug", day: 3 },
  { month: "Aug", day: 4 },
];

// Payouts initiate on every business day AFTER the first two — 20 in July.
const FIRST_PAYOUT_INDEX = 2;
const INITIATED_PAYOUT_DAYS = new Set(
  JULY_BUSINESS_DAYS.slice(FIRST_PAYOUT_INDEX),
);

/** A charge's proceeds after its own independently rounded Stripe fee. */
const netOfFee = (c: Charge): number => c.amount - feeFor(c.amount);

/**
 * Reconstruct the payout schedule from the ledger — nothing here is hard-coded.
 *
 * A payout initiated on business-day index `i` settles every not-yet-settled
 * charge dated on or before its cutoff: the business day two business days
 * earlier (index `i - 2`). Charges that land on weekends/holidays therefore
 * roll into the next cycle whose cutoff reaches them. The Jul 20 / Jul 27
 * payouts are additionally reduced by the refunds debited to them. Funds
 * arrive two business days after initiation (index `i + 2`). The final two
 * initiations (Jul 30 / Jul 31) are still in transit; all earlier ones paid.
 *
 * Returns the payouts plus a per-charge flag marking which charges an
 * initiated July payout settled, so callers can derive the unsettled balance.
 */
function derivePayouts(): { payouts: Payout[]; settled: boolean[] } {
  const settled = charges.map(() => false);
  const chronological: Payout[] = [];

  for (let i = FIRST_PAYOUT_INDEX; i < JULY_BUSINESS_DAYS.length; i++) {
    const day = JULY_BUSINESS_DAYS[i];
    const cutoffDay = JULY_BUSINESS_DAYS[i - 2];

    let cycleNet = 0;
    charges.forEach((c, idx) => {
      if (!settled[idx] && c.day <= cutoffDay) {
        settled[idx] = true;
        cycleNet += netOfFee(c);
      }
    });

    const refundTotal = refunds
      .filter((r) => r.debitedToPayoutDay === day)
      .reduce((s, r) => s + r.amount, 0);
    const amount = round2(cycleNet - refundTotal);

    const isTransit = i >= JULY_BUSINESS_DAYS.length - 2;
    const arrival = BUSINESS_DAYS[i + 2];

    const payout: Payout = {
      day,
      amount,
      status: isTransit ? "in_transit" : "paid",
      initiated: `Jul ${day}, 2026`,
      arrival:
        arrival.month === "Jul"
          ? `Jul ${arrival.day}, 2026`
          : `Expected Aug ${arrival.day}`,
    };
    if (refundTotal > 0) payout.note = `After ${usd(refundTotal)} refund`;
    chronological.push(payout);
  }

  // UI lists payouts most-recent first.
  return { payouts: chronological.reverse(), settled };
}

const derivedPayouts = derivePayouts();
export const payouts: Payout[] = derivedPayouts.payouts;

export const PAYOUTS_PAID_TOTAL = round2(
  payouts.filter((p) => p.status === "paid").reduce((s, p) => s + p.amount, 0),
);
export const PAYOUTS_IN_TRANSIT_TOTAL = round2(
  payouts.filter((p) => p.status === "in_transit").reduce((s, p) => s + p.amount, 0),
);
export const PAYOUTS_JULY_TOTAL = round2(
  payouts.reduce((s, p) => s + p.amount, 0),
);
// Earned but not yet paid out: the net proceeds of every charge that no
// initiated July payout settled, less any refunds not already debited to one
// of those payouts. Derived from the unsettled ledger, not NET − payouts.
const unsettledCharges = charges.filter((_, idx) => !derivedPayouts.settled[idx]);
export const AVAILABLE_SOON = round2(
  unsettledCharges.reduce((s, c) => s + netOfFee(c), 0) -
    refunds
      .filter((r) => !INITIATED_PAYOUT_DAYS.has(r.debitedToPayoutDay))
      .reduce((s, r) => s + r.amount, 0),
);
export const PAYOUTS_7D_TOTAL = round2(
  payouts.filter((p) => p.day >= 25).reduce((s, p) => s + p.amount, 0),
);

// Balances card figures.
export const AVAILABLE_NOW = 0; // all cleared funds paid out on schedule
export const IN_TRANSIT_TO_BANK = PAYOUTS_IN_TRANSIT_TOTAL;
export const AVAILABLE_SOON_BALANCE = AVAILABLE_SOON;

// --- recent transactions (mirror the last ledger charges) ------------------

export interface Payment {
  name: string;
  initials: string;
  description: string;
  amount: number;
  brand: string;
  card: string;
  date: string;
  /** July day this row maps to in the ledger. */
  chargeDay: number;
}

export const recentPayments: Payment[] = [
  { name: "Ironclad Roofing LLC", initials: "IR", description: "Starter", amount: 995, brand: "Visa", card: "4242", date: "Jul 31, 11:26 PM", chargeDay: 31 },
  { name: "BlueRock Builders", initials: "BB", description: "One Project Estimate", amount: 599, brand: "Mastercard", card: "5544", date: "Jul 30, 9:58 PM", chargeDay: 30 },
  { name: "Summit Ridge Remodeling", initials: "SR", description: "Growth", amount: 1995, brand: "Visa", card: "8899", date: "Jul 30, 4:17 PM", chargeDay: 30 },
  { name: "Mendez Concrete Co.", initials: "MC", description: "One Project Estimate", amount: 599, brand: "Amex", card: "1005", date: "Jul 29, 6:33 PM", chargeDay: 29 },
  { name: "TrueLine Electric", initials: "TE", description: "Estimating Department", amount: 2995, brand: "Visa", card: "6621", date: "Jul 28, 10:41 AM", chargeDay: 28 },
  { name: "Pacific Coast Drywall", initials: "PC", description: "One Project Estimate", amount: 599, brand: "Mastercard", card: "3410", date: "Jul 27, 8:05 PM", chargeDay: 27 },
  { name: "Hernandez Bros Roofing", initials: "HB", description: "Starter", amount: 995, brand: "Visa", card: "9023", date: "Jul 27, 3:52 PM", chargeDay: 27 },
  { name: "Copperfield Construction", initials: "CC", description: "Growth", amount: 1995, brand: "Mastercard", card: "7781", date: "Jul 27, 9:14 AM", chargeDay: 27 },
];
