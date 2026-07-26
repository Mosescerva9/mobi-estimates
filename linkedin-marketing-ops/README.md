# Mobi Estimating — LinkedIn Control Panel

A simple web app where an AI assistant writes your LinkedIn drafts and **you**
review and approve them. Nothing is ever posted or messaged automatically.

| Screen | What the assistant does | What you do |
|--------|-------------------------|-------------|
| **Posts** | Writes LinkedIn post drafts | Edit → **Approve & publish** (or a dry run) → or **Reject** |
| **Engage** | Writes comments & connection notes | Edit → **Approve & copy** → paste into LinkedIn |
| **Warm DMs** | Writes messages for people who already engaged | Edit → **Approve & copy** → paste → **Mark sent** |

Comments, connections, and DMs are always copy-and-paste by you. There is no
bot logging into LinkedIn, no auto-liking, and no cold or mass messaging.

---

## For the owner — your daily 5-step routine

You just need the web address (a normal `https://…` link) and your password.
Open it in any browser on your phone or computer. The same steps are on the
in-app **Help** screen.

1. **Open today's queue.** Everything waiting for you is on the **Today** screen,
   posts first. If it's empty, you're caught up.
2. **Review your posts.** Read each draft, edit the wording right in the box, and
   click **Approve & publish** (or **Reject** to discard). If LinkedIn isn't
   connected, approving saves it as a “dry run” so you can copy and post it by hand.
3. **Handle comments & connections.** On **Engage**, tweak the text and click
   **Approve & copy** — the text is copied for you. Paste it into LinkedIn.
4. **Send your warm DMs.** On **Warm DMs** (only people who already engaged),
   edit the message, click **Approve & copy**, paste it into LinkedIn, then click
   **Mark sent**.
5. **Adjust settings now and then.** On **Settings**, update your brand voice,
   keywords, link, and daily caps. Come back tomorrow and repeat.

Buttons you'll see: **Create drafts**, **Approve**, **Reject**, **Copy again**,
**Mark sent**. Status labels: **Needs approval**, **Approved**, **Published**,
**Sent**, **Rejected**.

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
4. **Deploy.** Open the URL Vercel gives you, enter your password, and start on
   the **Today** screen.

If the Supabase variables are missing in production, the app **stops with a clear
error instead of quietly losing your data** to temporary storage.

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
npm test        # status labels, store-mode fail-closed, AI helpers
npm run build
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
```

### API contract (unchanged)

- `GET /api/auth/status`, `POST /api/auth/login`, `POST /api/auth/logout`
- `GET /api/status`
- `GET /api/posts`, `POST /api/posts/generate`, `PATCH /api/posts/:id`
  (`edit` | `approve` | `reject` | `schedule`)
- `GET /api/engage`, `POST /api/engage`, `PATCH /api/engage/:id`
  (`edit` | `approve` | `reject` | `skip`)
- `GET /api/dms`, `POST /api/dms`, `PATCH /api/dms/:id`
  (`edit` | `approve` | `reject` | `mark_sent`)
- `GET`/`PATCH /api/settings`
- `POST /api/seed` (appends demo queue items; never erases existing data)

Item statuses: `draft`, `pending_approval`, `approved`, `scheduled`,
`published`, `sent`, `rejected`, `skipped`.
