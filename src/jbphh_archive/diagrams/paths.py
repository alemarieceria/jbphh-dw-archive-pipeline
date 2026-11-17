"""Where diagram files live.

Every diagram lives in this repo's docs/diagrams/, which has one subfolder per kind of
file, so the scripts and the notebooks find files the same way:

    specs/   name.toml             the editable source of a stepped diagram
    svgs/    name.excalidraw.svg   the drawing; VS Code's Excalidraw extension edits it
    pngs/    name.png              the drawing as an image, for Word and Google Docs
    embeds/  name.embed.html       the stepped (Back / Next) player
"""

import sys
from pathlib import Path

from jbphh_archive import REPO_ROOT

DIAGRAMS_FOLDER = REPO_ROOT / "docs" / "diagrams"
SVG_SUFFIX = ".excalidraw.svg"


def svg_path(folder: Path, name: str) -> Path:
    return folder / "svgs" / f"{name}{SVG_SUFFIX}"


def png_path(folder: Path, name: str) -> Path:
    return folder / "pngs" / f"{name}.png"


def embed_path(folder: Path, name: str) -> Path:
    return folder / "embeds" / f"{name}.embed.html"


def diagram_name(svg: Path) -> str:
    """The diagram's name, from its SVG file name."""
    return svg.name.removesuffix(SVG_SUFFIX)


def svg_files(folder: Path) -> list[Path]:
    """Every drawing in the folder's svgs/ subfolder, in name order."""
    return sorted(svg_path(folder, "x").parent.glob(f"*{SVG_SUFFIX}"))


def diagrams_folder() -> Path:
    """This repo's docs/diagrams/, or stop with a plain message if it is missing."""
    if not DIAGRAMS_FOLDER.is_dir():
        sys.exit(f"Diagrams folder not found at {DIAGRAMS_FOLDER}.")
    return DIAGRAMS_FOLDER
