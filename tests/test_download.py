"""Tests for the download stage. They use a fake web server, so no network is needed."""

import hashlib

import httpx
import pytest

from download import download, file_name, select_rows, site_folder

PDF = b"%PDF-1.5 test file"


def row(**fields: str) -> dict[str, str]:
    base = {
        "doc_id": "DOC-0001",
        "source_url": "https://jbphh-safewaters.org/public/x.pdf",
        "original_filename": "",
        "status": "to_download",
        "local_path": "",
        "title_as_posted": "t",
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


def test_download_refuses_path_owned_by_another_document(tmp_path):
    with pytest.raises(ValueError, match="already belongs to DOC-0099"):
        download(client(PDF), row(), tmp_path, {"raw/jbphh-safewaters/x.pdf": "DOC-0099"})
