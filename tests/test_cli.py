"""Tests for the `archive` command: it lists the steps and passes options through unchanged."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jbphh_archive import cli


def test_help_lists_every_step(capsys):
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    for name in cli.STEPS:
        assert name in out


def test_no_step_shows_help(capsys):
    assert cli.main([]) == 0
    assert "usage: archive <step>" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "step", "passed_on"),
    [
        (["inventory", "--zone", "I1"], "inventory", ["--zone", "I1"]),
        (["discover", "--zone", "I1"], "discover", ["--zone", "I1"]),
        (["merge", "review.csv", "--apply"], "merge", ["review.csv", "--apply"]),
        (["validate"], "validate", []),
        (["download", "--dry-run", "--limit", "5"], "download", ["--dry-run", "--limit", "5"]),
        (["publish", "--dry-run"], "publish", ["--dry-run"]),
        (["diagrams", "png", "--force"], "diagrams png", ["--force"]),
        (["diagrams", "build", "spec.toml"], "diagrams build", ["spec.toml"]),
    ],
)
def test_routes_options_to_the_step(monkeypatch, argv, step, passed_on):
    calls = []
    monkeypatch.setitem(cli.STEPS, step, ("", lambda options: calls.append(options) or 0))
    assert cli.main(argv) == 0
    assert calls == [passed_on]


def test_unknown_step_fails_with_the_step_list():
    with pytest.raises(SystemExit) as err:
        cli.main(["nope"])
    assert "Unknown step: nope" in str(err.value.code)
    assert "download" in str(err.value.code)


def test_archive_command_is_installed():
    """The real `archive` command (registered in pyproject.toml) runs and lists the steps."""
    command = shutil.which("archive", path=str(Path(sys.executable).parent))
    assert command, "archive command not found: run `uv sync`"
    result = subprocess.run([command, "--help"], capture_output=True, text=True, check=True)
    assert "diagrams build" in result.stdout
