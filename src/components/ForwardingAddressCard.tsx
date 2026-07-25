"use client";

import { useState } from "react";

/**
 * The company's forwarded-bid intake address, with a copy button.
 *
 * Addresses are rendered from server-resolved props rather than read from the
 * environment here, so a client bundle never has to know a company's tag.
 *
 * The tagged address is what we tell contractors to use. The plain shared
 * address also works, but only when the person forwarding is on the account —
 * which quietly isn't true for an assistant, a phone's personal account, or a
 * shared estimating inbox. Both are shown so a contractor who has already
 * saved the short one isn't left thinking it's broken.
 */
export function ForwardingAddressCard({
  address,
  sharedAddress,
  variant = "full",
}: {
  address: string;
  sharedAddress?: string | null;
  variant?: "full" | "compact";
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard permission denied — the address is selectable on screen.
      setCopied(false);
    }
  }

  const compact = variant === "compact";

  return (
    <div className={`rounded-2xl border border-brand/30 bg-brand/5 ${compact ? "p-4" : "p-6"}`}>
      <h2 className={`font-bold text-navy ${compact ? "text-sm" : "text-base"}`}>
        {compact ? "Can’t upload right now?" : "Forward a bid instead of uploading"}
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Forward the invitation to bid — plans, specs and addenda attached — to your
        company’s intake address. We’ll save the documents and hold them for you to
        review.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-navy">
          {address}
        </code>
        <button
          type="button"
          onClick={copy}
          className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-dark"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>

      <p className="mt-3 text-xs text-slate-500">
        This address is unique to your company, so it works no matter who on your
        team forwards the email.
        {sharedAddress ? (
          <>
            {" "}
            <span className="font-mono">{sharedAddress}</span> also works when you
            forward from the email address on your Mobi account.
          </>
        ) : null}
      </p>

      <p className="mt-2 text-xs text-slate-500">
        Works from any general contractor, plan room, or email client. Forwarding a
        bid doesn’t start an estimate on its own — you confirm the scope first, so a
        stray forward never uses up your free estimate.
      </p>
    </div>
  );
}
