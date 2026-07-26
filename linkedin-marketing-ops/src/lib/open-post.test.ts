import assert from "node:assert/strict";
import { test } from "node:test";
import { navigateOpenedTab, type OpenedTab } from "./open-post";

const POST_URL =
  "https://www.linkedin.com/posts/jordan-hale_bid-night-activity-7100000000000000000-abcd";

function fakeTab() {
  const tab: OpenedTab & { closed: boolean } = {
    location: { href: "about:blank" },
    closed: false,
    close() {
      this.closed = true;
    },
  };
  return tab;
}

test("navigates a pre-opened tab to a validated post URL", () => {
  const tab = fakeTab();
  const ok = navigateOpenedTab(tab, POST_URL);
  assert.equal(ok, true);
  assert.equal(tab.location.href, POST_URL);
  assert.equal(tab.closed, false);
});

test("closes the tab and refuses to navigate an unvalidated URL", () => {
  const tab = fakeTab();
  const ok = navigateOpenedTab(tab, "http://evil.example/x");
  assert.equal(ok, false);
  assert.equal(tab.closed, true);
  assert.equal(tab.location.href, "about:blank", "must never navigate to an unvalidated URL");
});

test("closes the tab when there is no URL at all", () => {
  const tab = fakeTab();
  assert.equal(navigateOpenedTab(tab, undefined), false);
  assert.equal(tab.closed, true);
});

test("returns false when the tab could not be opened (popup blocked)", () => {
  assert.equal(navigateOpenedTab(null, POST_URL), false);
  assert.equal(navigateOpenedTab(null, "http://evil.example/x"), false);
});
