"""Record fingerprints for collected files that have none, from their copies on the Shared Drive.

`archive download` records each file's SHA-256 fingerprint while it saves the file. Files saved
another way, such as the web pages captured manually, have a blank `sha256`. This step finds each
`done` row with a blank `sha256`, computes the fingerprint of every file in its `local_path`, and
shows what it would write; nothing is written until it runs with --apply.

- A row with several files gets one fingerprint per file, separated by '; ', in `local_path` order.
- Each filled row gets a dated note, because its fingerprint was recorded from the Drive's copy
  that day, not when the file was saved.
- Rows that already have a fingerprint are never changed; checking them is `archive verify`'s job.
- It stops without writing if any file is missing from the Drive.

Usage (from the project folder):
    uv run --env-file .env archive fingerprint            # see what would be filled
    uv run --env-file .env archive fingerprint --apply    # write the catalog
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from jbphh_archive import catalog
from jbphh_archive.catalog import Row, archive_folder, file_sha256, read_rows, values, write_rows
from jbphh_archive.validate import document_problems


def to_fingerprint(rows: list[Row]) -> list[Row]:
    """The `done` rows with a blank `sha256`."""
    return [row for row in rows if row["status"] == "done" and not row["sha256"]]


def note(today: date) -> str:
    return f"{today.isoformat()}: sha256 recorded by `archive fingerprint` from the file on the Drive, not when it was saved."


def fingerprints(row: Row, archive_root: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Each of the row's files with its fingerprint, and the files missing from the Drive."""
    found, missing = [], []
    for path in values(row["local_path"]):
        file = archive_root / path
        if file.is_file():
            found.append((path, file_sha256(file)))
        else:
            missing.append(path)
    return found, missing


def fill(row: Row, found: list[tuple[str, str]], today: date) -> None:
    row["sha256"] = "; ".join(digest for _, digest in found)
    row["notes"] = f"{row['notes']} {note(today)}" if row["notes"] else note(today)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="archive fingerprint",
        description="Record fingerprints (sha256) for `done` rows that have none, from their files on the Shared Drive.",
    )
    parser.add_argument("--apply", action="store_true", help="write the fingerprints to catalog/documents.csv")
    parser.add_argument("--archive-root", help="the Shared Drive folder (default: ARCHIVE_ROOT from .env)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, today: date | None = None) -> int:
    args = parse_args(argv)
    today = today or date.today()
    archive_root = archive_folder(args.archive_root)
    columns, rows = read_rows(catalog.CATALOG_FILE)
    todo = to_fingerprint(rows)
    if not todo:
        print("Every `done` row already has a fingerprint. Nothing to do.")
        return 0

    print(f"{len(todo)} `done` row(s) have no fingerprint:")
    all_missing: list[str] = []
    for row in todo:
        found, missing = fingerprints(row, archive_root)
        print(f"  {row['doc_id']}  {row['title_as_posted'][:60]}")
        for path, digest in found:
            print(f"      {digest[:16]}...  {path}")
        for path in missing:
            print(f"      MISSING             {path}")
        all_missing += [f"{row['doc_id']}: {path}" for path in missing]
        if not missing:
            fill(row, found, today)
    if all_missing:
        sys.exit("\nStopped, nothing written. These files are not on the Drive:\n" + "\n".join(all_missing))

    zone_ids = [zone["zone_id"] for zone in read_rows(catalog.ZONES_FILE)[1]]
    problems = document_problems(rows, zone_ids, only={row["doc_id"] for row in todo})
    if problems:
        sys.exit("\nStopped, nothing written. These rows would break the catalog's rules:\n" + "\n".join(problems))

    files = sum(len(values(row["local_path"])) for row in todo)
    print(f"\nEach row also gets this note: {note(today)}")
    if not args.apply:
        print(f"Dry run: nothing written. To write these {files} fingerprints, run again with --apply.")
        return 0
    try:
        write_rows(catalog.CATALOG_FILE, columns, rows)
    except PermissionError:
        catalog.CATALOG_FILE.with_name(catalog.CATALOG_FILE.name + ".tmp").unlink(missing_ok=True)
        sys.exit("Stopped: catalog/documents.csv is open in another program. Close it and run again.")
    print(f"Wrote {files} fingerprints to catalog/documents.csv ({len(todo)} rows). Commit it, then run:")
    print("    uv run --env-file .env archive publish")
    return 0
