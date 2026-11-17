"""Propose catalog rows for a zone from its zone page and library listings on the Safe Waters site.

Reads all 20 zone pages (so each document lists every zone that posts it), then the chosen
zone's Navy, DOH and LTM listings. Writes a review file, reports/<UTC date>-discover-<zone>.csv,
and never changes the catalog: `archive merge` applies the decisions made in the review file.

A zone page (linked from catalog/zones.csv) is a frame around an inner page,
html.aspx?dsn=SYSTM&idHTML=<id>. The inner page has three sections, each under a heading:
Extended Drinking Water Monitoring, Drinking Water Long Term Monitoring and Emergency
Response (J1 has only the first). Inside a section, a bold line ("Quarter 1 - ...",
"Period 3 - ...") starts each part, and the links under it are its documents. A link
before the first heading, such as the interactive map, is outside the sections and flagged.

Each document in the review file is `matched` (in the catalog, as the site shows it),
`changed` (in the catalog, but the site shows something different), `new` or `missing`
(in the catalog, but not on a source that should show it). Each source has one summary
row whose `decision` covers its rows; a flagged row needs its own `decision`.

Usage (from the project folder):
    uv run archive discover --zone I1
"""

import argparse
import csv
import hashlib
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

from jbphh_archive import REPO_ROOT
from jbphh_archive.catalog import CATALOG_FILE, ZONES_FILE, Row, read_rows, values, zone_row
from jbphh_archive.inventory import ListingError, Result, fetch_listing, make_client

REPORTS_FOLDER = REPO_ROOT / "reports"
ZONE_PAGE = "https://jbphh-safewaters.org/public/framework/html.aspx?dsn=SYSTM&idHTML={}"
LIBRARY_FILE = "https://jbphh-safewaters.org/public/library/StreamResource.axd?DSN=PUB&Mode=FileImage_Inline&ID={}"

# Section heading on a zone page -> the phase it holds (post-EDWM parts sit inside the EDWM section).
SECTIONS = {
    "Extended Drinking Water Monitoring": "edwm",
    "Drinking Water Long Term Monitoring": "ltm",
    "Emergency Response": "emergency_response",
}

# Listing source -> (its column in zones.csv, the catalog group of its results, its name in messages).
LISTINGS = {
    "navy_listing": ("navy_listing_url", "navy_lab_collection", "Navy"),
    "doh_listing": ("doh_listing_url", "doh_lab_collection", "DOH"),
    "ltm_listing": ("ltm_listing_url", "ltm_lab_collection", "LTM"),
}
ZONE_PAGE_GROUPS = ("zone_page_er", "zone_page_ltm", "zone_page_edwm", "zone_page_pem", "source_water")

REPORT_COLUMNS = [
    # review
    "row_type",  # run, zone_page, source or document
    "source",  # zone_page, navy_listing, doh_listing or ltm_listing (the found_via values)
    "result",  # documents: matched, changed, new, missing; sources: read, unavailable, no_listing
    "flag",  # why the row needs its own decision; blank when the source row's decision covers it
    "decision",  # filled by the reviewer: accept or reject
    "count",  # source rows: how many documents the source shows
    # where it was found (for reading only)
    "section",  # the bold line on the zone page above the link
    "link_text",  # the link or listing result text, as the site shows it
    # proposed catalog values (documents.csv column names)
    "doc_id",
    "group",
    "title_as_posted",
    "source_url",
    "original_filename",
    "library_id",
    "doc_type",
    "sdg",
    "package_or_validation_level",
    "date_as_listed",
    "size_listed",
    "zones",
    "phase",
    "stage",
    "period",
    "status",
    "found_via",
    "found_on",
    "first_seen_utc",
    "last_seen_utc",
    # run information
    "page_last_updated",  # zone_page rows: the page's "Last Updated"
    "catalog_sha256",  # run row: the catalog's fingerprint when the review file was made
]
# Values the site shows. On an existing row, only these are reported, and a difference from the catalog is flagged.
SITE_FACTS = ("title_as_posted", "source_url", "original_filename", "library_id", "date_as_listed", "size_listed")
COMPARED = ("title_as_posted", "original_filename", "date_as_listed", "size_listed")

