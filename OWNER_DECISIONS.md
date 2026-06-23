# Owner Decisions — Mobi Estimates Portal

These are business/legal values **only the owner can supply**. The code uses
clearly-labeled placeholders until you fill these in. Nothing here is invented or
final. Reply with answers (or use the ChatGPT intake prompt) and they'll be wired
into config + the `plans` / `service_agreements` / `training_modules` tables.

> Rule we are holding to: no fabricated prices, stats, reviews, certifications,
> guarantees, phone numbers, or "unlimited / 100% accurate / guaranteed" claims.

## 1. Accounts to create (required before the app can run/be tested)
- [ ] **Supabase** project (free tier ok) → provides URL + anon key + service-role key
- [ ] **Stripe** account → secret key, webhook secret, one Price per plan
- [ ] **Resend** account + verified sending domain → API key
- [ ] **Vercel** account (deploy target) + connect the portal repo
- [ ] DNS: `portal.mobiestimates.com` → Vercel

## 2. Plans & pricing (capacity-based, not hourly)
For each plan confirm name, monthly price, **active estimating capacity** (standard
bids/month), max concurrent active projects, turnaround guidance, revision policy.
The marketing site currently advertises these — confirm they are final:
- [ ] Starter — $995/mo — up to 3 standard bids — 1 active project — turnaround ? — revisions ?
- [ ] Growth — $1,995/mo — up to 7 standard bids — 2 active — turnaround ? — revisions ?
- [ ] Outsourced Estimating Department — $2,995/mo — up to 12 standard bids — 3 active — ? — ?
- [ ] Project-based starting prices ($199 / $399 / custom) — confirm or adjust
- [ ] Standard-bid definition wording — approve the version already drafted
- [ ] Do unused monthly bids roll over? (currently unstated — needs a real policy)

## 3. Turnaround ranges
- [ ] Single-trade takeoff: ___ business days (marketing says 2–4)
- [ ] Full estimate: ___ business days (marketing says 3–5)
- [ ] Rush availability terms: ___

## 4. Revisions & capacity
- [ ] Revisions included per estimate / per plan: ___
- [ ] What counts as a billable revision vs. a Mobi correction: ___
- [ ] How capacity overage is handled (custom quote? next month?): ___

## 5. Files
- [ ] Max file size per upload (default 25 MB): ___
- [ ] Total per-project cap (if any): ___

## 6. Billing policy
- [ ] Refund policy: ___
- [ ] Cancellation terms (default: month-to-month, cancel before next cycle): ___
- [ ] Payment timing (advance monthly?): ___

## 7. Support
- [ ] Target support response time to publish: ___
- [ ] Support email (default estimates@mobiestimates.com — confirm it works): ___
- [ ] Real business phone (optional; hidden until provided): ___

## 8. Content & media
- [ ] Welcome video URL: ___
- [ ] Training video URLs (6 modules): ___
- [ ] Founder name / bio / photo (optional; section hidden until provided): ___

## 9. Legal (DRAFTS — must be attorney-reviewed before launch)
The portal ships **draft** Terms of Service, Privacy Policy, Estimating Service
Agreement, Cancellation, Refund, and Confidentiality policies, each labeled
"draft — not attorney-approved." Owner to provide final language or approve drafts:
- [ ] Governing law (state/country): ___
- [ ] Liability limitations approved by counsel: ___
- [ ] File retention period: ___
- [ ] Confidentiality terms: ___

## 10. Email sender identity
- [ ] `EMAIL_FROM` display name + verified address: ___

---
_When the milestone-1 app scaffold is generated, this file will gain a checklist
of the exact env vars and DB rows that still need values._
