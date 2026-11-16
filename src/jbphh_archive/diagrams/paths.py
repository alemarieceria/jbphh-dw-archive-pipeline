"""Where diagram files live.

Every diagrams folder (this repo's docs/diagrams/ and the archive's) has the same
subfolders, one per kind of file, so the scripts and workflows.ipynb find files the
same way:

    specs/   name.toml             the editable source of a stepped diagram
    svgs/    name.excalidraw.svg   the drawing; VS Code's Excalidraw extension edits it
    pngs/    name.png              the drawing as an image, for Word and Google Docs
    embeds/  name.embed.html       the stepped (Back / Next) player
"""

import os
import sys
from pathlib import Path

DIAGRAMS_FOLDER = Path("docs") / "diagrams"  # inside this repo and inside the archive
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


def diagrams_folder(folder: str | None, archive_root: str | None) -> Path:
    """The folder given with --folder, otherwise the archive's docs/diagrams/ (from ARCHIVE_ROOT)."""
    path = Path(folder) if folder else Path(archive_root or os.environ.get("ARCHIVE_ROOT", "")) / DIAGRAMS_FOLDER
    if not path.is_dir():
        sys.exit(f"Diagrams folder not found at {path}. Pass --folder, or set ARCHIVE_ROOT in .env.")
    return path
