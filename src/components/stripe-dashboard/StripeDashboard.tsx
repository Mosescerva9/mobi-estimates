"use client";

import { useCallback, useEffect, useState } from "react";
import "./stripe-demo.css";
import { tokens } from "./tokens";
import SafariFrame from "./SafariFrame";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import OverviewSection from "./OverviewSection";
import BalancesCard from "./BalancesCard";
import PayoutsCard from "./PayoutsCard";
import RecentPaymentsCard from "./RecentPaymentsCard";
import type { RangeKey } from "./data";

type SidebarMode = "auto" | "open" | "collapsed";

// Combined height of the fixed Safari chrome + demo banner (status + tab row
// + toolbar + banner). The sidebar pins to this scroll viewport.
const CHROME_H =
  tokens.chrome.status + tokens.chrome.tabRow + tokens.chrome.toolbar + tokens.chrome.banner;

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
    <SafariFrame>
      <div className="flex min-h-full" style={{ background: tokens.color.bg }}>
        <div
          className="sticky top-0 z-20 shrink-0"
          style={{ height: `calc(100dvh - ${CHROME_H}px)` }}
        >
          <Sidebar mode={sidebarMode} />
        </div>

        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onToggleSidebar={toggleSidebar} />
          <main className="relative z-10 mx-auto w-full max-w-[1080px] space-y-4 px-5 py-5">
            <OverviewSection range={range} onRangeChange={setRange} />
            <BalancesCard />
            <PayoutsCard range={range} />
            <RecentPaymentsCard />

            <footer
              className="pb-2 pt-4 text-center text-[12px]"
              style={{ color: tokens.color.faint }}
            >
              Visual demonstration only. No connection to Stripe or live financial data.
            </footer>
          </main>
        </div>
      </div>
    </SafariFrame>
  );
}
