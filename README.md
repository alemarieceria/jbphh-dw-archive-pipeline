# JBPHH DW Archive Pipeline

Collects public JBPHH drinking water documents into the **JBPHH DW Archive & Registry** Shared Drive, recording where each file came from, when it was retrieved, and its SHA-256 hash.

The registry (`registry/documents.csv` in the Shared Drive) is the list of documents and the record of what has been collected. Its columns are described in `registry/README.md` there. This repo holds only code; files and the registry stay in the Shared Drive.

## Setup (once per computer)

1. Install [uv](https://docs.astral.sh/uv/).
2. In this folder, run `uv sync`.
3. Copy `.env.example` to `.env` and set `ARCHIVE_ROOT` to the Shared Drive folder on this computer.

## Download files

![What the download script does: it reads the catalog, picks rows marked to_download, and for each file downloads it and checks it is a real PDF. If not, it saves nothing and the row stays to_download. If so, it saves the file to raw/<website>/ and writes its fingerprint, time, location and done status to the catalog, then moves to the next file. At the end it reports what was saved and what failed.](docs/diagrams/download-script.excalidraw.svg)

*[Full-size image (PNG)](docs/diagrams/download-script.png)*

Downloads every registry row with status `to_download` into `raw/<site>/`, then marks it `done` with its hash, retrieval time and path. Safe to stop and rerun: finished rows are skipped. Close `documents.csv` in Excel before running.

```powershell
uv run --env-file .env scripts/download.py --dry-run   # list what would download
uv run --env-file .env scripts/download.py --limit 5   # try a few first
uv run --env-file .env scripts/download.py             # download everything left
```

Failed downloads are listed at the end and stay `to_download`, so a rerun retries them.

## Diagram PNGs

Diagrams are saved as `name.excalidraw.svg`: an SVG that is also the editable drawing. Diagrams of the archive live in the archive's `docs/diagrams/`; diagrams of this code live in this repo's `docs/diagrams/`. Edit them in VS Code with the Excalidraw extension; saving updates the SVG. Word and Google Docs can't show SVG, so this script writes `name.png` beside each one, rebuilding only PNGs older than their SVG:

```powershell
uv run playwright install chromium                     # once per computer
uv run --env-file .env scripts/export_pngs.py          # archive diagrams
uv run scripts/export_pngs.py --folder docs/diagrams   # this repo's diagrams
```

When a script's behavior changes, update its diagram in the same commit.

## Stepped diagrams

Some workflows are drawn as stepped diagrams: **Back / Next** buttons and a caption for each step, in the same hand-drawn Excalidraw style. Each one is a short spec in `docs/diagrams/specs/`; the top of each spec explains its format. Screenshots used in a diagram live in `docs/diagrams/screenshots/`, with the capture date in the file name, because websites change. To build one (this needs an internet connection, because Excalidraw is loaded from esm.sh):

```powershell
uv run --env-file .env scripts/build_stepper.py docs/diagrams/specs/listing-check-by-hand.toml
```

This writes `<name>.embed.html` (the stepped diagram), `<name>.excalidraw.svg` and `<name>.png` to the archive's `docs/diagrams/`. To change a stepped diagram, edit its spec and rebuild: a rebuild replaces all three files, so edits made to them directly are lost.

## Workflows notebook

`workflows.ipynb` shows every workflow diagram in one place. Open it in VS Code, select this folder's `.venv` as the kernel, and choose **Run All**. GitHub can't play stepped diagrams; open the `.embed.html` files in a web browser instead.

## Checks

```powershell
uv run pytest
uv run ruff check
```
