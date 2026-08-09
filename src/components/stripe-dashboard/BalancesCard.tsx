import { Landmark } from "lucide-react";
import { tokens } from "./tokens";
import { Card, InertButton } from "./ui";
import {
  usd,
  AVAILABLE_NOW,
  IN_TRANSIT_TO_BANK,
  AVAILABLE_SOON_BALANCE,
  BANK_NAME,
  BANK_LAST4,
} from "./data";

function BalanceItem({
  label,
  value,
  sub,
}: {
  label: string;
  value: number;
  sub?: string;
}) {
  return (
    <div className="px-4 py-3.5" style={{ borderColor: tokens.color.borderSoft }}>
      <div className="text-[12px] font-medium" style={{ color: tokens.color.muted }}>
        {label}
      </div>
      <div className="sd-nums mt-1 text-[20px] font-semibold" style={{ color: tokens.color.ink }}>
        {usd(value)}
      </div>
      {sub && (
        <div className="mt-0.5 text-[12px]" style={{ color: tokens.color.faint }}>
          {sub}
        </div>
      )}
    </div>
  );
}

export default function BalancesCard() {
  return (
    <Card>
      <div
        className="flex items-center justify-between border-b px-4 py-3"
        style={{ borderColor: tokens.color.border }}
      >
        <div className="flex items-center gap-2">
          <span className="text-[15px] font-semibold" style={{ color: tokens.color.ink }}>
            Balance
          </span>
          <span className="flex items-center gap-1 text-[12px]" style={{ color: tokens.color.muted }}>
            <Landmark size={13} />
            {BANK_NAME} ••••{BANK_LAST4}
          </span>
        </div>
        <InertButton
          label="Manage payouts"
          className="rounded-lg px-2.5 py-1 text-[13px] font-medium"
          style={{ border: `1px solid ${tokens.color.border}`, color: tokens.color.text }}
        >
          Manage payouts
        </InertButton>
      </div>
      <div
        className="sd-card-grid grid divide-y sm:divide-x sm:divide-y-0"
        style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))" }}
      >
        <BalanceItem label="Available now" value={AVAILABLE_NOW} sub="Ready to pay out" />
        <BalanceItem
          label="In transit to bank"
          value={IN_TRANSIT_TO_BANK}
          sub={`To ${BANK_NAME} ••••${BANK_LAST4}`}
        />
        <BalanceItem label="Available soon" value={AVAILABLE_SOON_BALANCE} sub="Funds still settling" />
      </div>
    </Card>
  );
}
