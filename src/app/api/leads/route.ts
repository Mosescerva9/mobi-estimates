import { NextRequest, NextResponse } from "next/server";
import { persistLeadCapture } from "@/lib/lead-capture-server";

const PRODUCTION_ORIGINS = new Set([
  "https://mobiestimates.com",
  "https://www.mobiestimates.com",
]);
const MAX_BODY_BYTES = 4096;

function isAllowedOrigin(origin: string | null): origin is string {
  if (!origin) return false;
  if (PRODUCTION_ORIGINS.has(origin)) return true;
  if (process.env.NODE_ENV === "production") return false;
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin);
}

function corsHeaders(origin: string): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "600",
    Vary: "Origin",
  };
}

function json(origin: string, body: object, status: number) {
  return NextResponse.json(body, { status, headers: corsHeaders(origin) });
}

export async function OPTIONS(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!isAllowedOrigin(origin)) {
    return NextResponse.json({ ok: false }, { status: 403 });
  }
  return new NextResponse(null, { status: 204, headers: corsHeaders(origin) });
}

export async function POST(request: NextRequest) {
  const origin = request.headers.get("origin");
  if (!isAllowedOrigin(origin)) {
    return NextResponse.json({ ok: false }, { status: 403 });
  }

  const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  if (contentType !== "application/json") {
    return json(origin, { ok: false }, 415);
  }

  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > MAX_BODY_BYTES) {
    return json(origin, { ok: false }, 413);
  }

  let raw: string;
  try {
    raw = await request.text();
  } catch {
    return json(origin, { ok: false }, 400);
  }
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) {
    return json(origin, { ok: false }, 413);
  }

  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return json(origin, { ok: false }, 400);
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return json(origin, { ok: false }, 400);
  }
  const input = value as Record<string, unknown>;

  try {
    const stored = await persistLeadCapture({
      email: input.email,
      source: input.source,
      utmSource: input.utm_source,
      utmMedium: input.utm_medium,
      utmCampaign: input.utm_campaign,
      utmContent: input.utm_content,
      utmTerm: input.utm_term,
      honeypot: input.company_website,
    });
    if (!stored) {
      return json(origin, { ok: false, message: "Please try again later." }, 503);
    }
  } catch {
    return json(origin, { ok: false, message: "Please try again later." }, 503);
  }

  // Same response for new, duplicate, invalid, and honeypot submissions.
  return json(origin, { ok: true, message: "Thanks. We received your request." }, 202);
}
