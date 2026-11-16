# JBPHH DW Archive Pipeline

Collects public JBPHH drinking water documents into the **[JBPHH DW Archive & Registry](https://drive.google.com/drive/folders/0AHEAE78xvLlaUk9PVA)** Shared Drive and records where each file came from, when it was saved, and its SHA-256 fingerprint. **This repo holds only code**. The files and the catalog (`registry/documents.csv`, columns explained in `registry/README.md`) live in the Shared Drive.

The goal, decisions and order of work are in [docs/pipeline-plan.md](docs/pipeline-plan.md).

## Setup (once per computer)

1. Install [uv](https://docs.astral.sh/uv/).
2. Open this folder in VS Code, open a new terminal, run `uv sync`, then `uv run playwright install chromium`.
3. Copy `.env.example` to `.env` and set `ARCHIVE_ROOT` to the Shared Drive folder on this computer.

## Run a step

```bash
uv run archive --help                                # list the steps
uv run archive download --help                       # one step's options
uv run --env-file .env archive download --dry-run    # example: see what would download
```

Add `--env-file .env` to any step that uses the Shared Drive. Close `documents.csv` in Excel first.

## Diagrams

- `notebooks/workflows.ipynb` shows every diagram. Open it in VS Code, select the repo's `.venv` as the kernel, and choose **Run All**. The files are in `docs/diagrams/`: `specs/`, `svgs/`, `pngs/`, `embeds/` (the Back / Next players) and `screenshots/`.
- **Stepped** (Back / Next) diagrams: edit the spec, then run `uv run archive diagrams build docs/diagrams/specs/<name>.toml`. A rebuild replaces the diagram's files, so don't edit those directly. **Hand-drawn** diagrams: edit `svgs/<name>.excalidraw.svg` in VS Code with the Excalidraw extension, then run `uv run archive diagrams png` to refresh its PNG for Word and Google Docs.
- Every diagram follows the style rules in [docs/diagrams/README.md](docs/diagrams/README.md).
- When a step's behavior changes, update its diagram in the same commit.

## Checks

```bash
uv run pytest
uv run ruff check .
```
