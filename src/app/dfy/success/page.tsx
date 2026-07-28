import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Payment received — Estimator Business Setup",
  robots: { index: false, follow: false },
};

export default function DfySuccessPage() {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-16">
      <div className="mx-auto w-full max-w-xl text-center">
        <h1 className="text-2xl font-bold text-slate-900">Payment received</h1>
        <p className="mt-4 text-slate-600">
          Thanks — your Estimator Business Setup is confirmed. Check your email for a
          link to your intake form; your answers there drive what we prepare for your
          onboarding call.
        </p>
        <p className="mt-3 text-sm text-slate-500">
          The email can take a minute to arrive. If it doesn&apos;t show up, check spam,
          then contact support and we&apos;ll re-send your intake link.
        </p>
        <Link href="/dfy" className="mt-8 inline-block text-sm font-medium text-blue-800 hover:underline">
          Back to the setup overview
        </Link>
      </div>
    </main>
  );
}
