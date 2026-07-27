# Mobi LinkedIn Scout — Safari Web Extension

An owner-triggered iPhone Safari extension that captures the LinkedIn feed posts
you can **already see on screen** and sends them to your Mobi LinkedIn Ops app,
where a separate on-demand job can draft comments for your approval.

It is deliberately minimal and read-only.

## What it does — and does not — do

**Does:**

- Reads only the top-level feed post containers currently visible when you tap
  **Capture visible posts**.
- Extracts only what is needed to ground a recommendation: the post permalink,
  the visible post text, and the author's visible name/headline.
- Validates every permalink against the same strict LinkedIn post-URL rules the
  server uses, de-duplicates, and caps at 25 items per capture.
- Uploads over HTTPS with a one-time pairing code (a Bearer token) that only the
  background service worker ever reads.

**Does not:**

- No auto-scrolling, clicking, liking, connecting, commenting, messaging, or
  following.
- No background or continuous scraping — it runs once, only when you tap Capture.
- No remote code, analytics, or third-party network calls.
- Never reads or stores your LinkedIn cookies or password.
- Never logs the pairing token, and never puts it in a URL.
- Ignores messaging (`/messaging/…`) and comment (`/comments/…`) pages entirely.

## Files

| File | Purpose |
| --- | --- |
| `manifest.json` | MV3 manifest, minimal permissions, two host permissions only. |
| `extract.js` | Dependency-free, read-only extraction + validation (also unit-tested in Node). |
| `background.js` | Service worker: reads config, runs a one-shot extraction, uploads with the Bearer token. |
| `popup.html` / `popup.css` / `popup.js` | One-time setup and the big **Capture** button. |
| `extract.test.js` | Deterministic unit tests (`node --test safari-extension/extract.test.js`). |

> Branded extension icons from 16px through 1024px are bundled under `icons/`
> and referenced by `manifest.json`. Confirm the generated containing-app icon
> in App Store Connect before TestFlight distribution.

## Permissions rationale

- `storage` — remembers your app URL and pairing code on-device only.
- `scripting` + `activeTab` — run the one-shot extractor in the LinkedIn tab you
  are looking at, only after you tap Capture.
- `host_permissions` — `https://www.linkedin.com/*` to read the visible feed, and
  `https://mobi-linkedin-ops.vercel.app/*` to upload. Nothing else.

## Daily use

1. In the Mobi app's **Scout** tab, create a pairing code (shown once) and copy it.
2. On iPhone, open the extension popup, paste your app URL and the pairing code,
   tap **Save & pair**.
3. Open LinkedIn in Safari, scroll to the posts you want, tap the extension, then
   **Capture visible posts**. You'll see how many were saved.
4. In Telegram, tell Hermes: **"Process my LinkedIn batch."**
5. Approve the resulting comment drafts in the app's **Engage** tab.

Use **Clear & re-pair** anytime to remove the stored code, and **Turn off
pairing** in the Scout tab to revoke it server-side.

## Desktop Chrome (fast alternative to App Store packaging)

You can use this same folder as an unpacked Chrome extension on a computer:

1. Open Chrome → `chrome://extensions`
2. Turn on **Developer mode**
3. Click **Load unpacked**
4. Select this `safari-extension/` folder
5. In Mobi Scout, create a pairing code and paste it into the extension settings
   with `https://mobi-linkedin-ops.vercel.app`
6. Open LinkedIn in Chrome, focus posts you want, click the extension → Capture

If LinkedIn’s page layout blocks extraction, use **Paste into Scout** in the
control panel instead — that path always works.

## Packaging for TestFlight / the App Store (verified Apple path)

Apple's current **Safari Web Extension Packager** can package and distribute
these resources from App Store Connect in any web browser, without a Mac or
Xcode:

1. Enroll the Apple account in the Apple Developer Program.
2. In App Store Connect, create an app record and select iOS.
3. Open the app's **Xcode Cloud** tab. Under **Safari Web Extension Packager**,
   choose **Upload** and upload the full contents of this folder.
4. Wait for the build to finish, resolve any compatibility report, then add the
   build to TestFlight for on-device testing.
5. After testing and required metadata are complete, submit the selected build
   for App Store review.

Apple states that the packager can create iOS and/or macOS apps and that its
compute is deducted from the Xcode Cloud time included with the Developer
Program membership.

**Account-holder actions still required:**

- Active Apple Developer Program enrollment.
- Creating the App Store Connect app record.
- Uploading the extension resources to the packager.
- TestFlight/App Store distribution, metadata, and review submission.

As an optional alternative, a Mac can use Xcode's Safari Web Extension
Converter and normal archive/sign flow. That path is no longer required for
packaging these resources.

> This folder is extension **source** prepared for that process. It has **not**
> been packaged, signed, or tested on a physical iPhone here. Treat the on-device
> selector behaviour as unverified until you run it on real LinkedIn in Safari,
> because LinkedIn's mobile DOM changes over time (the selectors use conservative
> fallbacks for exactly this reason).

## Privacy summary (for your App Store privacy form)

- Data read: publicly visible LinkedIn post text and author name/headline for
  posts you choose to capture.
- Data stored on device: your app URL and pairing code (in extension local
  storage). No credentials.
- Data sent: the captured posts, to your own Mobi LinkedIn Ops app only.
- No tracking, no advertising identifiers, no third-party sharing.
