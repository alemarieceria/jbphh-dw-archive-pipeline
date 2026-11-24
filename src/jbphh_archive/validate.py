"""Check the catalog files against the rules in catalog/README.md.

Reads catalog/documents.csv, catalog/document_links.csv, catalog/zones.csv and
catalog/communities.csv and lists every value that breaks a rule: a value outside its
vocabulary, a badly formed ID, date, time, fingerprint or list, or a row whose values
contradict each other (such as a `done` row with no `local_path`). It changes nothing. GitHub runs it on every push, so a catalog that breaks a
rule fails the checks.

The allowed values below must match catalog/README.md; a test compares them.

Usage (from the project folder):
    uv run archive validate
"""

import argparse
import re
from datetime import datetime

from jbphh_archive import catalog
from jbphh_archive.catalog import Row, read_rows

DOCUMENT_COLUMNS = [
    "doc_id",
    "group",
    "title_as_posted",
    "source_url",
    "original_filename",
    "library_id",
    "producer",
    "publisher",
    "doc_type",
    "date_as_listed",
    "zones",
    "phase",
    "stage",
    "period",
    "size_listed",
    "sdg",
    "package_or_validation_level",
    "revision",
    "duplicate_of",
    "priority",
    "in_team_folder",
    "status",
    "retrieved_utc",
    "sha256",
    "local_path",
    "notes",
    "found_via",
    "found_on",
    "first_seen_utc",
    "last_seen_utc",
]
ZONE_COLUMNS = [
    "zone_id",
    "name",
    "emergency_response",
    "zone_page_url",
    "page_last_updated",
    "navy_listing_url",
    "doh_listing_url",
    "ltm_listing_url",
    "notes",
]
COMMUNITY_COLUMNS = ["zone_id", "community", "homes", "notes"]
LINK_COLUMNS = ["doc_id", "related_doc_id", "relation", "notes"]
RELATIONS = ("same_results", "supersedes", "corrects", "supports", "summarizes", "part_of")

LTM_PERIODS = tuple(f"ltm_p{n}" for n in range(1, 8))
EDWM_PERIODS = tuple(f"edwm_q{n}" for n in range(1, 5))
VOCABULARY = {
    "group": (
        "zone_page_er",
        "navy_lab_collection",
        "doh_lab_collection",
        "governing",
        "doh_decision",
        "public_communication",
        "web_page",
        "zone_page_ltm",
        "zone_page_edwm",
        "ltm_lab_collection",
        "source_water",
    ),
    "doc_type": (
        "lab_report",
        "lab_report_bundle",
        "data_validation_report",
        "data_validation_checklist",
        "data_review_report",
        "data_table",
        "summary_report",
        "results_crosstab",
        "removal_action_report",
        "plan",
        "plan_addendum",
        "plan_and_results",
        "sop",
        "guidance",
        "technical_memo",
        "regulatory_directive",
        "regulatory_advisory",
        "regulatory_memo",
        "press_release",
        "fact_sheet",
        "map",
        "graphic",
        "transcript",
        "library_listing",
        "web_page",
    ),
    "phase": ("emergency_response", "ltm", "edwm", "post_edwm", "monitoring"),
    "stage": ("immediate", "stage_1", "stage_2", "stage_3", "stage_4"),
    "period": (*LTM_PERIODS, *EDWM_PERIODS, "pem"),
    "priority": ("core", "supporting", "context"),
    "in_team_folder": ("yes", "no"),
    "status": ("to_find", "to_download", "to_capture", "link_only", "done", "unavailable", "excluded"),
    "found_via": ("zone_page", "navy_listing", "doh_listing", "ltm_listing", "edwm_listing", "cited", "other_site"),
}
LISTS = ("zones", "stage", "local_path", "sha256")  # multi-value cells, separated by "; "
REQUIRED = ("doc_id", "group", "title_as_posted", "doc_type", "zones", "phase", "status")
# The periods each phase allows. An emergency response document has no period.
PERIODS_OF_PHASE = {
    "emergency_response": (),
    "ltm": LTM_PERIODS,
    "edwm": EDWM_PERIODS,
    "post_edwm": ("pem",),
    "monitoring": VOCABULARY["period"],
}


