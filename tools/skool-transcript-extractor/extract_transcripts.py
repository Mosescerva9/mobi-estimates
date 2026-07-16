#!/usr/bin/env python3
"""
Skool classroom transcript extractor.

Extracts closed-caption transcripts from Skool classroom lessons that use the
native (Mux / hls.js) player, for content you have legitimate member access to.

Two extraction strategies, tried in order per lesson:

  1. CLEAN PATH  -- Intercept the player's network traffic and grab the WebVTT
     caption track. Mux serves captions over HLS as a subtitle playlist (.m3u8)
     that points at a set of .vtt segments. When we can see that playlist we
     fetch *every* segment ourselves (inside the authenticated browser session,
     so the short-lived tokens are valid) and stitch the full transcript
     together deterministically -- no seeking required.

  2. ROBUST PATH -- If the clean path can't produce a complete track, fall back
     to driving the player: start playback, enable the text track, and seek
     through the whole video in small steps. Mux lazy-loads caption cues only
     for the region around the playhead, so we accumulate cues in Python after
     every seek step (cues outside the buffer get discarded by the browser, so
     we can't read them all at the end -- we collect as we go).

Login: launches a HEADED, persistent Chromium so your Skool session survives
between runs. On first run it pauses for you to log in by hand. It never asks
for or stores your password.

Usage:
    python extract_transcripts.py                # read urls.txt, write transcripts/
    python extract_transcripts.py --login        # force the manual-login pause
    python extract_transcripts.py --urls my.txt --out out/ --step 0.04

See README.md for setup and the live-verification checklist.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

# --------------------------------------------------------------------------- #
# Defaults (override on the command line)
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
DEFAULT_URLS = HERE / "urls.txt"
DEFAULT_OUT = HERE / "transcripts"
DEFAULT_PROFILE = HERE / ".browser-profile"   # persistent user-data dir (git-ignored)

# Robust-path tuning. Mux needs a beat to fetch the caption segment for each
# seek target; too small a wait and you miss cues, too large and runs crawl.
SEEK_STEP_FRACTION = 0.05     # ~5% of the video per seek step
SEEK_WAIT_MS = 700            # pause at each step so cues can load
NAV_TIMEOUT_MS = 60_000
METADATA_TIMEOUT_S = 30       # how long to wait for the <video> to report a duration

# Chromium bundled with this environment (Playwright finds it via
# PLAYWRIGHT_BROWSERS_PATH, so we normally don't set executable_path).
CHROME_ARGS = ["--autoplay-policy=no-user-gesture-required"]


# --------------------------------------------------------------------------- #
# WebVTT parsing
# --------------------------------------------------------------------------- #
_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_CUE_TIMING = re.compile(
    r"(?P<start>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?P<end>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})"
)
_TAG = re.compile(r"<[^>]+>")           # <c>, <v Bob>, <00:00:01.000> karaoke ts
_WS = re.compile(r"[ \t]+")


def _ts_to_seconds(ts: str) -> float:
    m = _TS.match(ts.strip())
    if not m:
        return 0.0
    hh, mm, ss, ms = m.groups()
    hh = int(hh) if hh else 0
    return hh * 3600 + int(mm) * 60 + int(ss) + int(ms.ljust(3, "0")) / 1000.0


def _clean_cue_text(raw: str) -> str:
    text = _TAG.sub("", raw)
    text = text.replace("&nbsp;", " ")
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    # Cue text can be multi-line; collapse to a single spaced line.
    text = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return _WS.sub(" ", text).strip()


def parse_vtt(content: str) -> list[dict]:
    """Parse WebVTT text into [{start, end, text}] cues. Ignores NOTE/STYLE."""
    cues: list[dict] = []
    # Split into blocks on blank lines.
    for block in re.split(r"\r?\n\r?\n", content):
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        if lines[0].strip().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            # A block can start with WEBVTT header + a following timing line only
            # in malformed files; safe to skip these headers.
            if not any(_CUE_TIMING.search(ln) for ln in lines):
                continue
        # Find the timing line; an optional cue id sits above it.
        timing_idx = next((i for i, ln in enumerate(lines) if _CUE_TIMING.search(ln)), None)
        if timing_idx is None:
            continue
        m = _CUE_TIMING.search(lines[timing_idx])
        start = _ts_to_seconds(m.group("start"))
        end = _ts_to_seconds(m.group("end"))
        text = _clean_cue_text("\n".join(lines[timing_idx + 1:]))
        if text:
            cues.append({"start": start, "end": end, "text": text})
    return cues


def normalize_cues(cues: list[dict]) -> list[dict]:
    """Strip markup/entities from cue text (needed for cues read via textTracks,
    whose .text still contains VTT tags) and drop cues that clean to empty."""
    out = []
    for c in cues:
        text = _clean_cue_text(c.get("text", ""))
        if text:
            out.append({"start": float(c["start"]), "end": float(c["end"]), "text": text})
    return out


def dedupe_and_sort(cues: list[dict]) -> list[dict]:
    """Normalize, sort by start time, and drop duplicate cues (rounded start + text)."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for c in sorted(normalize_cues(cues), key=lambda x: (x["start"], x["end"])):
        key = (round(c["start"], 2), c["text"])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def cues_to_transcript(cues: list[dict], title: str, url: str) -> str:
    """Render cues to clean prose: one line per cue, consecutive dups collapsed."""
    lines: list[str] = []
    prev = None
    for c in cues:
        t = c["text"]
        if t and t != prev:
            lines.append(t)
            prev = t
    header = [f"# {title}".rstrip(), f"# Source: {url}", ""]
    return "\n".join(header + lines) + "\n"