ATTEMPTS = 3  # tries per zone page before the run stops
RETRY_SECONDS = 5.0  # wait between tries
DELAY_SECONDS = 1.0  # pause between requests so the site isn't overloaded

# The page's headings, bold lines and links, in page order. The page's own HTML is regular
# (written by one template), so a pattern is enough; no HTML library is needed.
PARTS = re.compile(
    r'<div class="heading">(?P<heading>.*?)</div>|<strong>(?P<bold>.*?)</strong>|<a\b(?P<attrs>[^>]*)>(?P<text>.*?)</a>',
    re.DOTALL,
)


class ZonePageError(Exception):
    """The zone page could not be read (an error page, or the page wasn't what we expected)."""


@dataclass
class Link:
    section: str  # the phase key from SECTIONS, or "" for a link outside the sections
    part: str  # the bold line above the link, as the page writes it ("Quarter 1 - Samples Collected ...")
    text: str  # the link text, as the page writes it
    url: str


@dataclass
class ZonePage:
    zone_id: str
    last_updated: str  # the page's "Last Updated", as YYYY-MM-DD
    links: list[Link]


# ---- Reading zone pages


def plain(html: str) -> str:
    """Text without tags, entities decoded, spaces collapsed."""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def zone_page_url(zone: Row) -> str:
    """The inner page of the zone page in zones.csv (its frame holds no content)."""
    found = re.search(r"idhtml=(\d+)", zone["zone_page_url"], re.IGNORECASE)
    if not found:
        raise ZonePageError(f"zones.csv has no idhtml in {zone['zone_id']}'s zone_page_url")
    return ZONE_PAGE.format(found.group(1))


def read_zone_page(zone_id: str, page: str) -> ZonePage:
    """The page's "Last Updated" date and every link, with the section and bold line it sits under."""
    if "Application Error" in page:
        raise ZonePageError('the site showed "Application Error"')
    start = page.find('id="divHtmlContent"')
    if start == -1:
        raise ZonePageError("the page has no content area")
    content = page[start:]
    updated = re.search(r"<strong>Last Updated:</strong>\s*<br\s*/?>(.*?)<br", content, re.DOTALL)
    if not updated:
        raise ZonePageError('no "Last Updated" on the page')
    try:
        last_updated = datetime.strptime(plain(updated.group(1)), "%d %B %Y").date().isoformat()
    except ValueError as err:
        raise ZonePageError(f'"Last Updated" is not a date: {plain(updated.group(1))!r}') from err

    links = []
    section = part = ""
    for found in PARTS.finditer(content):
        if found["heading"] is not None:
            heading = plain(found["heading"])
            if heading not in SECTIONS:
                raise ZonePageError(f'unknown section heading "{heading}"')
            section, part = SECTIONS[heading], ""
        elif found["bold"] is not None:
            part = plain(found["bold"])
        else:
            href = re.search(r'href="([^"]*)"', found["attrs"])
            if href:  # an <a> without a link is plain text, such as "No samples were collected"
                links.append(Link(section, part, plain(found["text"]), unescape(href.group(1))))
    return ZonePage(zone_id, last_updated, links)


def link_key(url: str) -> str:
    """What makes two links the same document. Listing links are wrapped in a frame link whose
    other settings vary, so a listing is known by its subcategory; any other link by its URL."""
    if "searchresults.aspx" in url:
        subcategory = parse_qs(urlsplit(url).query).get("subcategory")
        if subcategory:
            return f"listing:{subcategory[0]}"
    return url


def posted_on(pages: list[ZonePage]) -> dict[str, list[str]]:
    """Each link (by link_key) -> the zones whose pages post it, in zones.csv order."""
    zones: dict[str, list[str]] = {}
    for page in pages:
        for link in page.links:
            posted = zones.setdefault(link_key(link.url), [])
            if page.zone_id not in posted:
                posted.append(page.zone_id)
    return zones


def zones_value(zone_ids: list[str], all_zone_ids: list[str]) -> str:
    """The catalog's `zones` cell: `all` when every zone in zones.csv posts it, else the IDs separated by '; '."""
    if set(zone_ids) == set(all_zone_ids):
        return "all"
    return "; ".join(z for z in all_zone_ids if z in zone_ids)


