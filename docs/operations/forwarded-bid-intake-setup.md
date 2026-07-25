# Turning on forwarded-bid intake

Updated: 2026-07-25

Contractors forward an invitation to bid — plans, specs, addenda attached — to
**`estimates@mobiestimates.com`**, and it lands in their portal as a reviewable
item. This is the setup that makes that work. None of it is in the repository:
it is DNS, a mail forwarding rule, a Resend receiving domain, a webhook, host
env vars, and two migrations.

Check state at any point with:

```bash
npm run check:intake-readiness
```

It is read-only, safe against production, and prints the exact fix for anything
that isn't ready. Everything below is written so that command ends green.

---

## How the address works

`estimates@mobiestimates.com` is the address, and it does not change. It is
printed in the portal and published on every page of the marketing site.

What changes is *delivery*. The address stays a real mailbox on the existing
mail host (Private Email), and that mailbox **forwards a copy** to a Resend
receiving subdomain, `bids.mobiestimates.com`. Resend fires the
`email.received` webhook, and the portal captures the documents.

```
contractor → estimates@mobiestimates.com   (Private Email — still a real inbox)
                      │  forwarding rule
                      ▼
             …@bids.mobiestimates.com       (MX → Resend)
                      │  email.received webhook
                      ▼
      portal.mobiestimates.com/api/email/inbound → /portal/inbox
```

### Why not just point the domain at Resend

Enabling receiving on a domain repoints its MX and makes Resend the destination
for **every** address on it. Resend is a webhook target, not a mailbox host, so
there would be nowhere to read that mail or reply from it — and
`estimates@mobiestimates.com` is the company's public contact address, not only
a bid drop box. `mobiestimates.com` also already carries the company's own
mailboxes:

```
mx1.privateemail.com  (priority 10)
mx2.privateemail.com  (priority 10)
```

Running both hosts on one domain isn't an option either: mail goes to the record
with the lowest priority value only, so a co-resident record either does nothing
or takes over, and equal priorities deliver unpredictably. Forwarding is what
lets the published address keep working while the documents still reach the
portal. It is also Resend's own documented recommendation.

Sending is unaffected throughout: SPF and DKIM are TXT records and never
conflict with MX.

### Why the forwarded copy still routes to the right company

Forwarding preserves the original `To` and `Cc` headers, so a relayed message
still carries the address the contractor typed — including the per-company tag
`estimates+{intake_slug}@mobiestimates.com`. That tag is what identifies the
tenant. `NEXT_PUBLIC_INTAKE_DELIVERY_DOMAIN` tells the app to also accept mail
that arrives on the receiving subdomain, for the case where a mail system
rewrites the headers on relay; such a message is still captured, and falls
through to sender matching or staff triage.

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

Without it — from a machine or CI box that has no CLI:

```bash
# over HTTPS, with a personal access token from
# https://supabase.com/dashboard/account/tokens
SUPABASE_ACCESS_TOKEN=sbp_... npm run db:apply-migrations -- 0036 0037

# or over a direct connection
SUPABASE_DB_URL=postgresql://... npm run db:apply-migrations -- 0036 0037
```

Use the **pooler** connection string for `SUPABASE_DB_URL`. The direct
`db.<ref>.supabase.co` host resolves to IPv6 only, so it fails outright from an
IPv4-only network.

Or with no credential at all — print both migrations as one script and paste it
into the Supabase SQL editor:

```bash
npm run db:apply-migrations -- 0036 0037 --print
```

Note that neither the anon key nor the service-role key can apply a migration.
They authenticate to PostgREST, which only reads and writes rows; creating
tables needs a personal access token or the database password. That gap is
deliberate and worth keeping — a leaked service-role key can currently read and
write data, but cannot drop a table or disable RLS. Installing a
"run arbitrary SQL" function to close it would hand exactly that power to
anything holding the key.

Both migrations are written to be re-runnable, so applying them twice is a
no-op.

## 2. Add the receiving subdomain in Resend

1. Resend → **Domains** → add `bids.mobiestimates.com`.
2. Enable **Receiving** on it and copy the MX record Resend shows.
3. Add that MX record to DNS **on the `bids` subdomain only**. Leave
   `mobiestimates.com`'s `privateemail.com` records exactly as they are.
4. Wait for Resend to mark the domain verified.

## 3. Forward the intake mailbox to it

In Private Email, on `estimates@mobiestimates.com`:

1. Add a forwarding rule to an address on `bids.mobiestimates.com` — any local
   part works, since Resend receives every address on the subdomain. Use
   `intake@bids.mobiestimates.com`.
2. Keep a local copy if you want to keep reading and replying to that mailbox
   normally. Forwarding a copy does not stop delivery to the inbox.
3. **Check plus-addressing.** The per-company address is
   `estimates+{intake_slug}@mobiestimates.com`, and that tag is what routes a
   forward deterministically. If the mail host delivers plus-tagged mail to the
   base mailbox, the forwarding rule picks it up automatically. If it does not,
   add a catch-all or alias rule that covers `estimates+*`. Without it, tagged
   forwards bounce and only sender matching routes — which fails whenever
   somebody forwards from an address that isn't on their portal account.

## 4. Point the webhook at the portal

1. Resend → **Webhooks** → add `https://portal.mobiestimates.com/api/email/inbound`.
2. Subscribe it to `email.received`.
3. Copy the signing secret (`whsec_…`).

## 5. Set the host environment variables

On Vercel (project `mobi-portal`), for Production:

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_INTAKE_EMAIL_DOMAIN` | `mobiestimates.com` |
| `NEXT_PUBLIC_INTAKE_DELIVERY_DOMAIN` | `bids.mobiestimates.com` |
| `NEXT_PUBLIC_INTAKE_EMAIL_MAILBOX` | `estimates` |
| `RESEND_INBOUND_WEBHOOK_SECRET` | the `whsec_…` secret from step 4 |
| `RESEND_API_KEY` | existing Resend key |
| `SUPABASE_SERVICE_ROLE_KEY` | existing service-role key |

The endpoint checks all three secrets up front and answers a single `503` if any
is missing, rather than failing part-way through and being retried. Redeploy
after setting them.

## 6. Verify

```bash
npm run check:intake-readiness
```

Then send one real forward to `estimates@mobiestimates.com` from an address that
belongs to a portal user, and confirm it appears at `/portal/inbox` with its
attachments. Send a second to the tagged
`estimates+{intake_slug}@mobiestimates.com` form shown in that company's portal
to confirm plus-addressing survives the forwarding rule. Forward once more from
an address that is *not* on any account and confirm it lands in `/admin/inbox`
as unrouted rather than disappearing.

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

1. **The per-company address** — `estimates+{intake_slug}@mobiestimates.com`,
   printed in the portal. The slug is unguessable, so this routes correctly no
   matter who forwards: an assistant, a phone's personal account, or the GC's own
   mail system re-sending it.
2. **The shared address** — `estimates@mobiestimates.com`, routed by matching
   the sender against company members.

Anything that matches neither, or whose sender belongs to more than one company,
is held as `unrouted` for staff triage in `/admin/inbox` rather than guessed at.
Unrouted forwards are recorded **without** their attachments — a public address
anyone can write to must not be a way to fill our storage — but the attachment
count is kept so staff can tell a contractor exactly what didn't come through.

Because `estimates@mobiestimates.com` is also the public contact address,
ordinary inquiries reach the webhook too. They arrive as unrouted, are visible
in `/admin/inbox`, and can be dismissed there; the mailbox itself still receives
them normally for a human to answer.
