#!/usr/bin/env python3
"""Split a turnaround sheet (several views of one character side by side) into separate images.

Usage:
    python tools/split_turnaround.py private/ninja_sheet.webp --out private/ninja

By default the sheet is cut into 3 equal columns and saved as front.png, side.png and back.png
(the usual order of a front, side, back sheet). Use --views 2 for a front/side sheet, or
--names to give your own file names. Check the result by eye: cut lines that run through a
character mean the sheet is not evenly spaced and needs cropping by hand.
"""

import argparse
from pathlib import Path

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a turnaround sheet into one image per view.")
    parser.add_argument("sheet", help="Path to the sheet image")
    parser.add_argument("--out", default="output/views", help="Folder for the cut images")
    parser.add_argument("--views", type=int, default=3, help="Number of equal columns (default 3)")
    parser.add_argument("--names", default="front,side,back",
                        help="Comma separated file names without extension, left to right")
    args = parser.parse_args()

    names = [n.strip() for n in args.names.split(",") if n.strip()]
    if len(names) < args.views:
        raise SystemExit(f"Need {args.views} names, got {len(names)}: {names}")

    img = Image.open(args.sheet).convert("RGB")
    width, height = img.size
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(args.views):
        left = round(i * width / args.views)
        right = round((i + 1) * width / args.views)
        path = out_dir / f"{names[i]}.png"
        img.crop((left, 0, right, height)).save(path)
        print(f"{path}  ({right - left} x {height})")


if __name__ == "__main__":
    main()
