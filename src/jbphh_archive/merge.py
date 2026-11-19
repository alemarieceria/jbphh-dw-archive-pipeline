"""Apply the decisions in a discover review file to the catalog.

`archive discover` writes a review file in reports/. A reviewer writes `accept` or `reject` in
`decision` on each source row (covering its unflagged rows) and on each flagged row, and may
correct a proposed value. This step shows what those decisions would change in
catalog/documents.csv; nothing is written until it runs with --apply.

What `accept` does:
- `new`: adds the row with the next doc_id. doc_ids are never reused.
- `matched`: fills `found_via`, `found_on`, `first_seen_utc` and `stage` where the catalog's are
  blank, and updates `last_seen_utc`.
- `changed`: as `matched`, and takes the site's new value; the old value goes into `notes`, dated.
  For `zones`, the site's zones are added to the catalog's, because `zones` lists every zone a
  document covers.
- `missing`: adds a dated note. Rows are never deleted; a `last_seen_utc` that stops updating
  already shows the site removed the document.
`reject` and a blank decision change nothing.

It stops without writing if the catalog changed since the review file was made (the run row's
`catalog_sha256`), so decisions are never applied to a catalog the reviewer didn't see.

Usage (from the project folder):
    uv run archive merge reports/2026-11-19-discover-I1.csv           # see what would change
    uv run archive merge reports/2026-11-19-discover-I1.csv --apply   # write the catalog
"""

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from jbphh_archive import catalog
from jbphh_archive.catalog import Row, read_rows, values, write_rows
from jbphh_archive.discover import COMPARED, REPORT_COLUMNS

# The review file's proposed values, which a reviewer may correct before accepting a new row.
EDITABLE = (
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
)
FILLED_ONCE = ("found_via", "found_on", "first_seen_utc")
DECISIONS = ("accept", "reject", "")
SOURCE_NAMES = {"zone_page": "zone page", "navy_listing": "Navy listing", "doh_listing": "DOH listing"}
SOURCE_NAMES |= {"ltm_listing": "LTM listing", "edwm_listing": "EDWM listing"}


class MergeError(Exception):
    """The review file can't be applied as it is. Nothing is written."""


@dataclass
class Changes:
    added: list[Row] = field(default_factory=list)
    filled: list[str] = field(default_factory=list)  # doc_ids whose discovery columns were filled
    staged: list[tuple[str, str]] = field(default_factory=list)  # (doc_id, stage)
    seen: list[str] = field(default_factory=list)  # doc_ids whose last_seen_utc was updated
    updated: list[tuple[str, str, str, str]] = field(default_factory=list)  # (doc_id, column, old, new)
    noted_missing: list[tuple[str, str]] = field(default_factory=list)  # (doc_id, note)
    accepted: int = 0
    rejected: int = 0
    undecided: list[Row] = field(default_factory=list)

    def any(self) -> bool:
        return bool(self.added or self.filled or self.staged or self.seen or self.updated or self.noted_missing)


def check_review(review: list[Row], columns: list[str], catalog_bytes: bytes) -> Row:
    """The run row, once the file is a discover review file made from this exact catalog."""
    missing = [column for column in REPORT_COLUMNS if column not in columns]
    if missing:
        raise MergeError(f"this is not a discover review file (no {', '.join(missing)} column)")
    runs = [r for r in review if r["row_type"] == "run"]
    if len(runs) != 1:
        raise MergeError(f"a review file has one run row; this one has {len(runs)}")
    if runs[0]["catalog_sha256"] != hashlib.sha256(catalog_bytes).hexdigest():
        raise MergeError(
            "the catalog changed since this review file was made. Run `archive discover` again and review the new file."
        )
    return runs[0]


def decided(review: list[Row]) -> list[tuple[Row, str]]:
    """Each document row with the decision that covers it: its own if it's flagged or filled in,
    otherwise its source row's (the source row comes just before its documents)."""
    errors, out = [], []
    source_decision = ""
    for line, r in enumerate(review, start=2):  # line 1 is the header
        decision = r["decision"].strip().lower()
        if decision not in DECISIONS:
            errors.append(f"line {line}: decision is {r['decision']!r}; write accept, reject or leave it blank")
        if r["row_type"] == "source":
            source_decision = decision
        elif r["row_type"] == "document":
            out.append((r, decision if r["flag"] or decision else source_decision))
    if errors:
        raise MergeError("\n".join(errors))
    return out


