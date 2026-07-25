# Environment Variables — Mobi Estimates Portal

No real secrets live in this file or in the repo. Set these in **Vercel → Project
→ Settings → Environment Variables** (and in `mobi-portal/.env.local` for local dev,
which is gitignored). Mirror of `.env.example`.

> ⚠️ Anything prefixed `NEXT_PUBLIC_` is shipped to the browser. Never put a
> secret behind that prefix. The Supabase **anon key** is safe to expose
> (RLS is the boundary); the **service-role key** is NOT.

| Variable | Public? | Required for | Where to get it | Status |
|---|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | yes | everything | Supabase → Project Settings → API → Project URL | ✅ set (baked default in `next.config.js`) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | yes | everything | Supabase → Project Settings → API → anon/publishable | ✅ set (baked default) |
| `SUPABASE_SERVICE_ROLE_KEY` | **no — server only** | Stripe webhook, admin automation, provisioning | Supabase → Project Settings → API → service_role | ❌ **needed** |
| `ADMIN_BOOTSTRAP_EMAILS` | no | promoting first staff/admin accounts | you choose (comma-separated emails) | ⬜ optional |
| `STRIPE_SECRET_KEY` | **no — server only** | Checkout, Billing portal, webhook | Stripe → Developers → API keys | ❌ needed for payments |
| `STRIPE_WEBHOOK_SECRET` | **no — server only** | verifying webhook signatures | Stripe → Developers → Webhooks → signing secret | ❌ needed for payments |
| `STRIPE_PRICE_STARTER` | **no — server only** | Starter checkout ($995/mo recurring price) | Stripe → Product "Starter" → recurring Price id (`price_…`) | ❌ needed for payments |
| `STRIPE_PRICE_GROWTH` | **no — server only** | Growth checkout ($1,995/mo recurring price) | Stripe → Product "Growth" → recurring Price id | ❌ needed for payments |
| `STRIPE_PRICE_ESTIMATING_DEPARTMENT` | **no — server only** | Estimating Department checkout ($2,995/mo recurring price) | Stripe → Product "Estimating Department" → recurring Price id | ❌ needed for payments |
| `STRIPE_PRICE_PAY_PER_PROJECT` | **no — server only** | Pay Per Project checkout ($599 one-time price) | Stripe → Product "Pay Per Project" → one-time Price id | ❌ needed for payments |
| ~~`STRIPE_FIRST_MONTH_COUPON_ID`~~ | — | **RETIRED** — the 50%-off-first-month promotion is removed; the regular monthly price applies from month one. Do not configure a first-month coupon. | — | ⬜ not used |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | yes | Checkout redirect (if used client-side) | Stripe → Developers → API keys | ⬜ optional |
| `RESEND_API_KEY` | **no — server only** | transactional + auth emails | Resend → API Keys | ❌ needed for email |
| `EMAIL_FROM` | no | "from" identity on emails | your verified Resend domain (e.g. `Mobi Estimates <estimates@mobiestimates.com>`) | ❌ needed for email |
| `NEXT_PUBLIC_PORTAL_URL` | yes | canonical portal links in Stripe returns and account emails | `https://portal.mobiestimates.com` (default) | ⬜ recommended |
| `NEXT_PUBLIC_INTAKE_EMAIL_DOMAIN` | yes | receiving domain for forwarded bid invitations | Resend → Domains → the receiving domain you added an MX record for | ⬜ defaults to `bids.mobiestimates.com` |
| `NEXT_PUBLIC_INTAKE_EMAIL_MAILBOX` | yes | shared intake mailbox (`estimates` in `estimates@…`) | you choose | ⬜ defaults to `estimates` |
| `RESEND_INBOUND_WEBHOOK_SECRET` | **no — server only** | verifying the `email.received` webhook at `/api/email/inbound` | Resend → Webhooks → signing secret (`whsec_…`) | ❌ needed for forwarded-bid intake |

## Recommended change (move Supabase values to env)
The Supabase URL + anon key are currently hard-coded as **defaults** in
`next.config.js` so the app deploys with zero config. This is safe (they're
public), but the cleaner setup is to set `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` in Vercel and delete the baked defaults. Host
env vars already override the defaults, so this can be done anytime.

## How to obtain each account
- **Supabase** — supabase.com → your project `mobi-portal` (ref `kzgfcgzewmqwlxfadtgz`).
- **Stripe** — stripe.com → create:
  - 3 Products with a **recurring monthly** Price each: Starter ($995), Growth ($1,995), Estimating Department ($2,995).
  - 1 Product with a **one-time** Price: Pay Per Project ($599).
  - Set the four `STRIPE_PRICE_*` vars above. The 50%-off-first-month coupon is retired — do not create one.
  - Do **not** configure any trial (`trial_period_days` / `trial_end`) anywhere.
- **Resend** — resend.com → verify the `mobiestimates.com` sending domain (DNS records). For
  forwarded-bid intake also add `bids.mobiestimates.com` as a **receiving** domain with its MX
  record, then create a webhook for the `email.received` event pointing at
  `https://portal.mobiestimates.com/api/email/inbound` and copy its signing secret into
  `RESEND_INBOUND_WEBHOOK_SECRET`. Until that is done the endpoint answers 503 and no forwarded
  mail is processed; the portal simply shows no address rather than one that doesn't route.
  Step-by-step: [docs/operations/forwarded-bid-intake-setup.md](docs/operations/forwarded-bid-intake-setup.md).

  > ⚠️ **Never point the root domain's MX at Resend.** `mobiestimates.com` already has MX records
  > for the company's own mailboxes (`mx1/mx2.privateemail.com`). Enabling receiving on a domain
  > makes Resend the destination for **every** address on it, and Resend is a webhook target, not a
  > mailbox host — there would be nowhere to read that mail. Mail is delivered to the lowest MX
  > priority only, so adding Resend alongside the existing records doesn't split traffic either; it
  > either does nothing or breaks the existing inbox, and equal priorities deliver unpredictably.
  >
  > Intake therefore lives on its own subdomain, which is also Resend's documented
  > recommendation. **Sending** is unaffected either way — SPF and DKIM are TXT records and do not
  > conflict with MX.
- **Vercel** — vercel.com → project `mobi-portal`.
