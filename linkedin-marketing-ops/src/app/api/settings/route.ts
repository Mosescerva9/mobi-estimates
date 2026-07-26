import { NextResponse } from "next/server";
import { z } from "zod";
import { storeErrorResponse } from "@/lib/api-errors";
import { updateStore } from "@/lib/store";

export const dynamic = "force-dynamic";

const schema = z.object({
  brandVoice: z.string().min(10).optional(),
  icpKeywords: z.array(z.string()).optional(),
  dailyConnectCap: z.number().int().min(1).max(50).optional(),
  dailyCommentCap: z.number().int().min(1).max(50).optional(),
  dailyDmCap: z.number().int().min(1).max(30).optional(),
  doNotContact: z.array(z.string()).optional(),
  ctaUrl: z.string().url().optional(),
  companyName: z.string().min(2).optional(),
});

export async function GET() {
  const { readStore } = await import("@/lib/store");
  const store = await readStore();
  return NextResponse.json(store.settings);
}

export async function PATCH(req: Request) {
  const body = await req.json();
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.flatten() }, { status: 400 });
  }

  try {
    const store = await updateStore((data) => {
      data.settings = { ...data.settings, ...parsed.data };
    });
    return NextResponse.json(store.settings);
  } catch (err) {
    const res = storeErrorResponse(err);
    if (res) return res;
    throw err;
  }
}