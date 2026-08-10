import { ArrowRight } from "lucide-react";
import { recentPayments, usd } from "./data";

const avatarColors = [
  "bg-[#635bff]",
  "bg-[#0e6245]",
  "bg-[#c84801]",
  "bg-[#0b4f9e]",
  "bg-[#9f3a38]",
  "bg-[#5b5bd6]",
  "bg-[#00736b]",
  "bg-[#b53d8f]",
];

const initials = (name: string) =>
  name
    .replace(/[^a-zA-Z ]/g, "")
    .split(" ")
    .filter(Boolean)
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

const RecentPaymentsCard = () => (
  <section className="rounded-lg border border-[#e6ebf1] bg-white shadow-[0_1px_1px_rgba(0,0,0,0.03)]">
    <div className="flex items-center justify-between px-5 pb-1 pt-4">
      <div>
        <h2 className="text-[16px] font-semibold text-[#0a2540]">Recent payments</h2>
        <p className="mt-0.5 text-[12px] text-[#8792a2]">
          Latest charges across estimates and subscription plans
        </p>
      </div>
      <button className="flex items-center gap-1 text-[13px] font-medium text-[#635bff] hover:text-[#5147ff]">
        View all
        <ArrowRight className="h-3.5 w-3.5" strokeWidth={2.4} />
      </button>
    </div>

    <div className="overflow-x-auto px-2 pb-2">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-[#e6ebf1] text-[11px] font-semibold uppercase tracking-[0.06em] text-[#8792a2]">
            <th className="px-3 py-2.5 font-semibold">Customer</th>
            <th className="px-3 py-2.5 font-semibold">Description</th>
            <th className="px-3 py-2.5 font-semibold">Amount</th>
            <th className="px-3 py-2.5 font-semibold">Status</th>
            <th className="px-3 py-2.5 font-semibold">Payment method</th>
            <th className="px-3 py-2.5 text-right font-semibold">Date</th>
          </tr>
        </thead>
        <tbody>
          {recentPayments.map((p, i) => (
            <tr
              key={p.email}
              className="border-b border-[#eef2f6] text-[14px] last:border-0 hover:bg-[#f6f9fc]"
            >
              <td className="px-3 py-[10px]">
                <span className="flex items-center gap-2.5">
                  <span
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white ${avatarColors[i % avatarColors.length]}`}
                  >
                    {initials(p.name)}
                  </span>
                  <span>
                    <span className="block font-medium leading-5 text-[#0a2540]">
                      {p.name}
                    </span>
                    <span className="block text-[12px] leading-4 text-[#8792a2]">
                      {p.email}
                    </span>
                  </span>
                </span>
              </td>
              <td className="px-3 py-[10px] text-[#425466]">{p.description}</td>
              <td className="px-3 py-[10px] font-semibold text-[#0a2540]">{usd(p.amount)}</td>
              <td className="px-3 py-[10px]">
                <span className="inline-flex items-center rounded-full bg-[#d3f8df] px-2 py-[2px] text-[12px] font-semibold text-[#0e6245]">
                  Succeeded
                </span>
              </td>
              <td className="px-3 py-[10px] text-[#425466]">
                {p.brand} ••••{p.card}
              </td>
              <td className="px-3 py-[10px] text-right text-[#425466]">{p.date}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </section>
);

export default RecentPaymentsCard;
