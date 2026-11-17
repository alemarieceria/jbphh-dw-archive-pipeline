"""Tests for the discover step. The 20 zone pages and the I1 LTM listing were saved from the live
site on 2026-11-17 (tests/fixtures/discover/); the Navy and DOH listings are the inventory step's
saved pages (tests/fixtures/inventory/). No network is needed."""

import csv
import hashlib
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from jbphh_archive import discover, inventory
from jbphh_archive.catalog import CATALOG_FILE, ZONES_FILE, read_rows
from jbphh_archive.discover import (
    ZonePageError,
    agree,
    differences,
    fetch_zone_pages,
    link_key,
    link_values,
    period_of,
    posted_on,
    read_zone_page,
    stage_of,
    title_values,
    zone_page_url,
    zones_value,
)
from jbphh_archive.inventory import Result

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


def test_a_zone_page_error_is_retried(monkeypatch):
    monkeypatch.setattr(discover, "RETRY_SECONDS", 0)
    error = (FIXTURES / "inventory" / "navy_j1_application_error.html").read_text(encoding="utf-8")
    answers = [error, saved("I1")]

    def site(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=answers.pop(0))

    with httpx.Client(transport=httpx.MockTransport(site)) as client:
        (i1,) = fetch_zone_pages(client, [z for z in ZONES if z["zone_id"] == "I1"])
    assert i1.last_updated == "2025-08-20"


# ---- Proposing values


def test_stage_and_period_follow_the_vocabulary():
    assert stage_of("Immediate Drinking Water Sampling Plan and Results - December 2021") == "immediate"
    assert stage_of("Data Summary for Zone I1 Stage 2, 24 January 2022") == "stage_2"
    assert stage_of("LTM Laboratory Reports for Zone I1 Stage 5, 20 August 2022") == ""  # Stage 5 is LTM
    assert period_of("Data Summary for Zone I1 Stage 5 Long-Term Monitoring Period 1, 26 April 2022") == "ltm_p1"
    assert period_of("Quarter 3 - Samples Collected October through December of 2024") == "edwm_q3"
    assert period_of("Sampling Results for Waiawa Shaft EDWM Q4") == "edwm_q4"
    assert period_of("Post-EDWM (PEM) - Samples Collected from April 2025 onward") == "pem"
    assert period_of("Supporting LTM Documentation") == ""


def test_a_disagreement_is_flagged_not_picked():
    assert agree("period", "ltm_p2", "ltm_p2") == ("ltm_p2", "")
    assert agree("period", "", "ltm_p2") == ("ltm_p2", "")
    assert agree("period", "ltm_p2", "ltm_p3") == ("", "period: link text says ltm_p2, bold line says ltm_p3")


def test_i1_emergency_response_values_reproduce_the_catalog():
    """Group, phase, doc_type and date proposed for the 9 emergency response links match the catalog's rows."""
    rows = {link_key(r["source_url"]): r for r in read_rows(CATALOG_FILE)[1] if r["group"] == "zone_page_er"}
    for link in page("I1").links:
        if link.section == "emergency_response":
            proposed, flags = link_values(link)
            row = rows[link_key(link.url)]
            assert (proposed["group"], proposed["phase"], flags) == (row["group"], row["phase"], [])
            if proposed["doc_type"]:
                assert proposed["doc_type"] == row["doc_type"]
            if proposed["date_as_listed"]:
                assert proposed["date_as_listed"] == row["date_as_listed"]


def test_i1_monitoring_links_get_group_phase_and_period():
    proposals = {link.text: link_values(link)[0] for link in page("I1").links}

    def check(text, **expected):
        assert {key: proposals[text][key] for key in expected} == expected

    check(
        "Sampling Results for Zone I1 Long-Term Monitoring Period 4, 22 December 2022",
        group="zone_page_ltm",
        phase="ltm",
        period="ltm_p4",
        doc_type="results_crosstab",
        status="link_only",
        date_as_listed="2022-12-22",
        original_filename="LTM_Month_4-9_Sampling_Results_Zone_I1_22DEC2022.pdf",
    )
    check(
        "LTM Laboratory Reports for Zone I1 Stage 5, 20 August 2022",
        group="zone_page_ltm",
        phase="ltm",
        period="",
        stage="",
        doc_type="library_listing",
        status="link_only",
    )
    check("Sampling Results for Zone I1 EDWM Q2", group="zone_page_edwm", phase="edwm", period="edwm_q2")
    check("EDWM Laboratory Reports", group="zone_page_edwm", phase="edwm", doc_type="library_listing")
    check("Sampling Results for Waiawa Shaft EDWM Q1", group="source_water", phase="edwm", period="edwm_q1")
    check("Waiawa Shaft PFAS Results (April 2023)", group="source_water", phase="ltm", period="")
    a1_pem = next(link_values(link)[0] for link in page("A1").links if link.text == "Sampling Results for Zone A1 PEM")
    assert (a1_pem["group"], a1_pem["phase"], a1_pem["period"]) == ("zone_page_pem", "post_edwm", "pem")


