// Mock data for the Mobi Estimates Stripe dashboard mockup.
// Every figure below is derived from a single transaction ledger of Mobi Estimates'
// real pricing and is internally consistent:
//
//   July charges (36):  Estimating Department $2,995 x5, Growth $1,995 x8,
//                       Starter $995 x9, One Project Estimate $599 x12,
//                       prorated upgrades $1,032.90 + $884.10
//   Gross volume            $48,995.00
//   - Stripe fees           $1,431.75   (2.9% + $0.30 per charge)
//   - Refunds               $1,594.00   ($599 estimate + $995 Starter)
//   = Net                   $45,969.25
//   = Payouts paid $38,996.07 + in transit $3,489.17 + available soon $3,484.01

export const BUSINESS_NAME = "Mobi Estimates";
export const BANK_NAME = "Chase Bank";
export const BANK_LAST4 = "6789";

export type RangeKey = "month" | "7d";

export const usd = (n: number): string =>
  n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

export const pctDelta = (current: number, previous: number): string =>
  `${(((current - previous) / previous) * 100).toFixed(1)}%`;

// Daily gross volume and new-customer counts, Jul 1-31 2026.
// Sums: gross $48,995.00, new customers 16.
const dailyGross = [
  2594, 3990, 1995, 599, 0, 995, 599, 1995, 2995, 2594, 995, 0, 599, 995,
  3027.9, 3594, 995, 599, 0, 995, 1995, 599, 2995, 884.1, 1594, 0, 3589, 2995,
  599, 2594, 995,
];
const dailyNewCustomers = [
  1, 1, 0, 1, 0, 0, 1, 1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 0, 1, 0, 0, 1, 0,
  1, 0, 1, 1, 0,
];

export interface DayPoint {
  day: string;
  gross: number;
  customers: number;
}

const allDays: DayPoint[] = dailyGross.map((gross, i) => ({
  day: `Jul ${i + 1}`,
  gross,
  customers: dailyNewCustomers[i],
}));

export interface RangeData {
  label: string;
  shortLabel: string;
  gross: number;
  prevGross: number;
  newCustomers: number;
  prevNewCustomers: number;
  freeEstimates: number;
  prevFreeEstimates: number;
  days: DayPoint[];
}

export const ranges: Record<RangeKey, RangeData> = {
  month: {
    label: "Jul 1 – Jul 31, 2026",
    shortLabel: "Jul 1 – Jul 31",
    gross: 48995,
    prevGross: 41206.3, // June 2026
    newCustomers: 16,
    prevNewCustomers: 13,
    freeEstimates: 23,
    prevFreeEstimates: 19,
    days: allDays,
  },
  "7d": {
    label: "Jul 25 – Jul 31, 2026",
    shortLabel: "Jul 25 – Jul 31",
    gross: 12366,
    prevGross: 8067.1, // Jul 18 – Jul 24
    newCustomers: 4,
    prevNewCustomers: 2,
    freeEstimates: 6,
    prevFreeEstimates: 5,
    days: allDays.slice(24),
  },
};

export type PayoutStatus = "paid" | "in_transit";

export interface Payout {
  day: number;
  amount: number;
  status: PayoutStatus;
  initiated: string;
  arrival: string;
  note?: string;
}

