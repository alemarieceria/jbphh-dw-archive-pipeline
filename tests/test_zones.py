"""Checks on catalog/zones.csv: the zones match the plan's Scope row, and every link follows the site's pattern."""

from jbphh_archive import REPO_ROOT
from jbphh_archive.catalog import read_rows

ZONES_FILE = REPO_ROOT / "catalog" / "zones.csv"

# The plan's Scope row: 19 flushing zones, plus J1 (Manana Housing), which has no emergency response documents.
FLUSHING_ZONES = [
    "A1",
    "A2",
    "A3",
    "B1",
    "C1",
    "C2",
    "C3",
    "D1",
    "D2",
    "D3",
    "D4",
    "E1",
    "F1",
    "F2",
    "G1",
    "H1",
    "H2",
    "H3",
    "I1",
]
LISTING = "https://jbphh-safewaters.org/public/library/searchresults.aspx?dsn=pub&category=JBPHH&subcategory={}%20Flushing%20Zone%20{}"


def zones() -> list[dict[str, str]]:
    return read_rows(ZONES_FILE)[1]


def test_zones_match_the_plan():
    ids = [z["zone_id"] for z in zones()]
    assert ids == [*FLUSHING_ZONES, "J1"]
    assert all(z["name"] for z in zones())


def test_only_j1_has_no_emergency_response():
    assert {z["zone_id"]: z["emergency_response"] for z in zones()} == {z: "yes" for z in FLUSHING_ZONES} | {"J1": "no"}


def test_links_follow_the_site_pattern():
    for z in zones():
        zone = z["zone_id"]
        assert z["zone_page_url"].startswith("https://jbphh-safewaters.org/public/framework/appcontainertall.aspx?")
        assert f"&title=Zone%20{zone}&" in z["zone_page_url"]
        listings = [z["navy_listing_url"], z["doh_listing_url"], z["ltm_listing_url"]]
        if z["emergency_response"] == "yes":
            assert listings == [LISTING.format(source, zone) for source in ("Navy", "DoH", "LTM")]
        else:
            assert listings == ["", "", ""]