def fetch_zone_page(client: httpx.Client, zone: Row) -> ZonePage:
    """One zone page, retried: a one-off "Application Error" often loads on the next try."""
    for attempt in range(1, ATTEMPTS + 1):
        try:
            time.sleep(DELAY_SECONDS)
            response = client.get(zone_page_url(zone))
            response.raise_for_status()
            return read_zone_page(zone["zone_id"], response.text)
        except (ZonePageError, httpx.HTTPError) as err:
            if attempt == ATTEMPTS:
                raise ZonePageError(f"Zone {zone['zone_id']} page: {err} ({ATTEMPTS} tries)") from err
            print(f"    try {attempt} failed: {err}. Trying again in {RETRY_SECONDS:g} seconds.")
            time.sleep(RETRY_SECONDS)
    raise AssertionError("unreachable")


def fetch_zone_pages(client: httpx.Client, zones: list[Row]) -> list[ZonePage]:
    """Read every zone page in zones.csv, in order."""
    return [fetch_zone_page(client, zone) for zone in zones]


# ---- Proposing values (the plan's Vocabulary rule)


def stage_of(text: str) -> str:
    """Emergency response stage named in the text: "Immediate", "Stage 1" to "Stage 4"."""
    if "Immediate" in text:
        return "immediate"
    found = re.search(r"\bStage ([1-4])\b", text)
    return f"stage_{found.group(1)}" if found else ""


def period_of(text: str) -> str:
    """Monitoring period named in the text: "Period 1" to "Period 7", "Quarter 1" to "Quarter 4" (or "EDWM Q1"), "PEM"."""
    if found := re.search(r"\bPeriod ([1-7])\b", text):
        return f"ltm_p{found.group(1)}"
    if found := re.search(r"\b(?:Quarter |EDWM Q)([1-4])\b", text):
        return f"edwm_q{found.group(1)}"
    return "pem" if re.search(r"\bPEM\b", text) else ""


def agree(name: str, from_text: str, from_heading: str) -> tuple[str, str]:
    """The value the link text and its bold line agree on, or a flag when they disagree (never picked silently)."""
    if from_text and from_heading and from_text != from_heading:
        return "", f"{name}: link text says {from_text}, bold line says {from_heading}"
    return from_text or from_heading, ""


def is_file(url: str) -> bool:
    return bool(re.search(r"\.(pdf|xlsx?|csv|docx?|zip)$", urlsplit(url).path, re.IGNORECASE))


def date_in(text: str) -> str:
    """A date at the end of link text ("..., 24 January 2022"), as YYYY-MM-DD."""
    found = re.search(r",\s*(\d{1,2} [A-Z][a-z]+ \d{4})$", text)
    if not found:
        return ""
    try:
        return datetime.strptime(found.group(1), "%d %B %Y").date().isoformat()
    except ValueError:
        return ""


def link_values(link: Link) -> tuple[Row, list[str]]:
    """Proposed catalog values for a zone page link, from its section, bold line and text; and any flags."""
    flags = []
    pem = link.part.startswith("Post-EDWM")
    phase = "post_edwm" if pem else link.section
    stage = period = ""
    if phase == "emergency_response":
        stage, flag = agree("stage", stage_of(link.text), stage_of(link.part))
    elif phase:
        period, flag = agree("period", period_of(link.text), period_of(link.part))
    else:
        flag = "outside the page's sections"
    if flag:
        flags.append(flag)

    if not phase:
        group = ""
    elif "Waiawa Shaft" in link.text:
        group = "source_water"
    else:
        group = {"emergency_response": "zone_page_er", "ltm": "zone_page_ltm", "post_edwm": "zone_page_pem"}.get(
            phase, "zone_page_edwm"
        )

    listing = "searchresults.aspx" in link.url
    if listing:
        doc_type = "library_listing"
    elif link.text.startswith("Data Summary"):
        doc_type = "summary_report"
    elif link.text.startswith("Sampling Results"):
        doc_type = "results_crosstab"
    else:
        doc_type = ""

    if not phase:
        status = ""
    elif phase == "emergency_response":
        status = "to_download" if is_file(link.url) else "to_capture"
    else:
        status = "link_only"

    proposed = {
        "group": group,
        "title_as_posted": link.text,
        "source_url": link.url,
        "original_filename": urlsplit(link.url).path.rsplit("/", 1)[-1] if is_file(link.url) else "",
        "doc_type": doc_type,
        "date_as_listed": date_in(link.text),
        "phase": phase,
        "stage": stage,
        "period": period,
        "status": status,
    }
    return proposed, flags