def test_the_map_is_flagged():
    (outside,) = [link for link in page("I1").links if not link.section]
    proposed, flags = link_values(outside)
    assert flags == ["outside the page's sections"]
    assert (proposed["group"], proposed["phase"], proposed["status"]) == ("", "", "")


def test_title_values_reproduce_the_catalog():
    """Every library row but one gets the catalog's doc_type, sdg and level back from its title. DOC-0040's title
    says SDG C22A014-I1 and the catalog says C22A014; on a new row that is flagged, not guessed."""
    rows = [r for r in read_rows(CATALOG_FILE)[1] if r["library_id"]]
    wrong = [
        r["doc_id"]
        for r in rows
        if title_values(r["title_as_posted"]) != (r["doc_type"], r["sdg"], r["package_or_validation_level"])
    ]
    assert len(rows) == 123
    assert wrong == ["DOC-0040"]


def test_title_values_leave_an_unknown_title_blank():
    assert title_values("Something Else Entirely") == ("", "", "")


def test_zones_differ_only_when_the_site_posts_it_somewhere_the_catalog_does_not_cover():
    def row(zones):
        return {"zones": zones, **dict.fromkeys(discover.COMPARED, "")}

    assert differences({"zones": "I1"}, row("I1; D1")) == []  # DOC-0003: covers D1 too
    assert differences({"zones": "A1; I1"}, row("all")) == []  # DOC-0001: all covers the 19 zones
    assert differences({"zones": "A1; I1"}, row("I1")) == ["zones (catalog: I1)"]
    assert differences({"zones": "all"}, row("I1; D1")) == ["zones (catalog: I1; D1)"]
    assert differences({"zones": "I1", "title_as_posted": "New"}, row("I1") | {"title_as_posted": "Old"}) == [
        "title_as_posted (catalog: Old)"
    ]


# ---- The whole run, against a fake site


class FakeSite:
    """Answers like the live site: zone pages by idHTML, and each I1 listing's start page, then a page per
    menu choice or Next click (the sorted page also shows 10; only the menu label differs)."""

    def __init__(self):
        self.zone_by_idhtml = {zone_page_url(z).rsplit("=", 1)[1]: z["zone_id"] for z in ZONES}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if "idHTML" in request.url.params:
            return httpx.Response(200, text=saved(self.zone_by_idhtml[request.url.params["idHTML"]]))
        folder, listing = {
            "Navy Flushing Zone I1": ("inventory", "navy_i1"),
            "DoH Flushing Zone I1": ("inventory", "doh_i1"),
            "LTM Flushing Zone I1": ("discover", "ltm_i1"),
        }[request.url.params["subcategory"]]
        name = "start"
        if request.method == "POST":
            target = parse_qs(request.content.decode())["__EVENTTARGET"][0]
            name = {
                "ctl00$cphMain$ddlSortField": "start",
                "ctl00$cphMain$ddlShowItems": "page1",
                "ctl00$cphMain$btnDisplayNextPage": "page2",
            }[target]
        return httpx.Response(200, text=(FIXTURES / folder / f"{listing}_{name}.html").read_text(encoding="utf-8"))


def run(monkeypatch, tmp_path, zone: str) -> tuple[int, list[dict[str, str]]]:
    monkeypatch.setattr(discover, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(FakeSite())))
    monkeypatch.setattr(discover, "REPORTS_FOLDER", tmp_path)
    monkeypatch.setattr(inventory, "DELAY_SECONDS", 0)
    code = discover.main(["--zone", zone])
    (report,) = tmp_path.glob(f"*-discover-{zone}.csv")
    with report.open(newline="", encoding="utf-8") as f:
        return code, list(csv.DictReader(f))


