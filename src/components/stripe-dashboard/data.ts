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
// Reconciles to:
//   gross $48,995.00 · fees $1,431.75 · refunds $1,594.00 · net $45,969.25
//   36 successful payments · avg order $1,360.97 · MRR $39,890 (22 subs)
//   16 new customers · 20 payouts totalling $42,485.24
// ---------------------------------------------------------------------------

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

// The ledger. Day = July 2026 day-of-month.
export const charges: Charge[] = [
  { day: 1, amount: 1995, plan: "growth" },
  { day: 1, amount: 599, plan: "ope", isNew: true },
  { day: 2, amount: 2995, plan: "ed" },
  { day: 2, amount: 995, plan: "starter", isNew: true },
  { day: 3, amount: 1995, plan: "growth" },
  { day: 4, amount: 599, plan: "ope", isNew: true },
  { day: 6, amount: 995, plan: "starter" },
  { day: 7, amount: 599, plan: "ope", isNew: true },
  { day: 8, amount: 1995, plan: "growth", isNew: true },
  { day: 9, amount: 2995, plan: "ed" },
  { day: 10, amount: 1995, plan: "growth" },
  { day: 10, amount: 599, plan: "ope", isNew: true },
  { day: 11, amount: 995, plan: "starter", isNew: true },
  { day: 13, amount: 599, plan: "ope", isNew: true },
  { day: 14, amount: 995, plan: "starter" },
  { day: 15, amount: 1995, plan: "growth" },
  { day: 15, amount: 1032.9, plan: "proration", note: "Starter → ED upgrade" },
  { day: 16, amount: 2995, plan: "ed" },
  { day: 16, amount: 599, plan: "ope", isNew: true },
  { day: 17, amount: 995, plan: "starter", isNew: true },
  { day: 18, amount: 599, plan: "ope", isNew: true },
  { day: 20, amount: 995, plan: "starter" },
  { day: 21, amount: 1995, plan: "growth" },
  { day: 22, amount: 599, plan: "ope", isNew: true },
  { day: 23, amount: 2995, plan: "ed" },
  { day: 24, amount: 884.1, plan: "proration", note: "Growth → ED upgrade" },
  { day: 25, amount: 995, plan: "starter" },
  { day: 25, amount: 599, plan: "ope", isNew: true },
  { day: 27, amount: 1995, plan: "growth" },
  { day: 27, amount: 995, plan: "starter" },
  { day: 27, amount: 599, plan: "ope", isNew: true },
  { day: 28, amount: 2995, plan: "ed" },
  { day: 29, amount: 599, plan: "ope", isNew: true },
  { day: 30, amount: 1995, plan: "growth" },
  { day: 30, amount: 599, plan: "ope", isNew: true },
  { day: 31, amount: 995, plan: "starter" },
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
    net: 47401,
    prevNet: 39968.3,
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
    net: 12366,
    prevNet: 7072.1,
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
