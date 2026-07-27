# Mobi Estimating — LinkedIn Control Panel

A simple web app where an AI assistant writes your LinkedIn drafts and **you**
approve them before anything is submitted.

| Screen | What the assistant does | What you do |
|--------|-------------------------|-------------|
| **Posts** | Writes LinkedIn post drafts | Edit → **Approve & publish** (or a dry run) → or **Reject** |
| **Engage** | Holds comment drafts & connection notes | Comment: **Approve & open for extension** → extension posts on LinkedIn. Note: **Approve & copy** |
| **Scout** | Pairing + optional paste/batch capture | Prefer drafting on the LinkedIn page via the extension |
| **Warm DMs** | Writes messages for people who already engaged | Edit → **Approve & copy** → paste → **Mark sent** |

**Comments (recommended):** open the LinkedIn post → Mobi extension → **Draft
comment for this post** → **Approve & Post**. The extension fills LinkedIn’s
comment box and clicks Post only after you approve. There is no unattended
botting, no auto-liking, and no cold or mass messaging.

> Official LinkedIn Community Management API commenting is not enabled. The
> owner-installed extension acts on the page you already have open, after approval.

---

## For the owner — your daily routine

You just need the web address (a normal `https://…` link) and your password.
Open it in any browser on your phone or computer. The same steps are on the
in-app **Help** screen.

1. **Open today's queue.** Everything waiting for you is on the **Today** screen,
   posts first. If it's empty, you're caught up.
2. **Review your posts.** On **Posts**, optionally pick an **Angle**, then
   **Create 3 drafts**. If a draft feels generic, click **Rewrite sharper**.
   Edit the wording, then **Approve & publish** (or **Reject**). If LinkedIn
   isn't connected, approving saves a dry run so you can post by hand.
3. **Comment on LinkedIn posts.** Pair the Chrome/Safari extension once (Scout
   tab). On a LinkedIn post: extension → **Draft comment for this post** →
   **Approve & Post**.
4. **Or finish Engage drafts.** **Approve & open for extension**, then on that
   LinkedIn tab tap **Post an already-approved comment**.
5. **Send warm DMs.** On **Warm DMs** (only people who already engaged),
   edit or **Rewrite**, **Approve & copy**, paste into LinkedIn, then **Mark sent**.
6. **Adjust settings now and then.** On **Settings**, update your brand voice,
   keywords, link, and daily caps. Come back tomorrow and repeat.

Buttons you'll see: **Create today's posts**, **Create 3 drafts**, **Rewrite sharper**,
**Approve & publish**, **Approve & open for extension**, **Approve & copy**,
**Draft comment for this post**, **Approve & Post**, **Mark commented**, **Mark sent**,
**Reject**. Status labels: **Needs approval**, **Ready to post**, **Published**,
**Commented**, **Rejected**.

---

## Deploying the hosted app (one-time setup)

