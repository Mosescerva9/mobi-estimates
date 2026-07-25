/**
 * Minimal dependency-free Resend client (REST via fetch), mirroring the style
 * of lib/stripe.ts. SERVER-ONLY: requires RESEND_API_KEY and EMAIL_FROM.
 */

import { portalBaseUrl } from "@/lib/site-url";

const RESEND_API = "https://api.resend.com/emails";

// Absolute base for account-claim links. Defaults to the canonical portal and
// rejects preview/fake hosts. See lib/site-url.
export const SITE_URL = portalBaseUrl();

export function emailConfigured(): boolean {
  return !!process.env.RESEND_API_KEY && !!process.env.EMAIL_FROM;
}

/**
 * Sends an email via Resend. Callers that must not fail their own operation
 * because of a delivery hiccup (e.g. the Stripe webhook) should wrap this in
 * their own try/catch — this function does not swallow errors itself.
 */
export async function sendEmail(params: {
  to: string;
  subject: string;
  html: string;
}): Promise<void> {
  const key = process.env.RESEND_API_KEY;
  const from = process.env.EMAIL_FROM;
  if (!key || !from) {
    console.warn(`Resend not configured; skipping email to ${params.to}: ${params.subject}`);
    return;
  }
  const res = await fetch(RESEND_API, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ from, to: params.to, subject: params.subject, html: params.html }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resend send failed (${res.status}): ${body}`);
  }
}

/**
 * Confirmation for a forwarded bid invitation. Sent only to a sender we matched
 * to a member of the receiving company — never to an unrecognized address, which
 * would turn the intake alias into a way to bounce mail at arbitrary third
 * parties.
 *
 * Deliberately promises nothing about turnaround: capturing a forward is not
 * acceptance of the work (see src/lib/intro-offer.ts).
 */
export function forwardedBidReceivedEmailHtml(params: {
  subject: string | null;
  storedCount: number;
  skippedCount: number;
  inboxUrl: string;
}): string {
  const documents =
    params.storedCount === 1 ? "1 document" : `${params.storedCount} documents`;
  const skipped =
    params.skippedCount > 0
      ? `<p style="color:#92400e;font-size:13px;">${params.skippedCount} attachment(s) weren't saved because of their file type or size. You can add them from the project page.</p>`
      : "";
  return `
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color:#16243f;">We received your forwarded bid</h2>
      <p>${params.subject ? `<strong>${escapeHtml(params.subject)}</strong><br/>` : ""}We saved ${documents} to your Mobi Estimates account.</p>
      <p>Review the documents and confirm the scope to submit it for an estimate.</p>
      <p style="margin: 24px 0;">
        <a href="${params.inboxUrl}" style="background:#2c5c9e;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:600;">
          Review forwarded bid
        </a>
      </p>
      ${skipped}
      <p style="color:#64748b;font-size:13px;">Forwarding a bid doesn't start an estimate on its own — we begin once you confirm the scope. We don't promise a turnaround time.</p>
    </div>
  `;
}

/** Escape untrusted text (a third party wrote the forwarded subject line). */
function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function claimAccountEmailHtml(claimUrl: string): string {
  return `
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color:#16243f;">Payment received — finish setting up your account</h2>
      <p>Thanks for your purchase from Mobi Estimates. Click below to set your password and finish setting up your account.</p>
      <p style="margin: 24px 0;">
        <a href="${claimUrl}" style="background:#2c5c9e;color:#fff;padding:12px 24px;border-radius:999px;text-decoration:none;font-weight:600;">
          Finish setting up your account
        </a>
      </p>
      <p style="color:#64748b;font-size:13px;">If you already finished setup after paying, you can ignore this email.</p>
    </div>
  `;
}
