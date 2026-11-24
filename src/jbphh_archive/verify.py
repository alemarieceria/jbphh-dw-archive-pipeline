"""Prove a zone's archive is complete and unchanged, in one run.

A zone's rows are the catalog rows whose `zones` lists the zone or `all`. Five checks:

1. Files: every file of every `done` row is on the Shared Drive and matches its fingerprint
   (`sha256`, one per file in `local_path`).
2. Drive: every file in the Drive's raw/ and web-captures/ belongs to a catalog row (README
   files aside), so nothing was saved without being cataloged.
3. Listings: the zone's Navy and DOH listings on the Safe Waters site still match the catalog,
   result by result (the same check as `archive inventory`).
4. Catalog rules: everything `archive validate` checks, including the links between documents.
5. Counts by status, and the known gaps: rows still `to_find` or `unavailable`, and lab batches
   (SDGs) whose only report is a copy of another batch's report.

It never changes the catalog. It writes a dated report, reports/<UTC date>-verify-<zone>.csv,
and ends with an error code if a check fails. Known gaps are listed but don't fail it.

Usage (from the project folder):
    uv run --env-file .env archive verify --zone I1
"""

import argparse
import csv
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from jbphh_archive import REPO_ROOT, catalog, inventory, validate
from jbphh_archive.catalog import Row, archive_folder, file_sha256, read_rows, registered_paths, values, zone_row
from jbphh_archive.inventory import LISTINGS, ListingError, fetch_listing, make_client

DRIVE_FOLDERS = ("raw", "web-captures")  # the folders that hold collected files
NOT_CATALOGED = ("README.txt", "README.md")  # notes about a folder, not archived files
REPORT_COLUMNS = ["check", "doc_id", "item", "result", "count", "detail"]
# Results that fail the run. The others: ok, no_listing, count, known_gap.
FAILURES = (
    "missing",
    "changed",
    "no_fingerprint",
    "not_in_catalog",
    "not_on_listing",
    "listing_unavailable",
    "problem",
)
GAP_STATUSES = ("to_find", "unavailable")


def report_row(check: str, **values: str | int) -> Row:
    return dict.fromkeys(REPORT_COLUMNS, "") | {"check": check} | {k: str(v) for k, v in values.items()}


def zone_rows(rows: list[Row], zone_id: str) -> list[Row]:
    """The rows whose `zones` lists the zone or `all`."""
    return [row for row in rows if zone_id in values(row["zones"]) or "all" in values(row["zones"])]


def check_files(rows: list[Row], archive_root: Path) -> list[Row]:
    """One report row per file of each `done` row: ok, missing, changed or no_fingerprint."""
    report = []
    done = [row for row in rows if row["status"] == "done"]
    total = sum(len(values(row["local_path"])) for row in done)
    checked = 0
    for row in done:
        paths, fingerprints = values(row["local_path"]), values(row["sha256"])
        fingerprints += [""] * (len(paths) - len(fingerprints))  # validate reports a count that differs
        for path, recorded in zip(paths, fingerprints, strict=False):
            file = archive_root / path
            if not file.is_file():
                result, detail = "missing", "not on the Drive"
            elif not recorded:
                result, detail = "no_fingerprint", "sha256 is blank; run `archive fingerprint`"
            elif file_sha256(file) != recorded:
                result, detail = "changed", "the file differs from its recorded fingerprint"
            else:
                result, detail = "ok", ""
            report.append(report_row("files", doc_id=row["doc_id"], item=path, result=result, detail=detail))
            checked += 1
            if checked % 25 == 0:
                print(f"    {checked} of {total} files read...")
    return report


def check_drive(all_rows: list[Row], archive_root: Path) -> list[Row]:
    """One report row per file in the Drive's collection folders that no catalog row lists."""
    cataloged = registered_paths(all_rows)
    report = []
    for folder in DRIVE_FOLDERS:
        for file in sorted((archive_root / folder).rglob("*")):
            path = file.relative_to(archive_root).as_posix()
            if file.is_file() and file.name not in NOT_CATALOGED and path not in cataloged:
                report.append(report_row("drive", item=path, result="not_in_catalog", detail="no catalog row lists it"))
    return report


def check_listings(zone: Row, all_rows: list[Row]) -> list[Row]:
    """One summary row per listing, then one row per result or catalog row that doesn't match."""
    report = []
    with make_client() as client:
        for listing, (column, _, name) in LISTINGS.items():
            if not zone[column]:
                report.append(report_row("listings", item=listing, result="no_listing", detail="zones.csv has no link"))
                continue
            print(f"    {name} listing: reading...")
            try:
                results = fetch_listing(client, zone[column])
            except ListingError as err:
                report.append(report_row("listings", item=listing, result="listing_unavailable", detail=str(err)))
                continue
            found = inventory.compare(listing, zone["zone_id"], results, all_rows)
            matched = sum(r["result"] == "matched" for r in found)
            others = [r for r in found if r["result"] != "matched"]
            summary = f"{len(results)} results on the listing, {matched} matched to catalog rows"
            result = "ok" if not others else "problem"
            report.append(report_row("listings", item=listing, result=result, count=len(results), detail=summary))
            for r in others:
                detail = f"{r['title']} ({r['filename']})".strip()
                report.append(
                    report_row("listings", doc_id=r["doc_id"], item=r["library_id"], result=r["result"], detail=detail)
                )
    return report


