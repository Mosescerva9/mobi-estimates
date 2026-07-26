import { NextResponse } from "next/server";
import { aiMode } from "@/lib/ai";
import { passwordConfigured } from "@/lib/auth";
import { readStore } from "@/lib/store";
import { StoreConfigError } from "@/lib/store-mode";

export const dynamic = "force-dynamic";

export async function GET() {
  let store;
  try {
    store = await readStore();
  } catch (err) {
    if (err instanceof StoreConfigError) {
      // Fail closed with a clear, owner-readable message (no secrets).
      return NextResponse.json({ error: err.message }, { status: 503 });
    }
    throw err;
  }
  const pending = {
    posts: store.posts.filter((p) => p.status === "pending_approval").length,
    engage: store.engage.filter((e) => e.status === "pending_approval").length,
    dms: store.dms.filter((d) => d.status === "pending_approval").length,
  };

  return NextResponse.json({
    app: process.env.NEXT_PUBLIC_APP_NAME || "Mobi LinkedIn Ops",
    aiMode: aiMode(),
    authRequired: passwordConfigured(),
    linkedinConfigured: Boolean(
      process.env.LINKEDIN_ACCESS_TOKEN?.trim() &&
        process.env.LINKEDIN_AUTHOR_URN?.trim()
    ),
    pending,
    settings: store.settings,
  });
}