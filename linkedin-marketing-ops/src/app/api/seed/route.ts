import { NextResponse } from "next/server";
import { aiMode } from "@/lib/ai";
import { seedStore } from "@/lib/seed-data";

export async function POST() {
  const data = await seedStore(true);
  return NextResponse.json({
    ok: true,
    aiMode: aiMode(),
    counts: {
      posts: data.posts.length,
      engage: data.engage.length,
      dms: data.dms.length,
    },
  });
}
