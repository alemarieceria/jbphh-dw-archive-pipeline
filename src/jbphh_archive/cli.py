"""One command for every archive step: `uv run archive <step> [options]`.

`uv run archive --help` lists the steps; `uv run archive <step> --help` shows a
step's options. Each step's code lives in its own module; this file only routes
to it. To add a step, add a line to STEPS.
"""

import sys

from jbphh_archive import download, inventory, publish
from jbphh_archive.diagrams import build_stepper, export_pngs

# Step name -> (one-line summary, function that runs the step with the remaining options).
STEPS = {
    "inventory": ("Compare a zone's Navy and DOH listings with the catalog; report in reports/", inventory.main),
    "download": ("Download catalog rows marked to_download into raw/<site>/", download.main),
    "publish": ("Copy the catalog to the Drive's registry/, where tools read it", publish.main),
    "diagrams png": ("Write a PNG in pngs/ for each SVG in svgs/ (only where the SVG changed)", export_pngs.main),
    "diagrams build": ("Build a stepped (Back / Next) diagram from its spec", build_stepper.main),
}


def usage() -> str:
    width = max(len(name) for name in STEPS)
    lines = ["usage: archive <step> [options]", "", "steps:"]
    lines += [f"  {name:<{width}}  {summary}" for name, (summary, _) in STEPS.items()]
    lines += ["", "Run `archive <step> --help` for a step's options."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(usage())
        return 0
    for name, (_, run) in STEPS.items():
        words = name.split()
        if argv[: len(words)] == words:
            return run(argv[len(words) :])
    sys.exit(f"Unknown step: {' '.join(argv)}\n\n{usage()}")
