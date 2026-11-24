"""Tests for the verify step. Each test uses a small catalog and a made-up archive folder in a
temporary folder, and fake Navy and DOH listings, so neither the Shared Drive nor the website is
touched."""

import csv
import hashlib
from pathlib import Path

import pytest

from jbphh_archive import catalog, inventory, verify
from jbphh_archive.catalog import write_rows
from jbphh_archive.inventory import ListingError, Result
from jbphh_archive.validate import DOCUMENT_COLUMNS, LINK_COLUMNS

FILES = {
    "raw/jbphh-safewaters/pub_000001.pdf": b"%PDF-1.5 Navy lab report",
    "raw/jbphh-safewaters/pub_000007.pdf": b"%PDF-1.5 Navy lab report",  # a copy of pub_000001
    "raw/doh/pub_000002.pdf": b"%PDF-1.5 DOH lab report",
    "raw/cpf-navy/plan.pdf": b"%PDF-1.5 plan for all zones",
    "raw/other/d1.pdf": b"%PDF-1.5 a D1 document",
    "web-captures/navy/page.pdf": b"%PDF-1.5 captured page",
    "web-captures/navy/page.html": b"<html>captured page</html>",
    "web-captures/README.txt": b"How the pages were captured.",
}


def sha(path: str) -> str:
    return hashlib.sha256(FILES[path]).hexdigest()


def doc(doc_id: str, local_path: str = "", **values: str) -> dict[str, str]:
    """A valid `done` row whose fingerprints match its files, changed by `values`."""
    paths = local_path.split("; ") if local_path else []
    row = dict.fromkeys(DOCUMENT_COLUMNS, "") | {
        "doc_id": doc_id,
        "group": "governing",
        "title_as_posted": f"Document {doc_id}",
        "source_url": "https://jbphh-safewaters.org/public/a.pdf",
        "doc_type": "plan",
        "zones": "I1",
        "phase": "emergency_response",
        "status": "done",
        "retrieved_utc": "2026-10-31T07:25:23Z",
        "sha256": "; ".join(sha(p) for p in paths),
        "local_path": local_path,
    }
    return row | values


def lab(doc_id: str, library_id: str, path: str, group: str = "navy_lab_collection", **values: str) -> dict[str, str]:
    return doc(doc_id, path, group=group, doc_type="lab_report", library_id=library_id, **values)


ROWS = [
    lab("DOC-0001", "pub_000001", "raw/jbphh-safewaters/pub_000001.pdf", sdg="A1"),
    lab("DOC-0002", "pub_000002", "raw/doh/pub_000002.pdf", group="doh_lab_collection", sdg="B1"),
    doc("DOC-0003", "raw/cpf-navy/plan.pdf", zones="all"),
    doc("DOC-0004", "web-captures/navy/page.pdf; web-captures/navy/page.html", group="web_page", doc_type="web_page"),
    doc("DOC-0005", "raw/other/d1.pdf", zones="D1"),
    doc("DOC-0006", status="to_find", source_url="", retrieved_utc="", title_as_posted="A plan still to find"),
    lab("DOC-0007", "pub_000007", "raw/jbphh-safewaters/pub_000007.pdf", sdg="C1", duplicate_of="DOC-0001"),
]
LISTED = {"navy": ["pub_000001", "pub_000007"], "doh": ["pub_000002"]}


@pytest.fixture
def archive(tmp_path, monkeypatch) -> Path:
    """An archive folder holding FILES, a catalog of ROWS with no links, and fake listings showing LISTED."""
    root = tmp_path / "archive"
    (root / "registry").mkdir(parents=True)
    for path, content in FILES.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(content)
    write_catalog(tmp_path / "documents.csv", ROWS)
    write_rows(tmp_path / "document_links.csv", LINK_COLUMNS, [])
    monkeypatch.setattr(catalog, "CATALOG_FILE", tmp_path / "documents.csv")
    monkeypatch.setattr(catalog, "LINKS_FILE", tmp_path / "document_links.csv")
    monkeypatch.setattr(inventory, "REPORTS_FOLDER", tmp_path / "reports")
    monkeypatch.delenv("ARCHIVE_ROOT", raising=False)
    set_listings(monkeypatch, LISTED)
    return root


def write_catalog(path: Path, rows: list[dict[str, str]]) -> None:
    write_rows(path, DOCUMENT_COLUMNS, rows)


def set_listings(monkeypatch, listed: dict[str, list[str]], unavailable: tuple[str, ...] = ()) -> None:
    def fake_fetch(_client, url: str) -> list[Result]:
        listing = "doh" if "DoH" in url else "navy"
        if listing in unavailable:
            raise ListingError('the site showed "Application Error" (3 tries)')
        return [Result(library_id=i, title=f"Report {i}", filename=f"{i}.pdf") for i in listed[listing]]

    monkeypatch.setattr(verify, "fetch_listing", fake_fetch)


