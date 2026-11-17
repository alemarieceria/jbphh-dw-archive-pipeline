"""Tests for finding the catalog in this repo and the archive on the Drive."""

from pathlib import Path

import pytest

from jbphh_archive.catalog import CATALOG_FILE, archive_folder


def test_catalog_is_in_this_repo():
    assert CATALOG_FILE == Path(__file__).resolve().parents[1] / "catalog" / "documents.csv"
    assert CATALOG_FILE.is_file()


def test_archive_folder_must_be_set(monkeypatch):
    monkeypatch.delenv("ARCHIVE_ROOT", raising=False)
    with pytest.raises(SystemExit, match=r"\(not set\)"):
        archive_folder(None)


def test_archive_folder_must_hold_a_registry_folder(tmp_path):
    with pytest.raises(SystemExit, match="Archive not found"):
        archive_folder(str(tmp_path))
    (tmp_path / "registry").mkdir()
    assert archive_folder(str(tmp_path)) == tmp_path
