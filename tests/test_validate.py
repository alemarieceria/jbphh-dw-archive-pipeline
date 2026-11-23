"""Tests for the validate step: each rule on small made-up rows, the real catalog files, and that the
code's columns and allowed values match catalog/README.md."""

import re
from pathlib import Path

import pytest

from jbphh_archive import catalog, validate
from jbphh_archive.catalog import ZONES_FILE, read_rows, write_rows
from jbphh_archive.validate import (
    COMMUNITY_COLUMNS,
    DOCUMENT_COLUMNS,
    LINK_COLUMNS,
    RELATIONS,
    VOCABULARY,
    ZONE_COLUMNS,
    community_problems,
    document_problems,
    is_date,
    is_utc,
    link_problems,
    list_values,
    zone_problems,
)

README = Path(catalog.CATALOG_FILE).parent / "README.md"
ZONES = read_rows(ZONES_FILE)[1]
ZONE_IDS = [z["zone_id"] for z in ZONES]
SHA = "a" * 64


def doc(**values: str) -> dict[str, str]:
    """A valid `done` row, changed by `values`."""
    row = dict.fromkeys(DOCUMENT_COLUMNS, "") | {
        "doc_id": "DOC-0001",
        "group": "navy_lab_collection",
        "title_as_posted": "Laboratory Report 810-12264-1, Level 4",
        "source_url": "https://jbphh-safewaters.org/public/a.pdf",
        "doc_type": "lab_report",
        "date_as_listed": "2022-02-09",
        "zones": "I1",
        "phase": "emergency_response",
        "status": "done",
        "retrieved_utc": "2026-10-31T07:25:23Z",
        "sha256": SHA,
        "local_path": "raw/jbphh-safewaters/a.pdf",
    }
    return row | values


def problems(*rows: dict[str, str]) -> list[str]:
    return document_problems(list(rows), ZONE_IDS)


# ---- The real catalog files


def test_the_catalog_follows_its_rules(capsys):
    assert validate.main([]) == 0, capsys.readouterr().out


def test_a_wrong_column_list_is_reported(tmp_path, monkeypatch):
    columns, rows = read_rows(catalog.CATALOG_FILE)
    path = tmp_path / "documents.csv"
    write_rows(path, [c for c in columns if c != "notes"], [{k: v for k, v in r.items() if k != "notes"} for r in rows])
    monkeypatch.setattr(catalog, "CATALOG_FILE", path)
    found, _ = validate.all_problems()  # the rows aren't checked when the columns are wrong
    assert len(found) == 1
    assert found[0].startswith("documents.csv: columns are doc_id, group,")
    assert found[0].endswith(f"catalog/README.md lists {', '.join(DOCUMENT_COLUMNS)}")


# ---- catalog/README.md lists the same columns and values as the code


def readme_rows(section: str) -> dict[str, list[str]]:
    """Each column's table row in a README section, as its cells."""
    text = README.read_text(encoding="utf-8").split(f"## {section}")[1].split("\n## ")[0]
    rows = {}
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.startswith("| `"):
            for name in re.findall(r"`(\w+)`", cells[0]):
                rows[name] = cells
    return rows


@pytest.mark.parametrize(
    ("section", "columns"),
    [
        ("documents.csv", DOCUMENT_COLUMNS),
        ("document_links.csv", LINK_COLUMNS),
        ("zones.csv", ZONE_COLUMNS),
        ("communities.csv", COMMUNITY_COLUMNS),
    ],
)
def test_the_readme_lists_the_same_columns(section, columns):
    assert list(readme_rows(section)) == columns


def readme_values(cells: list[str]) -> set[str]:
    """The values a column's README row names in backticks (its format and description), with
    ranges such as `stage_1` to `stage_4` filled in."""
    text = " ".join(cells[1:3])
    values = set(re.findall(r"`([a-z][a-z0-9_]*)`", text))
    for prefix, first, last in re.findall(r"`([a-z_]+?)(\d+)` to `\1(\d+)`", text):
        values |= {f"{prefix}{n}" for n in range(int(first), int(last) + 1)}
    return values - {"notes"}


@pytest.mark.parametrize("column", list(VOCABULARY))
def test_the_readme_lists_the_same_allowed_values(column):
    assert readme_values(readme_rows("documents.csv")[column]) == set(VOCABULARY[column])


def test_the_readme_lists_the_same_relations():
    assert readme_values(readme_rows("document_links.csv")["relation"]) == set(RELATIONS)


# ---- Formats


def test_list_values_follow_the_separator_rule():
    assert list_values("I1; D1") == (["I1", "D1"], "")
    assert list_values("")[1] == ""
    assert list_values("I1;D1")[1] == "separate values with '; ' (semicolon, one space)"
    assert list_values("I1 ; D1")[1] == "separate values with '; ' (semicolon, one space)"
    assert list_values("I1; I1")[1] == "lists a value twice"
    assert list_values(" I1")[1] == "starts or ends with a space"


