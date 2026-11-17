"""Copy the catalog to the Shared Drive, where tools such as the Evidence Tracer read it.

The catalog is edited only in this repo, in catalog/documents.csv. This replaces the
archive's registry/documents.csv with an exact copy, in one step, after listing the
rows that were added or changed. It refuses if rows would disappear, because rows
are never deleted.

Usage (from the project folder):
    uv run --env-file .env archive publish --dry-run   # show what would change
    uv run --env-file .env archive publish
"""

import argparse
import os
import shutil
import sys

from jbphh_archive.catalog import CATALOG_FILE, REGISTRY_FILE, Row, archive_folder, read_rows


def differences(published: list[Row], catalog: list[Row]) -> tuple[list[str], list[str], list[str]]:
    """The doc_ids added, changed and missing in the catalog, compared with the published copy."""
    old = {row["doc_id"]: row for row in published}
    new = {row["doc_id"]: row for row in catalog}
    added = [doc_id for doc_id in new if doc_id not in old]
    changed = [doc_id for doc_id in new if doc_id in old and new[doc_id] != old[doc_id]]
    missing = [doc_id for doc_id in old if doc_id not in new]
    return added, changed, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="archive publish", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--archive-root", help="archive folder (default: ARCHIVE_ROOT environment variable)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, then stop")
    args = parser.parse_args(argv)

    if not CATALOG_FILE.is_file():
        sys.exit(f"Catalog not found at {CATALOG_FILE}.")
    target = archive_folder(args.archive_root) / REGISTRY_FILE
    if target.is_file() and target.read_bytes() == CATALOG_FILE.read_bytes():
        print("The Drive's copy is already up to date.")
        return 0

    old_columns, old_rows = read_rows(target) if target.is_file() else ([], [])
    columns, rows = read_rows(CATALOG_FILE)
    added, changed, missing = differences(old_rows, rows)
    if missing:
        sys.exit(
            f"Not published: the catalog is missing rows the Drive's copy has ({', '.join(missing)}). "
            "Rows are never deleted, so check catalog/documents.csv."
        )
    print(f"{len(rows)} rows: {len(added)} added, {len(changed)} changed.")
    for label, doc_ids in (("added", added), ("changed", changed)):
        if doc_ids:
            print(f"  {label}: {', '.join(doc_ids)}")
    if old_columns and columns != old_columns:
        print(f"  columns were {', '.join(old_columns)}; now {', '.join(columns)}")
    if not added and not changed and columns == old_columns:
        print("  only the file's formatting differs (for example line endings)")
    if args.dry_run:
        return 0

    temp = target.with_name(target.name + ".tmp")
    try:
        shutil.copyfile(CATALOG_FILE, temp)
        os.replace(temp, target)  # swap in one step, so readers never see a half-written file
    except PermissionError:
        temp.unlink(missing_ok=True)
        sys.exit("Could not replace the Drive's documents.csv. Close it in Excel or other programs, then rerun.")
    print(f"Published to {target}")
    return 0
