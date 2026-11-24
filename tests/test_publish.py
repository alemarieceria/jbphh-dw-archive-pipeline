"""Tests for publishing the catalog to the Drive. They use temporary folders, never the real Drive."""

import shutil
from pathlib import Path

import pytest

from jbphh_archive import catalog, publish
from jbphh_archive.catalog import write_rows

COLUMNS = ["doc_id", "title_as_posted", "status"]
OTHER_FILES = ("document_links.csv", "zones.csv", "communities.csv")


def rows(*specs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"doc_id": doc_id, "title_as_posted": "t", "status": status} for doc_id, status in specs]


def small_table(path: Path, count: int) -> None:
    write_rows(path, ["id", "notes"], [{"id": str(n), "notes": ""} for n in range(count)])


@pytest.fixture
def files(tmp_path, monkeypatch):
    """Four small catalog files in a stand-in repo, and an archive whose registry/ has copies of the
    other three, so each test is about documents.csv unless it changes them. `archive validate` finds
    no problems unless a test says so."""
    folder = tmp_path / "repo" / "catalog"
    folder.mkdir(parents=True)
    archive = tmp_path / "drive"
    registry = archive / "registry"
    registry.mkdir(parents=True)
    for name, attribute in zip(OTHER_FILES, ("LINKS_FILE", "ZONES_FILE", "COMMUNITIES_FILE"), strict=True):
        small_table(folder / name, 2)
        shutil.copyfile(folder / name, registry / name)
        monkeypatch.setattr(catalog, attribute, folder / name)
    monkeypatch.setattr(catalog, "CATALOG_FILE", folder / "documents.csv")
    monkeypatch.setattr(publish, "catalog_problems", list)
    return folder / "documents.csv", archive, registry / "documents.csv"


def test_differences_lists_added_changed_and_missing_rows():
    old = rows(("DOC-0001", "done"), ("DOC-0002", "to_find"), ("DOC-0003", "done"))
    new = rows(("DOC-0001", "done"), ("DOC-0002", "done"), ("DOC-0004", "to_find"))
    assert publish.differences(old, new) == (["DOC-0004"], ["DOC-0002"], ["DOC-0003"])


def test_publish_copies_the_catalog_exactly(files, capsys):
    documents, archive, published = files
    write_rows(published, COLUMNS, rows(("DOC-0001", "to_find")))
    write_rows(documents, COLUMNS, rows(("DOC-0001", "done"), ("DOC-0002", "to_find")))
    assert publish.main(["--archive-root", str(archive)]) == 0
    assert published.read_bytes() == documents.read_bytes()
    out = capsys.readouterr().out
    assert "documents.csv: 2 rows: 1 added, 1 changed" in out
    assert "zones.csv: already up to date" in out
    assert "Published 1 file(s)" in out


def test_every_catalog_file_is_copied(files, capsys):
    documents, archive, published = files
    write_rows(documents, COLUMNS, rows(("DOC-0001", "done")))
    registry = published.parent
    (registry / "document_links.csv").unlink()  # not published yet
    small_table(documents.parent / "zones.csv", 3)  # one row added since the last publish
    assert publish.main(["--archive-root", str(archive)]) == 0
    for name in ("documents.csv", *OTHER_FILES):
        assert (registry / name).read_bytes() == (documents.parent / name).read_bytes()
    out = capsys.readouterr().out
    assert "documents.csv: 1 rows: 1 added, 0 changed." in out
    assert "document_links.csv: new on the Drive (2 rows)." in out
    assert "zones.csv: updated (3 rows; the Drive's copy has 2)." in out
    assert "communities.csv: already up to date." in out
    assert "Published 3 file(s)" in out


def test_dry_run_changes_nothing(files, capsys):
    documents, archive, published = files
    write_rows(published, COLUMNS, rows(("DOC-0001", "to_find")))
    write_rows(documents, COLUMNS, rows(("DOC-0001", "done")))
    small_table(documents.parent / "zones.csv", 3)
    before = {path.name: path.read_bytes() for path in published.parent.iterdir()}
    assert publish.main(["--archive-root", str(archive), "--dry-run"]) == 0
    assert {path.name: path.read_bytes() for path in published.parent.iterdir()} == before
    out = capsys.readouterr().out
    assert "changed: DOC-0001" in out
    assert "zones.csv: updated" in out
    assert "Dry run: nothing copied." in out


def test_identical_copies_are_left_alone(files, capsys):
    documents, archive, published = files
    write_rows(documents, COLUMNS, rows(("DOC-0001", "done")))
    published.write_bytes(documents.read_bytes())
    assert publish.main(["--archive-root", str(archive)]) == 0
    assert "The Drive's copy is already up to date." in capsys.readouterr().out


def test_refuses_when_rows_would_disappear(files):
    documents, archive, published = files
    write_rows(published, COLUMNS, rows(("DOC-0001", "done"), ("DOC-0002", "done")))
    write_rows(documents, COLUMNS, rows(("DOC-0001", "done")))
    small_table(documents.parent / "zones.csv", 3)
    before = {path.name: path.read_bytes() for path in published.parent.iterdir()}
    with pytest.raises(SystemExit, match="missing rows the Drive's copy has \\(DOC-0002\\)"):
        publish.main(["--archive-root", str(archive)])
    assert {path.name: path.read_bytes() for path in published.parent.iterdir()} == before


def test_refuses_when_validate_finds_a_problem(files, monkeypatch):
    documents, archive, published = files
    write_rows(documents, COLUMNS, rows(("DOC-0001", "done")))
    monkeypatch.setattr(publish, "catalog_problems", lambda: ["documents.csv line 2 (DOC-0001), phase: is blank"])
    with pytest.raises(SystemExit, match="`archive validate` finds these problems") as err:
        publish.main(["--archive-root", str(archive)])
    assert "phase: is blank" in str(err.value.code)
    assert not published.exists()


def test_the_real_catalog_publishes_to_an_empty_registry(tmp_path, capsys):
    """The repo's own four catalog files pass `archive validate` and are copied exactly."""
    (tmp_path / "registry").mkdir()
    assert publish.main(["--archive-root", str(tmp_path)]) == 0
    for source in publish.catalog_files():
        assert (tmp_path / "registry" / source.name).read_bytes() == source.read_bytes()
    assert "Published 4 file(s)" in capsys.readouterr().out
