"use client";

import { useEffect, useState } from "react";
import Sidebar from "@/components/stripe-dashboard/Sidebar";
import TopBar from "@/components/stripe-dashboard/TopBar";
import OverviewSection from "@/components/stripe-dashboard/OverviewSection";
import BalancesCard from "@/components/stripe-dashboard/BalancesCard";
import PayoutsCard from "@/components/stripe-dashboard/PayoutsCard";
import RecentPaymentsCard from "@/components/stripe-dashboard/RecentPaymentsCard";
import { type RangeKey } from "@/components/stripe-dashboard/data";

const initialRange = (): RangeKey => {
  if (typeof window === "undefined") return "month";
  return new URLSearchParams(window.location.search).get("range") === "7d"
    ? "7d"
    : "month";
};

// Mockup route only — mock data, not real Mobi Estimates earnings.
export default function StripeDashboardPage() {
  const [range, setRange] = useState<RangeKey>(initialRange);

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "Home | Stripe Dashboard";
    return () => {
      document.title = previousTitle;
    };
  }, []);

  return (
    <div
      className="flex min-h-screen bg-[#f6f9fc] antialiased"
      style={{
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Ubuntu, sans-serif',
      }}
    >
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="mx-auto w-full max-w-[1080px] flex-1 space-y-4 px-6 py-6">
          <OverviewSection range={range} onRangeChange={setRange} />
          <BalancesCard />
          <PayoutsCard range={range} />
          <RecentPaymentsCard />
        </main>
      </div>
    </div>
  );
}