def coverage(cues: list[dict], duration: float) -> float:
    """Fraction of the video's duration covered by the last cue's end time."""
    if not cues or not duration or duration <= 0:
        return 0.0
    return min(1.0, max(c["end"] for c in cues) / duration)


# --------------------------------------------------------------------------- #
# Filenames
# --------------------------------------------------------------------------- #
def slugify(value: str, fallback: str = "lesson") -> str:
    value = value.strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_-]+", "-", value).strip("-")
    return value[:120] or fallback


def slug_from_url(url: str) -> str:
    p = urlparse(url)
    parts = [seg for seg in p.path.split("/") if seg]
    tail = "-".join(parts[-2:]) if parts else p.netloc
    return slugify(tail or url, fallback="lesson")


# --------------------------------------------------------------------------- #
# Browser-side JS
# --------------------------------------------------------------------------- #
JS_PREPARE_PLAYER = """
async () => {
  const v = document.querySelector('video');
  if (!v) return { ok: false, reason: 'no <video> element found' };
  v.muted = true;
  // play() can hang if the media isn't ready; never let it block the run.
  try {
    await Promise.race([
      v.play().catch(() => {}),
      new Promise((r) => setTimeout(r, 3000)),
    ]);
  } catch (e) { /* autoplay may be blocked; seeking still drives caption loads */ }
  const tracks = v.textTracks || [];
  let enabled = 0;
  for (let i = 0; i < tracks.length; i++) {
    // 'showing' forces hls.js/Mux to fetch the subtitle segments near the playhead.
    tracks[i].mode = 'showing';
    enabled++;
  }
  return {
    ok: true,
    tracks: tracks.length,
    enabled,
    duration: (isFinite(v.duration) ? v.duration : 0),
    readyState: v.readyState,
  };
}
"""

JS_DURATION = """
() => {
  const v = document.querySelector('video');
  return v && isFinite(v.duration) ? v.duration : 0;
}
"""

JS_ENSURE_TRACKS_SHOWING = """
() => {
  const v = document.querySelector('video');
  if (!v) return 0;
  const tt = v.textTracks || [];
  for (let i = 0; i < tt.length; i++) {
    if (tt[i].mode === 'disabled') tt[i].mode = 'showing';
  }
  return tt.length;
}
"""

JS_SEEK = """
(t) => {
  const v = document.querySelector('video');
  if (v) { try { v.currentTime = t; } catch (e) {} }
}
"""

JS_READ_CUES = """
() => {
  const v = document.querySelector('video');
  const out = [];
  if (!v) return out;
  const tt = v.textTracks || [];
  for (let i = 0; i < tt.length; i++) {
    const cues = tt[i].cues;
    if (!cues) continue;
    for (let j = 0; j < cues.length; j++) {
      const c = cues[j];
      if (typeof c.text === 'string') {
        out.push({ start: c.startTime, end: c.endTime, text: c.text });
      }
    }
  }
  return out;
}
"""


