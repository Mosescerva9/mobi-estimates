import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { parseDfyIntake } from "@/lib/dfy-intake";
import { saveOrderIntake } from "@/lib/dfy-orders";

export const runtime = "nodejs";

/**
 * DFY intake submission. The token is the only credential, so the database
 * write itself enforces every invariant: the order must exist, be paid, and
 * not already have a submitted intake (see saveOrderIntake).
 */
export async function POST(request: Request) {
  let raw: Record<string, unknown>;
  try {
    raw = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid submission." }, { status: 400 });
  }

  const token = typeof raw.token === "string" ? raw.token : "";
  if (!token) {
    return NextResponse.json({ error: "This intake link is invalid." }, { status: 400 });
  }

  const parsed = parseDfyIntake(raw);
  if (!parsed.ok) {
    if (parsed.reason === "honeypot") {
      // Silent no-op: bots see success, nothing is stored.
      return NextResponse.json({ ok: true });
    }
    return NextResponse.json(
      { error: "Please check the highlighted fields and try again." },
      { status: 400 },
    );
  }

  const admin = createAdminClient();
  try {
    await saveOrderIntake(admin, token, parsed.intake);
  } catch {
    return NextResponse.json(
      { error: "This intake link is invalid, unpaid, or has already been submitted." },
      { status: 400 },
    );
  }

  return NextResponse.json({ ok: true });
}
