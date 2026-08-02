import { ArrowRight, Landmark } from "lucide-react";
import {
  payouts,
  BANK_NAME,
  BANK_LAST4,
  PAYOUTS_JULY_TOTAL,
  PAYOUTS_7D_TOTAL,
  usd,
  type PayoutStatus,
  type RangeKey,
} from "./data";

const StatusPill = ({ status }: { status: PayoutStatus }) =>
  status === "paid" ? (
    <span className="inline-flex items-center rounded-full bg-[#d3f8df] px-2 py-[2px] text-[12px] font-semibold text-[#0e6245]">
      Paid
    </span>
  ) : (
    <span className="inline-flex items-center rounded-full bg-[#dde9ff] px-2 py-[2px] text-[12px] font-semibold text-[#0b4f9e]">
      In transit
    </span>
  );

const PayoutsCard = ({ range }: { range: RangeKey }) => {
  const rows = range === "month" ? payouts : payouts.filter((p) => p.day >= 25);
  const summary =
    range === "month"
      ? `20 payouts initiated in July · ${usd(PAYOUTS_JULY_TOTAL)} total`
      : `5 payouts initiated Jul 25 – 31 · ${usd(PAYOUTS_7D_TOTAL)} total`;

  return (
    <section className="rounded-lg border border-[#e6ebf1] bg-white shadow-[0_1px_1px_rgba(0,0,0,0.03)]">
      <div className="flex items-center justify-between px-5 pb-1 pt-4">
        <div>
          <h2 className="text-[16px] font-semibold text-[#0a2540]">Payouts</h2>
          <p className="mt-0.5 text-[12px] text-[#8792a2]">{summary}</p>
        </div>
        <button className="flex items-center gap-1 text-[13px] font-medium text-[#635bff] hover:text-[#5147ff]">
          View all payouts
          <ArrowRight className="h-3.5 w-3.5" strokeWidth={2.4} />
        </button>
      </div>

      <div className="overflow-x-auto px-2 pb-2">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-[#e6ebf1] text-[11px] font-semibold uppercase tracking-[0.06em] text-[#8792a2]">
              <th className="px-3 py-2.5 font-semibold">Payout</th>
              <th className="px-3 py-2.5 font-semibold">Status</th>
              <th className="px-3 py-2.5 font-semibold">Destination</th>
              <th className="px-3 py-2.5 font-semibold">Initiated</th>
              <th className="px-3 py-2.5 text-right font-semibold">Arrival</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr
                key={`${p.initiated}-${p.amount}`}
                className="border-b border-[#eef2f6] text-[14px] last:border-0 hover:bg-[#f6f9fc]"
              >
                <td className="px-3 py-[10px]">
                  <span className="font-semibold text-[#0a2540]">{usd(p.amount)}</span>
                  {p.note && (
                    <span className="block text-[11px] leading-4 text-[#8792a2]">{p.note}</span>
                  )}
                </td>
                <td className="px-3 py-[10px]">
                  <StatusPill status={p.status} />
                </td>
                <td className="px-3 py-[10px] text-[#425466]">
                  <span className="flex items-center gap-2">
                    <Landmark className="h-4 w-4 text-[#8792a2]" />
                    {BANK_NAME} ••••{BANK_LAST4}
                  </span>
                </td>
                <td className="px-3 py-[10px] text-[#425466]">{p.initiated}</td>
                <td
                  className={`px-3 py-[10px] text-right ${
                    p.status === "in_transit" ? "font-medium text-[#0b4f9e]" : "text-[#425466]"
                  }`}
                >
                  {p.arrival}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
};

export default PayoutsCard;
