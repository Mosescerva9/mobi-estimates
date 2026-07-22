import { readFileSync, readdirSync, statSync } from "fs";
import { join, relative } from "path";
import { portalBaseUrl } from "../src/lib/site-url";

/**
 * Offline split-domain regression guard:
 *   - public marketing canonical URLs stay on https://mobiestimates.com;
 *   - authenticated signup/checkout/API handoffs use only approved paths on
 *     https://portal.mobiestimates.com;
 *   - no preview, GitHub Pages, or arbitrary portal URL reaches customers.
 */

const ROOT = join(__dirname, "..");
const SCAN_TARGETS = [
  "marketing-site/config.py",
  "marketing-site/generate.py",
  "marketing-site/build.py",
  "marketing-site/sitemap.xml",
  "marketing-site/robots.txt",
  "marketing-site",
  "src",
];
const FILE_EXTENSIONS = [".html", ".ts", ".tsx", ".py", ".xml", ".txt"];
const EXCLUDE = new Set([relative(ROOT, __filename)]);

const dot = String.raw`\.`;
const FORBIDDEN: { label: string; re: RegExp }[] = [
  {
    label: "legacy static host",
    re: new RegExp(`mosescerva9${dot}github${dot}io/stevens-${"transport"}-app`, "i"),
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

const APPROVED_PORTAL_URLS = [
  /^https:\/\/portal\.mobiestimates\.com$/,
  /^https:\/\/portal\.mobiestimates\.com\/api\/leads$/,
  /^https:\/\/portal\.mobiestimates\.com\/signup\?offer=first_estimate_free$/,
  /^https:\/\/portal\.mobiestimates\.com\/start\?plan=(starter|growth|estimating_department|pay_per_project)$/,
];
const PORTAL_URL = /https:\/\/portal\.mobiestimates\.com[^\s"'`<)]*/gi;

function walk(path: string, out: string[]): void {
  let st;
  try {
    st = statSync(path);
  } catch {
    return;
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
    for (const match of line.matchAll(PORTAL_URL)) {
      const url = match[0];
      if (!APPROVED_PORTAL_URLS.some((allowed) => allowed.test(url))) {
        violations.push(`${relative(ROOT, file)}:${i + 1}  [unapproved portal URL]  ${url}`);
      }
    }
  });
}

const portal = portalBaseUrl();
if (portal !== "https://portal.mobiestimates.com" && !process.env.NEXT_PUBLIC_PORTAL_URL) {
  violations.push(`portalBaseUrl() default is "${portal}", expected "https://portal.mobiestimates.com"`);
}

const marketingConfig = readFileSync(join(ROOT, "marketing-site/config.py"), "utf8");
if (!marketingConfig.includes('CANONICAL_BASE = "https://mobiestimates.com"')) {
  violations.push("marketing CANONICAL_BASE must remain https://mobiestimates.com");
}

if (violations.length > 0) {
  console.error(`FAIL: found ${violations.length} split-domain violation(s):\n`);
  for (const violation of violations) console.error("  " + violation);
  process.exit(1);
}

console.log(
  `PASS: scanned ${files.length} files; marketing remains on the apex and portal handoffs use approved paths only.`,
);
