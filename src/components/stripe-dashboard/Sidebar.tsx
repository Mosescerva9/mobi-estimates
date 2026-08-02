import {
  Home,
  CreditCard,
  Receipt,
  Network,
  Wallet,
  Nfc,
  ShieldAlert,
  TrendingUp,
  PieChart,
  LayoutGrid,
  ChevronDown,
  Code2,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { BUSINESS_NAME } from "./data";

interface NavItem {
  label: string;
  icon: LucideIcon;
  active?: boolean;
  hasChevron?: boolean;
}

const mainNav: NavItem[] = [
  { label: "Home", icon: Home, active: true },
  { label: "Payments", icon: CreditCard },
  { label: "Billing", icon: Receipt },
  { label: "Connect", icon: Network },
  { label: "Issuing", icon: Wallet },
  { label: "Terminal", icon: Nfc },
  { label: "Fraud & risk", icon: ShieldAlert },
  { label: "Revenue", icon: TrendingUp },
  { label: "Reporting", icon: PieChart },
];

const bottomNav: NavItem[] = [
  { label: "Developers", icon: Code2 },
  { label: "Settings", icon: Settings },
];

const NavRow = ({ item }: { item: NavItem }) => (
  <button
    className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[14px] font-medium transition-colors ${
      item.active
        ? "bg-[#f0efff] text-[#635bff]"
        : "text-[#3c4257] hover:bg-[#f6f9fc]"
    }`}
  >
    <item.icon
      className={`h-4 w-4 ${item.active ? "text-[#635bff]" : "text-[#697386]"}`}
      strokeWidth={item.active ? 2.2 : 1.8}
    />
    <span className="flex-1 text-left">{item.label}</span>
    {item.hasChevron && <ChevronDown className="h-3.5 w-3.5 text-[#8792a2]" />}
  </button>
);

const Sidebar = () => (
  <aside className="flex h-screen w-[240px] shrink-0 flex-col border-r border-[#e6ebf1] bg-white">
    <div className="px-4 pb-2 pt-4">
      <div className="text-[22px] font-bold leading-none tracking-[-0.5px] text-[#635bff]">
        stripe
      </div>
    </div>

    <div className="px-2 pb-2">
      <button className="flex w-full items-center gap-2.5 rounded-md px-2 py-2 hover:bg-[#f6f9fc]">
        <span className="flex h-6 w-6 items-center justify-center rounded bg-gradient-to-br from-[#635bff] to-[#0a2540] text-[10px] font-bold text-white">
          ME
        </span>
        <span className="flex-1 truncate text-left text-[14px] font-semibold text-[#0a2540]">
          {BUSINESS_NAME}
        </span>
        <span className="h-1.5 w-1.5 rounded-full bg-[#0abf53]" title="Live mode" />
        <ChevronDown className="h-3.5 w-3.5 text-[#8792a2]" />
      </button>
    </div>

    <nav className="flex-1 space-y-[1px] overflow-y-auto px-2">
      {mainNav.map((item) => (
        <NavRow key={item.label} item={item} />
      ))}
      <NavRow item={{ label: "More", icon: LayoutGrid }} />
    </nav>

    <div className="space-y-[1px] border-t border-[#e6ebf1] px-2 py-2">
      {bottomNav.map((item) => (
        <NavRow key={item.label} item={item} />
      ))}
      <div className="flex items-center justify-between rounded-md px-2.5 py-[7px]">
        <span className="text-[14px] font-medium text-[#3c4257]">Test mode</span>
        <span className="flex h-[18px] w-8 items-center rounded-full bg-[#e3e8ee] px-[2px]">
          <span className="h-[14px] w-[14px] rounded-full bg-white shadow" />
        </span>
      </div>
    </div>
  </aside>
);

export default Sidebar;
