# Hermes job — Process my LinkedIn Scout batch

On-demand job. It runs **only** when Moses asks in Telegram
("Process my LinkedIn batch"). Do **not** create or activate any schedule for it
in this implementation run.

## Runtime pinning (fail closed)

- Provider: `openai-codex`
- Model: `gpt-5.6-sol`

**Before doing anything else, confirm the active provider is `openai-codex` and
the active model is exactly `gpt-5.6-sol`.** If you cannot confirm both, STOP:
do not fetch, do not draft, do not submit. Report that the pinned model/runtime
could not be confirmed and exit. Never silently fall back to another model.

## What you may and may not do

- You **never** call LinkedIn or any LinkedIn API. You only read candidate text
  the owner already captured, and you write outcomes through the script below.
- You do **not** post, comment, connect, like, or message. Every qualified
  comment becomes a **pending** item the owner approves by hand in the app.
- Process **at most 20** candidates per run (the fetch endpoint already caps at
  20; never exceed it).

## Steps

1. **Fetch** the batch to a working file:

   ```sh
   python3 scripts/scout_job.py --env-file "$MOBI_SCOUT_ENV_FILE" \
     fetch --out /tmp/scout_batch.json
   ```

   The file contains `batchId`, `cap`, `commentMaxLength`, `skipReasons`, and a
   `candidates` array. If `candidates` is empty, report "nothing to process" and
   stop.

2. **Decide** an outcome for each candidate. For every candidate produce exactly
   one outcome object. Build an outcomes file of the shape:

   If a candidate has `"doNotContact": true`, submit `skip` with reason
   `do_not_contact` without drafting any comment.

   ```json
   {
     "batchId": "<the batchId from fetch>",
     "provider": "openai-codex",
     "model": "gpt-5.6-sol",
     "outcomes": [
       {
         "candidateId": "<id>",
         "decision": "qualify",
         "suggestedComment": "<grounded, specific, <= commentMaxLength chars>",
         "relevance": 0-100,
         "reason": "<one concise sentence, grounded in the post text>",
         "safety": "<why this is safe to comment on>"
       },
       {
         "candidateId": "<id>",
         "decision": "skip",
         "reason": "<one of the whitelisted skipReasons>"
       }
     ]
   }
   ```

3. **Submit** the outcomes:

   ```sh
   python3 scripts/scout_job.py --env-file "$MOBI_SCOUT_ENV_FILE" \
     submit --in /tmp/scout_outcomes.json --out /tmp/scout_result.json
   ```

4. Report back the `queued` and `skipped` counts. Remind Moses the drafts are
   waiting in **Engage** for his approval.

## Qualification rules

Qualify **only** when ALL of these hold:

- **Grounded:** the comment refers to something concretely stated in that post's
  `sourceText`. If you cannot ground it in the actual text, skip.
- **Relevant:** the post is about construction, general contracting, estimating,
  takeoffs, bidding, or the trades — Mobi's world. Otherwise skip `off_topic`.
- **Adds value:** the comment says something specific and useful. No generic
  praise ("Great post!", "So true!", "Congrats!"). No emojis-as-content.
- **No selling:** never pitch Mobi, never drop a link, never make an unsolicited
  promotion. This is a peer comment, not an ad.
- **Concise:** at or under `commentMaxLength` characters.

Skip (with the matching whitelisted `reason`) when the post is:

- sensitive or controversial (politics, layoffs, injuries, legal disputes,
  personal hardship) → `sensitive`
- low-information / nothing substantive to engage → `low_information`
- clearly a duplicate of another candidate for the same post → `duplicate`
- from someone on the do-not-contact list → `do_not_contact`
- too little post text to ground a reply → `insufficient_text`
- otherwise not a fit → `off_topic` or `other`

When in doubt, **skip**. A missed comment costs nothing; a bad or ungrounded one
costs trust. The owner still reviews everything you qualify before it goes live.
