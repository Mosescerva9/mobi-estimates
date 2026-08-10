/**
 * Optimistic-concurrency version metadata for the durable store.
 *
 * The Supabase adapter tags a StoreData snapshot with the row's `updated_at`
 * so a later write can compare-and-swap against it. The tag rides along on a
 * non-enumerable Symbol so it never leaks into JSON serialization, API
 * responses, or the file-mode store on disk.
 */

const VERSION = Symbol("linkedinOpsStoreVersion");

/** Attach the expected row version (its `updated_at`, or null for a missing row). */
export function attachVersion<T extends object>(data: T, version: string | null): T {
  Object.defineProperty(data, VERSION, {
    value: version,
    enumerable: false,
    writable: true,
    configurable: true,
  });
  return data;
}

/**
 * Read the version tag. `undefined` means the snapshot was never read from the
 * durable store (a blind write), `null` means the row was absent.
 */
export function getStoreVersion(data: object): string | null | undefined {
  return (data as Record<symbol, string | null>)[VERSION];
}
