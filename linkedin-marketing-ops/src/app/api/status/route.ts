import { NextResponse } from "next/server";
import { aiMode } from "@/lib/ai";
import { readStore } from "@/lib/store";

export async function GET() {
  const store = await readStore();
  const pending = {
    posts: store.posts.filter((p) => p.status === "pending_approval").length,
    engage: store.engage.filter((e) => e.status === "pending_approval").length,
    dms: store.dms.filter((d) => d.status === "pending_approval").length,
  };

  return NextResponse.json({
    app: process.env.NEXT_PUBLIC_APP_NAME || "Mobi LinkedIn Ops",
    aiMode: aiMode(),
    linkedinConfigured: Boolean(
      process.env.LINKEDIN_ACCESS_TOKEN?.trim() &&
        process.env.LINKEDIN_AUTHOR_URN?.trim()
    ),
    pending,
    settings: store.settings,
  });
}
