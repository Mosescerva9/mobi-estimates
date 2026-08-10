# Mobi LinkedIn Scout — browser extension

Owner-triggered Chrome / Safari extension for **Mobi LinkedIn Ops**.

Primary job: on a LinkedIn post you are viewing, **draft a comment**, let you
**approve** it, then **submit** it in LinkedIn’s comment box.

## What it does

**Does (only after you tap a button):**

- Reads the focused LinkedIn post (permalink page or centered feed card)
- Sends that post to your Mobi app to draft a comment
- After you tap **Approve & Post**, fills LinkedIn’s comment composer and clicks Post
- Marks the comment done in Mobi
- Optional: batch-capture visible feed posts into Scout

**Does not:**

- No background scraping, no auto-scroll, no likes/connects/DMs
- No remote code, analytics, or third-party network calls
- Never reads or stores your LinkedIn password
- Never logs the pairing token or puts it in a URL

LinkedIn’s page layout changes; if Post can’t be clicked, the text may still be
filled so you can click Post yourself.

## Daily use (comments)

1. In Mobi **Scout**, create a pairing code and paste it into the extension
2. Open the LinkedIn post you want to comment on
3. Extension → **Draft comment for this post**
4. Edit if you want → **Approve & Post**

If you already approved a draft in Engage: open that post → **Post an
already-approved comment**.

## Desktop Chrome

1. Open Chrome → `chrome://extensions`
2. Turn on **Developer mode**
3. **Load unpacked** → select this `safari-extension/` folder
4. Pair with the code from Scout (`https://mobi-linkedin-ops.vercel.app`)

After pulling updates, click **Reload** on the extension card.

## Files

| File | Purpose |
| --- | --- |
| `manifest.json` | MV3 manifest |
| `extract.js` | Read-only post extraction |
| `submit-comment.js` | Fill composer + click Post (owner-triggered) |
| `background.js` | Pairing token + API calls + script injection |
| `popup.*` | Setup + Draft / Approve & Post UI |
| `linkedin-page.mjs` | Which LinkedIn URLs are allowed |

## Permissions

- `storage` — app URL + pairing code on-device
- `scripting` + `activeTab` — run extract/submit only after you tap a button
- Hosts: `https://www.linkedin.com/*`, `https://mobi-linkedin-ops.vercel.app/*`

## Packaging for TestFlight / App Store

Apple's **Safari Web Extension Packager** in App Store Connect can package these
resources without a Mac/Xcode. Account-holder steps (Developer Program, app
record, upload, TestFlight/review) are still required. This folder is source
only until you package it.

## Privacy summary

- Data read: visible LinkedIn post text / author fields for posts you choose
- Data stored on device: app URL + pairing code
- Data sent: to your Mobi LinkedIn Ops app only
- No tracking / advertising identifiers / third-party sharing
