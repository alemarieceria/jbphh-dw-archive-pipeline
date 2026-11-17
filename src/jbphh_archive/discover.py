"""Find the documents a zone's pages on the Safe Waters site link to.

A zone page (linked from catalog/zones.csv) is a frame around an inner page,
html.aspx?dsn=SYSTM&idHTML=<id>. The inner page has three sections, each under a heading:
Extended Drinking Water Monitoring, Drinking Water Long Term Monitoring and Emergency
Response (J1 has only the first). Inside a section, a bold line ("Quarter 1 - ...",
"Period 3 - ...") starts each part, and the links under it are its documents. A link
before the first heading, such as the interactive map, is outside the sections.

Every zone page is read, so each document lists every zone that posts it.
"""

import re
import time
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from urllib.parse import parse_qs, urlsplit

import httpx

from jbphh_archive.catalog import Row

ZONE_PAGE = "https://jbphh-safewaters.org/public/framework/html.aspx?dsn=SYSTM&idHTML={}"

# Section heading on a zone page -> the phase it holds (post-EDWM parts sit inside the EDWM section).
SECTIONS = {
    "Extended Drinking Water Monitoring": "edwm",
    "Drinking Water Long Term Monitoring": "ltm",
    "Emergency Response": "emergency_response",
}

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


def fetch_zone_pages(client: httpx.Client, zones: list[Row]) -> list[ZonePage]:
    """Read every zone page in zones.csv, in order."""
    pages = []
    for zone in zones:
        time.sleep(DELAY_SECONDS)
        response = client.get(zone_page_url(zone))
        response.raise_for_status()
        try:
            pages.append(read_zone_page(zone["zone_id"], response.text))
        except ZonePageError as err:
            raise ZonePageError(f"Zone {zone['zone_id']} page: {err}") from err
    return pages
