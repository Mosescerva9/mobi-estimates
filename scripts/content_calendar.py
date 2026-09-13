#!/usr/bin/env python3
"""Content-calendar tracker for the YouTube -> Skool -> DFY funnel.

Tracks every video from idea to published. Data lives in a JSON file (default:
scripts/content-calendar.json — gitignored, it's your working data). Seeded
with the five content pillars and the first eight weeks of long-form topics
from the channel launch plan: weeks 1-2 are setup, publishing starts week 3 at
3 long-form videos/week plus daily Shorts clipped from them.

  python3 scripts/content_calendar.py init          # create + seed the calendar
  python3 scripts/content_calendar.py board         # kanban by status
  python3 scripts/content_calendar.py week 3        # one week's plan
  python3 scripts/content_calendar.py add "Title" --pillar tutorial --week 4
  python3 scripts/content_calendar.py move <id> recorded
  python3 scripts/content_calendar.py schedule <id> 2026-08-17
  python3 scripts/content_calendar.py stats

Shorts are not tracked one-by-one: they are derived from each long-form video
in OpusClip after the edit. Track the long-form item; the Shorts fall out of it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

DEFAULT_DATA = Path(__file__).with_name("content-calendar.json")

STATUSES = ["idea", "scripted", "recorded", "edited", "scheduled", "published"]
FORMATS = ["longform", "short"]

PILLARS: dict[str, str] = {
    "watch_me_work": "Screen-recorded real estimating work with AI voiceover. Highest trust-builder, no camera needed.",
    "tutorial": "Searchable how-to: prompts, workflows, pricing. Ranks in search and compounds over time.",
    "proof_story": "Revenue breakdowns, client stories, mistakes. The click-magnet that anchors credibility.",
    "tool_review": "Bluebeam/PlanSwift/ProEst vs AI workflows. Captures search traffic from working estimators.",
    "community_qa": "Answers to Skool member questions and live estimate hot seats. Content that also sells the community.",
}

SEED_VIDEOS: list[tuple[int, str, str, str]] = [
    # (week, pillar, format, title)
    (3, "proof_story", "longform", "I made $300k as a construction estimator - full breakdown"),
    (3, "watch_me_work", "longform", "Watch me estimate a commercial job with AI in 22 minutes"),
    (3, "tutorial", "longform", "The exact AI prompt I use to scope a concrete takeoff"),
    (4, "proof_story", "longform", "How I got my first 5 estimating clients"),
    (4, "tool_review", "longform", "Bluebeam vs AI takeoff: honest speed test"),
    (4, "tutorial", "longform", "How to price freelance estimates (my actual rates)"),
    (5, "watch_me_work", "longform", "Estimating a multifamily project live with AI"),
    (5, "proof_story", "longform", "5 mistakes that keep estimators broke"),
    (5, "tutorial", "longform", "Set up your estimating business in a weekend"),
    (6, "tool_review", "longform", "PlanSwift + AI: my full workflow"),
    (6, "tutorial", "longform", "Reading plans with AI: what it catches, what it misses"),
    (6, "watch_me_work", "longform", "Watch me price a change order in 10 minutes"),
    (7, "proof_story", "longform", "Opening 25 founding member spots - what is inside"),
    (7, "community_qa", "longform", "The $90/mo community explained: course + weekly estimate reviews"),
    (7, "tutorial", "longform", "How freelance estimators find GC clients (no ads)"),
    (8, "community_qa", "longform", "Founding member Q&A - your questions answered"),
    (8, "watch_me_work", "longform", "AI estimate review: catch scope gaps before you bid"),
    (8, "tutorial", "longform", "Service agreements for estimators: what to include"),
    (9, "proof_story", "longform", "From day job to $10k/mo estimating: the roadmap"),
    (9, "tutorial", "longform", "Building your estimating template stack"),
    (9, "community_qa", "longform", "Reacting to subscriber estimates (live hot seat)"),
    (10, "proof_story", "longform", "The 2-day content batch system I use"),
    (10, "tool_review", "longform", "ChatGPT vs Claude for construction takeoffs"),
    (10, "watch_me_work", "longform", "Watch me set up a done-for-you client portal"),
]


def slugify(title: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48] or "video"
    slug, n = base, 2
    while slug in existing:
        slug = f"{base}-{n}"
        n += 1
    return slug


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def load(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"no calendar at {path} — run `init` first")
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def find(data: dict, item_id: str) -> dict:
    for item in data["items"]:
        if item["id"] == item_id:
            return item
    matches = [i["id"] for i in data["items"] if i["id"].startswith(item_id)]
    if len(matches) == 1:
        return next(i for i in data["items"] if i["id"] == matches[0])
    raise SystemExit(f"unknown or ambiguous id: {item_id}")


def fmt_row(item: dict) -> str:
    sched = item.get("publish_date") or f"wk{item['week']}"
    return f"  {item['id']:<42} {item['status']:<10} {item['pillar']:<14} {sched}"


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.data)
    if path.exists() and not args.force:
        raise SystemExit(f"{path} already exists (use --force to reseed)")
    items = []
    existing: set[str] = set()
    for week, pillar, fmt, title in SEED_VIDEOS:
        slug = slugify(title, existing)
        existing.add(slug)
        items.append({
            "id": slug, "title": title, "pillar": pillar, "format": fmt,
            "status": "idea", "week": week, "publish_date": None,
            "notes": "", "created_at": now_iso(),
        })
    save(path, {"meta": {"created_at": now_iso(), "channel": "AI construction estimating"},
                "items": items})
    print(f"initialized {path} with {len(items)} seeded videos (weeks 3-10)")
    print("weeks 1-2 are setup: channel art, Descript template, demo projects, lead magnet")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    data = load(Path(args.data))
    slug = slugify(args.title, {i["id"] for i in data["items"]})
    data["items"].append({
        "id": slug, "title": args.title, "pillar": args.pillar, "format": args.format,
        "status": "idea", "week": args.week, "publish_date": None,
        "notes": args.notes or "", "created_at": now_iso(),
    })
    save(Path(args.data), data)
    print(f"added {slug} (week {args.week}, {args.pillar})")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    data = load(Path(args.data))
    items = data["items"]
    if args.status:
        items = [i for i in items if i["status"] == args.status]
    if args.pillar:
        items = [i for i in items if i["pillar"] == args.pillar]
    if args.week:
        items = [i for i in items if i["week"] == args.week]
    items.sort(key=lambda i: (i["week"], i["id"]))
    for item in items:
        print(fmt_row(item))
    print(f"\n{len(items)} video(s)")
    return 0


def cmd_move(args: argparse.Namespace) -> int:
    data = load(Path(args.data))
    item = find(data, args.id)
    old = item["status"]
    if STATUSES.index(args.status) < STATUSES.index(old):
        raise SystemExit(f"cannot move backwards ({old} -> {args.status}); edit the JSON if intentional")
    item["status"] = args.status
    if args.status == "published" and not item["publish_date"]:
        item["publish_date"] = date.today().isoformat()
    save(Path(args.data), data)
    print(f"{item['id']}: {old} -> {args.status}")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    data = load(Path(args.data))
    item = find(data, args.id)
    try:
        date.fromisoformat(args.publish_date)
    except ValueError:
        raise SystemExit("date must be YYYY-MM-DD")
    item["publish_date"] = args.publish_date
    if item["status"] in ("idea", "scripted", "recorded", "edited"):
        item["status"] = "scheduled"
    save(Path(args.data), data)
    print(f"{item['id']}: scheduled for {args.publish_date} ({item['status']})")
    return 0


def cmd_board(args: argparse.Namespace) -> int:
    data = load(Path(args.data))
    for status in STATUSES:
        group = [i for i in data["items"] if i["status"] == status]
        print(f"\n== {status.upper()} ({len(group)}) ==")
        for item in sorted(group, key=lambda i: i["week"]):
            print(fmt_row(item))
    return 0


def cmd_week(args: argparse.Namespace) -> int:
    data = load(Path(args.data))
    items = [i for i in data["items"] if i["week"] == args.number]
    items.sort(key=lambda i: i["id"])
    print(f"week {args.number} — {len(items)} long-form video(s) planned:")
    for item in items:
        print(fmt_row(item))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    data = load(Path(args.data))
    items = data["items"]
    print(f"total: {len(items)}")
    for status in STATUSES:
        n = sum(1 for i in items if i["status"] == status)
        if n:
            print(f"  {status:<10} {n}")
    print("by pillar:")
    for pillar in PILLARS:
        n = sum(1 for i in items if i["pillar"] == pillar)
        print(f"  {pillar:<14} {n}")
    published = [i for i in items if i["status"] == "published"]
    if published:
        print(f"publish streak: {len(published)} published")
    return 0


def cmd_pillars(_args: argparse.Namespace) -> int:
    for key, desc in PILLARS.items():
        print(f"{key:<14} {desc}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=str(DEFAULT_DATA),
                        help=f"calendar JSON path (default {DEFAULT_DATA.name})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the calendar seeded with the launch plan")
    p.add_argument("--force", action="store_true", help="overwrite an existing calendar")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("add", help="add a video idea")
    p.add_argument("title")
    p.add_argument("--pillar", choices=list(PILLARS), required=True)
    p.add_argument("--format", choices=FORMATS, default="longform")
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--notes", default="")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("list", help="list videos (filterable)")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--pillar", choices=list(PILLARS))
    p.add_argument("--week", type=int)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("move", help="advance a video to the next pipeline status")
    p.add_argument("id")
    p.add_argument("status", choices=STATUSES)
    p.set_defaults(fn=cmd_move)

    p = sub.add_parser("schedule", help="set a publish date (YYYY-MM-DD)")
    p.add_argument("id")
    p.add_argument("publish_date")
    p.set_defaults(fn=cmd_schedule)

    p = sub.add_parser("board", help="kanban view grouped by status")
    p.set_defaults(fn=cmd_board)

    p = sub.add_parser("week", help="show one week's plan")
    p.add_argument("number", type=int)
    p.set_defaults(fn=cmd_week)

    p = sub.add_parser("stats", help="counts by status and pillar")
    p.set_defaults(fn=cmd_stats)

    p = sub.add_parser("pillars", help="show the five content pillars")
    p.set_defaults(fn=cmd_pillars)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
