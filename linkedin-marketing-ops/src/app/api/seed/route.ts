import { NextResponse } from "next/server";
import { aiMode } from "@/lib/ai";
import { storeErrorResponse } from "@/lib/api-errors";
import { seedStore } from "@/lib/seed-data";

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const data = await seedStore();
    return NextResponse.json({
      ok: true,
      aiMode: aiMode(),
      counts: {
        posts: data.posts.length,
        engage: data.engage.length,
        dms: data.dms.length,
      },
    });
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}