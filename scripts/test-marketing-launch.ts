import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const root = process.cwd();
const read = (path: string) => readFileSync(join(root, path), "utf8");
const marketing = join(root, "marketing-site");
const htmlFiles = readdirSync(marketing).filter((name) => name.endsWith(".html")).sort();
const generated = htmlFiles.map((name) => read(`marketing-site/${name}`)).join("\n");
const source = [
  read("marketing-site/config.py"),
  read("marketing-site/build.py"),
  read("marketing-site/generate.py"),
].join("\n");
const home = read("marketing-site/index.html");
const pricing = read("marketing-site/pricing.html");
const privacy = read("marketing-site/privacy.html");
const js = read("marketing-site/assets/js/site.js");
const route = read("src/app/api/leads/route.ts");
const helper = read("src/lib/lead-capture-server.ts");
const leadLib = read("src/lib/lead-capture.ts");
const sitemap = read("marketing-site/sitemap.xml");

const tests: Array<[string, () => void]> = [
  ["canonical generator produced the expected page inventory", () => {
    assert(htmlFiles.length === 28, `expected 28 root HTML files, found ${htmlFiles.length}`);
    assert((sitemap.match(/<url>/g) ?? []).length === 26, "sitemap must contain 26 canonical URLs");
  }],
  ["retired promotion and turnaround promises are absent", () => {
    const forbidden = [
      /50% off/i,
      /first[- ]month discount/i,
      /in as little as 48/i,
      /48[- ]hour/i,
      />\s*Join Now\s*</i,
      /Preview copy/i,
      /pending legal review/i,
    ];
    for (const pattern of forbidden) {
      assert(!pattern.test(generated), `generated marketing HTML contains retired copy: ${pattern}`);
      assert(!pattern.test(source), `marketing source contains retired copy: ${pattern}`);
    }
  }],
  ["approved offer and portal CTA are rendered", () => {
    assert(home.includes("One qualifying estimate per new company. No card required."), "approved offer summary missing");
    assert(home.includes("Supported scope and project complexity are reviewed before acceptance."), "qualification rule missing");
    assert(home.includes("https://portal.mobiestimates.com/signup?offer=first_estimate_free"), "portal offer URL missing");
    assert(home.includes("Start Your Free Estimate"), "primary CTA missing");
  }],
  ["dashboard milestones and bid follow-up are rendered", () => {
    for (const text of [
      "Customer dashboard",
      "Qualification & document review",
      "Scope & takeoff",
      "Pricing & quality review",
      "Ready after approval",
      "Stay organized through bid follow-up",
      "does not promise that a bid will be won",
    ]) assert(home.includes(text), `homepage missing: ${text}`);
  }],
  ["regular paid prices remain unchanged", () => {
    for (const price of ["$599", "$995", "$1,995", "$2,995"]) {
      assert(pricing.includes(price), `pricing page missing ${price}`);
    }
  }],
  ["work-email consent and privacy disclosure are public", () => {
    const consent = "By submitting, you agree Mobi may contact you about your estimate request and related services. You can unsubscribe at any time.";
    assert(home.includes(consent), "homepage consent copy missing");
    assert(leadLib.includes(consent), "portal consent copy drifted");
    assert(home.includes('href="privacy.html"'), "homepage privacy link missing");
    assert(privacy.includes("Work-email offer captures"), "privacy page does not disclose email capture");
    assert(privacy.includes("marketing attribution fields"), "privacy page does not disclose attribution fields");
  }],
  ["lead API is bounded to approved origins and JSON", () => {
    assert(route.includes('"https://mobiestimates.com"'), "apex origin missing");
    assert(route.includes('"https://www.mobiestimates.com"'), "www origin missing");
    assert(!route.includes('"Access-Control-Allow-Origin": "*"'), "wildcard CORS is forbidden");
    assert(route.includes('contentType !== "application/json"'), "JSON content-type guard missing");
    assert(route.includes("MAX_BODY_BYTES = 4096"), "body-size guard missing");
    assert(route.includes("process.env.NODE_ENV === \"production\""), "localhost must fail closed in production");
  }],
  ["lead storage is narrow and no sender is integrated", () => {
    assert(helper.includes('import "server-only"'), "lead persistence helper must be server-only");
    assert(helper.includes("parseLeadCapture(input)"), "normalization must precede persistence");
    assert(helper.includes('.from("lead_captures")'), "lead helper must target only lead_captures");
    const blob = `${route}\n${helper}\n${js}`.toLowerCase();
    for (const forbidden of ["twilio", "resend", "sendemail", "sendsms", "stripe", "openai"]) {
      assert(!blob.includes(forbidden), `lead path must not integrate ${forbidden}`);
    }
    assert(js.includes('credentials: "omit"'), "cross-origin lead request must omit credentials");
    assert(js.includes("if (!response.ok) throw"), "API failures must not display success");
  }],
];

let failures = 0;
for (const [name, test] of tests) {
  try {
    test();
    console.log(`  PASS  ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`  FAIL  ${name}`);
    console.error(`        ${error instanceof Error ? error.message : String(error)}`);
  }
}
console.log(`\n${tests.length - failures}/${tests.length} passed`);
if (failures) process.exit(1);