def list_values(cell: str) -> tuple[list[str], str]:
    """The values in a multi-value cell, and what's wrong with how it's written ("" if nothing)."""
    if not cell:
        return [], ""
    if cell != cell.strip():
        return [], "starts or ends with a space"
    if re.search(r";(?! )|; {2,}|\s;", cell):
        return [], "separate values with '; ' (semicolon, one space)"
    parts = cell.split("; ")
    if "" in parts:
        return [], "has an empty value between separators"
    if len(set(parts)) < len(parts):
        return [], "lists a value twice"
    return parts, ""


def is_date(value: str, month_only: bool = False) -> bool:
    formats = ("%Y-%m-%d", "%Y-%m") if month_only else ("%Y-%m-%d",)
    return any(_parses(value, f) for f in formats) and len(value) in (7, 10)


def is_utc(value: str, date_only: bool = False) -> bool:
    """A UTC time, 2026-10-31T07:25:23Z (or, where only the day was recorded, 2026-10-31)."""
    return _parses(value, "%Y-%m-%dT%H:%M:%SZ") or (date_only and is_date(value))


def _parses(value: str, form: str) -> bool:
    try:
        datetime.strptime(value, form)
    except ValueError:
        return False
    return True


def is_url(value: str) -> bool:
    return re.fullmatch(r"https?://\S+", value) is not None


def document_problems(rows: list[Row], zone_ids: list[str], only: set[str] | None = None) -> list[str]:
    """Every rule documents.csv rows break, one line each, naming the row and column.
    With `only`, just the problems of those doc_ids (checked against all rows)."""
    problems: list[str] = []
    ids = [row["doc_id"] for row in rows]
    known = set(ids)
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        if only is not None and row["doc_id"] not in only:
            seen.add(row["doc_id"])
            continue
        where = f"documents.csv line {line} ({row['doc_id'] or 'no doc_id'})"

        def bad(column: str, message: str, where: str = where) -> None:
            problems.append(f"{where}, {column}: {message}")

        for column in REQUIRED:
            if not row[column]:
                bad(column, "is blank")
        doc_id = row["doc_id"]
        if doc_id and not re.fullmatch(r"DOC-\d{4}", doc_id):
            bad("doc_id", f"{doc_id!r} is not like DOC-0001")
        if doc_id in seen:
            bad("doc_id", f"{doc_id} is used twice")
        seen.add(doc_id)

        for column, allowed in VOCABULARY.items():
            if column in LISTS:
                continue
            if row[column] and row[column] not in allowed:
                bad(column, f"{row[column]!r} is not in the vocabulary")
        for column in LISTS:
            values, problem = list_values(row[column])
            if problem:
                bad(column, problem)
            if column == "stage":
                bad_values = [v for v in values if v not in VOCABULARY["stage"]]
                if bad_values:
                    bad(column, f"{', '.join(bad_values)} not in the vocabulary")
            if column == "zones":
                if "all" in values and len(values) > 1:
                    bad(column, "`all` must be the only value")
                unknown = [v for v in values if v != "all" and v not in zone_ids]
                if unknown:
                    bad(column, f"{', '.join(unknown)} not in zones.csv")

        phase, period = row["phase"], row["period"]
        if row["stage"] and phase != "emergency_response":
            bad("stage", f"only emergency response documents have a stage (phase is {phase!r})")
        if period and phase in PERIODS_OF_PHASE and period not in PERIODS_OF_PHASE[phase]:
            bad("period", f"{period!r} doesn't fit phase {phase!r}")

        if row["date_as_listed"] and not is_date(row["date_as_listed"], month_only=True):
            bad("date_as_listed", f"{row['date_as_listed']!r} is not YYYY-MM-DD or YYYY-MM")
        if row["retrieved_utc"] and not is_utc(row["retrieved_utc"], date_only=True):
            bad("retrieved_utc", f"{row['retrieved_utc']!r} is not like 2026-10-31T07:25:23Z")
        for column in ("first_seen_utc", "last_seen_utc"):
            if row[column] and not is_utc(row[column]):
                bad(column, f"{row[column]!r} is not like 2026-10-31T07:25:23Z")
        if bool(row["first_seen_utc"]) != bool(row["last_seen_utc"]):
            bad("last_seen_utc", "first_seen_utc and last_seen_utc are filled together")
        elif row["first_seen_utc"] > row["last_seen_utc"]:
            bad("last_seen_utc", "is before first_seen_utc")

        # One fingerprint per file in local_path, in the same order, separated by "; ".
        fingerprints, paths = list_values(row["sha256"])[0], list_values(row["local_path"])[0]
        if any(not re.fullmatch(r"[0-9a-f]{64}", f) for f in fingerprints):
            bad("sha256", "is not 64 lowercase hex characters")
        elif fingerprints and paths and len(fingerprints) != len(paths):
            bad("sha256", f"has {len(fingerprints)} fingerprint(s) for {len(paths)} file(s) in local_path")
        if row["library_id"] and not re.fullmatch(r"pub_\d{6}", row["library_id"]):
            bad("library_id", f"{row['library_id']!r} is not like pub_002925")
        if row["source_url"] and not is_url(row["source_url"]):
            bad("source_url", "is not a web address")
        if row["duplicate_of"] and (row["duplicate_of"] not in known or row["duplicate_of"] == doc_id):
            bad("duplicate_of", f"{row['duplicate_of']!r} is not another row's doc_id")

        if bool(row["found_via"]) != bool(row["found_on"]):
            bad("found_on", "found_via and found_on are filled together")
        elif row["found_via"] == "cited" and row["found_on"] not in known:
            bad("found_on", "for `cited`, it is the doc_id of the citing document")
        elif row["found_via"] and row["found_via"] != "cited" and not is_url(row["found_on"]):
            bad("found_on", "is not a web address")

        status = row["status"]
        if status == "to_find" and row["source_url"]:
            bad("status", "`to_find` means no source_url yet, but it has one")
        if status in ("to_download", "to_capture", "link_only") and not row["source_url"]:
            bad("source_url", f"is blank, but status is {status!r}")
        if status == "done" and not (row["retrieved_utc"] and row["local_path"]):
            bad("status", "`done` needs retrieved_utc and local_path")
    return problems


