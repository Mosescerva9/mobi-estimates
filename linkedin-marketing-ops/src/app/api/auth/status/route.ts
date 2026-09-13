import { NextResponse } from "next/server";
import { authConfigError, isAuthenticated, passwordConfigured } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const cfgErr = authConfigError();
  return NextResponse.json({
    authRequired: passwordConfigured(),
    authenticated: cfgErr ? false : await isAuthenticated(),
    configError: cfgErr ? cfgErr.message : null,
  });
}
