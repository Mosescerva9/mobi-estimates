# Turning on forwarded-bid intake

Updated: 2026-07-25

Contractors forward an invitation to bid — plans, specs, addenda attached — to
an address we own, and it lands in their portal as a reviewable item. This is
the setup that makes that work. None of it is in the repository: it is DNS, a
Resend receiving domain, a webhook, host env vars, and two migrations.

Check state at any point with:

```bash
npm run check:intake-readiness
```

It is read-only, safe against production, and prints the exact fix for anything
that isn't ready. Everything below is written so that command ends green.

---

## The one decision that matters: intake goes on a subdomain

**Do not point `mobiestimates.com`'s MX record at Resend.**

Enabling receiving on a domain makes Resend the destination for *every* address
on it. Resend is a webhook target, not a mailbox host, so there is nowhere to
read that mail afterwards. `mobiestimates.com` already has MX records for the
company's own mailboxes:

```
mx1.privateemail.com  (priority 10)
mx2.privateemail.com  (priority 10)
```

Repointing them sends all company email into a webhook. Adding Resend's record
alongside them doesn't split the traffic either — mail goes to the record with
the lowest priority value only, so a co-resident record either does nothing or
takes over, and equal priorities deliver unpredictably.

So intake lives on its own subdomain, `bids.mobiestimates.com`, which is also
Resend's documented recommendation. The company's existing mailboxes are
untouched. Sending is unaffected regardless: SPF and DKIM are TXT records and
never conflict with MX.

The address contractors see is `estimates@bids.mobiestimates.com`.

---

## 1. Apply the database migrations

Two migrations back the intake: `0036_inbound_bid_intake.sql` (the per-company
address, the captured-forward tables, and the two RPCs) and
`0037_inbound_intake_routing.sql` (shared-mailbox routing and the staff triage
queue).

With the Supabase CLI:

```bash
supabase db push
```

Without it — from a machine or CI box that has no CLI, or no outbound port 5432:

```bash
SUPABASE_ACCESS_TOKEN=sbp_... npm run db:apply-migrations -- 0036 0037
```

Both migrations are written to be re-runnable, so applying them twice is a
no-op. As a last resort, paste the two files into the Supabase SQL editor in
order.

## 2. Add the receiving domain in Resend

1. Resend → **Domains** → add `bids.mobiestimates.com`.
2. Enable **Receiving** on it and copy the MX record Resend shows.
3. Add that MX record to DNS **on the `bids` subdomain only**. Leave the root
   domain's `privateemail.com` records exactly as they are.
4. Wait for Resend to mark the domain verified.

## 3. Point the webhook at the portal

1. Resend → **Webhooks** → add `https://portal.mobiestimates.com/api/email/inbound`.
2. Subscribe it to `email.received`.
3. Copy the signing secret (`whsec_…`).

## 4. Set the host environment variables

On Vercel (project `mobi-portal`), for Production:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_INTAKE_EMAIL_DOMAIN` | `bids.mobiestimates.com` |
| `NEXT_PUBLIC_INTAKE_EMAIL_MAILBOX` | `estimates` |
| `RESEND_INBOUND_WEBHOOK_SECRET` | the `whsec_…` secret from step 3 |
| `RESEND_API_KEY` | existing Resend key |
| `SUPABASE_SERVICE_ROLE_KEY` | existing service-role key |

The endpoint checks all three secrets up front and answers a single `503` if any
is missing, rather than failing part-way through and being retried. Redeploy
after setting them.

## 5. Verify

```bash
npm run check:intake-readiness
```

Then send one real forward to `estimates@bids.mobiestimates.com` from an address
that belongs to a portal user, and confirm it appears at `/portal/inbox` with
its attachments. Forward once more from an address that is *not* on any account
and confirm it lands in `/admin/inbox` as unrouted rather than disappearing.

---

## What capture does and does not do

Capturing a forward **creates no project and spends no entitlement.** Migration
0034 restricted project creation to the entitlement-checked RPCs precisely so
the free-estimate boundary can only be crossed deliberately. An inbound email is
unauthenticated input — anyone who learns the address can send one — so a stray
or spoofed forward must not be able to consume a company's one free estimate.
The member converts a captured forward into a project through the normal
submission path, and the intake row is then bound to that project.

## How a forward finds its company

1. **The per-company address** — `estimates+{intake_slug}@bids.mobiestimates.com`,
   printed in the portal. The slug is unguessable, so this routes correctly no
   matter who forwards: an assistant, a phone's personal account, or the GC's own
   mail system re-sending it.
2. **The shared address** — `estimates@bids.mobiestimates.com`, routed by
   matching the sender against company members.

Anything that matches neither, or whose sender belongs to more than one company,
is held as `unrouted` for staff triage in `/admin/inbox` rather than guessed at.
Unrouted forwards are recorded **without** their attachments — a public address
anyone can write to must not be a way to fill our storage — but the attachment
count is kept so staff can tell a contractor exactly what didn't come through.