def sdg_form(sdg: str) -> str:
    """The catalog's way of writing an SDG: a 9- or 10-digit one gets its hyphens back (810120772 -> 810-12077-2)."""
    if re.fullmatch(r"\d{9,10}", sdg):
        return f"{sdg[:3]}-{sdg[3:-1]}-{sdg[-1]}"
    return sdg


def title_values(title: str) -> tuple[str, str, str]:
    """doc_type, sdg and package_or_validation_level from a library title that follows a known pattern;
    blanks for a title that doesn't."""
    level = re.search(r"\bLevel (\d|S\dA?VEM)\b", title)
    level_value = (f"Level {level.group(1)}" if level.group(1).isdigit() else level.group(1)) if level else ""
    sdg = re.search(r"\bSDG ([A-Z0-9-]+)", title)
    if title.startswith(
        "Laboratory Report"
    ):  # "Laboratory Report, SDG DA22131, Level 4" or "Laboratory Report 810-12264-1, Level 4"
        named = re.match(r"Laboratory Report,? (?:SDG )?([A-Z0-9-]+)", title)
        return "lab_report", sdg_form(named.group(1)) if named else "", level_value
    if title.startswith("Data Validation Report"):  # "Data Validation Report, Level S2AVEM, SDG DA22131"
        return "data_validation_report", sdg_form(sdg.group(1)) if sdg else "", level_value
    if "Data Review Report" in title:  # "Zone I1 - Data Review Report - SDG 810120772"
        return "data_review_report", sdg_form(sdg.group(1)) if sdg else "", ""
    if title.startswith("Data Tables"):
        return "data_table", "", ""
    if found := re.match(r"DVC_Stage (\w+?)_JBPHH_(\d{6})", title):  # DOH: "DVC_Stage 2A_JBPHH_981053_final"
        return "data_validation_checklist", found.group(2), f"Stage {found.group(1)}"
    if found := re.match(r"DVR_(\d{6})_", title):  # DOH: "DVR_981587_...", Stage 2A like the catalog's DVR rows
        return "data_validation_checklist", found.group(1), "Stage 2A"
    if found := re.match(r"(\d{6})_\d{8}", title):  # DOH: "981053_20220127-EPA 525.2_..."
        return "lab_report", found.group(1), ""
    return "", "", ""


def result_values(result: Result) -> Row:
    """Catalog values a library listing shows for one result."""
    return {
        "title_as_posted": result.title,
        "source_url": LIBRARY_FILE.format(int(result.library_id.removeprefix("pub_"))),
        "original_filename": result.filename,
        "library_id": result.library_id,
        "date_as_listed": result.date,
        "size_listed": result.size,
    }


# ---- Comparing with the catalog


def covers(cell: str, zone_id: str) -> bool:
    return "all" in values(cell) or zone_id in values(cell)


def differences(proposed: Row, row: Row) -> list[str]:
    """What the site shows differently from an existing catalog row. A zone the site posts it on but the
    catalog's `zones` doesn't cover is a difference; a catalog zone the site doesn't post it on isn't
    (`zones` lists the zones a document covers, which can be more than the pages that post it)."""
    found = [
        f"{column} (catalog: {row[column]})"
        for column in COMPARED
        if proposed.get(column) and row[column] and proposed[column] != row[column]
    ]
    uncovered = [z for z in values(proposed["zones"]) if z != "all" and not covers(row["zones"], z)]
    if (proposed["zones"] == "all" and "all" not in values(row["zones"])) or uncovered:
        found.append(f"zones (catalog: {row['zones']})")
    return found


