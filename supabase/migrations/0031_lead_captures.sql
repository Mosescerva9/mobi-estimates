-- =============================================================================
-- Mobi Estimates — Public work-email lead capture.
--
-- Backs the homepage email-capture form. This packet ONLY stores the lead — it
-- never sends a confirmation/nurture email and integrates no external sender.
--
-- Privacy/abuse posture:
--   • Email is normalized (lowercased/trimmed) by the server action before insert.
--   • source/UTM values come from a strict server-side allowlist.
--   • Explicit consent timestamp + consent version are required (DB-enforced).
--   • Unique on email → idempotent capture (ON CONFLICT DO NOTHING) so the
--     server can always return a generic response and never reveal whether an
--     address already exists (no email enumeration).
--   • RLS is DEFAULT DENY with NO public insert/select policy. The public form
--     never writes this table directly — the server action parses, normalizes,
--     honeypot-checks, and inserts through the service-role client (server-only,
--     inventoried in src/lib/supabase/service-role-inventory.ts). This prevents a
--     client from bypassing the allowlist/honeypot to write arbitrary UTM/source
--     values, which a raw `to anon` insert policy would have allowed.
--   • FUTURE: activate bot/rate-limit controls (e.g. captcha/turnstile + IP rate
--     limiting) before this is used beyond the gated preview.
-- =============================================================================

create table if not exists public.lead_captures (
  id              uuid primary key default gen_random_uuid(),
  email           text not null unique,
  source          text,
  utm_source      text,
  utm_medium      text,
  utm_campaign    text,
  utm_content     text,
  utm_term        text,
  consent_at      timestamptz not null,
  consent_version text not null,
  created_at      timestamptz not null default now()
);

alter table public.lead_captures enable row level security;

-- Intentionally NO insert/select/update/delete policy: RLS is default deny for
-- every anon/authenticated caller. Writes happen ONLY through the service-role
-- client in the server action, after the pure lead-capture lib has parsed,
-- normalized, allowlisted, and honeypot-checked the submission. There is no
-- direct public write path a client could use to bypass that validation.
