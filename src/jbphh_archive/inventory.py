"""Compare a zone's library listings on the Safe Waters site with the catalog.

For each of the zone's Navy and DOH library listings (links in catalog/zones.csv), read
every result, sorted by "Sort by System Filename" and showing 100 items, page by page.
The site's default sort skips and repeats files between pages, so the sort matters.
Then match each result's library ID to catalog/documents.csv and write a dated report
to reports/<date>-inventory-<zone>.csv. The catalog itself is not changed.

A listing that shows "Application Error" is retried before it counts as unavailable,
because a one-off server error looks the same as a zone with no listing.

Usage (from the project folder):
    uv run archive inventory --zone I1
"""

import argparse
import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path

import httpx

from jbphh_archive import REPO_ROOT
from jbphh_archive.catalog import CATALOG_FILE, Row, read_rows, values, zone_row
from jbphh_archive.download import USER_AGENT

REPORTS_FOLDER = REPO_ROOT / "reports"

# Listing -> (its column in zones.csv, the catalog group its documents belong to, its name in messages).
LISTINGS = {
    "navy": ("navy_listing_url", "navy_lab_collection", "Navy"),
    "doh": ("doh_listing_url", "doh_lab_collection", "DOH"),
}

# The two menus on a listing page: (control name, value to pick, label the site shows).
SORT = ("ddlSortField", "SystemFilename", "Sort by System Filename")
SHOW = ("ddlShowItems", "100", "Show 100 Items")
NEXT_PAGE = "ctl00$cphMain$btnDisplayNextPage"

ATTEMPTS = 3  # tries per listing before it counts as unavailable
RETRY_SECONDS = 5.0  # wait between tries (Navy H2 loaded on a retry a few seconds after an error)
DELAY_SECONDS = 1.0  # pause between requests so the site isn't overloaded
TIMEOUT = httpx.Timeout(30.0, read=120.0)

REPORT_COLUMNS = ["listing", "library_id", "title", "filename", "doc_id", "catalog_status", "result"]
# result values: matched, not_in_catalog (listed, no catalog row), not_on_listing (catalog row, not listed),
# no_listing (zones.csv has no link), listing_unavailable (still an error after every try)
COMPARE_RESULTS = ("matched", "not_in_catalog", "not_on_listing")


class ListingError(Exception):
    """The listing page could not be read (an error page, or the page wasn't what we expected)."""


@dataclass
class Result:
    library_id: str  # as the catalog writes it: pub_002925
    title: str
    filename: str
    date: str = ""  # the date the listing shows after the title: 2022-04-26
    size: str = ""  # the size the listing shows after the file name: 108 KB


def form_fields(page: str) -> dict[str, str]:
    """The page's form fields, to send back with a postback (how the site's menus and page buttons work)."""
    fields = {}
    for tag in re.findall(r"<input[^>]+>", page):
        name = re.search(r'name="([^"]+)"', tag)
        if name and not re.search(r'type="(submit|button|image|checkbox)"', tag):
            value = re.search(r'value="([^"]*)"', tag)
            fields[unescape(name.group(1))] = unescape(value.group(1)) if value else ""
    return fields


def menu_choice(page: str, menu: tuple[str, str, str]) -> dict[str, str]:
    """The form to send to pick one item from a listing menu, as the browser does."""
    control, value, label = menu
    options = re.search(rf'"_uniqueId":"ctl00\$cphMain\${control}".*?"itemData":(\[.*?\])', page)
    offered = [item["value"] for item in json.loads(options.group(1))] if options else []
    if value not in offered:
        raise ListingError(f'the page no longer offers "{label}"')
    fields = form_fields(page)
    fields[f"ctl00$cphMain${control}"] = label
    fields[f"ctl00_cphMain_{control}_ClientState"] = json.dumps(
        {"logEntries": [], "value": value, "text": label, "enabled": True, "checkedIndices": []}
    )
    fields["__EVENTTARGET"] = f"ctl00$cphMain${control}"
    fields["__EVENTARGUMENT"] = json.dumps({"Command": "Select", "Index": offered.index(value)})
    return fields


def read_page(page: str) -> tuple[list[Result], int, int, int]:
    """The page's results, and its "first - last of total Results" numbers."""
    if "Application Error" in page:
        raise ListingError('the site showed "Application Error"')
    counts = re.search(r"(\d+)\s*-\s*(\d+)\s+of\s+(\d+)\s+Results", re.sub(r"<[^>]+>|\s+", " ", page))
    if not counts:
        raise ListingError("no results count on the page")
    results = []
    # Each result starts with its link, <a id='aFile2925' ...>. (The page also lists these IDs
    # in a menu setting with double quotes, which grows with every postback, so it is ignored.)
    for chunk in page.split("<a id='aFile")[1:]:
        number = re.match(r"(\d+)'", chunk)
        title = re.search(r">(.*?)</a>", chunk, re.DOTALL)
        filename = re.search(r"<div class='\w+_GIF'>\s*([^\s<]+)\s*(?:\(([^)]+)\))?", chunk)
        date = re.search(r"</a>[^<]*?(\d{4}-\d{2}-\d{2})\s*<br", chunk)
        if not (number and title):
            raise ListingError("a result on the page has an unexpected layout")
        results.append(
            Result(
                library_id=f"pub_{int(number.group(1)):06d}",
                title=unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip(),
                filename=filename.group(1) if filename else "",
                date=date.group(1) if date else "",
                size=(filename.group(2) or "") if filename else "",
            )
        )
    first, last, total = (int(n) for n in counts.groups())
    return results, first, last, total


