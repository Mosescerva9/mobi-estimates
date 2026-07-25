import { promises as fs } from "fs";
import path from "path";
import { DEFAULT_SETTINGS } from "./prompts";
import type { StoreData } from "./types";

const DATA_DIR = path.join(process.cwd(), "data");
const STORE_PATH = path.join(DATA_DIR, "store.json");

function emptyStore(): StoreData {
  return {
    settings: { ...DEFAULT_SETTINGS },
    posts: [],
    engage: [],
    dms: [],
  };
}

async function ensureStore(): Promise<void> {
  await fs.mkdir(DATA_DIR, { recursive: true });
  try {
    await fs.access(STORE_PATH);
  } catch {
    await fs.writeFile(STORE_PATH, JSON.stringify(emptyStore(), null, 2), "utf8");
  }
}

export async function readStore(): Promise<StoreData> {
  await ensureStore();
  const raw = await fs.readFile(STORE_PATH, "utf8");
  const parsed = JSON.parse(raw) as StoreData;
  return {
    settings: { ...DEFAULT_SETTINGS, ...parsed.settings },
    posts: parsed.posts ?? [],
    engage: parsed.engage ?? [],
    dms: parsed.dms ?? [],
  };
}

export async function writeStore(data: StoreData): Promise<void> {
  await ensureStore();
  const tmp = `${STORE_PATH}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(data, null, 2), "utf8");
  await fs.rename(tmp, STORE_PATH);
}

export async function updateStore(
  mutator: (data: StoreData) => StoreData | void
): Promise<StoreData> {
  const current = await readStore();
  const next = mutator(current) ?? current;
  await writeStore(next);
  return next;
}
