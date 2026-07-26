import { NextResponse } from "next/server";
import { StoreConfigError, StoreConflictError } from "./store-mode";

/**
 * Map known durable-store errors to owner-readable HTTP responses:
 *  - StoreConflictError → 409 (reload and retry, another write landed first)
 *  - StoreConfigError   → 503 (durable storage not configured)
 * Returns null for anything else so the caller can rethrow.
 */
export function storeErrorResponse(err: unknown): NextResponse | null {
  if (err instanceof StoreConflictError) {
    return NextResponse.json({ error: err.message, conflict: true }, { status: 409 });
  }
  if (err instanceof StoreConfigError) {
    return NextResponse.json({ error: err.message }, { status: 503 });
  }
  return null;
}