# --------------------------------------------------------------------------- #
# HLS subtitle stitching (clean path)
# --------------------------------------------------------------------------- #
def _is_master_playlist(text: str) -> bool:
    return "#EXT-X-STREAM-INF" in text or "TYPE=SUBTITLES" in text


def _subtitle_uris_from_master(text: str, base_url: str) -> list[str]:
    """Pull subtitle rendition URIs out of an HLS master playlist."""
    uris = []
    for line in text.splitlines():
        if line.startswith("#EXT-X-MEDIA") and "TYPE=SUBTITLES" in line:
            m = re.search(r'URI="([^"]+)"', line)
            if m:
                uris.append(urljoin(base_url, m.group(1)))
    return uris


def _looks_like_vtt_media_playlist(text: str) -> bool:
    if "#EXTM3U" not in text:
        return False
    return ".vtt" in text or ".webvtt" in text or "vtt" in text.lower()


def _segment_uris(text: str, base_url: str) -> list[str]:
    return [
        urljoin(base_url, line.strip())
        for line in text.splitlines()
        if line.strip() and not line.startswith("#")
    ]


async def try_hls_subtitles(request, m3u8_urls: list[str], log) -> list[dict]:
    """
    Given m3u8 URLs seen on the wire, resolve a full WebVTT caption track by
    fetching every subtitle segment ourselves. Returns parsed cues (possibly
    empty). `request` is a Playwright APIRequestContext bound to the logged-in
    session, so tokenized URLs authenticate correctly.
    """
    visited: set[str] = set()
    queue = list(dict.fromkeys(m3u8_urls))  # de-dup, keep order
    all_cues: list[dict] = []

    async def fetch_text(u: str) -> str | None:
        try:
            resp = await request.get(u, timeout=30_000)
            if resp.ok:
                return await resp.text()
        except Exception as e:  # noqa: BLE001
            log(f"      fetch failed ({u.split('?')[0]}): {e}")
        return None

    while queue:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        text = await fetch_text(url)
        if not text:
            continue

        if _is_master_playlist(text):
            for sub in _subtitle_uris_from_master(text, url):
                if sub not in visited:
                    queue.append(sub)
            continue

        if _looks_like_vtt_media_playlist(text):
            segs = _segment_uris(text, url)
            log(f"      subtitle playlist: {len(segs)} segment(s)")
            for seg in segs:
                seg_text = await fetch_text(seg)
                if seg_text:
                    all_cues.extend(parse_vtt(seg_text))

    return all_cues


# --------------------------------------------------------------------------- #
# Per-lesson extraction
# --------------------------------------------------------------------------- #
async def get_title(page, url: str) -> str:
    candidates = []
    # Skool renders the lesson title in the classroom header; try a few spots,
    # then fall back to <title> and finally the URL slug.
    for sel in [
        "h1",
        "[class*='ClassroomLessonTitle']",
        "[data-testid*='title']",
        "meta[property='og:title']",
    ]:
        try:
            if sel.startswith("meta"):
                val = await page.get_attribute(sel, "content")
            else:
                el = await page.query_selector(sel)
                val = (await el.inner_text()) if el else None
            if val and val.strip():
                candidates.append(val.strip())
        except Exception:  # noqa: BLE001
            pass
    try:
        doc_title = (await page.title() or "").strip()
        if doc_title:
            candidates.append(doc_title)
    except Exception:  # noqa: BLE001
        pass
    for c in candidates:
        if c and c.lower() not in ("skool", "loading"):
            return c
    return slug_from_url(url)


