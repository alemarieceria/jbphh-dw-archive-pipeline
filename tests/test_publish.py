"""Tests for publishing the catalog to the Drive. They use temporary folders, never the real Drive."""

import pytest

from jbphh_archive import publish
from jbphh_archive.catalog import write_rows

COLUMNS = ["doc_id", "title_as_posted", "status"]


def rows(*specs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"doc_id": doc_id, "title_as_posted": "t", "status": status} for doc_id, status in specs]


@pytest.fixture
def files(tmp_path, monkeypatch):
    """A catalog in a stand-in repo, and an archive with its published copy."""
    catalog = tmp_path / "repo" / "catalog" / "documents.csv"
    catalog.parent.mkdir(parents=True)
    archive = tmp_path / "drive"
    (archive / "registry").mkdir(parents=True)
    monkeypatch.setattr(publish, "CATALOG_FILE", catalog)
    return catalog, archive, archive / "registry" / "documents.csv"


def test_differences_lists_added_changed_and_missing_rows():
    old = rows(("DOC-0001", "done"), ("DOC-0002", "to_find"), ("DOC-0003", "done"))
    new = rows(("DOC-0001", "done"), ("DOC-0002", "done"), ("DOC-0004", "to_find"))
    assert publish.differences(old, new) == (["DOC-0004"], ["DOC-0002"], ["DOC-0003"])


def test_publish_copies_the_catalog_exactly(files, capsys):
    catalog, archive, published = files
    write_rows(published, COLUMNS, rows(("DOC-0001", "to_find")))
    write_rows(catalog, COLUMNS, rows(("DOC-0001", "done"), ("DOC-0002", "to_find")))
    assert publish.main(["--archive-root", str(archive)]) == 0
    assert published.read_bytes() == catalog.read_bytes()
    assert "1 added, 1 changed" in capsys.readouterr().out


def test_dry_run_changes_nothing(files, capsys):
    catalog, archive, published = files
    write_rows(published, COLUMNS, rows(("DOC-0001", "to_find")))
    write_rows(catalog, COLUMNS, rows(("DOC-0001", "done")))
    before = published.read_bytes()
    assert publish.main(["--archive-root", str(archive), "--dry-run"]) == 0
    assert published.read_bytes() == before
    assert "changed: DOC-0001" in capsys.readouterr().out


def test_identical_copy_is_left_alone(files, capsys):
    catalog, archive, published = files
    write_rows(catalog, COLUMNS, rows(("DOC-0001", "done")))
    published.write_bytes(catalog.read_bytes())
    assert publish.main(["--archive-root", str(archive)]) == 0
    assert "already up to date" in capsys.readouterr().out


def test_refuses_when_rows_would_disappear(files):
    catalog, archive, published = files
    write_rows(published, COLUMNS, rows(("DOC-0001", "done"), ("DOC-0002", "done")))
    write_rows(catalog, COLUMNS, rows(("DOC-0001", "done")))
    before = published.read_bytes()
    with pytest.raises(SystemExit, match="missing rows the Drive's copy has \\(DOC-0002\\)"):
        publish.main(["--archive-root", str(archive)])
    assert published.read_bytes() == before
