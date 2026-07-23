#!/usr/bin/env python3
"""Build side-by-side reference(Togal) vs baseline(Mobi) comparison images.

Dependency: Pillow (already present). Read-only over the captured PNGs; writes
comparison sheets under review-artifacts/togal-faithful-rebuild/comparison/.

  python3 scripts/visual-review/compare.py
"""
import os
from PIL import Image, ImageDraw

ROOT = os.path.join("review-artifacts", "togal-faithful-rebuild")
REF = os.path.join(ROOT, "reference")
BASE = os.path.join(ROOT, "baseline")
OUT = os.path.join(ROOT, "comparison")
os.makedirs(OUT, exist_ok=True)

VIEWPORTS = ["390x844", "430x932", "768x1024", "834x1194", "1024x1366", "1440x1000", "1920x1080"]
GUTTER = 24
LABEL_H = 34
MAX_H = 4200  # cap tall pages so the sheet stays readable


def load(path, target_w):
    im = Image.open(path).convert("RGB")
    # captured at device scale; normalise to a common column width
    w, h = im.size
    scale = target_w / w
    im = im.resize((target_w, int(h * scale)))
    if im.height > MAX_H:
        im = im.crop((0, 0, target_w, MAX_H))
    return im


def sheet(vp):
    col_w = 520
    ref_p = os.path.join(REF, f"togal-{vp}.png")
    base_p = os.path.join(BASE, f"mobi-{vp}.png")
    if not (os.path.exists(ref_p) and os.path.exists(base_p)):
        return None
    a = load(ref_p, col_w)
    b = load(base_p, col_w)
    h = max(a.height, b.height) + LABEL_H
    canvas = Image.new("RGB", (col_w * 2 + GUTTER, h), (245, 247, 250))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, col_w * 2 + GUTTER, LABEL_H], fill=(15, 24, 40))
    d.text((12, 9), f"REFERENCE  Togal.ai  [{vp}]", fill=(255, 255, 255))
    d.text((col_w + GUTTER + 12, 9), f"BASELINE  Mobi (current)  [{vp}]", fill=(120, 200, 140))
    canvas.paste(a, (0, LABEL_H))
    canvas.paste(b, (col_w + GUTTER, LABEL_H))
    out = os.path.join(OUT, f"compare-{vp}.png")
    canvas.save(out)
    return out, canvas.size


if __name__ == "__main__":
    made = []
    for vp in VIEWPORTS:
        r = sheet(vp)
        if r:
            made.append((vp, r[0], r[1]))
            print(f"  compare {vp} -> {r[0]} {r[1]}")
    print(f"DONE: {len(made)} comparison sheets")
