import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import {
  emailConfigured,
  forwardedBidReceivedEmailHtml,
  sendEmail,
  SITE_URL,
} from "@/lib/email";
import {
  captureForwardedBid,
  notifyCompanyOfForwardedBid,
} from "@/lib/inbound-intake-server";
import {
  parseEmailReceivedEvent,
  readSvixHeaders,
  verifySvixSignature,
} from "@/lib/resend-inbound";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Plan sets are large and are downloaded from the provider and re-uploaded to
// private Storage inside this request.
export const maxDuration = 60;

/**
 * Inbound bid-invitation intake (Resend `email.received`).
 *
 * A contractor forwards an ITB to their company's intake address; this captures
 * the message and its attachments as a reviewable item in their portal. It never
 * creates a project and never spends an entitlement — the receiving address is
 * effectively public to anyone the contractor has ever forwarded from, so the
 * entitlement boundary stays behind an authenticated confirmation. See
 * supabase/migrations/0036_inbound_bid_intake.sql.
 *
 * Idempotent: a redelivered event resolves to the already-captured message.
 */
export async function POST(request: Request) {
  // Both secrets are checked up front. Capturing a forward needs the service
  // role (an inbound email has no session to attach RLS to), and a
  // half-configured deployment should answer with a clear 503 rather than let
  // the client constructor throw an HTML error page at the provider.
  const secret = process.env.RESEND_INBOUND_WEBHOOK_SECRET;
  if (!secret || !process.env.SUPABASE_SERVICE_ROLE_KEY) {
    return NextResponse.json({ error: "Inbound intake not configured." }, { status: 503 });
  }

  const raw = await request.text();
  let payload: Record<string, unknown>;
  try {
    payload = verifySvixSignature(raw, readSvixHeaders(request.headers), secret);
  } catch (e) {
    const message = e instanceof Error ? e.message : "Invalid signature.";
    return NextResponse.json({ error: message }, { status: 400 });
  }

  const event = parseEmailReceivedEvent(payload);
  if (!event) {
    // Some other webhook event type. Acknowledge so the provider stops retrying.
    return NextResponse.json({ received: true, ignored: "unsupported_event" });
  }

  const admin = createAdminClient();

  let outcome;
  try {
    outcome = await captureForwardedBid(admin, event);
  } catch (e) {
    // Non-2xx so the provider redelivers. captureForwardedBid already rolled
    // back anything it wrote, so the retry starts clean.
    console.error("Failed to capture forwarded bid:", e);
    return NextResponse.json({ error: "Could not capture the forwarded email." }, { status: 500 });
  }

  if (outcome.status !== "captured") {
    return NextResponse.json({ received: true, ...outcome });
  }

  // Everything below is best-effort: the documents are already stored and
  // visible in the portal, so a notification failure must not trigger a
  // redelivery that would duplicate them.
  try {
    await notifyCompanyOfForwardedBid(admin, {
      companyId: outcome.companyId,
      messageId: outcome.messageId,
      subject: outcome.subject,
      storedCount: outcome.stored,
    });
  } catch (e) {
    console.error("Failed to create forwarded-bid notifications:", e);
  }

  if (outcome.notifyEmail && emailConfigured()) {
    try {
      await sendEmail({
        to: outcome.notifyEmail,
        subject: "We received your forwarded bid — review and confirm",
        html: forwardedBidReceivedEmailHtml({
          subject: outcome.subject,
          storedCount: outcome.stored,
          skippedCount: outcome.skipped,
          inboxUrl: `${SITE_URL}/portal/inbox`,
        }),
      });
    } catch (e) {
      console.error("Failed to send forwarded-bid confirmation:", e);
    }
  }

  return NextResponse.json({
    received: true,
    messageId: outcome.messageId,
    stored: outcome.stored,
    skipped: outcome.skipped,
  });
}
