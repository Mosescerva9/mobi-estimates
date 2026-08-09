import { tokens } from "./tokens";
import { Card, InertButton, StatusPill, Avatar } from "./ui";
import { recentPayments, usd } from "./data";

const th = "px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-wide";
const td = "px-4 py-2.5 align-middle";

export default function RecentPaymentsCard() {
  return (
    <Card>
      <div
        className="flex items-center justify-between border-b px-4 py-3"
        style={{ borderColor: tokens.color.border }}
      >
        <div className="text-[15px] font-semibold" style={{ color: tokens.color.ink }}>
          Recent transactions
        </div>
        <InertButton
          label="View all transactions"
          className="rounded-lg px-2.5 py-1 text-[13px] font-medium"
          style={{ color: tokens.color.purpleDark }}
        >
          View all
        </InertButton>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse" style={{ minWidth: 620 }}>
          <thead>
            <tr style={{ color: tokens.color.faint }}>
              <th className={th}>Amount</th>
              <th className={th}>Customer</th>
              <th className={th}>Description</th>
              <th className={th}>Payment method</th>
              <th className={th}>Date</th>
            </tr>
          </thead>
          <tbody>
            {recentPayments.map((p, i) => (
              <tr
                key={i}
                className="border-t"
                style={{ borderColor: tokens.color.borderSoft }}
              >
                <td className={td}>
                  <span className="sd-nums text-[13px] font-semibold" style={{ color: tokens.color.ink }}>
                    {usd(p.amount)}
                  </span>{" "}
                  <StatusPill tone="success">Succeeded</StatusPill>
                </td>
                <td className={td}>
                  <span className="flex items-center gap-2">
                    <Avatar initials={p.initials} />
                    <span className="text-[13px] font-medium" style={{ color: tokens.color.ink }}>
                      {p.name}
                    </span>
                  </span>
                </td>
                <td className={`${td} text-[13px]`} style={{ color: tokens.color.text }}>
                  {p.description}
                </td>
                <td className={`${td} sd-nums text-[13px]`} style={{ color: tokens.color.muted }}>
                  {p.brand} ••••{p.card}
                </td>
                <td className={`${td} sd-nums text-[13px]`} style={{ color: tokens.color.muted }}>
                  {p.date}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
