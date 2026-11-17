"""Notebooks are saved without outputs, so they stay small and their diffs show only real changes."""

import json
from pathlib import Path

import pytest

NOTEBOOKS = sorted((Path(__file__).resolve().parents[1] / "notebooks").glob("*.ipynb"))


def cells_with_outputs(notebook_text: str) -> list[str]:
    """The ids of code cells that were saved after being run."""
    cells = json.loads(notebook_text)["cells"]
    return [c["id"] for c in cells if c["cell_type"] == "code" and (c.get("outputs") or c.get("execution_count"))]


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda path: path.name)
def test_notebook_is_saved_without_outputs(notebook):
    saved = cells_with_outputs(notebook.read_text(encoding="utf-8"))
    assert not saved, f"{notebook.name} has saved outputs in cells {saved}. In VS Code: Clear All Outputs, then save."