def test_i1_matches_the_plans_i1_check(monkeypatch, tmp_path, capsys):
    """The plan's I1 check: 132 rows matched (9 zone page, 109 Navy, 14 DOH), 179 new link_only proposals
    (24 zone page links, 155 LTM listing results) and 37 rows on no source; plus the map, flagged."""
    code, report = run(monkeypatch, tmp_path, "I1")
    assert code == 0
    assert [r["row_type"] for r in report[:21]] == ["run"] + ["zone_page"] * 20
    assert report[0]["catalog_sha256"] == hashlib.sha256(CATALOG_FILE.read_bytes()).hexdigest()
    assert all(not r["flag"] for r in report if r["row_type"] == "zone_page")

    sources = {r["source"]: (r["result"], r["count"], r["flag"]) for r in report if r["row_type"] == "source"}
    assert sources == {
        "zone_page": ("read", "34", ""),
        "navy_listing": ("read", "109", ""),
        "doh_listing": ("read", "14", ""),
        "ltm_listing": ("read", "155", ""),
    }
    documents = [r for r in report if r["row_type"] == "document"]
    assert Counter((r["source"], r["result"]) for r in documents) == {
        ("zone_page", "matched"): 9,
        ("zone_page", "new"): 25,
        ("navy_listing", "matched"): 109,
        ("doh_listing", "matched"): 14,
        ("ltm_listing", "new"): 155,
    }
    assert sum(r["result"] == "new" and r["status"] == "link_only" for r in documents) == 179
    assert [r["link_text"] for r in documents if r["flag"]] == ["View Interactive Results Map"]
    assert "37 catalog rows for I1 are on no source" in capsys.readouterr().out


def test_existing_rows_get_their_discovery_bookkeeping_once(monkeypatch, tmp_path):
    _, report = run(monkeypatch, tmp_path, "I1")
    navy = next(r for r in report if r["doc_id"] == "DOC-0010")
    i1 = next(z for z in ZONES if z["zone_id"] == "I1")
    assert (navy["found_via"], navy["found_on"], navy["first_seen_utc"]) == (
        "navy_listing",
        i1["navy_listing_url"],
        navy["last_seen_utc"],
    )
    assert navy["group"] == navy["doc_type"] == ""  # an existing row's values stay the catalog's


def test_new_ltm_results_get_every_proposed_value(monkeypatch, tmp_path):
    _, report = run(monkeypatch, tmp_path, "I1")
    first = next(r for r in report if r["library_id"] == "pub_006426")
    expected = {
        "group": "ltm_lab_collection",
        "doc_type": "data_validation_report",
        "sdg": "DA42801A",
        "package_or_validation_level": "S2AVEM",
        "zones": "I1",
        "phase": "ltm",
        "stage": "",
        "period": "",
        "status": "link_only",
        "found_via": "ltm_listing",
        "date_as_listed": "2022-04-26",
        "size_listed": "108 KB",
        "original_filename": "pub_006426.pdf",
    }
    assert {key: first[key] for key in expected} == expected
    assert first["source_url"].endswith("StreamResource.axd?DSN=PUB&Mode=FileImage_Inline&ID=6426")


def test_a_catalog_row_the_site_no_longer_shows_is_missing():
    """Build the report with one zone page link and 108 of the 109 Navy results taken away."""
    zone = next(z for z in ZONES if z["zone_id"] == "I1")
    i1 = page("I1")
    i1.links = [link for link in i1.links if "ER_Sampling_Results_Zone_I1" not in link.url]  # DOC-0005
    pages = [i1 if z == "I1" else page(z) for z in ZONE_IDS]
    navy = [Result("pub_002926", "t", "pub_002926.pdf")]  # DOC-0011 only
    report = discover.build_report(zone, ZONES, read_rows(CATALOG_FILE)[1], pages, {"navy_listing": navy}, "now", "")
    missing = [(r["source"], r["doc_id"]) for r in report if r["result"] == "missing"]
    assert ("zone_page", "DOC-0005") in missing
    assert sum(source == "navy_listing" for source, _ in missing) == 108
    assert {r["source"]: r["result"] for r in report if r["row_type"] == "source"} == {
        "zone_page": "read",
        "navy_listing": "read",
        "doh_listing": "no_listing",
        "ltm_listing": "no_listing",
    }


def test_a_changed_title_is_flagged():
    zone = next(z for z in ZONES if z["zone_id"] == "I1")
    rows = [r | {"title_as_posted": "Old"} if r["doc_id"] == "DOC-0004" else r for r in read_rows(CATALOG_FILE)[1]]
    report = discover.build_report(zone, ZONES, rows, [page(z) for z in ZONE_IDS], {}, "now", "")
    (changed,) = [r for r in report if r["result"] == "changed"]
    assert (changed["doc_id"], changed["flag"]) == ("DOC-0004", "changed: title_as_posted (catalog: Old)")


def test_j1_reads_only_its_zone_page(monkeypatch, tmp_path):
    code, report = run(monkeypatch, tmp_path, "J1")
    assert code == 0
    assert {r["source"]: r["result"] for r in report if r["row_type"] == "source"} == {
        "zone_page": "read",
        "navy_listing": "no_listing",
        "doh_listing": "no_listing",
        "ltm_listing": "no_listing",
    }