def test_dates_and_times():
    assert is_date("2022-02-09") and not is_date("2022-2-9") and not is_date("4/26/2022")
    assert is_date("2021-12", month_only=True) and not is_date("2021-12")
    assert not is_date("2022-02-30")
    assert is_utc("2026-10-31T07:25:23Z") and not is_utc("2026-10-31 07:25:23") and not is_utc("2026-10-31")
    assert is_utc("2026-10-31", date_only=True)


# ---- documents.csv rules


def test_a_valid_row_has_no_problems():
    assert problems(doc()) == []


def test_required_values_and_vocabulary():
    found = problems(doc(doc_type="", group="lab"))
    assert found == [
        "documents.csv line 2 (DOC-0001), doc_type: is blank",
        "documents.csv line 2 (DOC-0001), group: 'lab' is not in the vocabulary",
    ]


def test_doc_ids_are_well_formed_and_unique():
    assert problems(doc(), doc()) == ["documents.csv line 3 (DOC-0001), doc_id: DOC-0001 is used twice"]
    assert problems(doc(doc_id="DOC-1")) == ["documents.csv line 2 (DOC-1), doc_id: 'DOC-1' is not like DOC-0001"]


def test_zones_are_known_zone_ids_or_all_alone():
    assert problems(doc(zones="A1; A2; A3; B1; C1; C2; C3; D1; D2; D3; D4; E1; F1; F2; G1; H1; H2; H3; I1")) == []
    assert problems(doc(zones="I1; Z9")) == ["documents.csv line 2 (DOC-0001), zones: Z9 not in zones.csv"]
    assert problems(doc(zones="all; I1")) == ["documents.csv line 2 (DOC-0001), zones: `all` must be the only value"]


def test_stage_and_period_fit_the_phase():
    assert problems(doc(stage="stage_2; stage_4")) == []
    assert problems(doc(phase="ltm", period="ltm_p3", status="link_only")) == []
    assert problems(doc(phase="monitoring", status="link_only")) == []
    assert problems(doc(phase="ltm", stage="stage_4")) == [
        "documents.csv line 2 (DOC-0001), stage: only emergency response documents have a stage (phase is 'ltm')"
    ]
    assert problems(doc(phase="edwm", period="ltm_p3")) == [
        "documents.csv line 2 (DOC-0001), period: 'ltm_p3' doesn't fit phase 'edwm'"
    ]
    assert problems(doc(period="pem")) == [
        "documents.csv line 2 (DOC-0001), period: 'pem' doesn't fit phase 'emergency_response'"
    ]


def test_dates_times_and_fingerprints_are_well_formed():
    assert problems(doc(date_as_listed="2021-12", retrieved_utc="2026-10-31")) == []
    found = problems(doc(date_as_listed="2/9/2022", retrieved_utc="2026-10-31 07:25", sha256="ABC"))
    assert [p.split(", ")[1].split(":")[0] for p in found] == ["date_as_listed", "retrieved_utc", "sha256"]
    assert problems(doc(first_seen_utc="2026-11-19T00:00:00Z")) == [
        "documents.csv line 2 (DOC-0001), last_seen_utc: first_seen_utc and last_seen_utc are filled together"
    ]
    assert problems(doc(first_seen_utc="2026-11-19T00:00:00Z", last_seen_utc="2026-11-18T00:00:00Z")) == [
        "documents.csv line 2 (DOC-0001), last_seen_utc: is before first_seen_utc"
    ]


def test_links_between_rows_point_to_real_rows():
    second = doc(doc_id="DOC-0002", duplicate_of="DOC-0001", found_via="cited", found_on="DOC-0001")
    assert problems(doc(), second) == []
    assert problems(doc(duplicate_of="DOC-0009")) == [
        "documents.csv line 2 (DOC-0001), duplicate_of: 'DOC-0009' is not another row's doc_id"
    ]
    assert problems(doc(found_via="cited", found_on="DOC-0009")) == [
        "documents.csv line 2 (DOC-0001), found_on: for `cited`, it is the doc_id of the citing document"
    ]
    assert problems(doc(found_via="zone_page")) == [
        "documents.csv line 2 (DOC-0001), found_on: found_via and found_on are filled together"
    ]


def test_status_fits_the_other_columns():
    assert problems(doc(status="to_find", source_url="", retrieved_utc="", sha256="", local_path="")) == []
    assert problems(doc(status="to_find")) == [
        "documents.csv line 2 (DOC-0001), status: `to_find` means no source_url yet, but it has one"
    ]
    assert problems(doc(status="link_only", source_url="")) == [
        "documents.csv line 2 (DOC-0001), source_url: is blank, but status is 'link_only'"
    ]
    assert problems(doc(local_path="")) == [
        "documents.csv line 2 (DOC-0001), status: `done` needs retrieved_utc and local_path"
    ]


