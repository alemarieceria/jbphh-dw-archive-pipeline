"""Tests for the merge step. Each test works on a copy of the catalog in a temporary folder, with a
review file built offline from the saved zone pages (tests/fixtures/discover/) and listings made
from the catalog's own I1 library rows. No network is needed."""

import hashlib
import shutil
from pathlib import Path

import pytest

from jbphh_archive import catalog, discover, merge
from jbphh_archive.catalog import CATALOG_FILE, ZONES_FILE, read_rows
from jbphh_archive.discover import REPORT_COLUMNS, read_zone_page, write_report
from jbphh_archive.inventory import Result
from jbphh_archive.merge import MergeError, id_list, widened

FIXTURES = Path(__file__).parent / "fixtures"
ZONES = read_rows(ZONES_FILE)[1]
COLUMNS = read_rows(CATALOG_FILE)[0]
NOW = "2026-11-19T00:00:00Z"
MAP = "View Interactive Results Map"


@pytest.fixture
def catalog_file(tmp_path, monkeypatch) -> Path:
    """A copy of the real catalog, which merge reads and writes instead of the repo's."""
    copy = tmp_path / "documents.csv"
    shutil.copyfile(CATALOG_FILE, copy)
    monkeypatch.setattr(catalog, "CATALOG_FILE", copy)
    return copy


def i1_review(catalog_path: Path, decision: str = "accept") -> list[dict[str, str]]:
    """I1's review file as `archive discover` would write it, with `decision` on every source row."""
    rows = read_rows(catalog_path)[1]
    pages = [
        read_zone_page(z["zone_id"], (FIXTURES / "discover" / f"zone_{z['zone_id'].lower()}.html").read_text("utf-8"))
        for z in ZONES
    ]

    def listing(group: str) -> list[Result]:
        return [
            Result(r["library_id"], r["title_as_posted"], r["original_filename"], r["date_as_listed"], r["size_listed"])
            for r in rows
            if r["group"] == group
        ]

    listings = {"navy_listing": listing("navy_lab_collection"), "doh_listing": listing("doh_lab_collection")}
    zone = next(z for z in ZONES if z["zone_id"] == "I1")
    sha = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    report = discover.build_report(zone, ZONES, rows, pages, listings, NOW, sha)
    for r in report:
        if r["row_type"] == "source" and r["result"] == "read":
            r["decision"] = decision
    return report


def save(tmp_path: Path, report: list[dict[str, str]]) -> Path:
    path = tmp_path / "2026-11-19-discover-I1.csv"
    write_report(path, report)
    return path


def by_id(path: Path) -> dict[str, dict[str, str]]:
    return {r["doc_id"]: r for r in read_rows(path)[1]}


# ---- The whole step, on I1


def test_a_dry_run_shows_the_changes_and_writes_nothing(catalog_file, tmp_path, capsys):
    before = catalog_file.read_bytes()
    assert merge.main([str(save(tmp_path, i1_review(catalog_file)))]) == 0
    out = capsys.readouterr().out
    assert catalog_file.read_bytes() == before
    assert "Add 24 rows (169 -> 193):\n    DOC-0170 to DOC-0193" in out
    assert "Fill a blank stage on 129 rows:" in out
    assert "immediate (1): DOC-0001" in out
    assert "stage_2 (2): DOC-0002 to DOC-0003" in out
    assert f"zone_page, new: {MAP}" in out  # the flagged map is left for its own decision
    assert "Dry run: nothing written." in out


def test_apply_adds_new_rows_and_fills_existing_ones(catalog_file, tmp_path):
    assert merge.main([str(save(tmp_path, i1_review(catalog_file))), "--apply"]) == 0
    rows = by_id(catalog_file)
    assert len(rows) == 193
    added = [rows[f"DOC-{n:04d}"] for n in range(170, 194)]
    assert {(r["group"], r["status"], r["found_via"], r["first_seen_utc"]) for r in added} >= {
        ("zone_page_ltm", "link_only", "zone_page", NOW)
    }
    assert all(r["last_seen_utc"] == NOW and r["source_url"] for r in added)
    assert (rows["DOC-0001"]["stage"], rows["DOC-0001"]["found_via"]) == ("immediate", "zone_page")
    assert (rows["DOC-0010"]["stage"], rows["DOC-0010"]["found_via"]) == ("stage_4", "navy_listing")
    assert rows["DOC-0010"]["first_seen_utc"] == rows["DOC-0010"]["last_seen_utc"] == NOW
    assert rows["DOC-0135"]["stage"] == ""  # a cited document, on no source: unchanged


