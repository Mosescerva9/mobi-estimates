import { NextResponse } from "next/server";
import { isAuthenticated, passwordConfigured } from "@/lib/auth";

export async function GET() {
  return NextResponse.json({
    authRequired: passwordConfigured(),
    authenticated: await isAuthenticated(),
  });
}