def test_only_limits_the_problems_to_some_rows():
    rows = [doc(doc_type=""), doc(doc_id="DOC-0002", doc_type="")]
    assert document_problems(rows, ZONE_IDS, only={"DOC-0002"}) == [
        "documents.csv line 3 (DOC-0002), doc_type: is blank"
    ]


# ---- document_links.csv rules

LEVEL_2 = doc(doc_id="DOC-0052", sdg="DA40925", package_or_validation_level="Level 2")
LEVEL_4 = doc(doc_id="DOC-0053", sdg="DA40925", package_or_validation_level="Level 4")
VALIDATION = doc(doc_id="DOC-0082", doc_type="data_validation_report", sdg="DA40925")
COPY = doc(doc_id="DOC-0051", sdg="DA40924", package_or_validation_level="Level 4", duplicate_of="DOC-0053")
DOCUMENTS = [LEVEL_2, LEVEL_4, VALIDATION, COPY]


def link(first: str, relation: str, second: str, notes: str = "2026-11-24: cover pages compared.") -> dict[str, str]:
    return {"doc_id": first, "related_doc_id": second, "relation": relation, "notes": notes}


def link_issues(*rows: dict[str, str]) -> list[str]:
    return link_problems(list(rows), DOCUMENTS)


def test_valid_links_have_no_problems():
    assert link_issues(link("DOC-0052", "same_results", "DOC-0053"), link("DOC-0082", "supports", "DOC-0053")) == []


def test_links_need_every_value_and_a_known_relation():
    assert link_issues(link("DOC-0082", "backs", "DOC-0053", notes="")) == [
        "document_links.csv line 2 (DOC-0082 backs DOC-0053), notes: is blank",
        "document_links.csv line 2 (DOC-0082 backs DOC-0053), relation: 'backs' is not in the vocabulary",
    ]


def test_links_point_to_real_rows_that_are_not_duplicates():
    assert link_issues(link("DOC-0082", "supports", "DOC-0999")) == [
        "document_links.csv line 2 (DOC-0082 supports DOC-0999), related_doc_id: DOC-0999 is not in documents.csv"
    ]
    assert link_issues(link("DOC-0082", "supports", "DOC-0051")) == [
        "document_links.csv line 2 (DOC-0082 supports DOC-0051), related_doc_id: DOC-0051 is a duplicate; link DOC-0053 instead"
    ]


def test_a_document_is_not_linked_to_itself_or_to_the_same_document_twice():
    assert link_issues(link("DOC-0053", "supersedes", "DOC-0053")) == [
        "document_links.csv line 2 (DOC-0053 supersedes DOC-0053), related_doc_id: a document can't be linked to itself"
    ]
    assert link_issues(link("DOC-0082", "supports", "DOC-0053"), link("DOC-0053", "summarizes", "DOC-0082")) == [
        "document_links.csv line 3 (DOC-0053 summarizes DOC-0082), related_doc_id: these two documents are already linked"
    ]


def test_same_results_links_two_levels_of_one_batch_lower_level_first():
    assert link_issues(link("DOC-0053", "same_results", "DOC-0052")) == [
        "document_links.csv line 2 (DOC-0053 same_results DOC-0052), doc_id: for `same_results`, doc_id is the lower package level"
    ]
    assert link_issues(link("DOC-0082", "same_results", "DOC-0053")) == [
        (
            "document_links.csv line 2 (DOC-0082 same_results DOC-0053), relation: "
            "`same_results` links two reports with a package level (Level 2, 3 or 4)"
        )
    ]
    other_batch = doc(doc_id="DOC-0049", sdg="DA40915", package_or_validation_level="Level 2")
    assert link_problems([link("DOC-0049", "same_results", "DOC-0053")], [*DOCUMENTS, other_batch]) == [
        (
            "document_links.csv line 2 (DOC-0049 same_results DOC-0053), relation: "
            "`same_results` links two reports of the same batch (same sdg)"
        )
    ]


# ---- zones.csv and communities.csv rules


def test_zone_rules():
    zone = ZONES[0]
    assert zone_problems([zone]) == []
    found = zone_problems([zone, zone | {"emergency_response": "y", "page_last_updated": "4/7/2026"}])
    assert found == [
        "zones.csv line 3 (A1), zone_id: used twice",
        "zones.csv line 3 (A1), emergency_response: must be yes or no",
        "zones.csv line 3 (A1), page_last_updated: '4/7/2026' is not YYYY-MM-DD",
    ]


def test_community_rules():
    ok = {"zone_id": "A1", "community": "Pearl City Peninsula", "homes": "635", "notes": ""}
    assert community_problems([ok], ZONES) == []
    found = community_problems([ok | {"homes": "0"}, ok | {"community": "Nowhere", "homes": ""}], ZONES)
    assert found == [
        "communities.csv line 2 (A1, Pearl City Peninsula), homes: '0' is not a whole number above 0",
        "communities.csv line 3 (A1, Nowhere), community: not in that zone's name in zones.csv",
        'communities.csv line 3 (A1, Nowhere), notes: a blank homes needs the note "No home count on the zone page."',
    ]