This is a standard [Next.js](https://nextjs.org) app that runs great on
[Vercel](https://vercel.com). You do **not** need to run anything on your own
computer.

1. **Create a Supabase project** (free tier is fine). In the SQL editor, run the
   migration in `supabase/migrations/0001_linkedin_ops_state.sql`. This creates
   the table that stores your queue permanently.
2. **Import this app into Vercel** and set the project's root directory to
   `linkedin-marketing-ops`.
3. **Add environment variables** in Vercel → Project → Settings → Environment
   Variables (see `.env.example`):
   - `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` — **required.** From Supabase
     → Project Settings → API. These are server-only and never sent to browsers.
   - `OPS_PASSWORD` — the password to open the dashboard. **Required in
     production.** If it is missing on a hosted deployment, the dashboard locks
     itself and shows a configuration message instead of opening.
   - `OPENAI_API_KEY` — optional. Without it, the built-in draft writer is used.
   - `OPENAI_MODEL` — optional, defaults to `gpt-4o-mini`.
   - `LINKEDIN_ACCESS_TOKEN` and `LINKEDIN_AUTHOR_URN` — optional. Set both to let
     **Approve & publish** post to LinkedIn. Otherwise posts are dry-run only.
   - `SCOUT_JOB_TOKEN` — optional. Authorizes the on-demand Hermes worker that
     turns captured posts into comment drafts. If unset, the Scout job endpoints
     fail closed and no batches process. The iPhone pairing code is **not** an env
     var — you create it in the Scout tab.
4. **Deploy.** Open the URL Vercel gives you, enter your password, and start on
   the **Today** screen.

If the Supabase variables are missing in production, the app **stops with a clear
error instead of quietly losing your data** to temporary storage.

---

## Scout — draft & post comments (extension)

**Recommended:**

1. In **Scout**, create a pairing code (shown once)
2. Install the extension from `safari-extension/`
   - Desktop Chrome: `chrome://extensions` → Developer mode → **Load unpacked** → choose `safari-extension/`
   - iPhone Safari: Apple’s Safari Web Extension Packager / TestFlight (see that folder’s README)
3. Paste the pairing code into the extension
4. Open a LinkedIn post → **Draft comment for this post** → edit if needed → **Approve & Post**

**Backup (paste into Scout):**

1. Open a LinkedIn post → Share → Copy link
2. In Mobi → **Scout** → paste URL + post text → **Save to Scout**
3. Click **Draft comments now**
4. Approve in **Engage** → on LinkedIn use **Post an already-approved comment**

**Optional batch:** capture visible feed posts with the extension, then **Draft comments now** or Hermes (“Process my LinkedIn batch.”).

**Security:** pairing token is hashed; Hermes uses a separate `SCOUT_JOB_TOKEN`. Local
**Draft comments now** uses your logged-in session and does not need Hermes. Extension
draft/post endpoints (`/api/scout/draft-one`, `/api/scout/poster`) use the same
capture pairing token as capture.

**Verified Apple constraint:** Apple's Safari Web Extension Packager in **App
Store Connect** can package and distribute these extension resources from any
web browser, without a Mac or Xcode. It can create the iOS app/extension build
for TestFlight or App Store distribution. An active **Apple Developer Program**
membership, an **App Store Connect app record**, the packaging upload, beta/app
distribution, and review are still account-holder actions. This repo does not
perform those actions, and the extension has not yet been tested on a physical
iPhone. Xcode's Safari Web Extension Converter remains an optional Mac-based
alternative, not a requirement.

---

## What's under the hood

- **Durable storage:** your whole queue lives in one JSONB row in Supabase,
  reached through a server-only REST adapter. Writes use an optimistic
  compare-and-swap (a `linkedin_ops_state_cas` Postgres RPC checks the row's
  `updated_at`), so two overlapping requests can never silently overwrite each
  other — the loser gets a clear "reload and try again" (HTTP 409). Local
  development can fall back to a JSON file under `./data` (never used in
  production).
- **AI:** with `OPENAI_API_KEY` set, drafts come from OpenAI (`OPENAI_MODEL`,
  default `gpt-4o-mini`). Without it, high-quality built-in drafts are used. The
  assistant only writes drafts — **every approval is yours.**
- **Login:** on a hosted deployment `OPS_PASSWORD` is mandatory — with no
  password the dashboard fails closed (locked) rather than open. Locally you can
  leave it blank for convenience.
- **Assisted only:** comments, connections, and DMs are copied for you to paste.
  No browser automation, no auto-engagement, no cold/mass DMs.

---

## For developers

Local development uses a JSON file store, so you can run without Supabase.

```bash
cd linkedin-marketing-ops
npm install
cp .env.example .env.local   # leave SUPABASE_* blank for the local file store
npm run seed                 # optional: append sample drafts to ./data/store.json
npm run dev                  # http://localhost:3010
```

Checks:

```bash
npm run typecheck
npm run lint
npm test        # status labels, store-mode fail-closed, AI helpers, Scout logic/auth
npm run build

# Scout extension + Hermes job (not part of `npm test`):
node --test safari-extension/extract.test.js safari-extension/server-url.test.mjs safari-extension/linkedin-page.test.mjs
python3 -m py_compile scripts/scout_job.py
```

Project layout:

```text
linkedin-marketing-ops/
  src/app/                 # Next.js app + API routes (all force-dynamic)
  src/components/          # Control dashboard + status chips
  src/lib/                 # store, store-mode, ai, prompts, status, guide, auth
  src/lib/*.test.ts        # node:test unit tests
  supabase/migrations/     # linkedin_ops_state table
  data/                    # local JSON store (gitignored; dev only)
  safari-extension/        # iPhone Safari Web Extension source + its own README
  scripts/scout_job.py     # on-demand Hermes fetch/submit runner (stdlib only)
  ops/scout-hermes-job.md  # Hermes job prompt (on-demand; provider/model pinned)
```

### API contract (unchanged)

- `GET /api/auth/status`, `POST /api/auth/login`, `POST /api/auth/logout`
- `GET /api/status`
- `GET /api/posts`, `POST /api/posts/generate`, `PATCH /api/posts/:id`
  (`edit` | `approve` | `reject` | `schedule`)
- `GET /api/engage`, `POST /api/engage` (comments require a valid
  `sourcePostUrl`; a duplicate active comment for the same post is rejected 409),
  `PATCH /api/engage/:id` (`edit` | `approve` | `reject` | `skip` |
  `regenerate` | `mark_commented`). `mark_commented` is valid only for an
  approved comment and records `completedAt` (shown as **Commented**).
- `GET /api/dms`, `POST /api/dms`, `PATCH /api/dms/:id`
  (`edit` | `approve` | `reject` | `mark_sent`)
- `GET`/`PATCH /api/settings`
- `POST /api/seed` (appends demo queue items; never erases existing data)
- **Scout (owner-authenticated, behind login):** `GET /api/scout` (list + counts
  + pairing status, never the token hash); `POST`/`DELETE /api/scout/pairing`
  (create/rotate returns the plaintext code once; delete revokes);
  `PATCH /api/scout/:id` (`reject`).
- **Scout integration (own Bearer token, allowed through middleware):**
  `POST /api/scout/capture` (extension batch capture, capture token; ≤25 items);
  `POST /api/scout/draft-one` (extension: draft a comment for one focused post);
  `POST /api/scout/poster` (extension: `next` | `approve` | `complete` after
  human approval; page submit happens in the extension, not on the server);
  `GET /api/scout/job` (Hermes, `SCOUT_JOB_TOKEN`; ≤20 sanitized candidates + a
  batch id); `POST /api/scout/job` (Hermes; ≤20 outcomes — each qualify
  atomically creates one pending `EngageItem` bound to the source post,
  idempotent on retry; skips carry a whitelisted reason). Missing token config
  fails closed (503); no LinkedIn API calls from the server.

Item statuses: `draft`, `pending_approval`, `approved`, `scheduled`,
`published`, `sent`, `rejected`, `skipped`.
