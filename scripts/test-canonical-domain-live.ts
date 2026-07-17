import assert from "node:assert/strict";

/**
 * Live production guard for the public Mobi website.
 *
 * The canonical public domain must serve the completed static marketing site,
 * not the Next.js portal/app homepage. This catches accidental Vercel domain
 * reassignment such as `mobiestimates.com` being attached to `mobi-portal`.
 *
 * This test is read-only: it fetches public pages and checks stable markers.
 */

async function fetchText(url: string): Promise<{ status: number; finalUrl: string; text: string; contentType: string | null }> {
  const res = await fetch(url, { redirect: "follow", cache: "no-store" });
  return {
    status: res.status,
    finalUrl: res.url,
    text: await res.text(),
    contentType: res.headers.get("content-type"),
  };
}

function assertMarketingPage(url: string, page: { status: number; finalUrl: string; text: string; contentType: string | null }): void {
  assert.equal(page.status, 200, `${url} must return 200`);
  assert.match(page.contentType ?? "", /text\/html/i, `${url} must return HTML`);

  // Stable markers from the completed marketing-site static design.
  assert.ok(page.text.includes("mobi-logo.png"), `${url} must include the completed marketing logo asset`);
  assert.ok(page.text.includes("Sample Estimate"), `${url} must include the marketing navigation`);
  assert.ok(page.text.includes("How It Works"), `${url} must include the marketing navigation`);
  assert.ok(
    page.text.includes("Outsourced construction estimating") ||
      page.text.includes("Bid more projects without hiring another estimator"),
    `${url} must include marketing-site positioning copy`,
  );

  // Marker from the wrong Next.js portal homepage that accidentally replaced the
  // public website on 2026-07-17. This must never be the public apex again.
  assert.ok(
    !page.text.includes("Review-assisted estimating support for contractors"),
    `${url} is serving the portal/app homepage instead of the marketing site`,
  );
}

async function main(): Promise<void> {
  const urls = [
    "https://mobiestimates.com/",
    "https://www.mobiestimates.com/",
    "https://mobiestimates.com/pricing.html",
    "https://mobiestimates.com/how-it-works.html",
  ];

  for (const url of urls) {
    const page = await fetchText(url);
    assertMarketingPage(url, page);
  }

  const portalLogin = await fetchText("https://portal.mobiestimates.com/login");
  assert.equal(portalLogin.status, 200, "portal.mobiestimates.com/login should remain available for the app");
  assert.ok(
    !portalLogin.text.includes("mobi-logo.png") || portalLogin.text.includes("Sign in"),
    "portal login should not be mistaken for the public marketing homepage",
  );

  console.log("PASS: canonical public domain serves marketing-site; portal remains on portal.mobiestimates.com.");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
