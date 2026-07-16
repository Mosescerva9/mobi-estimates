# Skool classroom transcript extractor

Pulls closed-caption transcripts out of Skool classroom lessons that use the
native Skool/Mux player, for content **you have legitimate member access to**.
It drives a real, logged-in browser session (so the short-lived tokenized HLS
streams work) and writes one clean `.txt` per lesson.

## How it works

For each lesson the script tries two strategies in order:

1. **Clean path** — watches the player's network traffic, finds the WebVTT
   caption track Mux serves over HLS, and fetches *every* subtitle segment
   itself (inside your authenticated session) to assemble the complete
   transcript with no seeking. Used when it can produce a track covering ≥95% of
   the video's duration.
2. **Robust path** — if the clean path can't get a complete track, it plays the
   video, enables the text track, and seeks through the whole thing in ~5%
   steps. Mux only lazy-loads caption cues near the playhead, so the script
   **collects cues after every seek step** (the browser discards cues outside
   the buffer, so they can't all be read at the end).

Cue text is de-tagged, de-duplicated, and sorted by time before writing.

## Setup

```bash
cd tools/skool-transcript-extractor
python3 -m venv .venv && source .venv/bin/activate    # optional but recommended
pip install -r requirements.txt
playwright install chromium                            # one-time browser download
```

## Usage

1. Create your URL list:

   ```bash
   cp urls.txt.example urls.txt
   # then paste one lesson URL per line into urls.txt
   ```

2. Run it:

   ```bash
   python extract_transcripts.py
   ```

   - A **headed** Chromium window opens. On the **first run** it stops and prints
     `Log into Skool, then press Enter` — log in by hand in that window, then
     press Enter in the terminal. Your session is saved to `.browser-profile/`,
     so later runs skip the login. The script never asks for your password.
   - Transcripts are written to `transcripts/<lesson-title>.txt`.
   - Re-running is safe: lessons whose output already exists are **skipped**.
     Failures are logged and the run continues to the next URL.

   Force the login pause again anytime (e.g. session expired):

   ```bash
   python extract_transcripts.py --login
   ```

### Options

| Flag | Default | Purpose |
|------|---------|---------|
| `--urls PATH` | `urls.txt` | file with one lesson URL per line |
| `--out DIR` | `transcripts/` | output directory |
| `--profile DIR` | `.browser-profile/` | persistent login/profile directory |
| `--login` | off | force the manual-login pause |
| `--step FLOAT` | `0.05` | seek step as a fraction of duration (robust path) |
| `--wait INT` | `700` | ms to wait at each seek step |
| `--chrome-path PATH` | auto | explicit Chromium binary (only if Playwright can't find its own) |

## Verifying a run is complete

The whole point of the robust path is to beat Mux's lazy caption loading, so
**check the first lesson before trusting the batch**:

- The per-lesson log prints `coverage NN%`. Anything below ~90% on the robust
  path prints a warning — the transcript may be missing the tail.
- Open `transcripts/<that lesson>.txt` and confirm the last lines match the end
  of the video.
- If a long lesson comes up short, captions were probably loading slower than
  the seek cadence. Slow it down:

  ```bash
  python extract_transcripts.py --wait 1200 --step 0.03
  ```

  Then delete that lesson's `.txt` (and its entry in `transcripts/.index.json`)
  and re-run so it re-extracts.

## Notes / limitations

- Only for content you're entitled to access. It uses *your* login; it doesn't
  bypass any paywall or access control.
- If a lesson has **no captions**, you'll see `no cues found` and no file is
  written.
- Selector heuristics for the lesson **title** (`get_title`) target Skool's
  current DOM. If titles come out as URL slugs, the classroom markup changed —
  update the selector list in `get_title()`; caption extraction is unaffected.
- `.browser-profile/`, `urls.txt`, and `transcripts/` are git-ignored — they're
  your session and your data.
```
