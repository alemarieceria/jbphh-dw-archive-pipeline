"""Copy the catalog to the Shared Drive, where data processing and tools such as the Evidence Tracer read it.

The catalog is edited only in this repo, in catalog/. This replaces each catalog file in the
archive's registry/ (documents.csv, document_links.csv, zones.csv, communities.csv) with an exact
copy, each in one step, after listing what changed. Files that are already the same are left alone.

It refuses, and copies nothing, if `archive validate` finds a problem, or if rows of documents.csv
would disappear, because rows are never deleted.

Usage (from the project folder):
    uv run --env-file .env archive publish --dry-run   # show what would change
    uv run --env-file .env archive publish
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

from jbphh_archive import catalog, validate
from jbphh_archive.catalog import REGISTRY_FOLDER, Row, archive_folder, read_rows


def catalog_files() -> list[Path]:
    """The catalog files publish copies, in the order it reports them."""
    return [catalog.CATALOG_FILE, catalog.LINKS_FILE, catalog.ZONES_FILE, catalog.COMMUNITIES_FILE]


def catalog_problems() -> list[str]:
    """What `archive validate` finds wrong with the catalog files."""
    return validate.all_problems()[0]


def differences(published: list[Row], rows: list[Row]) -> tuple[list[str], list[str], list[str]]:
    """The doc_ids added, changed and missing in the catalog, compared with the published copy."""
    old = {row["doc_id"]: row for row in published}
    new = {row["doc_id"]: row for row in rows}
    added = [doc_id for doc_id in new if doc_id not in old]
    changed = [doc_id for doc_id in new if doc_id in old and new[doc_id] != old[doc_id]]
    missing = [doc_id for doc_id in old if doc_id not in new]
    return added, changed, missing


def documents_changes(source: Path, target: Path) -> list[str]:
    """What publishing documents.csv would change, line by line. Stops if rows would disappear."""
    old_columns, old_rows = read_rows(target) if target.is_file() else ([], [])
    columns, rows = read_rows(source)
    added, changed, missing = differences(old_rows, rows)
    if missing:
        sys.exit(
            f"Not published: the catalog is missing rows the Drive's copy has ({', '.join(missing)}). "
            "Rows are never deleted, so check catalog/documents.csv."
        )
    lines = [f"documents.csv: {len(rows)} rows: {len(added)} added, {len(changed)} changed."]
    lines += [f"  {label}: {', '.join(ids)}" for label, ids in (("added", added), ("changed", changed)) if ids]
    if old_columns and columns != old_columns:
        lines.append(f"  columns were {', '.join(old_columns)}; now {', '.join(columns)}")
    if not added and not changed and columns == old_columns:
        lines.append("  only the file's formatting differs (for example line endings)")
    return lines


def file_changes(source: Path, target: Path) -> list[str]:
    """What publishing one of the other catalog files would change."""
    rows = len(read_rows(source)[1])
    if not target.is_file():
        return [f"{source.name}: new on the Drive ({rows} rows)."]
    return [f"{source.name}: updated ({rows} rows; the Drive's copy has {len(read_rows(target)[1])})."]


def copy(source: Path, target: Path) -> None:
    """Replace the Drive's copy in one step, so readers never see a half-written file."""
    temp = target.with_name(target.name + ".tmp")
    try:
        shutil.copyfile(source, temp)
        os.replace(temp, target)
    except PermissionError:
        temp.unlink(missing_ok=True)
        sys.exit(f"Could not replace the Drive's {target.name}. Close it in Excel or other programs, then rerun.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="archive publish", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--archive-root", help="archive folder (default: ARCHIVE_ROOT environment variable)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, then stop")
    args = parser.parse_args(argv)

    missing = [path.name for path in catalog_files() if not path.is_file()]
    if missing:
        sys.exit(f"Not published: catalog files not found: {', '.join(missing)}.")
    problems = catalog_problems()
    if problems:
        sys.exit("Not published: `archive validate` finds these problems. Fix them first:\n" + "\n".join(problems))

    registry = archive_folder(args.archive_root) / REGISTRY_FOLDER
    to_copy: list[tuple[Path, Path]] = []
    for source in catalog_files():
        target = registry / source.name
        if target.is_file() and target.read_bytes() == source.read_bytes():
            print(f"{source.name}: already up to date.")
            continue
        changes = documents_changes if source == catalog.CATALOG_FILE else file_changes
        print("\n".join(changes(source, target)))
        to_copy.append((source, target))

    if not to_copy:
        print("The Drive's copy is already up to date.")
        return 0
    if args.dry_run:
        print("Dry run: nothing copied.")
        return 0
    for source, target in to_copy:
        copy(source, target)
    print(f"Published {len(to_copy)} file(s) to {registry}")
    return 0
