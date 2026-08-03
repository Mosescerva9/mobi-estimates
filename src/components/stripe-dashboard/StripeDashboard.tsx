"use client";

import { useCallback, useEffect, useState } from "react";
import "./stripe-demo.css";
import { tokens } from "./tokens";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import OverviewSection from "./OverviewSection";
import BalancesCard from "./BalancesCard";
import PayoutsCard from "./PayoutsCard";
import RecentPaymentsCard from "./RecentPaymentsCard";
import type { RangeKey } from "./data";

type SidebarMode = "auto" | "open" | "collapsed";

export default function StripeDashboard() {
  const [range, setRange] = useState<RangeKey>("month");
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>("auto");

  // Hydration-safe: never read window during render. Honour ?range=7d after mount.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("range") === "7d") {
      setRange("7d");
    }
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarMode((prev) => {
      if (prev === "auto") {
        const narrow =
          typeof window !== "undefined" &&
          window.matchMedia("(max-width: 1099px)").matches;
        return narrow ? "open" : "collapsed";
      }
      return prev === "collapsed" ? "open" : "collapsed";
    });
  }, []);

  return (
    <div
      className="sd-root flex h-[100dvh] overflow-hidden"
      style={{ background: tokens.color.bg }}
    >
      <div className="sticky top-0 z-20 h-[100dvh] shrink-0">
        <Sidebar mode={sidebarMode} />
      </div>

      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto overflow-x-hidden">
        <TopBar onToggleSidebar={toggleSidebar} />
        <main className="relative z-10 mx-auto w-full max-w-[1080px] space-y-4 px-5 py-5">
          <OverviewSection range={range} onRangeChange={setRange} />
          <BalancesCard />
          <PayoutsCard range={range} />
          <RecentPaymentsCard />

          <footer
            role="note"
            className="pb-2 pt-4 text-center text-[13px] font-semibold"
            style={{ color: tokens.color.dangerText }}
          >
            for Demo purposes only
          </footer>
        </main>
      </div>
    </div>
  );
}
