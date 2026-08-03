import { tokens } from "./tokens";
import { Card, InertButton, StatusPill } from "./ui";
import {
  payouts,
  usd,
  BANK_NAME,
  BANK_LAST4,
  PAYOUTS_JULY_TOTAL,
  PAYOUTS_7D_TOTAL,
  type RangeKey,
} from "./data";

const th =
  "px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-wide";
const td = "px-4 py-2.5 align-middle";

export default function PayoutsCard({ range }: { range: RangeKey }) {
  const rows = range === "7d" ? payouts.filter((p) => p.day >= 25) : payouts;
  const total = range === "7d" ? PAYOUTS_7D_TOTAL : PAYOUTS_JULY_TOTAL;

  return (
    <Card>
      <div
        className="flex items-center justify-between border-b px-4 py-3"
        style={{ borderColor: tokens.color.border }}
      >
        <div>
          <div className="text-[15px] font-semibold" style={{ color: tokens.color.ink }}>
            Payouts
          </div>
          <div className="sd-nums mt-0.5 text-[12px]" style={{ color: tokens.color.muted }}>
            {rows.length} payouts · {usd(total)}
          </div>
        </div>
        <InertButton
          label="View all payouts"
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
              <th className={th}>Status</th>
              <th className={th}>Bank account</th>
              <th className={th}>Initiated</th>
              <th className={th}>Arrival</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr
                key={p.day}
                className="border-t"
                style={{ borderColor: tokens.color.borderSoft }}
              >
                <td className={td}>
                  <span
                    className="sd-nums text-[13px] font-semibold"
                    style={{ color: tokens.color.ink }}
                  >
                    {usd(p.amount)}
                  </span>
                  {p.note && (
                    <span className="ml-2 text-[11px]" style={{ color: tokens.color.faint }}>
                      {p.note}
                    </span>
                  )}
                </td>
                <td className={td}>
                  {p.status === "paid" ? (
                    <StatusPill tone="success">Paid</StatusPill>
                  ) : (
                    <StatusPill tone="info">In transit</StatusPill>
                  )}
                </td>
                <td className={`${td} text-[13px]`} style={{ color: tokens.color.text }}>
                  {BANK_NAME} ••••{BANK_LAST4}
                </td>
                <td className={`${td} sd-nums text-[13px]`} style={{ color: tokens.color.muted }}>
                  {p.initiated}
                </td>
                <td className={`${td} sd-nums text-[13px]`} style={{ color: tokens.color.muted }}>
                  {p.arrival}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
