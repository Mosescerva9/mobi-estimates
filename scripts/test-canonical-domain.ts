import { readFileSync, readdirSync, statSync } from "fs";
import { join, relative } from "path";
import { publicBaseUrl } from "../src/lib/site-url";

/**
 * Offline regression guard: customer-facing marketing output and checkout code
 * must never route customers to a fake/staging/preview/portal host. If any of
 * these strings reappears in a scanned file, a marketing link, canonical URL,
 * Stripe return URL, or email default has regressed to the wrong domain.
 *
 * This scans real source/generated files only (not internal prose docs), so a
 * benign mention of an old host in a top-level *.md changelog won't trip it.
 */

const ROOT = join(__dirname, "..");

// Files/dirs that are customer-facing (marketing output, generators, checkout
// code, email). Everything reachable here is scanned recursively.
const SCAN_TARGETS = [
  "marketing-site/config.py",
  "marketing-site/generate.py",
  "marketing-site/build.py",
  "marketing-site/sitemap.xml",
  "marketing-site/robots.txt",
  "marketing-site", // *.html marketing pages (see FILE_EXTENSIONS filter)
  "src",
];

const FILE_EXTENSIONS = [".html", ".ts", ".tsx", ".py", ".xml", ".txt"];

// This test file itself contains the forbidden strings (as patterns), so it
// must be excluded from the scan.
const EXCLUDE = new Set([relative(ROOT, __filename)]);

const dot = String.raw`\.`;
const FORBIDDEN: { label: string; re: RegExp }[] = [
  {
    label: "legacy static host",
    re: new RegExp(`mosescerva9${dot}github${dot}io/stevens-${"transport"}-app`, "i"),
  },
  {
    label: "old portal subdomain",
    re: new RegExp(`portal${dot}mobiestimates${dot}com`, "i"),
  },
  {
    label: "portal Vercel preview",
    re: new RegExp(`mobi-portal[\\w-]*${dot}vercel${dot}app`, "i"),
  },
  {
    label: "marketing Vercel preview",
    re: new RegExp(`mobi-marketing-site[\\w-]*${dot}vercel${dot}app`, "i"),
  },
];

function walk(path: string, out: string[]): void {
  let st;
  try {
    st = statSync(path);
  } catch {
    return; // target may not exist in every checkout
  }
  if (st.isDirectory()) {
    if (path.includes("node_modules") || path.includes(".next") || path.includes(".git")) return;
    for (const entry of readdirSync(path)) walk(join(path, entry), out);
    return;
  }
  const rel = relative(ROOT, path);
  if (EXCLUDE.has(rel)) return;
  if (!FILE_EXTENSIONS.some((ext) => path.endsWith(ext))) return;
  out.push(path);
}

const files: string[] = [];
for (const target of SCAN_TARGETS) walk(join(ROOT, target), files);

const violations: string[] = [];
for (const file of Array.from(new Set(files))) {
  const text = readFileSync(file, "utf8");
  const lines = text.split("\n");
  lines.forEach((line, i) => {
    for (const { label, re } of FORBIDDEN) {
      if (re.test(line)) {
        violations.push(`${relative(ROOT, file)}:${i + 1}  [${label}]  ${line.trim()}`);
      }
    }
  });
}

// Positive assertion: the app's public base URL default must be the real site.
const base = publicBaseUrl();
if (base !== "https://mobiestimates.com" && !process.env.NEXT_PUBLIC_SITE_URL) {
  violations.push(`publicBaseUrl() default is "${base}", expected "https://mobiestimates.com"`);
}

if (violations.length > 0) {
  console.error(`FAIL: found ${violations.length} forbidden customer-facing domain reference(s):\n`);
  for (const v of violations) console.error("  " + v);
  console.error(
    "\nCustomer-facing marketing/checkout URLs must use https://mobiestimates.com. " +
      "Update config/source and regenerate marketing-site output.",
  );
  process.exit(1);
}

console.log(`PASS: scanned ${files.length} files; no forbidden customer-facing domains found.`);
