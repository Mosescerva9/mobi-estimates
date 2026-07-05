"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { btnClass, fieldClass, labelClass } from "@/components/AuthShell";
import { finalizeClaim } from "@/app/checkout/complete/actions";

const COMPANY_TYPES: { value: string; label: string }[] = [
  { value: "general_contractor", label: "General contractor" },
  { value: "subcontractor", label: "Subcontractor" },
  { value: "developer", label: "Developer" },
  { value: "owner", label: "Owner / builder" },
  { value: "supplier", label: "Supplier" },
  { value: "other", label: "Other" },
];

const PROJECT_TYPES: { value: string; label: string }[] = [
  { value: "residential", label: "Residential" },
  { value: "commercial", label: "Commercial" },
  { value: "industrial", label: "Industrial" },
  { value: "civil", label: "Civil" },
  { value: "infrastructure", label: "Infrastructure" },
  { value: "mixed", label: "Mixed-use" },
];

export function OnboardingForm({
  defaultContactName,
  defaultEmail,
  selectedPlan,
}: {
  defaultContactName: string;
  defaultEmail: string;
  selectedPlan?: string | null;
}) {
  const router = useRouter();
  const [legalName, setLegalName] = useState("");
  const [companyType, setCompanyType] = useState("");
  const [website, setWebsite] = useState("");
  const [contactName, setContactName] = useState(defaultContactName);
  const [contactPhone, setContactPhone] = useState("");
  const [serviceArea, setServiceArea] = useState("");
  const [trades, setTrades] = useState("");
  const [projectTypes, setProjectTypes] = useState<string[]>([]);
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function toggleType(value: string) {
    setProjectTypes((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value],
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!legalName.trim()) {
      setError("Please enter your company name.");
      return;
    }
    if (!agreed) {
      setError("Please accept the terms to continue.");
      return;
    }

    setLoading(true);
    const supabase = createClient();
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
      setLoading(false);
      setError("Your session expired. Please sign in again.");
      return;
    }

    // 1) Create the company.
    const { data: company, error: companyErr } = await supabase
      .from("companies")
      .insert({
        legal_name: legalName.trim(),
        website: website.trim() || null,
        company_type: companyType || null,
        created_by: user.id,
      })
      .select("id")
      .single();

    if (companyErr || !company) {
      setLoading(false);
      setError(companyErr?.message ?? "Could not create your company. Please try again.");
      return;
    }

    // 2) Link the user as the primary member (this is what RLS uses to grant
    //    access to all company-scoped data going forward).
    const { error: memberErr } = await supabase.from("company_members").insert({
      company_id: company.id,
      user_id: user.id,
      role: "client",
      is_primary: true,
    });

    if (memberErr) {
      setLoading(false);
      setError(memberErr.message);
      return;
    }

    // 3) Save company profile preferences (best-effort — membership above is the
    //    critical part; we don't block onboarding if these secondary writes fail).
    await supabase.from("company_preferences").upsert(
      {
        company_id: company.id,
        profile: {
          primary_contact: { name: contactName.trim(), phone: contactPhone.trim() },
          service_areas: serviceArea.trim(),
          trades: trades.trim(),
          project_types: projectTypes,
        },
      },
      { onConflict: "company_id" },
    );
    await supabase.from("onboarding_progress").insert({
      company_id: company.id,
      step: "company_profile",
      completed: true,
    });
    if (contactPhone.trim()) {
      await supabase.from("profiles").update({ phone: contactPhone.trim() }).eq("id", user.id);
    }

    // Pay-first checkout: if this user already paid before creating an account,
    // activate the real entitlement now that a company finally exists. If a
    // transient activation problem happens after the company/member rows are
    // created, send them to billing success, which retries the same finalization
    // server-side instead of stranding them on an onboarding page they no longer
    // need.
    try {
      const { claimed } = await finalizeClaim(company.id);
      if (claimed) {
        router.push("/billing/success");
        router.refresh();
        return;
      }
    } catch (claimErr) {
      console.error("Failed to finalize paid checkout claim after onboarding:", claimErr);
      router.push("/billing/success");
      router.refresh();
      return;
    }

    // Otherwise: resume checkout for a plan chosen before onboarding, or the portal.
    router.push(selectedPlan ? `/start?plan=${selectedPlan}` : "/portal");
    router.refresh();
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-10">
      <div className="mx-auto w-full max-w-2xl">
        <div className="mb-6 text-center">
          <span className="inline-block text-2xl font-extrabold tracking-tight text-navy">
            MOBI <span className="font-semibold text-brand">Estimates</span>
          </span>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <h1 className="text-xl font-bold text-navy">Set up your company</h1>
          <p className="mt-1 text-sm text-slate-500">
            A few details so we can route your projects correctly. You can refine
            these later in account settings.
          </p>

          <form onSubmit={onSubmit} className="mt-6 space-y-5">
            <div>
              <label htmlFor="legalName" className={labelClass}>
                Company name <span className="text-brand">*</span>
              </label>
              <input
                id="legalName"
                type="text"
                required
                className={fieldClass}
                value={legalName}
                onChange={(e) => setLegalName(e.target.value)}
              />
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor="companyType" className={labelClass}>Company type</label>
                <select
                  id="companyType"
                  className={fieldClass}
                  value={companyType}
                  onChange={(e) => setCompanyType(e.target.value)}
                >
                  <option value="">Select…</option>
                  {COMPANY_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="website" className={labelClass}>Website (optional)</label>
                <input
                  id="website"
                  type="text"
                  placeholder="example.com"
                  className={fieldClass}
                  value={website}
                  onChange={(e) => setWebsite(e.target.value)}
                />
              </div>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor="contactName" className={labelClass}>Primary contact</label>
                <input
                  id="contactName"
                  type="text"
                  autoComplete="name"
                  className={fieldClass}
                  value={contactName}
                  onChange={(e) => setContactName(e.target.value)}
                />
              </div>
              <div>
                <label htmlFor="contactPhone" className={labelClass}>Contact phone</label>
                <input
                  id="contactPhone"
                  type="tel"
                  autoComplete="tel"
                  className={fieldClass}
                  value={contactPhone}
                  onChange={(e) => setContactPhone(e.target.value)}
                />
              </div>
            </div>

            <div>
              <label htmlFor="serviceArea" className={labelClass}>
                Service area <span className="font-normal text-slate-400">(states / regions you work in)</span>
              </label>
              <input
                id="serviceArea"
                type="text"
                placeholder="e.g. Texas, Oklahoma, nationwide"
                className={fieldClass}
                value={serviceArea}
                onChange={(e) => setServiceArea(e.target.value)}
              />
            </div>

            <div>
              <label htmlFor="trades" className={labelClass}>
                Trades / scopes you typically bid <span className="font-normal text-slate-400">(comma-separated)</span>
              </label>
              <input
                id="trades"
                type="text"
                placeholder="e.g. concrete, framing, electrical"
                className={fieldClass}
                value={trades}
                onChange={(e) => setTrades(e.target.value)}
              />
            </div>

            <div>
              <span className={labelClass}>Typical project types</span>
              <div className="mt-1 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {PROJECT_TYPES.map((t) => {
                  const active = projectTypes.includes(t.value);
                  return (
                    <button
                      type="button"
                      key={t.value}
                      onClick={() => toggleType(t.value)}
                      aria-pressed={active}
                      className={
                        "rounded-lg border px-3 py-2 text-sm font-medium transition " +
                        (active
                          ? "border-brand bg-brand/10 text-brand"
                          : "border-slate-300 text-slate-600 hover:border-slate-400")
                      }
                    >
                      {t.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <label className="flex items-start gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                className="mt-1"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
              />
              <span>
                I agree to Mobi Estimates&rsquo; Terms of Service and Estimating
                Service Agreement.{" "}
                {/* TODO: link to finalized, attorney-reviewed legal pages (Legal milestone). */}
                <span className="text-slate-400">(Terms pages coming soon.)</span>
              </span>
            </label>

            {error && <p className="text-sm text-red-600">{error}</p>}

            <button type="submit" className={btnClass} disabled={loading}>
              {loading ? "Setting up…" : "Continue to portal"}
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-xs text-slate-400">
          Signed in as {defaultEmail}
        </p>
      </div>
    </main>
  );
}