async def collect_via_seeking(page, duration: float, log) -> list[dict]:
    """Drive the player through the whole video, accumulating cues as we go."""
    collected: list[dict] = []
    step = max(duration * SEEK_STEP_FRACTION, 3.0)  # never smaller than 3s
    t = 0.0
    steps_total = int(duration // step) + 2
    step_n = 0
    while t <= duration + step:
        step_n += 1
        target = min(t, max(duration - 0.1, 0))
        await page.evaluate(JS_SEEK, target)
        await page.evaluate(JS_ENSURE_TRACKS_SHOWING)
        await page.wait_for_timeout(SEEK_WAIT_MS)
        chunk = await page.evaluate(JS_READ_CUES)
        collected.extend(chunk)
        if step_n % 5 == 0 or target >= duration:
            uniq = len(dedupe_and_sort(collected))
            log(f"      seek {target:6.1f}s / {duration:.1f}s  "
                f"(step {step_n}/{steps_total}, {uniq} cues so far)")
        t += step
    return collected


async def process_url(context, url: str, out_dir: Path, index: dict, log) -> str:
    """Extract one lesson. Returns a status string. Never raises for lesson errors."""
    # ---- captured network state (reset per page) ----
    vtt_bodies: dict[str, str] = {}
    m3u8_urls: list[str] = []

    page = await context.new_page()
    page.set_default_timeout(NAV_TIMEOUT_MS)

    async def on_response(response):
        try:
            u = response.url
            ct = (response.headers or {}).get("content-type", "").lower()
            low = u.split("?")[0].lower()
            if low.endswith(".vtt") or low.endswith(".webvtt") or "text/vtt" in ct:
                try:
                    vtt_bodies[u] = await response.text()
                except Exception:  # noqa: BLE001
                    pass
            elif ".m3u8" in low or "application/vnd.apple.mpegurl" in ct or "mpegurl" in ct:
                if u not in m3u8_urls:
                    m3u8_urls.append(u)
        except Exception:  # noqa: BLE001
            pass

    page.on("response", lambda r: asyncio.create_task(on_response(r)))

    try:
        log(f"  → navigating")
        await page.goto(url, wait_until="domcontentloaded")

        # Give the SPA a moment and make sure a <video> mounts.
        try:
            await page.wait_for_selector("video", timeout=30_000)
        except PWTimeout:
            await page.close()
            return "no <video> element (not logged in, or wrong page?)"

        title = await get_title(page, url)
        out_path = out_dir / f"{slugify(title, fallback=slug_from_url(url))}.txt"
        log(f"    title: {title!r}")
        log(f"    file:  {out_path.name}")

        # Prepare player: play + enable text tracks (this kicks off caption loads).
        prep = await page.evaluate(JS_PREPARE_PLAYER)
        log(f"    player: {prep}")
        if not prep.get("ok"):
            await page.close()
            return f"could not start player: {prep.get('reason')}"

        # Wait for a real duration to appear.
        duration = float(prep.get("duration") or 0)
        waited = 0.0
        while duration <= 0 and waited < METADATA_TIMEOUT_S:
            await page.wait_for_timeout(500)
            waited += 0.5
            duration = float(await page.evaluate(JS_DURATION) or 0)
        log(f"    duration: {duration:.1f}s")

        # Let the initial caption/playlist requests settle.
        await page.wait_for_timeout(1500)

        # ---------------- CLEAN PATH ----------------
        clean_cues: list[dict] = []
        for body in vtt_bodies.values():
            clean_cues.extend(parse_vtt(body))
        if m3u8_urls:
            log(f"    clean path: resolving HLS subtitles from {len(m3u8_urls)} playlist(s)")
            clean_cues.extend(await try_hls_subtitles(context.request, m3u8_urls, log))
        clean_cues = dedupe_and_sort(clean_cues)
        cov = coverage(clean_cues, duration)
        log(f"    clean path: {len(clean_cues)} cues, coverage {cov*100:.0f}%")

        if clean_cues and (duration <= 0 or cov >= 0.95):
            transcript = cues_to_transcript(clean_cues, title, url)
            out_path.write_text(transcript, encoding="utf-8")
            index[url] = out_path.name
            await page.close()
            return f"OK (clean path, {len(clean_cues)} cues)"

        # ---------------- ROBUST PATH ----------------
        if duration <= 0:
            await page.close()
            return "no duration reported; cannot seek. Player may not have loaded."
        log(f"    robust path: seeking through video in ~{SEEK_STEP_FRACTION*100:.0f}% steps")
        seek_cues = await collect_via_seeking(page, duration, log)
        # Fold in anything the clean path already found.
        seek_cues.extend(clean_cues)
        seek_cues = dedupe_and_sort(seek_cues)
        cov = coverage(seek_cues, duration)
        log(f"    robust path: {len(seek_cues)} cues, coverage {cov*100:.0f}%")

        if not seek_cues:
            await page.close()
            return "no cues found (no captions on this lesson?)"

        transcript = cues_to_transcript(seek_cues, title, url)
        out_path.write_text(transcript, encoding="utf-8")
        index[url] = out_path.name
        await page.close()
        note = "" if cov >= 0.9 else f" (warning: only {cov*100:.0f}% coverage)"
        return f"OK (robust path, {len(seek_cues)} cues){note}"

    except Exception as e:  # noqa: BLE001
        try:
            await page.close()
        except Exception:  # noqa: BLE001
            pass
        return f"ERROR: {type(e).__name__}: {e}"


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def read_urls(path: Path) -> list[str]:
    if not path.exists():
        print(f"[!] URL file not found: {path}", file=sys.stderr)
        print(f"    Create it with one lesson URL per line.", file=sys.stderr)
        return []
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def load_index(out_dir: Path) -> dict:
    idx = out_dir / ".index.json"
    if idx.exists():
        try:
            return json.loads(idx.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_index(out_dir: Path, index: dict) -> None:
    (out_dir / ".index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def run(args) -> int:
    urls_path = Path(args.urls)
    out_dir = Path(args.out)
    profile_dir = Path(args.profile)
    out_dir.mkdir(parents=True, exist_ok=True)

    global SEEK_STEP_FRACTION, SEEK_WAIT_MS
    SEEK_STEP_FRACTION = args.step
    SEEK_WAIT_MS = args.wait

    urls = read_urls(urls_path)
    if not urls:
        return 1
    print(f"[i] {len(urls)} URL(s) from {urls_path}")

    index = load_index(out_dir)
    first_run = not profile_dir.exists()

    def log(msg: str):
        print(msg, flush=True)

    launch_kwargs = dict(
        user_data_dir=str(profile_dir),
        headless=False,
        args=CHROME_ARGS,
        viewport={"width": 1400, "height": 900},
    )
    if args.chrome_path:
        launch_kwargs["executable_path"] = args.chrome_path

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(**launch_kwargs)

        if first_run or args.login:
            # Open Skool so the user can authenticate in the visible window.
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto("https://www.skool.com/login", wait_until="domcontentloaded")
            except Exception:  # noqa: BLE001
                pass
            print("\n" + "=" * 64)
            print("Log into Skool in the browser window, then press Enter here.")
            print("(Your session is saved to the profile dir; you won't need to")
            print(" do this every run.)")
            print("=" * 64)
            # input() blocks the event loop briefly; fine for a one-off manual gate.
            await asyncio.get_running_loop().run_in_executor(None, input, "Press Enter to continue... ")

        ok = skipped = failed = 0
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] {url}")
            # Cheap skip: known URL whose output file still exists.
            prior = index.get(url)
            if prior and (out_dir / prior).exists():
                print(f"  ✓ skip (already have {prior})")
                skipped += 1
                continue
            status = await process_url(context, url, out_dir, index, log)
            save_index(out_dir, index)
            print(f"  = {status}")
            if status.startswith("OK"):
                ok += 1
            else:
                failed += 1

        await context.close()

    print(f"\n[done] {ok} extracted, {skipped} skipped, {failed} failed. "
          f"Transcripts in {out_dir}/")
    return 0 if failed == 0 else 2


def main():
    ap = argparse.ArgumentParser(description="Extract Skool classroom transcripts.")
    ap.add_argument("--urls", default=str(DEFAULT_URLS), help="file with one lesson URL per line")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output directory for transcripts")
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE), help="persistent browser profile dir")
    ap.add_argument("--login", action="store_true", help="force the manual-login pause")
    ap.add_argument("--step", type=float, default=SEEK_STEP_FRACTION,
                    help="seek step as a fraction of duration (default 0.05)")
    ap.add_argument("--wait", type=int, default=SEEK_WAIT_MS,
                    help="ms to wait at each seek step (default 700)")
    ap.add_argument("--chrome-path", default=None,
                    help="explicit Chromium executable (only if Playwright can't find its own)")
    args = ap.parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        print("\n[!] interrupted", file=sys.stderr)
        raise SystemExit(130)


if __name__ == "__main__":
    main()
