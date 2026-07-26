import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { AUTH_CONFIG_MESSAGE, classifyAuth } from "@/lib/auth-mode";
import { hashSessionToken } from "@/lib/session-token";

const OPS_COOKIE = "mobi_linkedin_ops_session";

/**
 * The ONLY paths that carry their own route-level bearer authentication and so
 * must bypass the owner session-cookie gate. Matched EXACTLY (not by prefix) so
 * nothing else — including owner-only Scout endpoints like the pairing manager
 * or the dashboard list — can slip past the cookie check. Both the job GET and
 * job POST share the single `/api/scout/job` path.
 */
const INTEGRATION_API_PATHS = new Set(["/api/scout/capture", "/api/scout/job"]);

function isIntegrationApi(pathname: string): boolean {
  return INTEGRATION_API_PATHS.has(pathname);
}

/** Always reachable so the login page can render and diagnose configuration. */
function isAlwaysAllowed(pathname: string): boolean {
  return (
    pathname.startsWith("/login") ||
    pathname.startsWith("/api/auth/login") ||
    pathname.startsWith("/api/auth/status") ||
    pathname.startsWith("/_next") ||
    pathname === "/favicon.ico"
  );
}

export async function middleware(req: NextRequest) {
  const state = classifyAuth(process.env);
  const { pathname } = req.nextUrl;

  // Local development with no password: dev-only open access.
  if (state === "open") {
    return NextResponse.next();
  }

  if (isAlwaysAllowed(pathname)) {
    return NextResponse.next();
  }

  // Hosted deployment with no OPS_PASSWORD: fail closed everywhere.
  if (state === "unconfigured-hosted") {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { error: AUTH_CONFIG_MESSAGE, configError: true },
        { status: 503 }
      );
    }
    const loginUrl = req.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.search = "";
    return NextResponse.redirect(loginUrl);
  }

  // Integration endpoints authenticate themselves at the route with an
  // independent bearer token, so they bypass the owner session cookie. They are
  // only reached HERE (after the fail-closed check above), so a hosted
  // OPS_PASSWORD misconfiguration still locks everything down first.
  if (isIntegrationApi(pathname)) {
    return NextResponse.next();
  }

  // Enforce: require a valid session cookie.
  const password = process.env.OPS_PASSWORD!.trim();
  const token = req.cookies.get(OPS_COOKIE)?.value;
  const expected = await hashSessionToken(password);
  if (token && token === expected) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const loginUrl = req.nextUrl.clone();
  loginUrl.pathname = "/login";
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