def document_row(source: str, found_on: str, now: str, proposed: Row, flags: list[str], row: Row | None) -> Row:
    """One document row of the review file. An existing row reports only the site's values and the
    discovery bookkeeping (filled once); a new row reports every proposed value."""
    out = dict.fromkeys(REPORT_COLUMNS, "") | {"row_type": "document", "source": source}
    if row is None:
        out |= proposed | {"result": "new", "found_via": source, "found_on": found_on, "first_seen_utc": now}
    else:
        changed = differences(proposed, row)
        out |= {column: proposed.get(column, "") for column in (*SITE_FACTS, "zones")}
        out |= {
            "result": "changed" if changed else "matched",
            "doc_id": row["doc_id"],
            "found_via": row["found_via"] or source,
            "found_on": row["found_on"] or found_on,
            "first_seen_utc": row["first_seen_utc"] or now,
        }
        flags = [f"changed: {'; '.join(changed)}"] if changed else []
    return out | {"flag": " | ".join(flags), "last_seen_utc": now}


def missing_row(source: str, row: Row) -> Row:
    """A catalog row that this source should show, but doesn't."""
    return dict.fromkeys(REPORT_COLUMNS, "") | {
        "row_type": "document",
        "source": source,
        "result": "missing",
        "flag": "missing: in the catalog, not on this source",
        "doc_id": row["doc_id"],
        "title_as_posted": row["title_as_posted"],
        "source_url": row["source_url"],
        "library_id": row["library_id"],
        "zones": row["zones"],
    }


def source_row(source: str, result: str, found_on: str, now: str, count: int | None = None, flag: str = "") -> Row:
    return dict.fromkeys(REPORT_COLUMNS, "") | {
        "row_type": "source",
        "source": source,
        "result": result,
        "count": "" if count is None else str(count),
        "flag": flag,
        "found_on": found_on,
        "last_seen_utc": now,
    }


def build_report(
    zone: Row,
    zones: list[Row],
    rows: list[Row],
    pages: list[ZonePage],
    listings: dict[str, list[Result] | str],
    now: str,
    catalog_sha256: str,
) -> list[Row]:
    """The whole review file. `listings` maps each listing source to its results, or to
    "unavailable" or "no_listing"."""
    zone_id = zone["zone_id"]
    all_zone_ids = [z["zone_id"] for z in zones]
    blank = dict.fromkeys(REPORT_COLUMNS, "")
    report = [blank | {"row_type": "run", "last_seen_utc": now, "catalog_sha256": catalog_sha256}]

    # One row per zone page, with its "Last Updated".
    for page, z in zip(pages, zones, strict=True):
        flag = (
            ""
            if page.last_updated == z["page_last_updated"]
            else f"changed: page_last_updated (zones.csv: {z['page_last_updated']})"
        )
        report.append(
            blank
            | {
                "row_type": "zone_page",
                "result": "read",
                "flag": flag,
                "zones": z["zone_id"],
                "found_on": z["zone_page_url"],
                "last_seen_utc": now,
                "page_last_updated": page.last_updated,
            }
        )

    by_key = {link_key(r["source_url"]): r for r in rows if r["source_url"]}
    by_library_id = {r["library_id"]: r for r in rows if r["library_id"]}
    zones_of = posted_on(pages)
    page = next(p for p in pages if p.zone_id == zone_id)

    # The zone page's links.
    found_on = zone["zone_page_url"]
    found: list[Row] = []
    seen: set[str] = set()
    for link in page.links:
        proposed, flags = link_values(link)
        proposed["zones"] = zones_value(zones_of[link_key(link.url)], all_zone_ids)
        row = by_key.get(link_key(link.url))
        found.append(document_row("zone_page", found_on, now, proposed, flags, row))
        found[-1] |= {"section": link.part, "link_text": link.text}
        if row:
            seen.add(row["doc_id"])
    for row in rows:
        if row["group"] in ZONE_PAGE_GROUPS and covers(row["zones"], zone_id) and row["doc_id"] not in seen:
            found.append(missing_row("zone_page", row))
    report += [source_row("zone_page", "read", found_on, now, count=len(page.links)), *found]

    # The zone's Navy, DOH and LTM listings. Each result takes its phase, stage and period
    # from the zone page's link to the listing.
    links_by_key = {link_key(link.url): link for link in page.links}
    for source, (column, group, name) in LISTINGS.items():
        url = zone[column]
        results = listings.get(source, "no_listing")
        if isinstance(results, str):
            report.append(source_row(source, results, url, now))
            continue
        listing_link = links_by_key.get(link_key(url))
        flag = "" if listing_link else "the zone page has no link to this listing"
        inherited, _ = link_values(listing_link) if listing_link else ({}, [])
        phase = inherited.get("phase") or ("ltm" if source == "ltm_listing" else "emergency_response")
        found = []
        for result in results:
            proposed = result_values(result) | {
                "group": group,
                "zones": zone_id,
                "phase": phase,
                "stage": inherited.get("stage", ""),
                "period": inherited.get("period", ""),
                "status": "to_download" if phase == "emergency_response" else "link_only",
            }
            doc_type, sdg, level = title_values(result.title)
            proposed |= {"doc_type": doc_type, "sdg": sdg, "package_or_validation_level": level}
            flags = [f"check: sdg {sdg} ends with a zone ID"] if re.search(r"-[A-J]\d$", sdg) else []
            row = by_library_id.get(result.library_id)
            found.append(document_row(source, url, now, proposed, flags, row))
            found[-1]["link_text"] = result.title
        listed = {result.library_id for result in results}
        for row in rows:
            if row["group"] == group and covers(row["zones"], zone_id) and row["library_id"] not in listed:
                found.append(missing_row(source, row))
        report += [source_row(source, "read", url, now, count=len(results), flag=flag), *found]
    return report


