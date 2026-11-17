"""Read and write the catalog, and find the archive on the Shared Drive.

The catalog is edited only in this repo, in catalog/documents.csv. `archive publish`
copies it to the archive's registry/documents.csv, where tools such as the Evidence
Tracer read it.
"""

import csv
import os
import sys
from pathlib import Path

from jbphh_archive import REPO_ROOT

CATALOG_FILE = REPO_ROOT / "catalog" / "documents.csv"
ZONES_FILE = REPO_ROOT / "catalog" / "zones.csv"
REGISTRY_FILE = Path("registry") / "documents.csv"  # the published copy, inside the archive

Row = dict[str, str]


def archive_folder(given: str | None) -> Path:
    """The archive's folder: --archive-root if given, else ARCHIVE_ROOT. Stops with a plain message if it's missing."""
    value = given or os.environ.get("ARCHIVE_ROOT", "")
    root = Path(value)
    if not value or not (root / "registry").is_dir():
        sys.exit(f"Archive not found at {value or '(not set)'}. Set ARCHIVE_ROOT in .env or pass --archive-root.")
    return root


def read_rows(path: Path) -> tuple[list[str], list[Row]]:
    """Return the column names and rows. utf-8-sig tolerates a BOM added by Excel."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, columns: list[str], rows: list[Row]) -> None:
    """Write to a temporary file, then swap it in, so a crash never leaves a half-written catalog."""
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def zone_row(zone_id: str) -> Row:
    """The zone's row in catalog/zones.csv. Stops with a plain message if the zone isn't there."""
    zones = read_rows(ZONES_FILE)[1]
    for zone in zones:
        if zone["zone_id"] == zone_id:
            return zone
    sys.exit(f"Zone {zone_id} is not in catalog/zones.csv. Zones: {', '.join(z['zone_id'] for z in zones)}.")


def values(cell: str) -> list[str]:
    """The values in a multi-value cell such as `zones`, separated by '; '."""
    return [value for value in cell.split("; ") if value]


def registered_paths(rows: list[Row]) -> dict[str, str]:
    """Map each local_path already in the catalog to its doc_id. A row can list several paths separated by '; '."""
    paths: dict[str, str] = {}
    for row in rows:
        for path in row["local_path"].split("; "):
            if path:
                paths[path] = row["doc_id"]
    return paths
