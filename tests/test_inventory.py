"""Tests for the inventory step. A fake Safe Waters site serves listing pages saved from the
live site on 2026-11-17 (tests/fixtures/inventory/), so no network is needed."""

import csv
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from jbphh_archive import inventory
from jbphh_archive.inventory import ListingError, Result, compare, fetch_listing, read_page

PAGES = Path(__file__).parent / "fixtures" / "inventory"
NAVY_I1 = "https://jbphh-safewaters.org/public/library/searchresults.aspx?dsn=pub&category=JBPHH&subcategory=Navy%20Flushing%20Zone%20I1"


def page(name: str) -> str:
    return (PAGES / f"{name}.html").read_text(encoding="utf-8")


class FakeSite:
    """Answers like the live listing: the start page, then a page per menu choice or Next click."""

    def __init__(self, errors_first: int = 0):
        self.errors_first = errors_first  # how many requests get "Application Error" before the site works
        self.posts: list[dict[str, list[str]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.errors_first:
            self.errors_first -= 1
            return httpx.Response(200, text=page("navy_j1_application_error"))
        listing = "doh_i1" if "DoH" in str(request.url) else "navy_i1"
        if request.method == "GET":
            return httpx.Response(200, text=page(f"{listing}_start"))
        form = parse_qs(request.content.decode())
        self.posts.append(form)
        target = form["__EVENTTARGET"][0]
        name = {
            "ctl00$cphMain$ddlSortField": "start",  # the sorted page also shows 10; only the menu label differs
            "ctl00$cphMain$ddlShowItems": "page1",
            "ctl00$cphMain$btnDisplayNextPage": "page2",
        }[target]
        return httpx.Response(200, text=page(f"{listing}_{name}"))


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(inventory, "DELAY_SECONDS", 0)
    monkeypatch.setattr(inventory, "RETRY_SECONDS", 0)


def client(site: FakeSite) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(site))


def test_read_page_reads_results_and_counts():
    results, first, last, total = read_page(page("navy_i1_page1"))
    assert (first, last, total, len(results)) == (1, 100, 109, 100)
    assert results[0].library_id == "pub_002925"
    assert results[0].filename == "pub_002925.pdf"
    assert results[0].title
    assert (results[0].date, results[0].size) == ("2022-02-09", "31 MB")  # as DOC-0010 records them


def test_read_page_ignores_the_ids_in_the_menu_setting():
    """Page 2 also lists every ID seen so far in a menu setting; only its 9 real results count."""
    results, first, last, _ = read_page(page("navy_i1_page2"))
    assert (first, last, len(results)) == (101, 109, 9)
    assert [r.library_id for r in results][-1] == "pub_003033"


def test_read_page_rejects_an_error_page():
    with pytest.raises(ListingError, match="Application Error"):
        read_page(page("navy_j1_application_error"))


def test_fetch_listing_sorts_shows_100_and_reads_every_page():
    site = FakeSite()
    results = fetch_listing(client(site), NAVY_I1)
    ids = [r.library_id for r in results]
    assert ids == [f"pub_{n:06d}" for n in range(2925, 3034)]  # the 109 known Navy I1 IDs, in order
    sort, show, next_page = site.posts
    assert '"value": "SystemFilename"' in sort["ctl00_cphMain_ddlSortField_ClientState"][0]
    assert '"value": "100"' in show["ctl00_cphMain_ddlShowItems_ClientState"][0]
    assert next_page["__EVENTTARGET"] == ["ctl00$cphMain$btnDisplayNextPage"]


def test_a_one_off_application_error_is_retried():
    """Like Navy H2 on 2026-11-17: an error, then the listing loads on the next try."""
    site = FakeSite(errors_first=1)
    assert len(fetch_listing(client(site), NAVY_I1)) == 109


def test_a_listing_that_keeps_failing_is_unavailable():
    """Like Navy J1: "Application Error" on every try."""
    site = FakeSite(errors_first=99)
    with pytest.raises(ListingError, match="3 tries"):
        fetch_listing(client(site), NAVY_I1)


def test_compare_finds_both_kinds_of_gap():
    def row(doc_id, library_id, group="navy_lab_collection", zones="I1"):
        return {
            "doc_id": doc_id,
            "library_id": library_id,
            "group": group,
            "zones": zones,
            "status": "done",
            "title_as_posted": "t",
            "original_filename": f"{library_id}.pdf",
        }

    rows = [row("DOC-0001", "pub_000001"), row("DOC-0002", "pub_000002"), row("DOC-0003", "pub_000003", zones="D1")]
    listed = [Result("pub_000001", "a", "pub_000001.pdf"), Result("pub_000009", "b", "pub_000009.pdf")]
    report = {r["library_id"]: (r["doc_id"], r["result"]) for r in compare("navy", "I1", listed, rows)}
    assert report == {
        "pub_000001": ("DOC-0001", "matched"),
        "pub_000009": ("", "not_in_catalog"),
        "pub_000002": ("DOC-0002", "not_on_listing"),  # DOC-0003 is a D1 document, so it isn't expected here
    }


def run(monkeypatch, tmp_path, zone: str, site: FakeSite) -> tuple[int, list[dict[str, str]]]:
    monkeypatch.setattr(inventory, "make_client", lambda: client(site))
    monkeypatch.setattr(inventory, "REPORTS_FOLDER", tmp_path)
    code = inventory.main(["--zone", zone])
    (report,) = tmp_path.glob(f"*-inventory-{zone}.csv")
    with report.open(newline="", encoding="utf-8") as f:
        return code, list(csv.DictReader(f))


def test_i1_matches_the_known_facts(monkeypatch, tmp_path):
    """The real catalog against the saved I1 listings: Navy 109 and DOH 14, every one matched to a `done` row."""
    code, report = run(monkeypatch, tmp_path, "I1", FakeSite())
    assert code == 0
    for listing, count in (("navy", 109), ("doh", 14)):
        rows = [r for r in report if r["listing"] == listing]
        assert len(rows) == count
        assert {(r["result"], r["catalog_status"]) for r in rows} == {("matched", "done")}


def test_j1_has_no_listings_and_asks_the_site_nothing(monkeypatch, tmp_path):
    site = FakeSite(errors_first=99)
    code, report = run(monkeypatch, tmp_path, "J1", site)
    assert code == 0
    assert [(r["listing"], r["result"]) for r in report] == [("navy", "no_listing"), ("doh", "no_listing")]
    assert site.errors_first == 99  # no requests were made


def test_unknown_zone_stops_with_the_zone_list():
    with pytest.raises(SystemExit) as err:
        inventory.main(["--zone", "Z9"])
    assert "Zone Z9 is not in catalog/zones.csv" in str(err.value.code)