// 2-business-day rolling payouts, July 2026 (none on the Jul 3 bank holiday).
// Each payout = charges settled that cycle minus per-charge Stripe fees;
// the Jul 20 and Jul 27 payouts are reduced by refunds of $599.00 and $995.00.
export const payouts: Payout[] = [
  { day: 31, amount: 581.33, status: "in_transit", initiated: "Jul 31, 2026", arrival: "Expected Aug 4" },
  { day: 30, amount: 2907.84, status: "in_transit", initiated: "Jul 30, 2026", arrival: "Expected Aug 3" },
  { day: 29, amount: 5031.18, status: "paid", initiated: "Jul 29, 2026", arrival: "Jul 31, 2026" },
  { day: 28, amount: 858.16, status: "paid", initiated: "Jul 28, 2026", arrival: "Jul 30, 2026" },
  { day: 27, amount: 1912.84, status: "paid", initiated: "Jul 27, 2026", arrival: "Jul 29, 2026", note: "After $995.00 refund" },
  { day: 24, amount: 581.33, status: "paid", initiated: "Jul 24, 2026", arrival: "Jul 28, 2026" },
  { day: 23, amount: 1936.84, status: "paid", initiated: "Jul 23, 2026", arrival: "Jul 27, 2026" },
  { day: 22, amount: 1547.17, status: "paid", initiated: "Jul 22, 2026", arrival: "Jul 24, 2026" },
  { day: 21, amount: 965.84, status: "paid", initiated: "Jul 21, 2026", arrival: "Jul 23, 2026" },
  { day: 20, amount: 2890.17, status: "paid", initiated: "Jul 20, 2026", arrival: "Jul 22, 2026", note: "After $599.00 refund" },
  { day: 17, amount: 2939.49, status: "paid", initiated: "Jul 17, 2026", arrival: "Jul 21, 2026" },
  { day: 16, amount: 965.84, status: "paid", initiated: "Jul 16, 2026", arrival: "Jul 20, 2026" },
  { day: 15, amount: 1547.17, status: "paid", initiated: "Jul 15, 2026", arrival: "Jul 17, 2026" },
  { day: 14, amount: 2518.17, status: "paid", initiated: "Jul 14, 2026", arrival: "Jul 16, 2026" },
  { day: 13, amount: 2907.84, status: "paid", initiated: "Jul 13, 2026", arrival: "Jul 15, 2026" },
  { day: 10, amount: 1936.84, status: "paid", initiated: "Jul 10, 2026", arrival: "Jul 14, 2026" },
  { day: 9, amount: 581.33, status: "paid", initiated: "Jul 9, 2026", arrival: "Jul 13, 2026" },
  { day: 8, amount: 3484.01, status: "paid", initiated: "Jul 8, 2026", arrival: "Jul 10, 2026" },
  { day: 7, amount: 3873.68, status: "paid", initiated: "Jul 7, 2026", arrival: "Jul 9, 2026" },
  { day: 6, amount: 2518.17, status: "paid", initiated: "Jul 6, 2026", arrival: "Jul 8, 2026" },
];

export const FEES_TOTAL = 1431.75;
export const REFUNDS_TOTAL = 1594;
export const NET_TOTAL = 45969.25;
export const PAYOUTS_PAID_TOTAL = 38996.07;
export const PAYOUTS_IN_TRANSIT_TOTAL = 3489.17;
export const AVAILABLE_SOON = 3484.01;
export const PAYOUTS_JULY_TOTAL = 42485.24; // 20 payouts initiated Jul 6-31
export const PAYOUTS_7D_TOTAL = 11291.35; // 5 payouts initiated Jul 27-31

export interface Payment {
  name: string;
  email: string;
  description: string;
  amount: number;
  card: string;
  brand: string;
  date: string;
}

// The eight most recent charges in the ledger (Jul 27-31).
export const recentPayments: Payment[] = [
  { name: "Ironclad Roofing LLC", email: "office@ironcladroofing.com", description: "Starter plan — monthly", amount: 995, brand: "Visa", card: "4242", date: "Jul 31, 11:26 PM" },
  { name: "BlueRock Builders", email: "estimating@bluerockbuilders.com", description: "One Project Estimate", amount: 599, brand: "Mastercard", card: "5544", date: "Jul 30, 9:58 PM" },
  { name: "Summit Ridge Remodeling", email: "jeremy@summitridgeremodel.com", description: "Growth plan — monthly", amount: 1995, brand: "Visa", card: "8899", date: "Jul 30, 4:17 PM" },
  { name: "Mendez Concrete Co.", email: "ramon@mendezconcrete.com", description: "One Project Estimate", amount: 599, brand: "Amex", card: "1005", date: "Jul 29, 6:33 PM" },
  { name: "TrueLine Electric", email: "bids@truelineelectric.com", description: "Estimating Department — monthly", amount: 2995, brand: "Visa", card: "6621", date: "Jul 28, 10:41 AM" },
  { name: "Pacific Coast Drywall", email: "mike@pacificcoastdrywall.com", description: "One Project Estimate", amount: 599, brand: "Mastercard", card: "3410", date: "Jul 27, 8:05 PM" },
  { name: "Hernandez Bros Roofing", email: "luis@hernandezbrosroofing.com", description: "Starter plan — monthly", amount: 995, brand: "Visa", card: "9023", date: "Jul 27, 3:52 PM" },
  { name: "Copperfield Construction", email: "dawn@copperfieldconstruction.com", description: "Growth plan — monthly", amount: 1995, brand: "Mastercard", card: "7781", date: "Jul 27, 9:14 AM" },
];
