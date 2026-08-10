import { Info, MoreHorizontal } from "lucide-react";
import {
  PAYOUTS_IN_TRANSIT_TOTAL,
  AVAILABLE_SOON,
  usd,
} from "./data";

interface BalanceStat {
  label: string;
  amount: string;
  hint: string;
}

const stats: BalanceStat[] = [
  { label: "Available now", amount: usd(0), hint: "No funds ready" },
  {
    label: "In transit to bank",
    amount: usd(PAYOUTS_IN_TRANSIT_TOTAL),
    hint: "Expected Aug 3 – 4",
  },
  {
    label: "Available soon",
    amount: usd(AVAILABLE_SOON),
    hint: "Within 2 business days",
  },
];

const BalancesCard = () => (
  <section className="rounded-lg border border-[#e6ebf1] bg-white shadow-[0_1px_1px_rgba(0,0,0,0.03)]">
    <div className="flex items-center justify-between border-b border-[#e6ebf1] px-5 py-4">
      <h2 className="text-[16px] font-semibold text-[#0a2540]">Balances</h2>
      <div className="flex items-center gap-2">
        <button className="rounded-md bg-[#635bff] px-3 py-[7px] text-[13px] font-medium text-white shadow-sm hover:bg-[#5147ff]">
          Manage payouts
        </button>
        <button className="rounded-md p-1.5 text-[#697386] hover:bg-[#f6f9fc]">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
    </div>
    <div className="grid grid-cols-1 divide-y divide-[#e6ebf1] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
      {stats.map((s) => (
        <div key={s.label} className="px-5 py-4">
          <div className="flex items-center gap-1.5">
            <span className="text-[13px] font-medium text-[#425466]">{s.label}</span>
            <Info className="h-3.5 w-3.5 text-[#adbdcc]" />
          </div>
          <div className="mt-1 text-[22px] font-semibold text-[#0a2540]">{s.amount}</div>
          <div className="mt-0.5 text-[12px] text-[#8792a2]">{s.hint}</div>
        </div>
      ))}
    </div>
  </section>
);

export default BalancesCard;
