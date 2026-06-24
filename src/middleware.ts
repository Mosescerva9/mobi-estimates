import { type NextRequest, NextResponse } from "next/server";

const PROTECTED = ["/portal", "/onboarding", "/admin", "/billing"];

/**
 * Lightweight, Edge-safe route gate (no external dependencies).
 *
 * It only checks for the *presence* of a Supabase auth cookie to decide whether
 * to bounce a clearly-logged-out visitor to /login — a UX convenience so
 * protected pages don't flash. It deliberately does NOT import the Supabase SDK:
 * that pulls @supabase/supabase-js (which touches the Node-only `process.version`)
 * into the Edge bundle and fails Vercel's Edge deploy validation.
 *
 * The real authorization is enforced server-side — getSessionUser()/requireUser()
 * call supabase.auth.getUser() (verified, not just a decoded cookie) — and in the
 * database via Row Level Security. This gate is not a security boundary.
 */
export function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const needsAuth = PROTECTED.some((p) => path === p || path.startsWith(`${p}/`));
  if (!needsAuth) return NextResponse.next();

  // Supabase stores the session in cookies named `sb-<project-ref>-auth-token`
  // (possibly chunked with a numeric suffix).
  const hasSession = request.cookies
    .getAll()
    .some((c) => c.name.startsWith("sb-") && c.name.includes("auth-token"));

  if (!hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("redirect", path);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Run on everything except static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
