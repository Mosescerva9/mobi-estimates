/**
 * Minimal dependency-free Resend client (REST via fetch), mirroring the style
 * of lib/stripe.ts. SERVER-ONLY: requires RESEND_API_KEY and EMAIL_FROM.
 */

import { publicBaseUrl } from "@/lib/site-url";

const RESEND_API = "https://api.resend.com/emails";

// Absolute base for links in emails (e.g. the account-claim URL). Defaults to
// the canonical public site; never a portal/preview host. See lib/site-url.
export const SITE_URL = publicBaseUrl();

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