def zone_problems(rows: list[Row]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for line, row in enumerate(rows, start=2):
        where = f"zones.csv line {line} ({row['zone_id'] or 'no zone_id'})"
        if not re.fullmatch(r"[A-Z]\d", row["zone_id"]):
            problems.append(f"{where}, zone_id: {row['zone_id']!r} is not like I1")
        if row["zone_id"] in seen:
            problems.append(f"{where}, zone_id: used twice")
        seen.add(row["zone_id"])
        if not row["name"]:
            problems.append(f"{where}, name: is blank")
        if row["emergency_response"] not in ("yes", "no"):
            problems.append(f"{where}, emergency_response: must be yes or no")
        if not is_url(row["zone_page_url"]):
            problems.append(f"{where}, zone_page_url: is not a web address")
        if not is_date(row["page_last_updated"]):
            problems.append(f"{where}, page_last_updated: {row['page_last_updated']!r} is not YYYY-MM-DD")
        for column in ("navy_listing_url", "doh_listing_url", "ltm_listing_url"):
            if row[column] and not is_url(row[column]):
                problems.append(f"{where}, {column}: is not a web address")
    return problems


def community_problems(rows: list[Row], zones: list[Row]) -> list[str]:
    problems: list[str] = []
    names = {zone["zone_id"]: zone["name"] for zone in zones}
    seen: set[tuple[str, str]] = set()
    for line, row in enumerate(rows, start=2):
        where = f"communities.csv line {line} ({row['zone_id']}, {row['community']})"
        if row["zone_id"] not in names:
            problems.append(f"{where}, zone_id: not in zones.csv")
        elif row["community"] not in names[row["zone_id"]]:
            problems.append(f"{where}, community: not in that zone's name in zones.csv")
        if (row["zone_id"], row["community"]) in seen:
            problems.append(f"{where}: listed twice")
        seen.add((row["zone_id"], row["community"]))
        if row["homes"] and not re.fullmatch(r"[1-9]\d*", row["homes"]):
            problems.append(f"{where}, homes: {row['homes']!r} is not a whole number above 0")
        if not row["homes"] and row["notes"] != "No home count on the zone page.":
            problems.append(f'{where}, notes: a blank homes needs the note "No home count on the zone page."')
    return problems


def package_level(row: Row) -> int | None:
    """A lab report's package level as a number (`Level 2` is 2), or None if it has none."""
    match = re.fullmatch(r"Level (\d)", row["package_or_validation_level"])
    return int(match[1]) if match else None


def link_problems(rows: list[Row], documents: list[Row]) -> list[str]:
    """Every rule document_links.csv rows break. Each row reads "doc_id relation related_doc_id"."""
    problems: list[str] = []
    by_id = {row["doc_id"]: row for row in documents}
    seen: set[frozenset[str]] = set()
    for line, row in enumerate(rows, start=2):
        first, relation, second = row["doc_id"], row["relation"], row["related_doc_id"]
        where = f"document_links.csv line {line} ({first} {relation} {second})"

        def bad(column: str, message: str, where: str = where) -> None:
            problems.append(f"{where}, {column}: {message}")

        for column in LINK_COLUMNS:
            if not row[column]:
                bad(column, "is blank")
        if relation and relation not in RELATIONS:
            bad("relation", f"{relation!r} is not in the vocabulary")
        for column in ("doc_id", "related_doc_id"):
            if not row[column]:
                continue
            if row[column] not in by_id:
                bad(column, f"{row[column]} is not in documents.csv")
            elif by_id[row[column]]["duplicate_of"]:
                bad(column, f"{row[column]} is a duplicate; link {by_id[row[column]]['duplicate_of']} instead")
        if first and first == second:
            bad("related_doc_id", "a document can't be linked to itself")
        pair = frozenset((first, second))
        if first and second and pair in seen:
            bad("related_doc_id", "these two documents are already linked")
        seen.add(pair)

        if relation == "same_results" and first in by_id and second in by_id:
            one, other = by_id[first], by_id[second]
            if not one["sdg"] or one["sdg"] != other["sdg"]:
                bad("relation", "`same_results` links two reports of the same batch (same sdg)")
            low, high = package_level(one), package_level(other)
            if low is None or high is None:
                bad("relation", "`same_results` links two reports with a package level (Level 2, 3 or 4)")
            elif low >= high:
                bad("doc_id", "for `same_results`, doc_id is the lower package level")
    return problems


def all_problems() -> tuple[list[str], dict[str, int]]:
    """Every problem in the four catalog files, and each file's row count."""
    files = {
        "documents.csv": (catalog.CATALOG_FILE, DOCUMENT_COLUMNS),
        "document_links.csv": (catalog.LINKS_FILE, LINK_COLUMNS),
        "zones.csv": (catalog.ZONES_FILE, ZONE_COLUMNS),
        "communities.csv": (catalog.COMMUNITIES_FILE, COMMUNITY_COLUMNS),
    }
    problems, tables, counts = [], {}, {}
    for name, (path, expected) in files.items():
        columns, rows = read_rows(path)
        counts[name] = len(rows)
        if columns != expected:
            problems.append(f"{name}: columns are {', '.join(columns)}; catalog/README.md lists {', '.join(expected)}")
        else:
            tables[name] = rows
    zones = tables.get("zones.csv", [])
    if "zones.csv" in tables:
        problems += zone_problems(zones)
    if "documents.csv" in tables:
        problems += document_problems(tables["documents.csv"], [zone["zone_id"] for zone in zones])
    if "communities.csv" in tables:
        problems += community_problems(tables["communities.csv"], zones)
    if "document_links.csv" in tables and "documents.csv" in tables:
        problems += link_problems(tables["document_links.csv"], tables["documents.csv"])
    return problems, counts


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="archive validate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args(argv)
    problems, counts = all_problems()
    checked = ", ".join(f"{name} {count} rows" for name, count in counts.items())
    if problems:
        print("\n".join(problems))
        print(f"\n{len(problems)} problem{'s' if len(problems) > 1 else ''} ({checked}).")
        return 1
    print(f"No problems ({checked}).")
    return 0
