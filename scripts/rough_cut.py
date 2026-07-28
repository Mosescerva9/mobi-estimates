#!/usr/bin/env python3
"""AI rough-cut pipeline for the daily-video machine.

Removes dead air from talking-head / screen-recording footage with ffmpeg's
silence detector and (optionally) generates captions with Whisper, so a raw
recording lands in Descript/OpusClip already tight instead of needing a manual
first pass. No third-party Python packages are required for cutting; the
`captions` command needs openai-whisper (pip install openai-whisper).

Typical batch-day flow:
  1. Record raw takes into ./raw/
  2. python3 scripts/rough_cut.py batch ./raw --out-dir ./cut
  3. python3 scripts/rough_cut.py captions ./cut/video.mp4   # timings match the CUT file
  4. Import the cut mp4 + srt into Descript for the polish pass

Requires ffmpeg + ffprobe on PATH.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_NOISE_DB = -35.0
DEFAULT_MIN_SILENCE = 0.5
DEFAULT_PADDING = 0.15


@dataclass
class Segment:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def run(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, capture_output=capture, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-2000:] if capture else ""
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{tail}")
    return proc


def probe_duration(path: Path) -> float:
    out = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(out.stdout.strip())


def probe_has_audio(path: Path) -> bool:
    out = run([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
    ])
    return bool(out.stdout.strip())


def detect_silences(path: Path, noise_db: float, min_silence: float) -> list[Segment]:
    """Return silence intervals via ffmpeg's silencedetect filter (logs to stderr)."""
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    log = proc.stderr or ""
    starts = [float(m) for m in re.findall(r"silence_start:\s*([0-9.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([0-9.]+)", log)]
    silences: list[Segment] = []
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else probe_duration(path)
        silences.append(Segment(start, end))
    return silences


def speech_segments(silences: list[Segment], duration: float, padding: float) -> list[Segment]:
    """Invert silence intervals into keep-segments, re-expanding each by `padding`
    into the surrounding silence so cuts don't clip words, then merging overlaps."""
    keep: list[Segment] = []
    cursor = 0.0
    for sil in sorted(silences, key=lambda s: s.start):
        if sil.start > cursor:
            keep.append(Segment(cursor, sil.start))
        cursor = max(cursor, sil.end)
    if cursor < duration:
        keep.append(Segment(cursor, duration))

    padded = [
        Segment(max(0.0, s.start - padding), min(duration, s.end + padding))
        for s in keep if s.duration > 0.05
    ]
    merged: list[Segment] = []
    for seg in padded:
        if merged and seg.start <= merged[-1].end:
            merged[-1].end = max(merged[-1].end, seg.end)
        else:
            merged.append(Segment(seg.start, seg.end))
    return merged


def render_cut(src: Path, dst: Path, segments: list[Segment]) -> None:
    """Re-encode only the keep-segments. A filter-complex script file keeps the
    command line short enough for videos with hundreds of cuts."""
    lines: list[str] = []
    for i, seg in enumerate(segments):
        lines.append(
            f"[0:v]trim=start={seg.start:.3f}:end={seg.end:.3f},setpts=PTS-STARTPTS[v{i}];"
        )
        lines.append(
            f"[0:a]atrim=start={seg.start:.3f}:end={seg.end:.3f},asetpts=PTS-STARTPTS[a{i}];"
        )
    concat_in = "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
    lines.append(f"{concat_in}concat=n={len(segments)}:v=1:a=1[vout][aout]")

    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".ffm", delete=False) as f:
        f.write("\n".join(lines))
        script_path = f.name
    try:
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
            "-filter_complex_script", script_path,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(dst),
        ], capture=False)
    finally:
        Path(script_path).unlink(missing_ok=True)


def cut_one(src: Path, dst: Path, args: argparse.Namespace) -> dict[str, float | int]:
    duration = probe_duration(src)
    if not probe_has_audio(src):
        raise RuntimeError(f"{src.name}: no audio track — silence detection needs audio")

    silences = detect_silences(src, args.noise, args.min_silence)
    segments = speech_segments(silences, duration, args.padding)

    if not segments:
        raise RuntimeError(f"{src.name}: everything detected as silence — lower --noise?")

    kept = sum(s.duration for s in segments)
    removed = duration - kept
    unchanged = len(segments) == 1 and math.isclose(
        segments[0].duration, duration, abs_tol=args.padding * 2 + 0.01
    )
    if unchanged and dst.suffix.lower() == src.suffix.lower():
        dst.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
             "-c", "copy", str(dst)], capture=False)
    else:
        render_cut(src, dst, segments)

    return {
        "input_s": duration,
        "output_s": kept,
        "removed_s": removed,
        "cuts": max(0, len(segments) - 1),
        "silences": len(silences),
    }


def cmd_analyze(args: argparse.Namespace) -> int:
    src = Path(args.input)
    duration = probe_duration(src)
    silences = detect_silences(src, args.noise, args.min_silence)
    segments = speech_segments(silences, duration, args.padding)
    removed = duration - sum(s.duration for s in segments)
    print(f"{src.name}: {duration:.1f}s total")
    print(f"  silences: {len(silences)}  cuts: {max(0, len(segments) - 1)}")
    print(f"  removed:  {removed:.1f}s ({removed / duration * 100:.0f}% of raw footage)")
    for i, seg in enumerate(segments):
        print(f"  keep {i + 1:>3}: {seg.start:8.2f} -> {seg.end:8.2f}  ({seg.duration:6.2f}s)")
    return 0