def run(archive: Path) -> tuple[int, list[dict[str, str]]]:
    code = verify.main(["--zone", "I1", "--archive-root", str(archive)])
    (report,) = (Path(inventory.REPORTS_FOLDER)).glob("*-verify-I1.csv")
    with report.open(encoding="utf-8", newline="") as f:
        return code, list(csv.DictReader(f))


def results(report: list[dict[str, str]], check: str) -> list[tuple[str, str, str]]:
    return [(r["doc_id"], r["item"], r["result"]) for r in report if r["check"] == check]


def test_a_complete_archive_passes_and_lists_every_file(archive, capsys):
    code, report = run(archive)
    assert code == 0
    files = results(report, "files")
    assert len(files) == 6 and {result for _, _, result in files} == {"ok"}
    assert ("DOC-0004", "web-captures/navy/page.html", "ok") in files
    out = capsys.readouterr().out
    assert "1. Files: 6 of 6 files are on the Drive and match their fingerprints. PASS" in out
    assert "Every check passed." in out


def test_rows_for_all_zones_count_and_other_zones_dont(archive):
    _, report = run(archive)
    doc_ids = {doc_id for doc_id, _, _ in results(report, "files")}
    assert "DOC-0003" in doc_ids  # zones = all
    assert "DOC-0005" not in doc_ids  # zones = D1


def test_a_changed_missing_or_unfingerprinted_file_fails(archive, tmp_path):
    (archive / "raw/cpf-navy/plan.pdf").write_bytes(b"%PDF-1.5 changed")
    (archive / "web-captures/navy/page.html").unlink()
    rows = [dict(r) for r in ROWS]
    rows[1]["sha256"] = ""
    write_catalog(catalog.CATALOG_FILE, rows)
    code, report = run(archive)
    assert code == 1
    failed = [r for r in results(report, "files") if r[2] != "ok"]
    assert failed == [
        ("DOC-0002", "raw/doh/pub_000002.pdf", "no_fingerprint"),
        ("DOC-0003", "raw/cpf-navy/plan.pdf", "changed"),
        ("DOC-0004", "web-captures/navy/page.html", "missing"),
    ]


def test_a_drive_file_no_row_lists_fails_but_readme_files_dont(archive):
    (archive / "raw/other/stray.pdf").write_bytes(b"%PDF-1.5 saved but never cataloged")
    code, report = run(archive)
    assert code == 1
    assert results(report, "drive") == [("", "raw/other/stray.pdf", "not_in_catalog")]


def test_listings_that_differ_from_the_catalog_fail(archive, monkeypatch):
    set_listings(monkeypatch, {"navy": ["pub_000001", "pub_000099"], "doh": ["pub_000002"]})
    code, report = run(archive)
    assert code == 1
    assert results(report, "listings") == [
        ("", "navy", "problem"),
        ("", "pub_000099", "not_in_catalog"),
        ("DOC-0007", "pub_000007", "not_on_listing"),
        ("", "doh", "ok"),
    ]


def test_an_unavailable_listing_fails(archive, monkeypatch):
    set_listings(monkeypatch, LISTED, unavailable=("doh",))
    code, report = run(archive)
    assert code == 1
    assert ("", "doh", "listing_unavailable") in results(report, "listings")


def test_catalog_rule_problems_fail(archive):
    rows = [dict(r) for r in ROWS]
    rows[2]["phase"] = "later"
    write_catalog(catalog.CATALOG_FILE, rows)
    code, report = run(archive)
    assert code == 1
    (problem,) = [r for r in report if r["check"] == "catalog"]
    assert problem["result"] == "problem" and "'later' is not in the vocabulary" in problem["detail"]


def test_counts_and_known_gaps_dont_fail(archive):
    code, report = run(archive)
    assert code == 0
    counts = {r["item"]: r["count"] for r in report if r["check"] == "counts"}
    assert counts == {"done": "5", "to_find": "1"}  # DOC-0005 is D1's
    gaps = [(r["doc_id"], r["item"], r["detail"]) for r in report if r["check"] == "gaps"]
    assert gaps == [
        ("DOC-0006", "plan", "to_find: A plan still to find"),
        ("DOC-0007", "SDG C1", "SDG C1 has no report of its own: DOC-0007 is a copy of DOC-0001"),
    ]


def test_a_batch_with_only_a_validation_report_is_a_known_gap(archive):
    rows = [*ROWS, doc("DOC-0008", "raw/cpf-navy/plan.pdf", doc_type="data_validation_report", sdg="D1")]
    write_catalog(catalog.CATALOG_FILE, rows)
    code, report = run(archive)
    assert code == 0
    gaps = [(r["doc_id"], r["item"], r["detail"]) for r in report if r["check"] == "gaps"]
    assert ("DOC-0008", "SDG D1", "SDG D1 has no lab report, only DOC-0008 (data_validation_report)") in gaps


def test_it_never_changes_the_catalog(archive, monkeypatch):
    before = catalog.CATALOG_FILE.read_bytes()
    set_listings(monkeypatch, {"navy": [], "doh": []})
    run(archive)
    assert catalog.CATALOG_FILE.read_bytes() == before