def test_the_written_catalog_keeps_its_columns_and_other_rows(catalog_file, tmp_path):
    original = read_rows(catalog_file)
    merge.main([str(save(tmp_path, i1_review(catalog_file))), "--apply"])
    columns, rows = read_rows(catalog_file)
    assert columns == original[0]
    kept = {"doc_id", "title_as_posted", "sha256", "local_path", "status", "notes"}
    assert [{k: r[k] for k in kept} for r in rows[:169]] == [{k: r[k] for k in kept} for r in original[1]]


def test_a_changed_catalog_stops_the_merge(catalog_file, tmp_path):
    path = save(tmp_path, i1_review(catalog_file))
    catalog_file.write_bytes(catalog_file.read_bytes() + b"\r\n")
    with pytest.raises(SystemExit, match="the catalog changed since this review file was made"):
        merge.main([str(path), "--apply"])


def test_the_same_review_file_cannot_be_applied_twice(catalog_file, tmp_path):
    path = save(tmp_path, i1_review(catalog_file))
    merge.main([str(path), "--apply"])
    after = catalog_file.read_bytes()
    with pytest.raises(SystemExit, match="the catalog changed"):
        merge.main([str(path), "--apply"])
    assert catalog_file.read_bytes() == after


def test_a_flagged_row_takes_its_own_decision_and_corrected_values(catalog_file, tmp_path):
    report = i1_review(catalog_file)
    (map_row,) = [r for r in report if r["link_text"] == MAP]
    map_row |= {"decision": "Accept ", "group": "web_page", "doc_type": "map", "phase": "monitoring"}
    map_row["status"] = "link_only"
    merge.main([str(save(tmp_path, report)), "--apply"])
    (added,) = [r for r in by_id(catalog_file).values() if r["title_as_posted"] == MAP]
    assert (added["doc_id"], added["group"], added["doc_type"], added["phase"], added["status"], added["zones"]) == (
        "DOC-0170",  # the first link on the zone page, so the first new row
        "web_page",
        "map",
        "monitoring",
        "link_only",
        "all",
    )


def test_an_accepted_new_row_needs_a_group_and_status(catalog_file, tmp_path):
    report = i1_review(catalog_file)
    (map_row,) = [r for r in report if r["link_text"] == MAP]
    map_row["decision"] = "accept"
    with pytest.raises(SystemExit, match=f"new row '{MAP}' has no group or status"):
        merge.main([str(save(tmp_path, report)), "--apply"])


def test_blank_and_reject_decisions_change_nothing(catalog_file, tmp_path, capsys):
    for decision in ("", "reject"):
        merge.main([str(save(tmp_path, i1_review(catalog_file, decision))), "--apply"])
        assert "No changes." in capsys.readouterr().out
    assert catalog_file.read_bytes() == CATALOG_FILE.read_bytes()


def test_an_unknown_decision_stops_the_merge(catalog_file, tmp_path):
    report = i1_review(catalog_file, decision="yes")
    # line 23 is the first source row: header, run row, 20 zone page rows, then the zone page source
    with pytest.raises(SystemExit, match="line 23: decision is 'yes'; write accept, reject or leave it blank"):
        merge.main([str(save(tmp_path, report))])