def check_catalog() -> list[Row]:
    """`archive validate`'s problems, one row each, or one `ok` row."""
    problems, counts = validate.all_problems()
    if not problems:
        checked = ", ".join(f"{name} {count} rows" for name, count in counts.items())
        return [report_row("catalog", result="ok", detail=f"No problems ({checked})")]
    return [report_row("catalog", result="problem", detail=problem) for problem in problems]


def counts_and_gaps(rows: list[Row]) -> list[Row]:
    """One row per status with its count, then one row per known gap."""
    report = [
        report_row("counts", item=status, result="count", count=count)
        for status, count in sorted(Counter(row["status"] for row in rows).items())
    ]
    for row in rows:
        if row["status"] in GAP_STATUSES:
            detail = f"{row['status']}: {row['title_as_posted']}"
            report.append(
                report_row("gaps", doc_id=row["doc_id"], item=row["doc_type"], result="known_gap", detail=detail)
            )
    batches: dict[str, list[Row]] = {}
    for row in rows:
        if row["doc_type"] == "lab_report" and row["sdg"]:
            batches.setdefault(row["sdg"], []).append(row)
    for sdg, reports in sorted(batches.items()):
        if all(r["duplicate_of"] for r in reports):
            copies = ", ".join(f"{r['doc_id']} is a copy of {r['duplicate_of']}" for r in reports)
            detail = f"SDG {sdg} has no report of its own: {copies}"
            doc_ids = "; ".join(r["doc_id"] for r in reports)
            report.append(report_row("gaps", doc_id=doc_ids, item=f"SDG {sdg}", result="known_gap", detail=detail))
    return report


def write_report(path: Path, report: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report)


def summary(check: str, report: list[Row]) -> str:
    """The check's line for the screen: what was checked and PASS or FAIL."""
    rows = [r for r in report if r["check"] == check]
    failed = [r for r in rows if r["result"] in FAILURES]
    if check == "files":
        ok = sum(r["result"] == "ok" for r in rows)
        line = f"1. Files: {ok} of {len(rows)} files are on the Drive and match their fingerprints"
    elif check == "drive":
        line = f"2. Drive: {len(rows)} file(s) in raw/ and web-captures/ that no catalog row lists"
    elif check == "listings":
        parts = [f"{LISTINGS[r['item']][2]}: {r['detail'] or r['result']}" for r in rows if r["item"] in LISTINGS]
        line = "3. Listings: " + "; ".join(parts)
    else:
        line = f"4. Catalog rules: {rows[0]['detail'] if not failed else f'{len(failed)} problem(s)'}"
    return f"{line}. {'FAIL' if failed else 'PASS'}"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="archive verify", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--zone", required=True, help="zone ID as in catalog/zones.csv, for example I1")
    parser.add_argument("--archive-root", help="the Shared Drive folder (default: ARCHIVE_ROOT from .env)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    zone = zone_row(args.zone)
    archive_root = archive_folder(args.archive_root)
    all_rows = read_rows(catalog.CATALOG_FILE)[1]
    rows = zone_rows(all_rows, args.zone)
    print(f"Verifying Zone {args.zone}: {len(rows)} catalog rows list {args.zone} or all zones.")

    print("Reading the files on the Drive...")
    report = check_files(rows, archive_root)
    report += check_drive(all_rows, archive_root)
    print("Reading the Navy and DOH listings...")
    report += check_listings(zone, all_rows)
    report += check_catalog()
    report += counts_and_gaps(rows)

    path = inventory.REPORTS_FOLDER / f"{datetime.now(UTC):%Y-%m-%d}-verify-{args.zone}.csv"
    write_report(path, report)

    print()
    for check in ("files", "drive", "listings", "catalog"):
        print(summary(check, report))
    counts = [f"{r['item']} {r['count']}" for r in report if r["check"] == "counts"]
    print(f"5. Rows by status: {', '.join(counts)}.")
    gaps = [r for r in report if r["check"] == "gaps"]
    print(f"   Known gaps (don't fail the check): {len(gaps)}")
    for gap in gaps:
        print(f"     {gap['doc_id']}  {gap['detail'][:90]}")
    print(f"\nReport: {path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else path}")
    failed = [r for r in report if r["result"] in FAILURES]
    if failed:
        print(f"{len(failed)} row(s) failed: see the report's `result` column.")
        return 1
    print("Every check passed. The known gaps above are still open.")
    return 0