def read_listing(client: httpx.Client, url: str) -> list[Result]:
    """Every result on one listing, sorted by System Filename, 100 per page."""

    def fetch(form: dict[str, str] | None = None) -> str:
        time.sleep(DELAY_SECONDS)
        response = client.post(url, data=form) if form else client.get(url)
        response.raise_for_status()
        return response.text

    page = fetch()
    read_page(page)  # stop early on an error page
    page = fetch(menu_choice(page, SORT))
    page = fetch(menu_choice(page, SHOW))
    for _, _, label in (SORT, SHOW):
        if not re.search(rf'value="{re.escape(label)}"', page):
            raise ListingError(f'the site did not apply "{label}"')
    results: list[Result] = []
    while True:
        more, first, last, total = read_page(page)
        if first != len(results) + 1 or last != len(results) + len(more):
            raise ListingError(f'"{first} - {last} of {total} Results" does not follow the pages before it')
        results += more
        if last >= total:
            break
        page = fetch(form_fields(page) | {"__EVENTTARGET": NEXT_PAGE, "__EVENTARGUMENT": ""})
    if len({r.library_id for r in results}) != len(results):
        raise ListingError("the same result appeared on two pages")
    return results


def fetch_listing(client: httpx.Client, url: str) -> list[Result]:
    """read_listing, retried: a one-off "Application Error" often loads on the next try."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return read_listing(client, url)
        except (ListingError, httpx.HTTPError) as err:
            if attempt == ATTEMPTS:
                raise ListingError(f"{err} ({ATTEMPTS} tries)") from err
            print(f"    try {attempt} failed: {err}. Trying again in {RETRY_SECONDS:g} seconds.")
            time.sleep(RETRY_SECONDS)
    raise AssertionError("unreachable")


def compare(listing: str, zone_id: str, results: list[Result], rows: list[Row]) -> list[Row]:
    """One report row per listed result, plus one per catalog row this listing should show but doesn't."""
    by_library_id = {row["library_id"]: row for row in rows if row["library_id"]}
    report = []
    for result in results:
        row = by_library_id.get(result.library_id)
        report.append(
            {
                "listing": listing,
                "library_id": result.library_id,
                "title": result.title,
                "filename": result.filename,
                "doc_id": row["doc_id"] if row else "",
                "catalog_status": row["status"] if row else "",
                "result": "matched" if row else "not_in_catalog",
            }
        )
    listed = {result.library_id for result in results}
    group = LISTINGS[listing][1]
    for row in rows:
        if row["group"] == group and zone_id in values(row["zones"]) and row["library_id"] not in listed:
            report.append(
                {
                    "listing": listing,
                    "library_id": row["library_id"],
                    "title": row["title_as_posted"],
                    "filename": row["original_filename"],
                    "doc_id": row["doc_id"],
                    "catalog_status": row["status"],
                    "result": "not_on_listing",
                }
            )
    return report


def listing_only_row(listing: str, result: str) -> Row:
    return {column: "" for column in REPORT_COLUMNS} | {"listing": listing, "result": result}


def write_report(path: Path, report: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report)


def make_client() -> httpx.Client:
    transport = httpx.HTTPTransport(retries=2)  # retries connection errors only
    return httpx.Client(transport=transport, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="archive inventory", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--zone", required=True, help="zone ID as in catalog/zones.csv, for example I1")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    zone = zone_row(args.zone)
    rows = read_rows(CATALOG_FILE)[1]
    report: list[Row] = []
    with make_client() as client:
        for listing, (column, _, name) in LISTINGS.items():
            url = zone[column]
            if not url:
                print(f"{name} {args.zone} listing: none (no link in zones.csv).")
                report.append(listing_only_row(listing, "no_listing"))
                continue
            print(f"{name} {args.zone} listing: reading...")
            try:
                results = fetch_listing(client, url)
            except ListingError as err:
                print(f"    UNAVAILABLE: {err}")
                report.append(listing_only_row(listing, "listing_unavailable"))
                continue
            found = compare(listing, args.zone, results, rows)
            count = {result: sum(r["result"] == result for r in found) for result in COMPARE_RESULTS}
            print(
                f"    {len(results)} results: {count['matched']} matched, {count['not_in_catalog']} not in the catalog;"
                f" {count['not_on_listing']} catalog rows not on the listing."
            )
            report += found

    path = REPORTS_FOLDER / f"{datetime.now(UTC):%Y-%m-%d}-inventory-{args.zone}.csv"
    write_report(path, report)
    print(f"\nReport: {path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else path}")
    problems = [r for r in report if r["result"] not in ("matched", "no_listing")]
    if problems:
        print(f"{len(problems)} row(s) need a look: see the report's `result` column.")
    return 1 if problems else 0
