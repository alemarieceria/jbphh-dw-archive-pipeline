"""Render each diagram's SVG to a PNG, for documents that can't show SVG (Word, Google Docs).

Diagrams are saved as `name.excalidraw.svg` (an SVG with the editable
Excalidraw drawing embedded). This writes `name.png` beside each one. A PNG is
only rebuilt when its SVG is newer, unless --force.

Usage (from the project folder):
    uv run --env-file .env scripts/export_pngs.py                        # archive's docs/diagrams/
    uv run scripts/export_pngs.py --folder docs/diagrams                 # this repo's diagrams
"""

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DIAGRAMS_FOLDER = Path("docs") / "diagrams"
SUFFIX = ".excalidraw.svg"
SCALE = 2  # render at twice the drawing size so text stays sharp in documents


def png_path(svg: Path) -> Path:
    return svg.with_name(svg.name.removesuffix(SUFFIX) + ".png")


def needs_png(svg: Path, force: bool) -> bool:
    png = png_path(svg)
    return force or not png.exists() or png.stat().st_mtime < svg.stat().st_mtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive-root", help="archive folder (default: ARCHIVE_ROOT environment variable)")
    parser.add_argument("--folder", help="diagrams folder to use instead of the archive's docs/diagrams/")
    parser.add_argument("--force", action="store_true", help="rebuild every PNG")
    args = parser.parse_args(argv)

    if args.folder:
        folder = Path(args.folder)
    else:
        folder = Path(args.archive_root or os.environ.get("ARCHIVE_ROOT", "")) / DIAGRAMS_FOLDER
    if not folder.is_dir():
        sys.exit(f"Diagrams folder not found at {folder}. Pass --folder, or set ARCHIVE_ROOT in .env.")

    svgs = [svg for svg in sorted(folder.glob(f"*{SUFFIX}")) if needs_png(svg, args.force)]
    print(f"{len(svgs)} PNG(s) to build.")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=SCALE)
        for svg in svgs:
            page.goto(svg.resolve().as_uri())
            page.evaluate("document.fonts.ready")  # wait for the hand-drawn font before capturing
            page.locator("svg").first.screenshot(path=png_path(svg))
            print(f"    saved {png_path(svg).name}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