def test_a_file_that_is_not_a_review_file_stops_the_merge(catalog_file, tmp_path):
    other = tmp_path / "other.csv"
    other.write_text("doc_id,status\nDOC-0001,done\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="this is not a discover review file"):
        merge.main([str(other)])


# ---- Single rules, on small made-up rows


def catalog_row(**values: str) -> dict[str, str]:
    return dict.fromkeys(COLUMNS, "") | values


def review(*documents: dict[str, str]) -> list[dict[str, str]]:
    blank = dict.fromkeys(REPORT_COLUMNS, "")
    rows = [blank | {"row_type": "run", "last_seen_utc": NOW}, blank | {"row_type": "source", "decision": "accept"}]
    return rows + [blank | {"row_type": "document", "decision": "accept", "last_seen_utc": NOW} | d for d in documents]


def test_accepting_a_changed_row_keeps_the_old_value_in_notes():
    rows = [catalog_row(doc_id="DOC-0004", title_as_posted="Old", zones="I1", notes="18 pages.")]
    changed = {"result": "changed", "doc_id": "DOC-0004", "title_as_posted": "New", "zones": "I1", "flag": "x"}
    merged, changes = merge.merge(COLUMNS, rows, review(changed), "I1")
    assert merged[0]["title_as_posted"] == "New"
    assert merged[0]["notes"] == '18 pages. 2026-11-19: title_as_posted was "Old".'
    assert changes.updated == [("DOC-0004", "title_as_posted", "Old", "New")]


def test_a_changed_zones_value_adds_the_new_zones():
    assert widened("I1; D1", "A1") == "I1; D1; A1"
    assert widened("I1", "all") == "all"
    assert widened("all", "I1") == "all"
    rows = [catalog_row(doc_id="DOC-0003", zones="I1; D1")]
    changed = {"result": "changed", "doc_id": "DOC-0003", "zones": "I1; A1", "flag": "x"}
    merged, _ = merge.merge(COLUMNS, rows, review(changed), "I1")
    assert merged[0]["zones"] == "I1; D1; A1"
    assert merged[0]["notes"] == '2026-11-19: zones was "I1; D1".'


def test_accepting_a_missing_row_adds_a_dated_note_and_nothing_else():
    rows = [catalog_row(doc_id="DOC-0011", last_seen_utc="2026-11-17T22:16:26Z", status="done")]
    missing = {"result": "missing", "source": "navy_listing", "doc_id": "DOC-0011", "flag": "missing"}
    merged, _ = merge.merge(COLUMNS, rows, review(missing), "I1")
    assert merged == [rows[0] | {"notes": "2026-11-19: not on the I1 Navy listing (archive discover)."}]


def test_a_stage_or_discovery_value_the_catalog_has_is_kept():
    rows = [catalog_row(doc_id="DOC-0001", stage="stage_1", found_via="cited", found_on="DOC-0134")]
    matched = {"result": "matched", "doc_id": "DOC-0001", "stage": "immediate", "found_via": "zone_page"}
    merged, changes = merge.merge(COLUMNS, rows, review(matched | {"found_on": "u", "first_seen_utc": NOW}), "I1")
    assert (merged[0]["stage"], merged[0]["found_via"], merged[0]["found_on"]) == ("stage_1", "cited", "DOC-0134")
    assert merged[0]["first_seen_utc"] == merged[0]["last_seen_utc"] == NOW  # blank before, so filled
    assert changes.staged == []


def test_a_new_row_listed_twice_stops_the_merge():
    new = {"result": "new", "group": "ltm_lab_collection", "status": "link_only", "source_url": "u", "library_id": "p"}
    with pytest.raises(MergeError, match="already in the catalog or listed twice"):
        merge.merge(COLUMNS, [catalog_row(doc_id="DOC-0001")], review(new, new), "I1")


def test_doc_ids_continue_from_the_highest_one():
    new = {"result": "new", "group": "web_page", "status": "link_only", "source_url": "u"}
    rows = [catalog_row(doc_id="DOC-0001"), catalog_row(doc_id="DOC-0007")]
    merged, _ = merge.merge(COLUMNS, rows, review(new), "I1")
    assert merged[-1]["doc_id"] == "DOC-0008"


def test_id_list_shortens_runs_of_doc_ids():
    assert id_list(["DOC-0012", "DOC-0010", "DOC-0011", "DOC-0020"]) == "DOC-0010 to DOC-0012, DOC-0020"
