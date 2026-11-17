"""Tools that build and check the JBPHH drinking water archive."""

from pathlib import Path

# This repo's folder, found from this file's own place (src/jbphh_archive/__init__.py), so it
# works from any folder, including notebooks/. This relies on `uv sync` installing the project
# in editable mode (uv's default), which keeps this file inside the repo's src/.
REPO_ROOT = Path(__file__).resolve().parents[2]
