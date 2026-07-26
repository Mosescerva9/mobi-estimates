import { NextResponse } from "next/server";
import { z } from "zod";
import {
  OPS_COOKIE,
  authConfigError,
  makeSessionToken,
  passwordConfigured,
  verifyPassword,
} from "@/lib/auth";

export const dynamic = "force-dynamic";

const schema = z.object({
  password: z.string().min(1),
});

export async function POST(req: Request) {
  const cfgErr = authConfigError();
  if (cfgErr) {
    // Hosted with no OPS_PASSWORD: fail closed with a configuration message.
    return NextResponse.json(
      { error: cfgErr.message, configError: true },
      { status: 503 }
    );
  }

  if (!passwordConfigured()) {
    return NextResponse.json({ ok: true, authRequired: false });
  }

  const parsed = schema.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json({ error: "Password required" }, { status: 400 });
  }

  if (!(await verifyPassword(parsed.data.password))) {
    return NextResponse.json({ error: "Invalid password" }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true, authRequired: true });
  res.cookies.set(OPS_COOKIE, await makeSessionToken(parsed.data.password), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 14,
  });
  return res;
}