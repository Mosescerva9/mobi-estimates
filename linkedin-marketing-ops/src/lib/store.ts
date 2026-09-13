import { promises as fs } from "fs";
import path from "path";
import { DEFAULT_SETTINGS } from "./prompts";
import { StoreConflictError, selectStoreMode } from "./store-mode";
import { attachVersion, getStoreVersion } from "./store-version";
import type { StoreData } from "./types";

export { StoreConflictError } from "./store-mode";

/**
 * Durable store for the LinkedIn Ops queue.
 *
 * Production/hosted: a server-only Supabase REST adapter persists the whole
 * queue as one JSONB row (single-owner app). The service-role key never leaves
 * the server and is never sent to the browser.
 *
 * Local development: a JSON file under ./data. This is an explicit dev-only
 * fallback — see store-mode.ts for the fail-closed rules.
 */

const DATA_DIR = path.join(process.cwd(), "data");
const STORE_PATH = path.join(DATA_DIR, "store.json");

const SUPABASE_TABLE = "linkedin_ops_state";
const SUPABASE_ROW_ID = "singleton";

export function emptyStore(): StoreData {
  return {
    settings: { ...DEFAULT_SETTINGS },
    posts: [],
    engage: [],
    dms: [],
    scout: {},
    scoutCandidates: [],
  };
}

/** Merge persisted data over safe defaults so a partial/empty row never breaks the app. */
export function normalizeStore(parsed: Partial<StoreData> | null | undefined): StoreData {
  return {
    settings: { ...DEFAULT_SETTINGS, ...(parsed?.settings ?? {}) },
    posts: parsed?.posts ?? [],
    engage: parsed?.engage ?? [],
    dms: parsed?.dms ?? [],
    // Scout is new: old production JSON has neither field. Defaulting here keeps
    // reads of a pre-Scout row working and never resurrects a token.
    scout: parsed?.scout ?? {},
    scoutCandidates: parsed?.scoutCandidates ?? [],
  };
}

/* ---------------------------------------------------------------- file mode */

async function ensureFileStore(): Promise<void> {
  await fs.mkdir(DATA_DIR, { recursive: true });
  try {
    await fs.access(STORE_PATH);
  } catch {
    await fs.writeFile(STORE_PATH, JSON.stringify(emptyStore(), null, 2), "utf8");
  }
}

async function fileRead(): Promise<StoreData> {
  await ensureFileStore();
  const raw = await fs.readFile(STORE_PATH, "utf8");
  return normalizeStore(JSON.parse(raw) as Partial<StoreData>);
}

async function fileWrite(data: StoreData): Promise<void> {
  await ensureFileStore();
  const tmp = `${STORE_PATH}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(data, null, 2), "utf8");
  await fs.rename(tmp, STORE_PATH);
}

/* ------------------------------------------------------------ supabase mode */

function supabaseConfig(): { url: string; key: string } {
  const url = process.env.SUPABASE_URL!.trim().replace(/\/+$/, "");
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY!.trim();
  return { url, key };
}

function supabaseHeaders(): Record<string, string> {
  const { key } = supabaseConfig();
  return {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  };
}

/** Generic failure message — never leak the service-role key or raw provider body to callers. */
function supabaseError(context: string, status: number): Error {
  return new Error(
    `Durable storage ${context} failed (status ${status}). Check SUPABASE_URL and ` +
      `SUPABASE_SERVICE_ROLE_KEY, and that the linkedin_ops_state migration has been applied.`
  );
}

// Postgres RPC that performs the compare-and-swap. See the 0001 migration.
const SUPABASE_CAS_RPC = "linkedin_ops_state_cas";

async function supabaseRead(): Promise<StoreData> {
  const { url } = supabaseConfig();
  const res = await fetch(
    `${url}/rest/v1/${SUPABASE_TABLE}?id=eq.${SUPABASE_ROW_ID}&select=data,updated_at`,
    { headers: supabaseHeaders(), cache: "no-store" }
  );
  if (!res.ok) throw supabaseError("read", res.status);
  const rows = (await res.json()) as Array<{
    data?: Partial<StoreData>;
    updated_at?: string;
  }>;
  // A missing row initializes to an empty store with a null version, so the
  // first write is allowed to insert it (see the CAS RPC).
  if (!rows.length) return attachVersion(emptyStore(), null);
  return attachVersion(normalizeStore(rows[0]?.data), rows[0]?.updated_at ?? null);
}

async function supabaseWrite(data: StoreData): Promise<void> {
  const { url } = supabaseConfig();
  // The expected version is the `updated_at` this snapshot was read at. `null`
  // means "the row was absent" (allow insert); a mismatch means someone else
  // wrote first and this write must not clobber them.
  const expected = getStoreVersion(data) ?? null;
  const res = await fetch(`${url}/rest/v1/rpc/${SUPABASE_CAS_RPC}`, {
    method: "POST",
    headers: supabaseHeaders(),
    body: JSON.stringify({ p_expected_updated_at: expected, p_data: data }),
    cache: "no-store",
  });
  if (!res.ok) throw supabaseError("write", res.status);
  // The RPC returns the new `updated_at` on success, or null on a CAS conflict.
  const newVersion = (await res.json()) as string | null;
  if (newVersion === null) {
    throw new StoreConflictError();
  }
  // Keep the snapshot usable for a subsequent write in the same request.
  attachVersion(data, newVersion);
}

/* -------------------------------------------------------------- public API */

export async function readStore(): Promise<StoreData> {
  return selectStoreMode() === "supabase" ? supabaseRead() : fileRead();
}

export async function writeStore(data: StoreData): Promise<void> {
  if (selectStoreMode() === "supabase") {
    await supabaseWrite(data);
  } else {
    await fileWrite(data);
  }
}

/**
 * Read-modify-write with optimistic concurrency. If a concurrent write lands
 * between our read and write, we re-read and re-apply the mutator against fresh
 * data rather than clobbering it. After a bounded number of attempts we give up
 * and surface the conflict so the caller can return HTTP 409.
 */
export async function updateStore(
  mutator: (data: StoreData) => StoreData | void
): Promise<StoreData> {
  const MAX_ATTEMPTS = 4;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const current = await readStore();
    const next = mutator(current) ?? current;
    try {
      await writeStore(next);
      return next;
    } catch (err) {
      if (err instanceof StoreConflictError && attempt < MAX_ATTEMPTS) continue;
      throw err;
    }
  }
  // Unreachable: the loop either returns or throws.
  throw new StoreConflictError();
}