def number(doc_id: str) -> int:
    return int(doc_id.removeprefix("DOC-"))


def widened(catalog_zones: str, site_zones: str) -> str:
    """The catalog's zones plus any zone the site posts the document on that they don't cover."""
    if "all" in values(catalog_zones):
        return catalog_zones
    if "all" in values(site_zones):
        return "all"
    kept = values(catalog_zones)
    return "; ".join(kept + [z for z in values(site_zones) if z not in kept])


def merge(columns: list[str], rows: list[Row], review: list[Row], zone: str) -> tuple[list[Row], Changes]:
    """The catalog rows after applying the review file's decisions, and what changed."""
    rows = [dict(row) for row in rows]
    by_id = {row["doc_id"]: row for row in rows}
    run = next(r for r in review if r["row_type"] == "run")
    day = run["last_seen_utc"][:10]
    next_number = max((number(row["doc_id"]) for row in rows), default=0) + 1
    known_urls = {row["source_url"] for row in rows if row["source_url"]}
    known_ids = {row["library_id"] for row in rows if row["library_id"]}
    changes = Changes()
    errors = []

    for r, decision in decided(review):
        if decision != "accept":
            if decision == "reject":
                changes.rejected += 1
            else:
                changes.undecided.append(r)
            continue
        changes.accepted += 1
        name = r["title_as_posted"] or r["link_text"] or r["source_url"]

        if r["result"] == "new":
            blank = [column for column in ("group", "status") if not r[column].strip()]
            if blank:
                errors.append(f"new row {name!r} has no {' or '.join(blank)}; fill it in or reject the row")
                continue
            if r["source_url"] in known_urls or (r["library_id"] and r["library_id"] in known_ids):
                errors.append(f"new row {name!r} is already in the catalog or listed twice in the review file")
                continue
            known_urls.add(r["source_url"])
            known_ids.add(r["library_id"])
            row = dict.fromkeys(columns, "") | {column: r[column].strip() for column in EDITABLE}
            row |= {column: r[column] for column in (*FILLED_ONCE, "last_seen_utc")}
            row["doc_id"] = f"DOC-{next_number:04d}"
            next_number += 1
            rows.append(row)
            changes.added.append(row)
            continue

        row = by_id.get(r["doc_id"])
        if row is None:
            errors.append(f"{r['doc_id'] or name!r} is not in the catalog")
            continue

        if r["result"] == "missing":
            where = f"the {zone} {SOURCE_NAMES.get(r['source'], r['source'])}".replace("  ", " ")
            note = f"{day}: not on {where} (archive discover)."
            row["notes"] = f"{row['notes']} {note}".strip()
            changes.noted_missing.append((row["doc_id"], note))
            continue

        if r["result"] == "changed":
            new_values = {column: r[column] for column in COMPARED if r[column] and r[column] != row[column]}
            if r["zones"] and widened(row["zones"], r["zones"]) != row["zones"]:
                new_values["zones"] = widened(row["zones"], r["zones"])
            for column, new in new_values.items():
                old = row[column]
                row[column] = new
                row["notes"] = f'{row["notes"]} {day}: {column} was "{old}".'.strip()
                changes.updated.append((row["doc_id"], column, old, new))

        if any(not row[column] and r[column] for column in FILLED_ONCE):
            changes.filled.append(row["doc_id"])
            for column in FILLED_ONCE:
                row[column] = row[column] or r[column]
        if not row["stage"] and r["stage"]:
            row["stage"] = r["stage"]
            changes.staged.append((row["doc_id"], r["stage"]))
        if r["last_seen_utc"] > row["last_seen_utc"]:
            row["last_seen_utc"] = r["last_seen_utc"]
            changes.seen.append(row["doc_id"])

    if errors:
        raise MergeError("\n".join(errors))
    return rows, changes


