import type { Metadata } from "next";
import { DfyIntakeForm } from "./DfyIntakeForm";

export const metadata: Metadata = {
  title: "Setup intake — Estimator Business Setup",
  robots: { index: false, follow: false },
};

/**
 * Token-gated intake form. The token alone proves nothing — the POST endpoint
 * re-validates that the order exists, is paid, and has not already submitted
 * intake before anything is stored.
 */
export default async function DfyIntakePage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12">
      <div className="mx-auto w-full max-w-2xl">
        <h1 className="text-2xl font-bold text-slate-900">Estimator Business Setup — intake</h1>
        <p className="mt-2 text-slate-600">
          Your answers drive what we prepare before your onboarding call. Nothing here is
          shared publicly.
        </p>
        {token ? (
          <DfyIntakeForm token={token} />
        ) : (
          <p className="mt-8 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            This intake link is missing its token. Use the exact link from your
            post-purchase email, or contact support to have it re-sent.
          </p>
        )}
      </div>
    </main>
  );
}