def cmd_cut(args: argparse.Namespace) -> int:
    src = Path(args.input)
    dst = Path(args.output) if args.output else src.with_name(f"{src.stem}.cut{src.suffix}")
    stats = cut_one(src, dst, args)
    print(
        f"{src.name} -> {dst.name}: "
        f"{stats['input_s']:.1f}s -> {stats['output_s']:.1f}s "
        f"({stats['cuts']} cuts, {stats['removed_s']:.1f}s dead air removed)"
    )
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    src_dir = Path(args.dir)
    out_dir = Path(args.out_dir) if args.out_dir else src_dir / "cut"
    files = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"})
    if not files:
        print(f"no video files found in {src_dir}", file=sys.stderr)
        return 1
    failures = 0
    for src in files:
        dst = out_dir / f"{src.stem}.cut.mp4"
        try:
            stats = cut_one(src, dst, args)
            print(
                f"{src.name}: {stats['input_s']:.1f}s -> {stats['output_s']:.1f}s "
                f"({stats['cuts']} cuts)"
            )
        except RuntimeError as e:
            failures += 1
            print(f"  SKIP  {e}", file=sys.stderr)
    print(f"done: {len(files) - failures}/{len(files)} cut into {out_dir}")
    return 1 if failures else 0


def format_timestamp(seconds: float, sep: str = ",") -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def cmd_captions(args: argparse.Namespace) -> int:
    """Transcribe a (preferably already cut) video and write an .srt/.vtt so the
    caption timings line up with the edited file. Whisper is an optional, local
    dependency — no audio ever leaves the machine."""
    try:
        import whisper  # type: ignore
    except ImportError:
        print(
            "openai-whisper is not installed. Captions need it once per machine:\n"
            "  pip3 install openai-whisper\n"
            "(first run also downloads the model weights, ~150MB for 'base')",
            file=sys.stderr,
        )
        return 2

    src = Path(args.input)
    dst = Path(args.output) if args.output else src.with_suffix(".srt")
    model = whisper.load_model(args.model)
    result = model.transcribe(str(src))

    is_vtt = dst.suffix.lower() == ".vtt"
    lines: list[str] = ["WEBVTT", ""] if is_vtt else []
    sep = "." if is_vtt else ","
    for i, seg in enumerate(result["segments"], start=1):
        if not is_vtt:
            lines.append(str(i))
        lines.append(f"{format_timestamp(seg['start'], sep)} --> {format_timestamp(seg['end'], sep)}")
        lines.append(seg["text"].strip())
        lines.append("")
    dst.write_text("\n".join(lines), encoding="utf-8")
    print(f"{src.name}: {len(result['segments'])} caption cues -> {dst}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cut dead air out of raw talking-head/screen recordings and "
                    "optionally generate captions. ffmpeg required; Whisper optional.",
        epilog="Workflow: batch-cut the day's raw takes, then run `captions` on the "
               "CUT file so timings match what you import into Descript/OpusClip.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_tuning(p: argparse.ArgumentParser) -> None:
        p.add_argument("--noise", type=float, default=DEFAULT_NOISE_DB,
                       help=f"silence threshold in dB (default {DEFAULT_NOISE_DB}; "
                            "raise toward -25 for noisy rooms, lower toward -45 for quiet studios)")
        p.add_argument("--min-silence", type=float, default=DEFAULT_MIN_SILENCE,
                       help=f"minimum silence length in seconds to cut (default {DEFAULT_MIN_SILENCE})")
        p.add_argument("--padding", type=float, default=DEFAULT_PADDING,
                       help=f"seconds of air kept around each speech segment (default {DEFAULT_PADDING})")

    p = sub.add_parser("analyze", help="show detected silences and keep-segments, no render")
    p.add_argument("input")
    add_tuning(p)
    p.set_defaults(fn=cmd_analyze)

    p = sub.add_parser("cut", help="render a dead-air-free rough cut")
    p.add_argument("input")
    p.add_argument("-o", "--output", help="default: <name>.cut.<ext> next to the input")
    add_tuning(p)
    p.set_defaults(fn=cmd_cut)

    p = sub.add_parser("batch", help="cut every video in a folder")
    p.add_argument("dir")
    p.add_argument("--out-dir", help="default: <dir>/cut")
    add_tuning(p)
    p.set_defaults(fn=cmd_batch)

    p = sub.add_parser("captions", help="transcribe with local Whisper and write .srt/.vtt")
    p.add_argument("input", help="use the CUT file so caption timings match the edit")
    p.add_argument("-o", "--output", help="default: <name>.srt (use .vtt suffix for WebVTT)")
    p.add_argument("--model", default="base",
                   help="whisper model: tiny/base/small/medium (default base)")
    p.set_defaults(fn=cmd_captions)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.fn(args)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
