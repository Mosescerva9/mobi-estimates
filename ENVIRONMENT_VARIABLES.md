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
| `STRIPE_PRICE_PAY_PER_PROJECT` | **no — server only** | Pay Per Project checkout ($199 one-time price) | Stripe → Product "Pay Per Project" → one-time Price id | ❌ needed for payments |
| `STRIPE_FIRST_MONTH_COUPON_ID` | **no — server only** | 50%-off-first-month promotion (monthly plans) | Stripe → Coupons → create `percent_off=50`, `duration=once` → coupon id | ❌ needed for payments |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | yes | Checkout redirect (if used client-side) | Stripe → Developers → API keys | ⬜ optional |
| `RESEND_API_KEY` | **no — server only** | transactional + auth emails | Resend → API Keys | ❌ needed for email |
| `EMAIL_FROM` | no | "from" identity on emails | your verified Resend domain (e.g. `Mobi Estimates <estimates@mobiestimates.com>`) | ❌ needed for email |
| `NEXT_PUBLIC_SITE_URL` | yes | absolute links in emails / redirects | your Vercel/prod URL | ⬜ recommended |

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
  - 1 Product with a **one-time** Price: Pay Per Project ($199).
  - 1 Coupon: `percent_off = 50`, `duration = once` (discounts only the first month).
  - Set the five `STRIPE_PRICE_*` / `STRIPE_FIRST_MONTH_COUPON_ID` vars above.
  - Do **not** configure any trial (`trial_period_days` / `trial_end`) anywhere.
- **Resend** — resend.com → verify the `mobiestimates.com` sending domain (DNS records).
- **Vercel** — vercel.com → project `mobi-portal`.
