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
const homeText = home.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
const pricing = read("marketing-site/pricing.html");
const privacy = read("marketing-site/privacy.html");
const js = read("marketing-site/assets/js/site.js");
const route = read("src/app/api/leads/route.ts");
const helper = read("src/lib/lead-capture-server.ts");
const leadLib = read("src/lib/lead-capture.ts");
const sitemap = read("marketing-site/sitemap.xml");
const portalHome = read("src/app/page.tsx");
const portalVideo = read("src/components/ExplainerVideo.tsx");
const portalVideoConfig = read("src/lib/explainer-video.ts");
const introOffer = read("src/lib/intro-offer.ts");

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
  ["approved FleetBuilt offer and contact CTA are rendered", () => {
    assert(home.includes("Feasibility Blueprint"), "Blueprint offer missing");
    assert(home.includes("$2,500"), "Blueprint fee missing");
    assert(home.includes("$15,000"), "founding fee missing");
    assert(home.includes("moses@fleetbuiltpartners.com"), "public email missing");
    assert(home.includes("Discuss the Blueprint"), "primary CTA missing");
    assert(!home.includes("https://portal.mobiestimates.com"), "Mobi portal checkout must not remain on the marketing homepage");
    assert(!home.includes("Book a Free Estimate"), "retired Mobi CTA remains on homepage");
    assert(portalHome.includes("Book a Free Estimate"), "portal homepage primary CTA missing");
    assert(introOffer.includes('INTRO_OFFER_CTA = "Book a Free Estimate"'), "portal CTA source of truth drifted");
  }],
  ["premium homepage contract and in-page video link are rendered", () => {
    for (const text of [
      "You supply the trucks. We help you build the training operation.",
      "Stop searching for CDL drivers.",
      "A Blueprint, then founding implementation if you proceed",
      "What fleets run into",
      "Discuss a Feasibility Blueprint",
    ]) assert(homeText.includes(text), `generated homepage visible text missing: ${text}`);
    assert(home.includes('href="#explainer-video"'), "hero secondary link must target explainer section");
    assert(home.includes('id="explainer-video"'), "explainer section ID missing");
    assert(home.includes("family=Poppins"), "generated homepage must load Poppins");
    assert(!home.includes("Plus+Jakarta") && !home.includes("Fraunces"), "retired homepage fonts remain");
    assert(!/turnkey/i.test(home), "homepage must not use turnkey language");
    assert(!/FMCSA certified/i.test(home), "homepage must not claim FMCSA certification");
  }],
  ["video placeholder is temporary, 16:9, and has no fake source", () => {
    assert(home.includes("Temporary preview · final explainer video coming soon"), "static placeholder is not clearly temporary");
    assert(portalHome.includes('href="#explainer-video"'), "portal secondary CTA must scroll to video");
    assert(portalVideo.includes("aspect-video"), "portal video is not constrained to 16:9");
    assert(portalVideo.includes("Temporary development preview"), "portal placeholder is not clearly temporary");
    assert(portalVideoConfig.includes('src: ""'), "portal placeholder must not ship a fake video source");
  }],
  ["no fabricated testimonials or customer logos are rendered", () => {
    assert(!home.includes('class="quote-card"'), "homepage must not render unverified testimonials");
    assert(!/trusted by.+(?:customer|contractor)/i.test(home), "homepage must not claim unverified customer trust");
  }],
  ["generated pages avoid estimator-replacement and blanket-coverage claims", () => {
    for (const pattern of [
      /replaces? the traditional estimating department/i,
      /can mobi replace our internal estimator/i,
      /serve as your primary estimating resource/i,
      /estimating for every sector of construction/i,
      /whatever you're bidding/i,
      /an entire estimating department/i,
      /everything you need to submit a stronger bid/i,
      /\ball trades\b/i,
      /\ball project types\b/i,
      /\ball csi divisions\b/i,
      /fast turnaround options/i,
      /without missing deadlines/i,
      /bid faster and more competitively/i,
      /primary outsourced estimating resource/i,
      /across every division/i,
      /scale without hiring/i,
      /watch a 2-minute overview/i,
      /complete estimating service and operating system/i,
      /\("Coverage when one person is unavailable",\s*"No",\s*"No",\s*"Included"\)/i,
      /\bcompetitive\b/i,
      /every cost accounted for/i,
      /bid more work/i,
      /pursue more(?: full-project)? bids?/i,
      /fast,\s*detailed takeoffs/i,
      /a number they can stand behind/i,
      /price faster and bid more/i,
      /primary or ongoing estimating resource/i,
      /bid more consistently/i,
      /stop turning down profitable work/i,
      /handle more bidding opportunities with a faster/i,
      /dependable estimating capacity exactly when/i,
      /estimating department you can scale/i,
      /bid more projects without hiring another estimator/i,
      /fast turnaround/i,
    ]) {
      assert(!pattern.test(generated), `generated marketing HTML contains overbroad claim: ${pattern}`);
      assert(!pattern.test(source), `marketing source contains overbroad claim: ${pattern}`);
    }
  }],
  ["homepage collapses to the locked compact eight-block rhythm", () => {
    // The visual-director directive removed the standalone dashboard-milestones,
    // bid-follow-up, internal-hire-comparison, FAQ, and duplicate collaboration
    // bands from the HOME page (their content remains on dedicated routes). The
    // home page now follows the compact eight-block Togal rhythm.
    for (const removed of [
      "Customer dashboard",
      "Stay organized through bid follow-up",
      "Contractor-controlled collaboration",
      "Common questions",
      "Add estimating capacity without building another department first",
    ]) assert(!home.includes(removed), `homepage must not re-introduce retired section: ${removed}`);
    // Exactly one dark accent band on the homepage (the multi-trade capability band).
    assert((home.match(/band-dark/g) ?? []).length === 1, "homepage must have exactly one dark accent band");
    // Real-proof structures are present but hidden until genuine content exists.
    assert(home.includes("hidden until real"), "hidden-until-real proof placeholders missing");
    assert(home.includes("What fleets run into"), "problems / dark-band copy missing");
  }],
  ["locked FleetBuilt prices are rendered and Mobi checkout prices are gone", () => {
    for (const price of ["$2,500", "$15,000"]) {
      assert(pricing.includes(price), `pricing page missing ${price}`);
    }
    for (const retired of ["$599", "$995", "$1,995", "$2,995"]) {
      assert(!pricing.includes(retired), `pricing page still shows retired Mobi price ${retired}`);
    }
    assert(pricing.includes("60 days"), "60-day Blueprint credit language missing");
    assert(!pricing.includes("portal.mobiestimates.com"), "Mobi Stripe/portal checkout remains on pricing");
  }],
  ["work-email consent and privacy disclosure are public", () => {
    const consent = "By submitting, you agree FleetBuilt Partners may contact you about Blueprint or founding-implementation support. You can unsubscribe at any time.";
    assert(home.includes(consent), "homepage consent copy missing");
    assert(home.includes('href="privacy.html"'), "homepage privacy link missing");
    assert(privacy.includes("Contact-form data"), "privacy page does not disclose form capture");
    assert(privacy.includes("marketing attribution fields"), "privacy page does not disclose attribution fields");
  }],
  ["generated marketing UI copy has no leftover Mobi Estimates branding", () => {
    assert(!/Mobi Estimates/i.test(generated), "generated marketing HTML still names Mobi Estimates");
    assert(!/mobiestimates\.com/i.test(generated), "generated marketing HTML still points at mobiestimates.com");
    assert(!/Book a Free Estimate/i.test(generated), "generated marketing HTML still uses the Mobi CTA");
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
