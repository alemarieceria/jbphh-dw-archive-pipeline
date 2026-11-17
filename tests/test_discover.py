"""Tests for the discover step. The 20 zone pages were saved from the live site on 2026-11-17
(tests/fixtures/discover/), so no network is needed."""

from collections import Counter
from pathlib import Path

import httpx
import pytest

from jbphh_archive import discover
from jbphh_archive.catalog import CATALOG_FILE, ZONES_FILE, read_rows
from jbphh_archive.discover import (
    ZonePageError,
    fetch_zone_pages,
    link_key,
    posted_on,
    read_zone_page,
    zone_page_url,
    zones_value,
)

FIXTURES = Path(__file__).parent / "fixtures"
ZONES = read_rows(ZONES_FILE)[1]
ZONE_IDS = [z["zone_id"] for z in ZONES]
WAIAWA_EDWM = "https://jbphh-safewaters.org/public/EDWM_Q{}_Sampling_Results_Waiawa_Shaft_24JUL2025.pdf"
WAIAWA_PFAS = "https://jbphh-safewaters.org/public/Waiawa_Shaft_PFAS_Results_06JUN23.pdf"


def saved(zone_id: str) -> str:
    return (FIXTURES / "discover" / f"zone_{zone_id.lower()}.html").read_text(encoding="utf-8")


def page(zone_id: str) -> discover.ZonePage:
    return read_zone_page(zone_id, saved(zone_id))


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(discover, "DELAY_SECONDS", 0)


def test_zone_page_url_is_the_inner_page():
    i1 = next(z for z in ZONES if z["zone_id"] == "I1")
    assert zone_page_url(i1) == "https://jbphh-safewaters.org/public/framework/html.aspx?dsn=SYSTM&idHTML=10762"


def test_i1_page_matches_the_known_facts():
    """34 links: the map outside the sections, 9 EDWM, 15 LTM and 9 emergency response (checked 2026-11-17)."""
    i1 = page("I1")
    assert i1.last_updated == "2025-08-20"
    assert Counter(link.section for link in i1.links) == {"": 1, "edwm": 9, "ltm": 15, "emergency_response": 9}
    (outside,) = [link for link in i1.links if not link.section]
    assert (outside.part, outside.text) == ("Interactive Map:", "View Interactive Results Map")
    assert outside.url.startswith("https://app.powerbi.com/")


def test_each_link_keeps_its_bold_line():
    links = {link.text: link for link in page("I1").links}
    q2 = links["Sampling Results for Zone I1 EDWM Q2"]
    assert (q2.section, q2.part) == ("edwm", "Quarter 2 - Samples Collected July through September of 2024")
    p7 = links["Sampling Results for Zone I1 Long-Term Monitoring Period 7, 20 August 2024"]
    assert (p7.section, p7.part) == ("ltm", "Period 7 - Samples Collected January through March of 2024")
    advisory = links["Health Advisory Amended for Red Hill Housing"]
    assert advisory.part == "Current Status of the Hawaii Department of Health Public Health Advisory"


def test_text_without_a_link_is_not_a_document():
    """I1's post-EDWM part says "No samples were collected from this zone" inside an <a> with no link."""
    pem = [link for link in page("I1").links if link.part.startswith("Post-EDWM (PEM)")]
    assert pem == []
    (a1_pem,) = [link for link in page("A1").links if link.part.startswith("Post-EDWM (PEM)")]
    assert a1_pem.url.endswith("EDWM_PEM_Zone_A1_20260406.pdf")


def test_i1_emergency_response_links_are_the_9_zone_page_er_rows():
    """7 match the catalog's source_url exactly; the DOH and Navy listings (DOC-0006, DOC-0007) by subcategory."""
    links = [link.url for link in page("I1").links if link.section == "emergency_response"]
    rows = [r for r in read_rows(CATALOG_FILE)[1] if r["group"] == "zone_page_er"]  # all 9 are I1's
    assert len(links) == len(rows) == 9
    assert sum(url in {r["source_url"] for r in rows} for url in links) == 7
    assert {link_key(url) for url in links} == {link_key(r["source_url"]) for r in rows}


def test_link_key_knows_a_listing_by_its_subcategory():
    wrapped = (
        "https://jbphh-safewaters.org/public/framework/appcontainer.aspx?url=../library/searchresults.aspx"
        "&dsn=pub&category=JBPHH&subcategory=Navy%20Flushing%20Zone%20I1&title=Navy&idMenu=88894&ddlDSN=SYSTM"
    )
    plain = "https://jbphh-safewaters.org/public/library/searchresults.aspx?dsn=pub&category=JBPHH&subcategory=Navy%20Flushing%20Zone%20I1"
    assert link_key(wrapped) == link_key(plain) == "listing:Navy Flushing Zone I1"
    assert link_key(WAIAWA_PFAS) == WAIAWA_PFAS


def test_every_last_updated_matches_zones_csv():
    pages = [page(zone_id) for zone_id in ZONE_IDS]
    assert {p.zone_id: p.last_updated for p in pages} == {z["zone_id"]: z["page_last_updated"] for z in ZONES}


def test_j1_has_only_the_edwm_section():
    assert {link.section for link in page("J1").links} == {"", "edwm"}


def test_waiawa_shaft_files_list_every_zone_that_posts_them():
    """The 4 EDWM Waiawa Shaft files are on all 20 pages; the PFAS file on the 19 flushing zones, not J1."""
    zones = posted_on([page(zone_id) for zone_id in ZONE_IDS])
    for quarter in range(1, 5):
        assert zones_value(zones[WAIAWA_EDWM.format(quarter)], ZONE_IDS) == "all"
    pfas = zones_value(zones[WAIAWA_PFAS], ZONE_IDS)
    assert pfas == "; ".join(z for z in ZONE_IDS if z != "J1")
    assert zones_value(zones["listing:EDWM"], ZONE_IDS) == "all"
    assert zones["listing:LTM Flushing Zone I1"] == ["I1"]


def test_an_error_page_is_not_read():
    error = (FIXTURES / "inventory" / "navy_j1_application_error.html").read_text(encoding="utf-8")
    with pytest.raises(ZonePageError, match="Application Error"):
        read_zone_page("I1", error)


def test_an_unknown_heading_stops_the_read():
    changed = saved("I1").replace(
        '<div class="heading">Emergency Response</div>', '<div class="heading">Recovery</div>'
    )
    with pytest.raises(ZonePageError, match='unknown section heading "Recovery"'):
        read_zone_page("I1", changed)


def test_fetch_zone_pages_reads_every_zone_in_order():
    by_id = {zone_page_url(z).rsplit("=", 1)[1]: z["zone_id"] for z in ZONES}

    def site(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=saved(by_id[request.url.params["idHTML"]]))

    with httpx.Client(transport=httpx.MockTransport(site)) as client:
        pages = fetch_zone_pages(client, ZONES)
    assert [p.zone_id for p in pages] == ZONE_IDS