def write_report(path: Path, report: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="archive discover", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--zone", required=True, help="zone ID as in catalog/zones.csv, for example I1")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    zone = zone_row(args.zone)
    zones = read_rows(ZONES_FILE)[1]
    rows = read_rows(CATALOG_FILE)[1]
    catalog_sha256 = hashlib.sha256(CATALOG_FILE.read_bytes()).hexdigest()
    now = f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}"

    listings: dict[str, list[Result] | str] = {}
    with make_client() as client:
        print(f"Zone pages: reading all {len(zones)}...")
        try:
            pages = fetch_zone_pages(client, zones)
        except ZonePageError as err:
            sys.exit(f"Stopped: {err}. Every zone page is needed to list the zones that post each document.")
        for source, (column, _, name) in LISTINGS.items():
            if not zone[column]:
                print(f"{name} {args.zone} listing: none (no link in zones.csv).")
                listings[source] = "no_listing"
                continue
            print(f"{name} {args.zone} listing: reading...")
            try:
                listings[source] = fetch_listing(client, zone[column])
            except ListingError as err:
                print(f"    UNAVAILABLE: {err}")
                listings[source] = "unavailable"

    report = build_report(zone, zones, rows, pages, listings, now, catalog_sha256)
    path = REPORTS_FOLDER / f"{now[:10]}-discover-{args.zone}.csv"
    write_report(path, report)

    print()
    for source in ("zone_page", *LISTINGS):
        (summary,) = [r for r in report if r["row_type"] == "source" and r["source"] == source]
        documents = [r for r in report if r["row_type"] == "document" and r["source"] == source]
        counts = ", ".join(
            f"{sum(r['result'] == result for r in documents)} {result}"
            for result in ("matched", "changed", "new", "missing")
        )
        flagged = sum(bool(r["flag"]) for r in documents)
        shown = (
            f"{summary['count']} shown: {counts}; {flagged} flagged"
            if summary["result"] == "read"
            else summary["result"]
        )
        print(f"{source}: {shown}")
    checked = {r["doc_id"] for r in report if r["doc_id"]}
    unchecked = [r for r in rows if covers(r["zones"], args.zone) and r["doc_id"] not in checked]
    print(
        f"{len(unchecked)} catalog rows for {args.zone} are on no source discover reads (cited documents, other sites)."
    )
    print(f"\nReview file: {path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else path}")
    return 1 if any(r["result"] == "unavailable" for r in report) else 0
