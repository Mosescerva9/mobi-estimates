import { NextResponse } from "next/server";
import { readStore } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function GET() {
  const store = await readStore();
  return NextResponse.json({ items: store.posts });
}