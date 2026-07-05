import Link from "next/link";
import type { Metadata } from "next";
import {
  MonthlyPlanCard,
  PayPerProjectCard,
  PricingFAQ,
  PricingHeader,
  PromoBanner,
  monthlyOffers,
  payPerProjectOffer,
} from "@/components/PricingCards";
import { OFFERS } from "@/lib/pricing";

export const metadata: Metadata = {
  title: "Pricing — Mobi Estimates",
  description:
    "Mobi Estimates pricing: three monthly construction-estimating plans (Starter, Growth, Estimating Department) or a one-time $599 Pay Per Project estimate. New monthly subscribers get 50% off the first month.",
  alternates: { canonical: "/pricing" },
  robots: { index: true, follow: true },
  openGraph: {
    title: "Pricing — Mobi Estimates",
    description:
      "Three monthly estimating plans or a one-time $599 Pay Per Project estimate. 50% off your first month on any monthly plan.",
    type: "website",
  },
};

/** Truthful structured data — prices match the page and Stripe checkout exactly. */
function pricingJsonLd() {
  const offers = OFFERS.map((offer) => ({
    "@type": "Offer",
    name: offer.name,
    priceCurrency: "USD",
    price: (offer.regularAmountCents / 100).toFixed(2),
    ...(offer.billingType === "monthly"
      ? {
          description:
            "Monthly subscription. New subscribers pay 50% for the first month, then the regular monthly price from the second month.",
          priceSpecification: {
            "@type": "UnitPriceSpecification",
            price: (offer.regularAmountCents / 100).toFixed(2),
            priceCurrency: "USD",
            billingIncrement: 1,
            unitCode: "MON",
          },
        }
      : {
          description: "One-time purchase of a single construction estimate. Not a subscription.",
        }),
  }));

  const faq = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "Do you offer a free trial?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "No. Mobi Estimates does not offer a free trial. New monthly subscribers receive 50% off their first month, and regular monthly pricing begins with the second month.",
        },
      },
      {
        "@type": "Question",
        name: "Is the 50% discount recurring?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "No. The 50% discount applies only to the first month of a new monthly subscription. Regular pricing begins with the second month.",
        },
      },
      {
        "@type": "Question",
        name: "Can I purchase only one estimate?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Yes. The Pay Per Project option is a one-time payment of $599 for one estimate. It does not create a monthly subscription.",
        },
      },
    ],
  };

  return [
    {
      "@context": "https://schema.org",
      "@type": "Service",
      name: "Mobi Estimates",
      serviceType: "Construction estimating service for contractors",
      description:
        "AI-assisted construction estimates and takeoffs, independently audited and reconciled before customer review and approval, that help contractors submit more bids.",
      offers,
    },
    faq,
  ];
}

export default async function PricingPage({
  searchParams,
}: {
  searchParams: Promise<{ notice?: string }>;
}) {
  const monthly = monthlyOffers();
  const ppp = payPerProjectOffer();
  const { notice } = await searchParams;
  const noticeText =
    notice === "checkout_soon"
      ? "Checkout is being finalized. You can review every plan now — selection goes live shortly."
      : notice === "checkout_error"
        ? "We couldn't start checkout just now. Please try again in a moment."
        : null;

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-12">
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: JSON.stringify(pricingJsonLd()) }}
      />
      <div className="mx-auto w-full max-w-5xl">
        <PricingHeader />
        {noticeText && (
          <p className="mx-auto mt-6 max-w-2xl rounded-lg border border-slate-300 bg-white px-4 py-3 text-center text-sm text-slate-600">
            {noticeText}
          </p>
        )}
        <PromoBanner />

        {/* Three monthly subscription plans — Growth centered & emphasized. */}
        <section aria-label="Monthly subscription plans" className="mt-10">
          <div className="grid gap-6 md:grid-cols-3 md:items-start">
            {monthly.map((offer) => (
              <MonthlyPlanCard
                key={offer.id}
                offer={offer}
                cta={
                  <Link
                    href={`/start?plan=${offer.id}`}
                    prefetch={false}
                    aria-label={`${offer.ctaLabel}: ${offer.name}`}
                    className={
                      "block w-full rounded-full px-5 py-3 text-center font-semibold transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30 " +
                      (offer.mostPopular
                        ? "bg-brand text-white hover:bg-brand-dark"
                        : "border border-slate-300 text-navy hover:border-brand hover:text-brand")
                    }
                  >
                    {offer.ctaLabel}
                  </Link>
                }
              />
            ))}
          </div>
        </section>

        {/* Pay Per Project — directly beneath the monthly plans, clearly separated. */}
        <section aria-label="One-time option" className="mt-8">
          <PayPerProjectCard
            cta={
              <Link
                href={`/start?plan=${ppp.id}`}
                prefetch={false}
                aria-label={`${ppp.ctaLabel}: one-time ${ppp.name}`}
                className="block w-full rounded-full border border-slate-300 px-6 py-3 text-center font-semibold text-navy transition hover:border-brand hover:text-brand focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/30 sm:w-auto"
              >
                {ppp.ctaLabel}
              </Link>
            }
          />
        </section>

        <p className="mx-auto mt-6 max-w-2xl text-center text-xs text-slate-400">
          No free trial. You can review every plan here before creating an account.
          You choose your plan first, then create an account and check out securely.
        </p>

        <PricingFAQ />

        <p className="mt-10 text-center text-sm text-slate-500">
          Already have an account?{" "}
          <Link href="/login" className="font-semibold text-brand hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
