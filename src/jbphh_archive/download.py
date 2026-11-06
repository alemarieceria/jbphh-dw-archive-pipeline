"""Download registry files marked `to_download` into the archive, with provenance.

For each row: fetch source_url, save it under raw/<site>/ with its original
filename, and record the retrieval time (UTC), SHA-256 hash, and path in
registry/documents.csv, setting status to `done`. Rows already `done` are
skipped, so it is safe to stop and rerun.

Usage (from the project folder):
    uv run --env-file .env archive download --dry-run   # list what would download
    uv run --env-file .env archive download --limit 5   # try a few first
    uv run --env-file .env archive download             # everything left to download
    uv run --env-file .env archive download --doc-id DOC-0010 --doc-id DOC-0011
"""

import argparse
import hashlib
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import httpx

from jbphh_archive.catalog import REGISTRY_FILE, Row, read_rows, registered_paths, write_rows

# raw/ subfolder for each source website. Unlisted sites go to raw/other.
SITE_FOLDERS = {
    "jbphh-safewaters.org": "jbphh-safewaters",
    "health.hawaii.gov": "doh",
    "www.cpf.navy.mil": "cpf-navy",
    "www.navy.mil": "navy",
}
OTHER_FOLDER = "other"

USER_AGENT = "jbphh-dw-archive-pipeline/0.1 (University of Hawaii research archive)"
DELAY_SECONDS = 1.0  # pause between requests so source sites aren't overloaded
TIMEOUT = httpx.Timeout(30.0, read=120.0)  # Level 4 lab reports can exceed 60 MB


def site_folder(url: str) -> str:
    return SITE_FOLDERS.get(urlsplit(url).hostname or "", OTHER_FOLDER)


def file_name(row: Row, headers: httpx.Headers) -> str:
    """Original filename: the registry value, else the server's suggested name, else the URL's last segment."""
    name = row["original_filename"]
    if not name:
        match = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", headers.get("content-disposition", ""))
        name = unquote(match.group(1)) if match else unquote(PurePosixPath(urlsplit(row["source_url"]).path).name)
    name = PurePosixPath(name.strip()).name  # never allow a path to escape the folder
    if not name:
        raise ValueError("could not determine a filename")
    return name


def select_rows(rows: list[Row], doc_ids: list[str] | None, limit: int | None) -> list[Row]:
    todo = [r for r in rows if r["status"] == "to_download" and r["source_url"]]
    if doc_ids:
        todo = [r for r in todo if r["doc_id"] in doc_ids]
    return todo[:limit] if limit else todo


def download(client: httpx.Client, row: Row, archive_root: Path, taken: dict[str, str]) -> Row:
    """Fetch one file into the archive and return the registry fields to update."""
    url = row["source_url"]
    with client.stream("GET", url) as response:
        response.raise_for_status()
        name = file_name(row, response.headers)
        relative = str(PurePosixPath("raw", site_folder(url), name))
        if taken.get(relative, row["doc_id"]) != row["doc_id"]:
            raise ValueError(f"{relative} already belongs to {taken[relative]}")
        target = archive_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(name + ".part")  # renamed only once complete and checked
        digest = hashlib.sha256()
        try:
            with partial.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
                    digest.update(chunk)
            if name.lower().endswith(".pdf") and partial.read_bytes()[:4] != b"%PDF":
                raise ValueError("server did not return a PDF (likely an error page)")
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
    return {
        "original_filename": name,
        "local_path": relative,
        "sha256": digest.hexdigest(),
        "retrieved_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "done",
    }


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="archive download", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--archive-root", help="archive folder (default: ARCHIVE_ROOT environment variable)")
    parser.add_argument("--doc-id", action="append", help="download only this doc_id (repeatable)")
    parser.add_argument("--limit", type=int, help="download at most this many files")
    parser.add_argument("--dry-run", action="store_true", help="list what would be downloaded, then stop")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    archive_root = Path(args.archive_root or os.environ.get("ARCHIVE_ROOT", ""))
    registry = archive_root / REGISTRY_FILE
    if not registry.is_file():
        sys.exit(f"Registry not found at {registry}. Set ARCHIVE_ROOT in .env or pass --archive-root.")

    columns, rows = read_rows(registry)
    todo = select_rows(rows, args.doc_id, args.limit)
    print(f"{len(todo)} file(s) to download.")
    if args.dry_run:
        for row in todo:
            print(f"  {row['doc_id']}  {row['title_as_posted'][:70]}")
        return 0

    taken = registered_paths(rows)
    failures: list[tuple[str, str]] = []
    transport = httpx.HTTPTransport(retries=2)  # retries connection errors only
    with httpx.Client(
        transport=transport, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=True
    ) as client:
        for i, row in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {row['doc_id']}  {row['title_as_posted'][:60]}")
            try:
                updates = download(client, row, archive_root, taken)
            except (httpx.HTTPError, ValueError, OSError) as err:
                failures.append((row["doc_id"], str(err)))
                print(f"    FAILED: {err}")
            else:
                row.update(updates)
                taken[updates["local_path"]] = row["doc_id"]
                try:
                    write_rows(registry, columns, rows)  # save after every file so progress survives a stop
                except PermissionError:
                    sys.exit("Could not save documents.csv. Close it in Excel or other programs, then rerun.")
                print(f"    saved {updates['local_path']}")
            time.sleep(DELAY_SECONDS)

    print(f"\nDone: {len(todo) - len(failures)} downloaded, {len(failures)} failed.")
    for doc_id, error in failures:
        print(f"  {doc_id}: {error}")
    return 1 if failures else 0
