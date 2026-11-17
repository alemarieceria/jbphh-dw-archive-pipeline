# JBPHH DW Archive Pipeline

Collects public JBPHH drinking water documents into the **[JBPHH DW Archive & Registry](https://drive.google.com/drive/folders/0AHEAE78xvLlaUk9PVA)** Shared Drive and records where each file came from, when it was saved, and its SHA-256 fingerprint. The files live in the Shared Drive. **The catalog lives in this repo** (`catalog/documents.csv`, columns explained in [catalog/README.md](catalog/README.md)), and `archive publish` copies it to the Drive's `registry/` for tools such as the Evidence Tracer.

The goal, decisions and order of work are in [docs/pipeline-plan.md](docs/pipeline-plan.md).

## Setup (once per computer)

1. Install [uv](https://docs.astral.sh/uv/).
2. Open this folder in VS Code, open a new terminal, run `uv sync`, then `uv run playwright install chromium`.
3. Copy `.env.example` to `.env` and set `ARCHIVE_ROOT` to the Shared Drive folder on this computer.

## Run a step

```bash
uv run archive --help                                # list the steps
uv run archive download --help                       # one step's options
uv run archive inventory --zone I1                   # example: compare I1's listings with the catalog
uv run --env-file .env archive download --dry-run    # example: see what would download
uv run --env-file .env archive publish --dry-run     # example: see what publishing would change
```

Add `--env-file .env` to any step that uses the Shared Drive. Close `documents.csv` in Excel first. After a step changes the catalog, commit `catalog/documents.csv` and run `archive publish`.

## Diagrams

- `notebooks/workflows.ipynb` shows every diagram. Open it in VS Code, select the repo's `.venv` as the kernel, and choose **Run All**. The files are in `docs/diagrams/`: `specs/`, `svgs/`, `pngs/`, `embeds/` (the Back / Next players) and `screenshots/`.
- **Stepped** (Back / Next) diagrams: edit the spec, then run `uv run archive diagrams build docs/diagrams/specs/<name>.toml`. A rebuild replaces the diagram's files, so don't edit those directly. Diagrams **created in Excalidraw**: edit `svgs/<name>.excalidraw.svg` in VS Code with the Excalidraw extension, then run `uv run archive diagrams png` to refresh its PNG for Word and Google Docs.
- Every diagram follows the style rules in [docs/diagrams/README.md](docs/diagrams/README.md).
- When a step's behavior changes, update its diagram in the same commit.

## Checks

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
