import {
  Home,
  Wallet,
  ArrowLeftRight,
  Users,
  Package,
  CreditCard,
  TrendingUp,
  Share2,
  MoreHorizontal,
  Code2,
  Settings,
  ChevronsUpDown,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { tokens } from "./tokens";
import { BUSINESS_NAME } from "./data";

type SidebarMode = "auto" | "open" | "collapsed";

function NavRow({
  icon: Icon,
  label,
  active = false,
}: {
  icon: LucideIcon;
  label: string;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      aria-disabled={active ? undefined : "true"}
      aria-current={active ? "page" : undefined}
      onClick={(e) => e.preventDefault()}
      title={active ? undefined : `${label} — unavailable in this demonstration`}
      className="sd-inert flex w-full items-center gap-3 rounded-md px-2.5 py-[7px] text-[14px] font-medium"
      style={
        active
          ? { background: tokens.color.purpleSoft, color: tokens.color.purpleDark }
          : { color: tokens.color.text }
      }
    >
      <Icon size={16} strokeWidth={1.9} className="shrink-0" />
      <span className="sd-nav-label truncate">{label}</span>
    </button>
  );
}

export default function Sidebar({ mode }: { mode: SidebarMode }) {
  const modeClass =
    mode === "open" ? "sd-open" : mode === "collapsed" ? "sd-collapsed" : "sd-auto";

  return (
    <aside
      className={`sd-sidebar flex h-full flex-col border-r bg-white ${modeClass}`}
      style={{ borderColor: tokens.color.border }}
    >
      {/* Wordmark */}
      <div className="flex h-14 items-center px-4">
        <span
          className="sd-wordmark-full text-[19px] font-bold lowercase tracking-tight"
          style={{ color: tokens.color.purple }}
        >
          stripe
        </span>
        <span
          className="sd-wordmark-mini text-[19px] font-bold lowercase"
          style={{ color: tokens.color.purple }}
        >
          s
        </span>
      </div>

      {/* Account switcher */}
      <button
        type="button"
        aria-disabled="true"
        onClick={(e) => e.preventDefault()}
        title="Switch account — unavailable in this demonstration"
        className="sd-inert sd-account-switcher mx-2 mb-2 flex items-center gap-2 rounded-lg px-2.5 py-2 hover:bg-[#f6f9fc]"
      >
        <span
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[11px] font-bold text-white"
          style={{ background: tokens.color.ink }}
        >
          M
        </span>
        <span className="sd-account-meta flex min-w-0 flex-1 items-center gap-1.5">
          <span
            className="sd-sidebar-hideable min-w-0 truncate text-[13px] font-semibold"
            style={{ color: tokens.color.ink }}
          >
            {BUSINESS_NAME}
          </span>
          {/* Safety pill: must survive screenshots and never be hidden
              responsively. Kept outside .sd-sidebar-hideable so the 64px rail
              still shows it (stacked under the avatar via .sd-account-switcher). */}
          <span
            className="sd-demo-pill shrink-0 rounded-full px-1.5 py-[1px] text-[10px] font-semibold uppercase tracking-wide"
            style={{ background: tokens.color.infoBg, color: tokens.color.infoText }}
          >
            Demo
          </span>
          <span className="sd-sidebar-hideable flex shrink-0 items-center gap-1.5">
            <span
              className="h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: "#24b47e" }}
              title="Live mode"
            />
            <ChevronsUpDown size={14} className="shrink-0 text-[#8792a2]" />
          </span>
        </span>
      </button>

      {/* Primary nav */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-1">
        <NavRow icon={Home} label="Home" active />
        <NavRow icon={Wallet} label="Balances" />
        <NavRow icon={ArrowLeftRight} label="Transactions" />
        <NavRow icon={Users} label="Customers" />
        <NavRow icon={Package} label="Product catalog" />

        <div
          className="sd-sidebar-hideable px-2.5 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: tokens.color.faint }}
        >
          Products
        </div>
        <NavRow icon={CreditCard} label="Billing" />
        <NavRow icon={TrendingUp} label="Revenue" />
        <NavRow icon={Share2} label="Connect" />
        <NavRow icon={MoreHorizontal} label="More" />
      </nav>

      {/* Footer nav */}
      <div
        className="space-y-0.5 border-t px-2 py-2"
        style={{ borderColor: tokens.color.borderSoft }}
      >
        <NavRow icon={Code2} label="Developers" />
        <NavRow icon={Settings} label="Settings" />
        <div className="flex items-center justify-between px-2.5 py-[7px]">
          <span
            className="sd-nav-label text-[14px] font-medium"
            style={{ color: tokens.color.text }}
          >
            Test mode
          </span>
          <span
            role="switch"
            aria-checked="false"
            aria-label="Test mode off"
            className="relative inline-flex h-[18px] w-[32px] shrink-0 items-center rounded-full"
            style={{ background: "#c3c8d0" }}
          >
            <span className="absolute left-[2px] h-[14px] w-[14px] rounded-full bg-white shadow-sm" />
          </span>
        </div>
      </div>
    </aside>
  );
}
