"""Tests for the download stage. They use a fake web server, so no network is needed."""

import hashlib

import httpx
import pytest

import jbphh_archive.download as download_step
from jbphh_archive.catalog import read_rows, write_rows
from jbphh_archive.download import download, file_name, select_rows, site_folder

PDF = b"%PDF-1.5 test file"


def row(**fields: str) -> dict[str, str]:
    base = {
        "doc_id": "DOC-0001",
        "source_url": "https://jbphh-safewaters.org/public/x.pdf",
        "original_filename": "",
        "status": "to_download",
        "local_path": "",
        "title_as_posted": "t",
        "duplicate_of": "",
        "sha256": "",
        "retrieved_utc": "",
    }
    return base | fields


def client(content: bytes, headers: dict[str, str] | None = None) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=content, headers=headers)))


def test_site_folder():
    assert site_folder("https://health.hawaii.gov/a.pdf") == "doh"
    assert site_folder("https://example.com/a.pdf") == "other"


def test_file_name_prefers_registry_then_server_then_url():
    headers = httpx.Headers({"content-disposition": 'attachment; filename="from-server.pdf"'})
    assert file_name(row(original_filename="pub_002925.pdf"), headers) == "pub_002925.pdf"
    assert file_name(row(), headers) == "from-server.pdf"
    assert file_name(row(source_url="https://x.org/a/My%20File.pdf"), httpx.Headers()) == "My File.pdf"


def test_select_rows_skips_done_and_unfound():
    rows = [row(doc_id="DOC-0001"), row(doc_id="DOC-0002", status="done"), row(doc_id="DOC-0003", source_url="")]
    assert [r["doc_id"] for r in select_rows(rows, None, None)] == ["DOC-0001"]


def test_select_rows_skips_duplicates():
    rows = [row(doc_id="DOC-0001"), row(doc_id="DOC-0002", duplicate_of="DOC-0001")]
    assert [r["doc_id"] for r in select_rows(rows, None, None)] == ["DOC-0001"]


def test_dry_run_reads_the_repo_catalog_without_the_drive(tmp_path, monkeypatch, capsys):
    catalog = tmp_path / "documents.csv"
    write_rows(catalog, list(row()), [row(), row(doc_id="DOC-0002", status="done")])
    monkeypatch.setattr(download_step, "CATALOG_FILE", catalog)
    monkeypatch.delenv("ARCHIVE_ROOT", raising=False)
    assert download_step.main(["--dry-run"]) == 0
    assert "1 file(s) to download." in capsys.readouterr().out


def test_download_saves_file_and_records_provenance(tmp_path):
    updates = download(client(PDF), row(), tmp_path, {})
    assert updates["local_path"] == "raw/jbphh-safewaters/x.pdf"
    assert (tmp_path / updates["local_path"]).read_bytes() == PDF
    assert updates["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert updates["status"] == "done"


def test_download_rejects_error_page_and_leaves_nothing(tmp_path):
    with pytest.raises(ValueError, match="did not return a PDF"):
        download(client(b"<html>Application Error</html>"), row(), tmp_path, {})
    assert not any(tmp_path.rglob("*.pdf*"))


def test_download_checks_pdf_header_split_across_chunks(tmp_path):
    chunks = httpx.MockTransport(lambda _: httpx.Response(200, content=iter([b"%P", b"DF-1.5", b" rest"])))
    updates = download(httpx.Client(transport=chunks), row(), tmp_path, {})
    assert (tmp_path / updates["local_path"]).read_bytes() == b"%PDF-1.5 rest"


def test_main_downloads_and_updates_the_catalog(tmp_path, monkeypatch):
    """A full run: fake website in, file on the fake Drive and an updated catalog row out."""
    archive = tmp_path / "archive"
    (archive / "registry").mkdir(parents=True)
    catalog = tmp_path / "documents.csv"
    rows = [
        row(),
        row(doc_id="DOC-0002", source_url="https://jbphh-safewaters.org/public/y.pdf", duplicate_of="DOC-0001"),
    ]
    write_rows(catalog, list(row()), rows)

    requested: list[str] = []

    def website(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=PDF)

    monkeypatch.setattr(download_step, "CATALOG_FILE", catalog)
    monkeypatch.setattr(download_step, "DELAY_SECONDS", 0)
    monkeypatch.setattr(download_step.httpx, "HTTPTransport", lambda **_: httpx.MockTransport(website))

    assert download_step.main(["--archive-root", str(archive)]) == 0

    assert requested == ["https://jbphh-safewaters.org/public/x.pdf"]  # the duplicate was skipped
    assert (archive / "raw" / "jbphh-safewaters" / "x.pdf").read_bytes() == PDF
    _, saved = read_rows(catalog)
    assert saved[0]["status"] == "done"
    assert saved[0]["local_path"] == "raw/jbphh-safewaters/x.pdf"
    assert saved[0]["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert saved[0]["retrieved_utc"].endswith("Z")
    assert saved[1]["status"] == "to_download"  # the duplicate row is unchanged


def test_download_refuses_path_owned_by_another_document(tmp_path):
    with pytest.raises(ValueError, match="already belongs to DOC-0099"):
        download(client(PDF), row(), tmp_path, {"raw/jbphh-safewaters/x.pdf": "DOC-0099"})
