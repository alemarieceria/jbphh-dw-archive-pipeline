import os
from pathlib import Path

import pytest

from jbphh_archive.diagrams import paths
from jbphh_archive.diagrams.export_pngs import needs_png
from jbphh_archive.diagrams.paths import (
    DIAGRAMS_FOLDER,
    diagram_name,
    diagrams_folder,
    embed_path,
    png_path,
    svg_files,
    svg_path,
)

THIS_REPO_DIAGRAMS = Path(__file__).resolve().parents[1] / "docs" / "diagrams"


def test_diagrams_folder_is_this_repos_docs_diagrams():
    assert DIAGRAMS_FOLDER == THIS_REPO_DIAGRAMS
    assert DIAGRAMS_FOLDER.is_dir()


def test_diagrams_folder_is_found_from_any_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # a notebook in notebooks/ runs from there, not the repo root
    assert diagrams_folder() == THIS_REPO_DIAGRAMS


def test_each_kind_of_file_has_its_own_subfolder():
    folder = Path("docs") / "diagrams"
    assert svg_path(folder, "flow") == folder / "svgs" / "flow.excalidraw.svg"
    assert png_path(folder, "flow") == folder / "pngs" / "flow.png"
    assert embed_path(folder, "flow") == folder / "embeds" / "flow.embed.html"


def test_svg_files_finds_only_drawings_in_svgs(tmp_path):
    (tmp_path / "svgs").mkdir()
    (tmp_path / "svgs" / "b.excalidraw.svg").write_text("<svg/>")
    (tmp_path / "svgs" / "a.excalidraw.svg").write_text("<svg/>")
    (tmp_path / "svgs" / "notes.txt").write_text("")
    (tmp_path / "old.excalidraw.svg").write_text("<svg/>")  # outside svgs/, so ignored
    assert [diagram_name(svg) for svg in svg_files(tmp_path)] == ["a", "b"]


def test_png_is_rebuilt_only_when_missing_or_older_than_its_svg(tmp_path):
    svg, png = tmp_path / "a.excalidraw.svg", tmp_path / "a.png"
    svg.write_text("<svg/>")
    assert needs_png(svg, png, force=False)
    png.write_bytes(b"")
    newer = svg.stat().st_mtime + 10
    os.utime(png, (newer, newer))
    assert not needs_png(svg, png, force=False)
    assert needs_png(svg, png, force=True)


def test_missing_diagrams_folder_stops_with_a_plain_message(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DIAGRAMS_FOLDER", tmp_path / "nowhere")
    with pytest.raises(SystemExit, match="Diagrams folder not found"):
        diagrams_folder()
