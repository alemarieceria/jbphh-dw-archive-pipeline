"""Render each diagram's SVG to a PNG, for documents that can't show SVG (Word, Google Docs).

Diagrams are saved as `svgs/name.excalidraw.svg` (an SVG with the editable Excalidraw
drawing embedded). This writes `pngs/name.png` for each one. A PNG is only rebuilt when
its SVG is newer, unless --force.

Usage (from the project folder):
    uv run archive diagrams png            # only PNGs whose SVG changed
    uv run archive diagrams png --force    # every PNG
"""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

from jbphh_archive.diagrams.paths import diagram_name, diagrams_folder, png_path, svg_files

SCALE = 2  # render at twice the drawing size so text stays sharp in documents


def needs_png(svg: Path, png: Path, force: bool) -> bool:
    return force or not png.exists() or png.stat().st_mtime < svg.stat().st_mtime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="archive diagrams png", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--force", action="store_true", help="rebuild every PNG")
    args = parser.parse_args(argv)

    folder = diagrams_folder()
    pairs = [(svg, png_path(folder, diagram_name(svg))) for svg in svg_files(folder)]
    todo = [(svg, png) for svg, png in pairs if needs_png(svg, png, args.force)]
    print(f"{len(todo)} PNG(s) to build.")
    if not todo:
        return 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=SCALE)
        for svg, png in todo:
            png.parent.mkdir(parents=True, exist_ok=True)
            page.goto(svg.resolve().as_uri())
            page.evaluate("document.fonts.ready")  # wait for the hand-drawn font before capturing
            page.locator("svg").first.screenshot(path=png)
            print(f"    saved {png}")
        browser.close()
    return 0
