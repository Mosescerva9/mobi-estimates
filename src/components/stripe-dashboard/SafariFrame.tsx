import type { ReactNode } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Upload,
  Lock,
  RotateCw,
  Download,
  Plus,
  PanelLeft,
  Copy,
  Wifi,
  BatteryFull,
  X,
} from "lucide-react";
import { tokens } from "./tokens";

const hairline = "0.5px solid rgba(60,60,67,0.12)";

/**
 * A realistic light-appearance iPadOS Safari window that fills the viewport
 * like a screenshot. All browser controls are decorative and aria-hidden; the
 * address field is a div (never editable, focusable, or navigating). The Safari
 * chrome and the DEMO banner stay fixed while `children` scroll beneath them.
 */
export default function SafariFrame({ children }: { children: ReactNode }) {
  return (
    <div
      className="sd-root flex h-[100dvh] flex-col overflow-hidden"
      style={{
        background:
          "linear-gradient(180deg, #eef1f6 0%, #e6eaf1 100%)",
      }}
    >
      {/* Status bar */}
      <div
        aria-hidden="true"
        className="sd-chrome flex shrink-0 items-center justify-between text-[13px] font-semibold text-[#1c1c1e]"
        style={{
          height: tokens.chrome.status,
          paddingTop: "env(safe-area-inset-top, 0px)",
          paddingLeft: "calc(env(safe-area-inset-left, 0px) + 22px)",
          paddingRight: "calc(env(safe-area-inset-right, 0px) + 22px)",
        }}
      >
        <span className="sd-nums tracking-tight">9:41</span>
        <span className="flex items-center gap-1.5">
          <Wifi size={15} strokeWidth={2.2} />
          <span className="sd-nums text-[12px]">100%</span>
          <BatteryFull size={22} strokeWidth={1.6} />
        </span>
      </div>

      {/* Tab row */}
      <div
        aria-hidden="true"
        className="sd-chrome flex shrink-0 items-center gap-2 px-3"
        style={{ height: tokens.chrome.tabRow, borderBottom: hairline }}
      >
        <button
          type="button"
          tabIndex={-1}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[#3c4257]/70"
        >
          <PanelLeft size={17} />
        </button>

        {/* Active tab */}
        <div
          className="flex h-[28px] min-w-[180px] max-w-[280px] flex-1 items-center gap-2 rounded-[10px] bg-white px-2.5 shadow-[0_1px_2px_rgba(0,0,0,0.08)]"
          style={{ border: hairline }}
        >
          <span
            className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] text-[10px] font-bold text-white"
            style={{ background: tokens.color.purple }}
          >
            S
          </span>
          <span className="flex-1 truncate text-[12px] font-medium text-[#1c1c1e]">
            Home – Stripe
          </span>
          <span className="flex h-4 w-4 items-center justify-center rounded-full text-[#697386] hover:bg-black/5">
            <X size={12} />
          </span>
        </div>

        <button
          type="button"
          tabIndex={-1}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[#3c4257]/70"
        >
          <Plus size={17} />
        </button>
        <button
          type="button"
          tabIndex={-1}
          className="flex h-7 w-7 items-center justify-center rounded-md text-[#3c4257]/70"
        >
          <Copy size={16} />
        </button>
      </div>

      {/* Nav toolbar */}
      <div
        aria-hidden="true"
        className="sd-chrome flex shrink-0 items-center gap-2 px-3"
        style={{ height: tokens.chrome.toolbar, borderBottom: hairline }}
      >
        <div className="flex items-center gap-0.5 text-[#3c4257]">
          <button
            type="button"
            tabIndex={-1}
            className="flex h-8 w-8 items-center justify-center rounded-md text-[#8792a2]"
          >
            <ChevronLeft size={20} />
          </button>
          <button
            type="button"
            tabIndex={-1}
            className="flex h-8 w-8 items-center justify-center rounded-md text-[#c3c8d0]"
          >
            <ChevronRight size={20} />
          </button>
        </div>
        <button
          type="button"
          tabIndex={-1}
          className="flex h-8 w-8 items-center justify-center rounded-md text-[#3c4257]/80"
        >
          <Upload size={18} />
        </button>

        {/* Centered decorative address pill — a div, never an input. */}
        <div className="flex flex-1 justify-center">
          <div
            className="flex h-8 w-full max-w-[520px] items-center justify-center gap-2 rounded-lg px-3 text-[13px] text-[#3c4257]"
            style={{ background: "rgba(118,118,128,0.12)" }}
          >
            <span className="text-[13px] font-medium text-[#697386]">
              a<span className="text-[16px]">A</span>
            </span>
            <Lock size={12} className="text-[#697386]" />
            <span className="font-medium text-[#1c1c1e]">
              dashboard.stripe.com
            </span>
            <RotateCw size={13} className="text-[#697386]" />
          </div>
        </div>

        <button
          type="button"
          tabIndex={-1}
          className="flex h-8 w-8 items-center justify-center rounded-md text-[#3c4257]/80"
        >
          <Download size={18} />
        </button>
      </div>

      {/* DEMO safety banner — fixed, cannot be dismissed. */}
      <div
        role="note"
        className="flex shrink-0 items-center justify-center gap-2 px-3 text-center text-[11px] font-semibold uppercase tracking-wide"
        style={{
          height: tokens.chrome.banner,
          background: tokens.color.warningBg,
          color: tokens.color.warningText,
          borderBottom: `1px solid ${tokens.color.border}`,
        }}
      >
        DEMO — SAMPLE DATA — NOT A LIVE STRIPE ACCOUNT
      </div>

      {/* Scroll region: content scrolls; watermark stays fixed above it. */}
      <div className="relative min-h-0 flex-1">
        <div className="absolute inset-0 overflow-y-auto overflow-x-hidden">
          {children}
        </div>
        <div
          aria-hidden="true"
          className="sd-watermark pointer-events-none absolute inset-0 z-40"
        />
      </div>
    </div>
  );
}
