import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { hashSessionToken } from "@/lib/session-token";

const OPS_COOKIE = "mobi_linkedin_ops_session";

export async function middleware(req: NextRequest) {
  const password = process.env.OPS_PASSWORD?.trim();
  if (!password) {
    return NextResponse.next();
  }

  const { pathname } = req.nextUrl;
  if (
    pathname.startsWith("/login") ||
    pathname.startsWith("/api/auth/login") ||
    pathname.startsWith("/_next") ||
    pathname === "/favicon.ico"
  ) {
    return NextResponse.next();
  }

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
