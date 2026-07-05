import { readdirSync, readFileSync, statSync } from "fs";
import { join, relative } from "path";

/**
 * Regression guard for checkout-start links.
 *
 * `/start?plan=...` is a GET handoff that can create a Stripe Checkout Session,
 * so any Next.js <Link> pointing at it must opt out of prefetch. This script is
 * intentionally static/offline: it never starts checkout, never calls Stripe,
 * and never touches Supabase.
 */

const ROOT = process.cwd();
const SEARCH_DIRS = [join(ROOT, "src", "app"), join(ROOT, "src", "components")];
const TSX_EXT = ".tsx";

function walk(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      files.push(...walk(path));
    } else if (path.endsWith(TSX_EXT)) {
      files.push(path);
    }
  }
  return files;
}

function lineNumber(source: string, index: number): number {
  return source.slice(0, index).split("\n").length;
}

const failures: string[] = [];
let checked = 0;

for (const file of SEARCH_DIRS.flatMap(walk)) {
  const source = readFileSync(file, "utf8");
  const linkPattern = /<Link\b[\s\S]*?>/g;
  for (const match of source.matchAll(linkPattern)) {
    const tag = match[0];
    if (!tag.includes("/start?plan")) continue;
    checked += 1;
    if (!/\bprefetch=\{false\}/.test(tag)) {
      failures.push(`${relative(ROOT, file)}:${lineNumber(source, match.index ?? 0)} checkout-start Link missing prefetch={false}`);
    }
  }
}

if (checked === 0) {
  failures.push("No /start?plan checkout-start <Link> tags were found; update this guard if checkout CTAs moved.");
}

if (failures.length > 0) {
  console.error("Checkout prefetch safety check failed:");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}

console.log(`Checkout prefetch safety check passed (${checked} /start?plan Link tags).`);
