"use client";

import { ArrowUpRight, ArrowDownRight, CalendarDays } from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { tokens } from "./tokens";
import { Card } from "./ui";
import {
  ranges,
  usd,
  usd0,
  pctDelta,
  pctDeltaLabel,
  MRR,
  NET_TOTAL,
  type RangeKey,
  type DayPoint,
} from "./data";

function Delta({ current, previous }: { current: number; previous: number }) {
  const up = pctDelta(current, previous) >= 0;
  return (
    <span
      className="inline-flex items-center gap-0.5 text-[12px] font-semibold"
      style={{ color: up ? tokens.color.successText : tokens.color.dangerText }}
    >
      {up ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
      <span className="sd-nums">{pctDeltaLabel(current, previous)}</span>
    </span>
  );
}

interface TipProps {
  active?: boolean;
  payload?: { payload: DayPoint }[];
  formatter: (d: DayPoint) => string;
}
function ChartTooltip({ active, payload, formatter }: TipProps) {
  if (!active || !payload || !payload.length) return null;
  const point = payload[0].payload;
  return (
    <div
      className="rounded-md px-2.5 py-1.5 text-[12px] text-white shadow-lg"
      style={{ background: tokens.chart.tooltipBg }}
    >
      <div className="font-medium opacity-70">{point.day}, 2026</div>
      <div className="sd-nums font-semibold">{formatter(point)}</div>
    </div>
  );
}

const axisTick = { fontSize: 11, fill: tokens.color.faint };

function RangeTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="rounded-md px-2.5 py-1 text-[13px] font-medium transition-colors"
      style={
        active
          ? { background: tokens.color.white, color: tokens.color.ink, boxShadow: tokens.shadow.card }
          : { color: tokens.color.muted }
      }
    >
      {label}
    </button>
  );
}

export default function OverviewSection({
  range,
  onRangeChange,
}: {
  range: RangeKey;
  onRangeChange: (r: RangeKey) => void;
}) {
  const data = ranges[range];

  return (
    <div className="space-y-4">
      {/* Header + range controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[20px] font-semibold" style={{ color: tokens.color.ink }}>
          Your overview
        </h1>
        <div className="flex items-center gap-2">
          <div
            className="flex items-center gap-0.5 rounded-lg p-0.5"
            style={{ background: tokens.color.bg, border: `1px solid ${tokens.color.border}` }}
          >
            <RangeTab label="Last 7 days" active={range === "7d"} onClick={() => onRangeChange("7d")} />
            <RangeTab label="Custom" active={range === "month"} onClick={() => onRangeChange("month")} />
          </div>
          <div
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium"
            style={{ border: `1px solid ${tokens.color.border}`, color: tokens.color.text }}
          >
            <CalendarDays size={14} className="text-[#8792a2]" />
            <span className="sd-nums whitespace-nowrap">{data.shortLabel}</span>
          </div>
        </div>
      </div>

      {/* Chart cards */}
      <div className="sd-card-grid grid gap-4" style={{ gridTemplateColumns: "3fr 2fr" }}>
        {/* Gross volume area chart */}
        <Card className="p-4">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[13px] font-medium" style={{ color: tokens.color.muted }}>
              Gross volume
            </span>
            <Delta current={data.gross} previous={data.prevGross} />
          </div>
          <div className="sd-nums text-[24px] font-semibold" style={{ color: tokens.color.ink }}>
            {usd(data.gross)}
          </div>
          <div className="mt-3 h-[180px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.days} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="sdGross" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={tokens.chart.line} stopOpacity={tokens.chart.areaTop} />
                    <stop offset="100%" stopColor={tokens.chart.line} stopOpacity={tokens.chart.areaBottom} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke={tokens.chart.grid} />
                <XAxis
                  dataKey="day"
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  interval={data.tickInterval}
                  minTickGap={0}
                />
                <YAxis
                  width={44}
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => usd0(v)}
                />
                <Tooltip
                  cursor={{ stroke: tokens.color.border }}
                  content={<ChartTooltip formatter={(d) => usd(d.gross)} />}
                />
                <Area
                  type="monotone"
                  dataKey="gross"
                  stroke={tokens.chart.line}
                  strokeWidth={tokens.chart.lineWidth}
                  fill="url(#sdGross)"
                  isAnimationActive={false}
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* New customers bar chart */}
        <Card className="p-4">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[13px] font-medium" style={{ color: tokens.color.muted }}>
              New customers
            </span>
            <Delta current={data.newCustomers} previous={data.prevNewCustomers} />
          </div>
          <div className="sd-nums text-[24px] font-semibold" style={{ color: tokens.color.ink }}>
            {data.newCustomers}
          </div>
          <div className="mt-3 h-[180px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.days} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
                <CartesianGrid vertical={false} stroke={tokens.chart.grid} />
                <XAxis
                  dataKey="day"
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  interval={data.tickInterval}
                  minTickGap={0}
                />
                <YAxis width={28} tick={axisTick} tickLine={false} axisLine={false} allowDecimals={false} />
                <Tooltip
                  cursor={{ fill: "rgba(99,91,255,0.06)" }}
                  content={
                    <ChartTooltip
                      formatter={(d) => `${d.customers} new customer${d.customers === 1 ? "" : "s"}`}
                    />
                  }
                />
                <Bar
                  dataKey="customers"
                  fill={tokens.chart.line}
                  radius={[2, 2, 0, 0]}
                  isAnimationActive={false}
                  maxBarSize={18}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {/* Stat strip */}
      <Card>
        <div
          className="sd-card-grid grid divide-y sm:divide-x sm:divide-y-0"
          style={{ gridTemplateColumns: "repeat(3, minmax(0,1fr))" }}
        >
          <Stat
            label="Net volume"
            value={usd(range === "month" ? NET_TOTAL : data.net)}
            sub={`${data.successful} payments`}
          />
          <Stat
            label="Successful payments"
            value={String(data.successful)}
            sub={<Delta current={data.successful} previous={data.prevSuccessful} />}
          />
          <Stat label="Monthly recurring revenue" value={usd(MRR)} sub="22 active subscriptions" />
        </div>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: React.ReactNode;
}) {
  return (
    <div className="px-4 py-3.5" style={{ borderColor: tokens.color.borderSoft }}>
      <div className="text-[12px] font-medium" style={{ color: tokens.color.muted }}>
        {label}
      </div>
      <div className="sd-nums mt-1 text-[20px] font-semibold" style={{ color: tokens.color.ink }}>
        {value}
      </div>
      <div className="mt-0.5 text-[12px]" style={{ color: tokens.color.faint }}>
        {sub}
      </div>
    </div>
  );
}
