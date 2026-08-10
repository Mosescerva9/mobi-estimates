import { Search, Plus, Bell, HelpCircle, ChevronDown } from "lucide-react";

const TopBar = () => (
  <header className="sticky top-0 z-10 flex h-[60px] items-center gap-4 border-b border-[#e6ebf1] bg-white px-6">
    <div className="flex max-w-[420px] flex-1 items-center gap-2 rounded-md border border-[#e6ebf1] bg-[#f6f9fc] px-3 py-[7px] text-[#8792a2]">
      <Search className="h-4 w-4" />
      <input
        className="w-full bg-transparent text-[14px] text-[#0a2540] outline-none placeholder:text-[#8792a2]"
        placeholder="Search"
      />
      <kbd className="rounded border border-[#e6ebf1] bg-white px-1.5 text-[11px] text-[#697386]">
        ⌘K
      </kbd>
    </div>

    <div className="ml-auto flex items-center gap-1.5">
      <button className="flex items-center gap-1.5 rounded-md border border-[#e6ebf1] bg-white px-3 py-[7px] text-[14px] font-medium text-[#3c4257] shadow-sm hover:bg-[#f6f9fc]">
        <Plus className="h-4 w-4 text-[#635bff]" strokeWidth={2.4} />
        Create
        <ChevronDown className="h-3.5 w-3.5 text-[#8792a2]" />
      </button>
      <button className="relative rounded-md p-2 text-[#697386] hover:bg-[#f6f9fc]">
        <Bell className="h-[18px] w-[18px]" />
        <span className="absolute right-[7px] top-[7px] h-2 w-2 rounded-full border border-white bg-[#ed5f74]" />
      </button>
      <button className="rounded-md p-2 text-[#697386] hover:bg-[#f6f9fc]">
        <HelpCircle className="h-[18px] w-[18px]" />
      </button>
      <button className="ml-1 flex h-8 w-8 items-center justify-center rounded-full bg-[#0a2540] text-[12px] font-semibold text-white">
        A
      </button>
    </div>
  </header>
);

export default TopBar;
