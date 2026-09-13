import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ArrowDownRight,
  ArrowUpRight,
  Calendar,
  ClipboardList,
  Info,
} from "lucide-react";
import { ranges, pctDelta, usd, type RangeKey } from "./data";

interface ChartTooltipProps {
  active?: boolean;
  label?: string;
  payload?: Array<{ value: number; dataKey: string }>;
  format: (v: number) => string;
}

const ChartTooltip = ({ active, label, payload, format }: ChartTooltipProps) => {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-md bg-[#0a2540] px-3 py-2 shadow-lg">
      <div className="text-[12px] font-semibold text-white">
        {format(payload[0].value)}
      </div>
      <div className="text-[11px] text-[#adbdcc]">{label}, 2026</div>
    </div>
  );
};

interface RangeTabsProps {
  range: RangeKey;
  onRangeChange: (r: RangeKey) => void;
}

const RangeTabs = ({ range, onRangeChange }: RangeTabsProps) => {
  const tab = (key: RangeKey, label: string) => (
    <button
      key={key}
      onClick={() => onRangeChange(key)}
      className={`rounded-[5px] px-3 py-[5px] text-[13px] font-medium transition-colors ${
        range === key
          ? "bg-white font-semibold text-[#0a2540] shadow-sm"
          : "text-[#425466] hover:text-[#0a2540]"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div className="flex items-center gap-3">
      <div className="flex rounded-md border border-[#e6ebf1] bg-[#f6f9fc] p-[3px]">
        {tab("7d", "Last 7 days")}
        {tab("month", "Custom")}
      </div>
      <button className="flex items-center gap-2 rounded-md border border-[#e6ebf1] bg-white px-3 py-[7px] text-[13px] font-medium text-[#3c4257] shadow-sm">
        <Calendar className="h-4 w-4 text-[#697386]" />
        {ranges[range].label}
      </button>
    </div>
  );
};

const Delta = ({ pct, abs }: { pct: string; abs: string }) => {
  const negative = pct.startsWith("-");
  const Icon = negative ? ArrowDownRight : ArrowUpRight;
  return (
    <div className="flex items-center gap-1.5">
      <span
        className={`flex items-center gap-0.5 rounded-full px-2 py-[2px] text-[12px] font-semibold ${
          negative ? "bg-[#fbe3e8] text-[#a42538]" : "bg-[#d3f8df] text-[#0e6245]"
        }`}
      >
        <Icon className="h-3 w-3" strokeWidth={2.6} />
        {pct}
      </span>
      <span className="text-[12px] text-[#8792a2]">{abs} vs. previous period</span>
    </div>
  );
};

const CardHeader = ({ title }: { title: string }) => (
  <div className="flex items-center gap-1.5">
    <span className="text-[14px] font-medium text-[#425466]">{title}</span>
    <Info className="h-3.5 w-3.5 text-[#adbdcc]" />
  </div>
);

const axisStyle = {
  fontSize: 11,
  fill: "#8792a2",
  tickLine: false,
  axisLine: false,
} as const;

interface OverviewSectionProps {
  range: RangeKey;
  onRangeChange: (r: RangeKey) => void;
}

const OverviewSection = ({ range, onRangeChange }: OverviewSectionProps) => {
  const data = ranges[range];
  const xTicks =
    range === "month"
      ? ["Jul 1", "Jul 8", "Jul 15", "Jul 22", "Jul 29"]
      : data.days.map((d) => d.day);

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-[20px] font-bold text-[#0a2540]">Your overview</h1>
        <RangeTabs range={range} onRangeChange={onRangeChange} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-lg border border-[#e6ebf1] bg-white p-5 shadow-[0_1px_1px_rgba(0,0,0,0.03)] lg:col-span-2">
          <div className="flex items-start justify-between">
            <div>
              <CardHeader title="Gross volume" />
              <div className="mt-1 text-[28px] font-semibold leading-9 text-[#0a2540]">
                {usd(data.gross)}
              </div>
              <div className="mt-1">
                <Delta
                  pct={pctDelta(data.gross, data.prevGross)}
                  abs={`+${usd(data.gross - data.prevGross)}`}
                />
              </div>
            </div>
            <span className="rounded-md bg-[#f6f9fc] px-2.5 py-1 text-[12px] font-medium text-[#425466]">
              {data.shortLabel}
            </span>
          </div>
          <div className="mt-4 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.days} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="grossFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#635bff" stopOpacity={0.22} />
                    <stop offset="100%" stopColor="#635bff" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#e6ebf1" strokeDasharray="4 4" />
                <XAxis
                  dataKey="day"
                  ticks={xTicks}
                  tick={axisStyle}
                  tickLine={false}
                  axisLine={false}
                  dy={6}
                />
                <YAxis hide domain={[0, "dataMax + 600"]} />
                <Tooltip
                  content={<ChartTooltip format={(v) => usd(v)} />}
                  cursor={{ stroke: "#adbdcc", strokeDasharray: "3 3" }}
                />
                <Area
                  type="monotone"
                  dataKey="gross"
                  stroke="#635bff"
                  strokeWidth={2}
                  fill="url(#grossFill)"
                  activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="flex-1 rounded-lg border border-[#e6ebf1] bg-white p-5 shadow-[0_1px_1px_rgba(0,0,0,0.03)]">
            <CardHeader title="New customers" />
            <div className="mt-1 text-[28px] font-semibold leading-9 text-[#0a2540]">
              {data.newCustomers}
            </div>
            <div className="mt-1">
              <Delta
                pct={pctDelta(data.newCustomers, data.prevNewCustomers)}
                abs={`+${data.newCustomers - data.prevNewCustomers}`}
              />
            </div>
            <div className="mt-3 h-[104px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.days} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#e6ebf1" strokeDasharray="4 4" />
                  <XAxis
                    dataKey="day"
                    ticks={xTicks}
                    tick={axisStyle}
                    tickLine={false}
                    axisLine={false}
                    dy={6}
                  />
                  <YAxis hide domain={[0, "dataMax + 1"]} />
                  <Tooltip
                    content={<ChartTooltip format={(v) => `${v} customers`} />}
                    cursor={{ fill: "rgba(99,91,255,0.06)" }}
                  />
                  <Bar dataKey="customers" fill="#635bff" radius={[2, 2, 0, 0]} maxBarSize={14} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-lg border border-[#e6ebf1] bg-white p-5 shadow-[0_1px_1px_rgba(0,0,0,0.03)]">
            <div className="flex items-center justify-between">
              <div>
                <CardHeader title="Free qualifying estimates" />
                <div className="mt-1 text-[28px] font-semibold leading-9 text-[#0a2540]">
                  {data.freeEstimates}
                </div>
                <div className="mt-1">
                  <Delta
                    pct={pctDelta(data.freeEstimates, data.prevFreeEstimates)}
                    abs={`+${data.freeEstimates - data.prevFreeEstimates}`}
                  />
                </div>
              </div>
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f0efff]">
                <ClipboardList className="h-5 w-5 text-[#635bff]" />
              </span>
            </div>
            <p className="mt-2 text-[12px] leading-4 text-[#8792a2]">
              First estimate is free — {data.freeEstimates} new leads started an
              estimate {range === "month" ? "in July" : "in the last 7 days"}.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default OverviewSection;
