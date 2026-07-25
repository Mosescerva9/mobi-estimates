# LinkedIn Marketing Ops (Mobi Estimating)

AI-assisted LinkedIn control panel for **Mobi Estimating**. This lives as a folder in the Mobi monorepo now and is structured so it can be copied into its own GitHub repo later.

## What it does

| Queue | AI role | Your control |
|-------|---------|--------------|
| **Posts** | Drafts LinkedIn posts from estimating topics | Edit → Approve & publish (or dry-run) |
| **Engage** | Drafts comments + connection notes | Approve → you copy/send from LinkedIn |
| **Warm DMs** | Drafts messages for people who already engaged | Approve → mark sent after you send |

Nothing engagement-related is autonomously posted by a browser bot. That keeps the company account safer and closer to LinkedIn’s rules.

## How you control it

1. Open the dashboard (`npm run dev` → http://localhost:3010)
2. **Posts** tab → Generate drafts → edit → **Approve & publish**
3. **Engage** tab → add a person/context → AI drafts → **Approve (copy & send)** → paste in LinkedIn
4. **Warm DMs** tab → add a warm lead + trigger → AI drafts → **Approve (copy DM)** → paste in LinkedIn → **Mark sent**
5. **Settings** → brand voice, ICP keywords, daily caps, do-not-contact list
6. Optional: set `OPS_PASSWORD` so the dashboard requires login
7. Use **Seed sample data** anytime to load a demo queue

## AI usage

- If `OPENAI_API_KEY` is set → drafts use OpenAI (`OPENAI_MODEL`, default `gpt-4o-mini`)
- If not set → local **mock** drafts (still useful for UI/workflow testing)

AI only writes drafts. Approval is always human.

## Quick start

```bash
cd linkedin-marketing-ops
npm install
cp .env.example .env.local
npm run seed
npm run dev
```

Open [http://localhost:3010](http://localhost:3010).

## Optional LinkedIn publish

Set in `.env.local`:

```env
LINKEDIN_ACCESS_TOKEN=...
LINKEDIN_AUTHOR_URN=urn:li:person:XXXX
```

Without these, **Approve & publish** runs in **dry-run** mode (status becomes `published` locally with a note).

## Layout

```text
linkedin-marketing-ops/
  src/app/           # Next.js app + API routes
  src/components/    # Control dashboard
  src/lib/           # store, AI, prompts, LinkedIn stub
  data/              # local JSON store (gitignored)
  scripts/seed.ts    # sample queue data
```

## Design choices (v1)

- **File JSON store** so you can run without Postgres
- **Assisted send** for comments/connects/DMs (no mass automation)
- **Warm-only DMs** with explicit triggers (`liked_post`, `demo_request`, etc.)
- Ready to extract: own `package.json`, own README, no imports from the parent app

## Next upgrades

1. Postgres/Supabase instead of `data/store.json`
2. LinkedIn OAuth connect flow for posting
3. Slack “approve/reject” buttons for the daily queue
4. CRM webhook → auto-create warm DM drafts on demo requests
5. Extract this folder into its own GitHub repo when ready
