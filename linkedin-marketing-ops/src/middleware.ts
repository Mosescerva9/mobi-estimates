import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { AUTH_CONFIG_MESSAGE, classifyAuth } from "@/lib/auth-mode";
import { hashSessionToken } from "@/lib/session-token";

const OPS_COOKIE = "mobi_linkedin_ops_session";

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