def id_list(doc_ids: list[str]) -> str:
    """doc_ids as short ranges: DOC-0010 to DOC-0118, DOC-0120."""
    numbers = sorted({number(doc_id) for doc_id in doc_ids})
    spans: list[list[int]] = []
    for n in numbers:
        if spans and n == spans[-1][1] + 1:
            spans[-1][1] = n
        else:
            spans.append([n, n])
    return ", ".join(f"DOC-{a:04d}" if a == b else f"DOC-{a:04d} to DOC-{b:04d}" for a, b in spans)


def summary(changes: Changes, before: int) -> list[str]:
    lines = [
        f"Decisions: {changes.accepted} accepted, {changes.rejected} rejected, {len(changes.undecided)} not decided.",
        "",
    ]
    if changes.added:
        lines.append(f"Add {len(changes.added)} rows ({before} -> {before + len(changes.added)}):")
        lines.append(f"    {id_list([row['doc_id'] for row in changes.added])}")
        groups: dict[str, int] = {}
        for row in changes.added:
            key = f"{row['group']}, {row['phase'] or 'no phase'}, {row['status']}"
            groups[key] = groups.get(key, 0) + 1
        lines += [f"    {count:>4}  {key}" for key, count in groups.items()]
    if changes.filled:
        lines.append(f"Fill found_via, found_on, first_seen_utc where blank on {len(changes.filled)} rows:")
        lines.append(f"    {id_list(changes.filled)}")
    if changes.staged:
        lines.append(f"Fill a blank stage on {len(changes.staged)} rows:")
        for stage in sorted({stage for _, stage in changes.staged}):
            ids = [doc_id for doc_id, s in changes.staged if s == stage]
            lines.append(f"    {stage} ({len(ids)}): {id_list(ids)}")
    if changes.seen:
        lines.append(f"Update last_seen_utc on {len(changes.seen)} rows.")
    for doc_id, column, old, new in changes.updated:
        lines.append(f'Change {doc_id} {column}: "{old}" -> "{new}" (old value kept in notes)')
    for doc_id, note in changes.noted_missing:
        lines.append(f"Note on {doc_id}: {note}")
    if not changes.any():
        lines.append("No changes.")
    if changes.undecided:
        lines += ["", "Not decided (blank decision, so left out):"]
        unflagged: dict[str, int] = {}
        for r in changes.undecided:
            if r["flag"]:
                name = r["title_as_posted"] or r["link_text"]
                lines.append(f"    {r['source']}, {r['result']}: {name}  [flag: {r['flag']}]")
            else:
                unflagged[r["source"]] = unflagged.get(r["source"], 0) + 1
        lines += [f"    {source}: {count} rows (its source row has no decision)" for source, count in unflagged.items()]
    return lines


def zone_of(path: Path) -> str:
    """The zone in a review file's name: 2026-11-19-discover-I1.csv -> I1."""
    found = re.search(r"-discover-(\w+)\.csv$", path.name)
    return found.group(1) if found else ""


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="archive merge", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "review_file", type=Path, help="the review file, for example reports/2026-11-19-discover-I1.csv"
    )
    parser.add_argument("--apply", action="store_true", help="write catalog/documents.csv (without it, only show)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.review_file.is_file():
        sys.exit(f"Review file not found: {args.review_file}")
    catalog_bytes = catalog.CATALOG_FILE.read_bytes()
    columns, rows = read_rows(catalog.CATALOG_FILE)
    review_columns, review = read_rows(args.review_file)
    try:
        run = check_review(review, review_columns, catalog_bytes)
        merged, changes = merge(columns, rows, review, zone_of(args.review_file))
    except MergeError as err:
        sys.exit(f"Stopped, nothing written:\n{err}")

    print(f"Review file: {args.review_file} (made {run['last_seen_utc']})")
    print("\n".join(summary(changes, len(rows))))
    print()
    if not args.apply:
        print("Dry run: nothing written. To write these changes, run again with --apply.")
        return 0
    if not changes.any():
        print("Nothing to write.")
        return 0
    try:
        write_rows(catalog.CATALOG_FILE, columns, merged)
    except PermissionError:
        catalog.CATALOG_FILE.with_name(catalog.CATALOG_FILE.name + ".tmp").unlink(missing_ok=True)
        sys.exit("Stopped: catalog/documents.csv is open in another program. Close it and run again.")
    print(f"Wrote catalog/documents.csv ({len(merged)} rows). Commit it, then run:")
    print("    uv run --env-file .env archive publish")
    return 0
