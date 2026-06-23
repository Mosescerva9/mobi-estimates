/** @type {import('next').NextConfig} */

// Public, browser-safe Supabase connection values. The anon key is designed to
// be shipped to the browser (Row Level Security is the real security boundary),
// so baking these defaults in lets the app deploy with zero env-var setup.
// Real secrets (e.g. SUPABASE_SERVICE_ROLE_KEY) are NEVER hardcoded — they stay
// in the host's environment variables. If NEXT_PUBLIC_* env vars are set on the
// host, those override these defaults.
const SUPABASE_URL =
  process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://kzgfcgzewmqwlxfadtgz.supabase.co";
const SUPABASE_ANON_KEY =
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ??
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt6Z2ZjZ3pld21xd2x4ZmFkdGd6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODIyMDc0NzUsImV4cCI6MjA5Nzc4MzQ3NX0.kjPWSxMXfTHeKBDqL_Nmry4IQZ-9NSyKiuZmNMxOLtM";

const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_SUPABASE_URL: SUPABASE_URL,
    NEXT_PUBLIC_SUPABASE_ANON_KEY: SUPABASE_ANON_KEY,
  },
};
module.exports = nextConfig;
