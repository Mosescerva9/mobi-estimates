import { PanelLeft, Search, Plus, Bell, HelpCircle } from "lucide-react";
import { tokens } from "./tokens";
import { InertButton } from "./ui";

/**
 * The Stripe app's own header (sticky, 56px) — visually distinct from the
 * Safari chrome above it. The sidebar toggle is a real interaction; everything
 * else is inert in the demonstration.
 */
export default function TopBar({
  onToggleSidebar,
}: {
  onToggleSidebar: () => void;
}) {
  return (
    <header
      className="sticky top-0 z-30 flex items-center gap-3 border-b bg-white/95 px-4 backdrop-blur"
      style={{ height: tokens.chrome.header, borderColor: tokens.color.border }}
    >
      <button
        type="button"
        onClick={onToggleSidebar}
        aria-label="Toggle navigation"
        className="flex h-8 w-8 items-center justify-center rounded-md text-[#3c4257] hover:bg-[#f6f9fc]"
      >
        <PanelLeft size={18} />
      </button>

      {/* Search pill (⌘K) — inert */}
      <InertButton
        label="Search"
        className="flex h-8 max-w-[280px] flex-1 items-center gap-2 rounded-lg px-3 text-left"
        style={{ background: tokens.color.bg, border: `1px solid ${tokens.color.border}` }}
      >
        <Search size={15} className="text-[#8792a2]" />
        <span className="flex-1 text-[13px] text-[#8792a2]">Search</span>
        <kbd
          className="rounded border px-1 text-[11px] font-medium text-[#8792a2]"
          style={{ borderColor: tokens.color.border }}
        >
          ⌘K
        </kbd>
      </InertButton>

      <div className="flex-1" />

      <InertButton
        label="Create"
        className="flex h-8 items-center gap-1.5 rounded-lg px-3 text-[13px] font-semibold text-white"
        style={{ background: tokens.color.purple }}
      >
        <Plus size={15} />
        <span>Create</span>
      </InertButton>

      <InertButton
        label="Notifications"
        className="flex h-8 w-8 items-center justify-center rounded-md text-[#3c4257] hover:bg-[#f6f9fc]"
      >
        <Bell size={17} />
      </InertButton>
      <InertButton
        label="Help"
        className="flex h-8 w-8 items-center justify-center rounded-md text-[#3c4257] hover:bg-[#f6f9fc]"
      >
        <HelpCircle size={17} />
      </InertButton>
      <span
        className="flex h-7 w-7 items-center justify-center rounded-full text-[12px] font-semibold text-white"
        style={{ background: tokens.color.ink }}
        aria-label="Account avatar"
      >
        M
      </span>
    </header>
  );
}
