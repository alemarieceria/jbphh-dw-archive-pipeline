"""Read and write the archive registry (registry/documents.csv)."""

import csv
import os
from pathlib import Path

REGISTRY_FILE = Path("registry") / "documents.csv"

Row = dict[str, str]


def read_rows(path: Path) -> tuple[list[str], list[Row]]:
    """Return the column names and rows. utf-8-sig tolerates a BOM added by Excel."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_rows(path: Path, columns: list[str], rows: list[Row]) -> None:
    """Write to a temporary file, then swap it in, so a crash never leaves a half-written registry."""
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def registered_paths(rows: list[Row]) -> dict[str, str]:
    """Map each local_path already in the registry to its doc_id. A row can list several paths separated by '; '."""
    paths: dict[str, str] = {}
    for row in rows:
        for path in row["local_path"].split("; "):
            if path:
                paths[path] = row["doc_id"]
    return paths
