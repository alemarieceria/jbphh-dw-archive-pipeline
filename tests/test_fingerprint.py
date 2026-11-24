"""Tests for the fingerprint step. Each test uses a small catalog and a made-up archive folder in a
temporary folder, so neither the real catalog nor the Shared Drive is touched."""

import hashlib
from datetime import date
from pathlib import Path

import pytest

from jbphh_archive import catalog, fingerprint
from jbphh_archive.catalog import file_sha256, read_rows, write_rows
from jbphh_archive.validate import DOCUMENT_COLUMNS

TODAY = date(2026, 11, 24)
NOTE = "2026-11-24: sha256 recorded by `archive fingerprint` from the file on the Drive, not when it was saved."
PAGE_PDF = b"%PDF-1.5 captured page"
PAGE_HTML = b"<html>captured page</html>"
LAB_PDF = b"%PDF-1.5 downloaded report"


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def doc(doc_id: str, local_path: str, **values: str) -> dict[str, str]:
    """A valid `done` web page row with no fingerprint, changed by `values`."""
    row = dict.fromkeys(DOCUMENT_COLUMNS, "") | {
        "doc_id": doc_id,
        "group": "web_page",
        "title_as_posted": "A captured page",
        "source_url": "https://www.navy.mil/page/",
        "doc_type": "press_release",
        "zones": "I1",
        "phase": "emergency_response",
        "status": "done",
        "retrieved_utc": "2026-10-31",
        "local_path": local_path,
    }
    return row | values


@pytest.fixture
def archive(tmp_path, monkeypatch) -> Path:
    """An archive folder with a captured page (PDF and HTML) and a downloaded report, and a catalog
    with a row for each, a fingerprinted row, and a row still to find."""
    root = tmp_path / "archive"
    (root / "registry").mkdir(parents=True)
    (root / "web-captures" / "navy").mkdir(parents=True)
    (root / "raw").mkdir()
    (root / "web-captures" / "navy" / "page.pdf").write_bytes(PAGE_PDF)
    (root / "web-captures" / "navy" / "page.html").write_bytes(PAGE_HTML)
    (root / "raw" / "report.pdf").write_bytes(LAB_PDF)
    rows = [
        doc("DOC-0001", "web-captures/navy/page.pdf; web-captures/navy/page.html", notes="Web page; capture."),
        doc("DOC-0002", "raw/report.pdf"),
        doc("DOC-0003", "raw/report.pdf", sha256=sha(b"recorded at download"), duplicate_of="DOC-0002"),
        doc("DOC-0004", "", status="to_find", source_url="", retrieved_utc=""),
    ]
    catalog_file = tmp_path / "documents.csv"
    write_rows(catalog_file, DOCUMENT_COLUMNS, rows)
    monkeypatch.setattr(catalog, "CATALOG_FILE", catalog_file)
    monkeypatch.delenv("ARCHIVE_ROOT", raising=False)
    return root


def rows_by_id() -> dict[str, dict[str, str]]:
    return {row["doc_id"]: row for row in read_rows(catalog.CATALOG_FILE)[1]}


def test_file_sha256_matches_hashlib(tmp_path):
    file = tmp_path / "big.bin"
    file.write_bytes(b"x" * (3 * 1024 * 1024 + 5))  # more than one piece
    assert file_sha256(file) == hashlib.sha256(file.read_bytes()).hexdigest()


def test_dry_run_shows_the_fingerprints_and_writes_nothing(archive, capsys):
    before = catalog.CATALOG_FILE.read_bytes()
    assert fingerprint.main(["--archive-root", str(archive)], today=TODAY) == 0
    out = capsys.readouterr().out
    assert "2 `done` row(s) have no fingerprint" in out
    assert f"{sha(PAGE_HTML)[:16]}...  web-captures/navy/page.html" in out
    assert "DOC-0003" not in out and "DOC-0004" not in out
    assert "Dry run: nothing written. To write these 3 fingerprints" in out
    assert catalog.CATALOG_FILE.read_bytes() == before


def test_apply_fills_one_fingerprint_per_file_in_local_path_order(archive):
    assert fingerprint.main(["--archive-root", str(archive), "--apply"], today=TODAY) == 0
    rows = rows_by_id()
    assert rows["DOC-0001"]["sha256"] == f"{sha(PAGE_PDF)}; {sha(PAGE_HTML)}"
    assert rows["DOC-0002"]["sha256"] == sha(LAB_PDF)


def test_apply_adds_a_dated_note_after_the_existing_one(archive):
    fingerprint.main(["--archive-root", str(archive), "--apply"], today=TODAY)
    rows = rows_by_id()
    assert rows["DOC-0001"]["notes"] == f"Web page; capture. {NOTE}"
    assert rows["DOC-0002"]["notes"] == NOTE


def test_rows_with_a_fingerprint_or_not_done_are_never_changed(archive):
    before = rows_by_id()
    fingerprint.main(["--archive-root", str(archive), "--apply"], today=TODAY)
    after = rows_by_id()
    assert after["DOC-0003"] == before["DOC-0003"]
    assert after["DOC-0004"] == before["DOC-0004"]


def test_a_second_run_has_nothing_to_do(archive, capsys):
    fingerprint.main(["--archive-root", str(archive), "--apply"], today=TODAY)
    after_first = catalog.CATALOG_FILE.read_bytes()
    assert fingerprint.main(["--archive-root", str(archive), "--apply"], today=TODAY) == 0
    assert "Nothing to do" in capsys.readouterr().out
    assert catalog.CATALOG_FILE.read_bytes() == after_first


def test_a_missing_file_stops_without_writing(archive):
    (archive / "web-captures" / "navy" / "page.html").unlink()
    before = catalog.CATALOG_FILE.read_bytes()
    with pytest.raises(SystemExit) as err:
        fingerprint.main(["--archive-root", str(archive), "--apply"], today=TODAY)
    assert "DOC-0001: web-captures/navy/page.html" in str(err.value.code)
    assert catalog.CATALOG_FILE.read_bytes() == before
