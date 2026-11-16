"""Build a stepped (Back / Next) Excalidraw diagram from a diagram spec.

A spec is a TOML file in docs/diagrams/specs/ with the diagram's title, one caption
per step, and its elements (boxes, text, arrows), each tagged with the step where it
first appears. Elements can include screenshots (PNG or JPEG) stored next to the specs.
Excalidraw draws the picture, so it has the same hand-drawn look as diagrams made in VS Code. Excalidraw runs in a headless browser and is loaded from
esm.sh, so this needs an internet connection.

Writes three files, named after the spec's `name`, into docs/diagrams/'s subfolders:
    embeds/<name>.embed.html    the stepped diagram: open it in a browser or show it in a notebook
    svgs/<name>.excalidraw.svg  the finished drawing, which VS Code's Excalidraw extension can open
    pngs/<name>.png             the finished drawing as an image, for Word and Google Docs

Usage (from the project folder):
    uv run archive diagrams build docs/diagrams/specs/listing-check-by-hand.toml
"""

import argparse
import base64
import json
import re
import sys
import tomllib
from html import escape
from pathlib import Path

from playwright.sync_api import sync_playwright

from jbphh_archive.diagrams.export_pngs import SCALE
from jbphh_archive.diagrams.paths import diagrams_folder, embed_path, png_path, svg_path

# Pinned versions, so the same spec always draws the same way.
EXCALIDRAW = "https://esm.sh/@excalidraw/excalidraw@0.18.0?deps=react@19.0.0,react-dom@19.0.0"
LOADER_PAGE = "https://esm.sh/"  # any page on the CDN's own site, so the browser may load its modules
PLAY_SECONDS = 4  # time on each step when "Play" is pressed
MARKED_TEXT = re.compile(r"[^\[\]]*(\[[^\[\]]+\][^\[\]]*)*")  # text with [marked] parts

# Runs inside the browser. Excalidraw turns the spec's simple elements into full drawing
# elements, then draws one picture per step: everything up to and including that step.
# An invisible rectangle the size of the canvas keeps every step's picture the same size.
DRAW_JS = r"""async ({url, elements, width, height, files}) => {
  const ex = await import(url);
  const appState = {exportBackground: true, viewBackgroundColor: "#ffffff"};

  // Marked lines need exact text widths, measured in Excalidraw's own font. Drawing those
  // lines once embeds the font in an SVG; loading it from there lets the browser measure it.
  const marked = elements.filter((el) => el.type === "marked");
  const unbracket = (text) => text.replace(/[\[\]]/g, "");
  if (marked.length) {
    const probe = await ex.exportToSvg({
      elements: ex.convertToExcalidrawElements(marked.map((el) => (
        {type: "text", x: 0, y: 0, text: unbracket(el.text), fontSize: el.fontSize ?? 20}))),
      appState, files: null,
    });
    const faces = probe.outerHTML.matchAll(/@font-face\s*\{\s*font-family:\s*([^;]+);\s*src:\s*url\(([^)]+)\)/g);
    for (const [, family, src] of faces) document.fonts.add(await new FontFace(family.trim(), `url(${src})`).load());
    if (!document.fonts.check("20px Excalifont")) throw new Error("Could not load Excalidraw's font to measure text");
  }
  const ctx = document.createElement("canvas").getContext("2d");
  const textWidth = (text, size) => { ctx.font = `${size}px Excalifont`; return ctx.measureText(text).width; };

  // A marked line becomes plain text plus, for each [bracketed] part, a tinted box behind
  // that part (and an optional arrow) that appears at that mark's step.
  const expand = (el) => {
    if (el.type !== "marked") return [el];
    const size = el.fontSize ?? 20, parts = el.text.split(/[\[\]]/);
    const marks = [];
    let before = "";
    parts.forEach((part, i) => {
      if (i % 2 === 1) {
        const n = (i - 1) / 2, mark = el.marks[n];
        const x = el.x + textWidth(before, size) - 3, y = el.y - 3;
        const w = textWidth(part, size) + 6, h = size * 1.25 + 6;
        marks.push({id: `${el.id}m${n}`, step: mark.step, type: "rectangle", x, y, width: w, height: h,
                    strokeColor: mark.strokeColor, backgroundColor: mark.backgroundColor ?? "transparent",
                    strokeWidth: 2, roughness: 0});
        if (mark.arrowTo) {
          const [ax, ay] = [x + w / 2, y + h + 4];
          marks.push({id: `${el.id}a${n}`, step: mark.step, type: "arrow", x: ax, y: ay,
                      points: [[0, 0], [mark.arrowTo[0] - ax, mark.arrowTo[1] - ay]], strokeColor: mark.strokeColor});
        }
      }
      before += part;
    });
    // The boxes come first so the text is drawn on top of them.
    return [...marks, {id: el.id, step: el.step, type: "text", x: el.x, y: el.y, text: parts.join(""),
                       fontSize: size, strokeColor: el.strokeColor ?? "#1e1e1e"}];
  };
  const expanded = elements.flatMap(expand);

  const stepOf = {};
  for (const el of expanded) stepOf[el.id] = el.step;
  const plain = expanded.map(({step, marks, ...rest}) => rest);
  const canvas = {type: "rectangle", id: "canvas", x: 0, y: 0, width, height,
                  strokeColor: "transparent", backgroundColor: "transparent"};
  const all = ex.convertToExcalidrawElements([canvas, ...plain], {regenerateIds: false});
  // Text inside a box or on an arrow belongs to the same step as its container.
  const step = (e) => (e.id === "canvas" ? 0 : stepOf[e.id] ?? stepOf[e.containerId] ?? 0);
  const last = Math.max(...Object.values(stepOf));
  const frames = [];
  for (let k = 1; k <= last; k++) {
    const svg = await ex.exportToSvg({elements: all.filter((e) => step(e) <= k), appState, files});
    frames.push(svg.outerHTML);
  }
  const final = await ex.exportToSvg({
    elements: all.filter((e) => e.id !== "canvas"),
    appState: {...appState, exportEmbedScene: true},  // keeps the drawing editable in VS Code
    files,
  });
  return {frames, final: final.outerHTML};
}"""


class SpecError(ValueError):
    """The spec file is missing something the builder needs."""


def load_spec(path: Path) -> dict:
    """Read a spec and check it has what the builder needs, with plain error messages."""
    spec = tomllib.loads(path.read_text(encoding="utf-8"))
    for key in ("name", "title", "width", "height", "steps", "elements"):
        if key not in spec:
            raise SpecError(f"{path.name}: missing `{key}`")
    count = len(spec["steps"])
    for number, step in enumerate(spec["steps"], 1):
        if not step.get("caption"):
            raise SpecError(f"{path.name}: step {number} has no caption")
    used = set()
    for number, element in enumerate(spec["elements"], 1):
        where = f"{path.name}: element {number}"
        used |= element_steps(element, count, where)
        if element.get("type") == "image":
            check_image(element, path.parent, where)
    if empty := sorted(set(range(1, count + 1)) - used):
        raise SpecError(f"{path.name}: no elements appear in step(s) {', '.join(map(str, empty))}")
    spec["_folder"] = path.parent  # image paths in the spec are relative to this folder
    return spec


def element_steps(element: dict, count: int, where: str) -> set[int]:
    """The steps an element appears in; a marked line also appears at each of its marks' steps."""
    steps = [element.get("step")] + [mark.get("step") for mark in element.get("marks", [])]
    if not all(isinstance(step, int) and 1 <= step <= count for step in steps):
        raise SpecError(f"{where} needs `step` between 1 and {count} (and so does each of its marks)")
    if element.get("type") == "marked":
        text = element.get("text", "")
        if not MARKED_TEXT.fullmatch(text):
            raise SpecError(f"{where}: marked text needs [brackets] in pairs, not nested")
        parts, marks = text.count("["), len(element.get("marks", []))
        if parts != marks:
            raise SpecError(f"{where}: has {parts} [bracketed] part(s) but {marks} mark(s)")
    return set(steps)


def check_image(element: dict, folder: Path, where: str) -> None:
    """An image needs a file that exists (relative to the spec's folder) and a width."""
    src = element.get("src")
    if not src or not (folder / src).is_file():
        raise SpecError(f"{where}: image file not found: {src}")
    if not element.get("width"):
        raise SpecError(f"{where}: image needs a `width`")


def image_size(data: bytes) -> tuple[int, int]:
    """Width and height, in pixels, of a PNG or JPEG file."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):  # walk the JPEG's segments to the one that holds the size
            marker, length = data[i + 1], int.from_bytes(data[i + 2 : i + 4], "big")
            if marker in (0xC0, 0xC1, 0xC2):
                return int.from_bytes(data[i + 7 : i + 9], "big"), int.from_bytes(data[i + 5 : i + 7], "big")
            i += 2 + length
    raise SpecError("images must be PNG or JPEG files")


def prepare_images(elements: list[dict], folder: Path) -> tuple[list[dict], dict]:
    """Load each image file for Excalidraw, with a height that keeps the image's proportions."""
    files: dict[str, dict] = {}
    prepared = []
    for element in elements:
        if element.get("type") != "image":
            prepared.append(element)
            continue
        data = (folder / element["src"]).read_bytes()
        width, height = image_size(data)
        mime = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
        file_id = f"image-{len(files) + 1}"
        data_url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        files[file_id] = {"id": file_id, "mimeType": mime, "dataURL": data_url, "created": 0}
        shown = {key: value for key, value in element.items() if key != "src"}
        shown.setdefault("height", round(element["width"] * height / width))
        prepared.append({**shown, "fileId": file_id})
    return prepared, files


def with_ids(elements: list[dict]) -> list[dict]:
    """Give each element a fixed id (e1, e2, ...) so its step can be traced after drawing."""
    return [{**element, "id": f"e{number}"} for number, element in enumerate(elements, 1)]


def summary(spec: dict) -> str:
    """One text description of every step, for screen readers."""
    steps = " ".join(f"Step {n}: {s['caption']}" for n, s in enumerate(spec["steps"], 1))
    return f"{spec['title']}, in {len(spec['steps'])} steps. {steps}"


def player_page(spec: dict, frames: list[str]) -> str:
    """A self-contained page that shows one step at a time, with Back, Next and Play."""
    # Each step's drawing goes straight into the page, not in an <img>, so its embedded
    # hand-drawn font loads in every browser, including Safari on iPads and iPhones.
    images = "".join(f'<div class="frame" aria-hidden="true">{svg}</div>' for svg in frames)
    captions = [step["caption"] for step in spec["steps"]]
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(spec["title"])}</title><style>
body{{margin:0;padding-bottom:1px;background:#fff;color:#172033;font:16px system-ui,sans-serif}}
nav{{display:flex;gap:8px;align-items:center;justify-content:center;padding:10px 12px;border-bottom:1px solid #dde2ea}}
button{{font:inherit;padding:6px 14px;cursor:pointer;border:1px solid #8a939e;border-radius:6px;background:#f6f7f9;color:#172033}}
button:disabled{{opacity:.5;cursor:default}}button:focus-visible{{outline:3px solid #005a8c;outline-offset:2px}}
output{{min-width:6.5em;text-align:center;font-variant-numeric:tabular-nums}}
.layout{{max-width:{spec["width"] + 20}px;margin:12px auto;padding:0 12px}}
.stage{{display:grid}}
.frame{{grid-area:1/1;opacity:0;transition:opacity .4s}}.frame.on{{opacity:1}}.frame svg{{display:block;width:100%;height:auto}}
@media (prefers-reduced-motion:reduce){{.frame{{transition:none}}}}
/* The caption sits right under the buttons, so it is always on screen; the drawing gets the full width. */
#panel{{background:#f1f3f5;border-left:5px solid #005a8c;border-radius:8px;padding:12px 16px;margin-bottom:10px;
font-size:17px;line-height:1.5;min-height:3em}}#steplabel{{margin:0 0 4px;font-weight:600;color:#005a8c}}#caption{{margin:0}}
</style>
<nav aria-label="Figure controls"><button id="back">&#9664; Back</button><button id="next">Next &#9654;</button>
<button id="play">Play</button><output id="status"></output></nav>
<div class="layout"><div id="panel" aria-live="polite"><p id="steplabel"></p><p id="caption"></p></div>
<div class="stage" role="img" aria-label="{escape(summary(spec))}">{images}</div></div>
<script>
const captions = {json.dumps(captions)};
const frames = [...document.querySelectorAll(".frame")], get = (id) => document.getElementById(id);
let step = 0, timer = null;
function show(k) {{
  step = (k + frames.length) % frames.length;
  frames.forEach((f, i) => f.classList.toggle("on", i === step));
  get("status").textContent = "Step " + (step + 1) + " / " + frames.length;
  get("steplabel").textContent = "Step " + (step + 1) + " of " + frames.length;
  get("caption").textContent = captions[step];
  get("back").disabled = step === 0;
}}
function stop() {{ clearInterval(timer); timer = null; get("play").textContent = "Play"; }}
function play() {{
  if (timer) {{ stop(); return; }}
  get("play").textContent = "Pause";
  timer = setInterval(() => show(step + 1), {PLAY_SECONDS * 1000});
}}
get("next").onclick = () => {{ stop(); show(step + 1); }};
get("back").onclick = () => {{ stop(); show(step - 1); }};
get("play").onclick = play;
document.addEventListener("keydown", (e) => {{
  if (e.key === "ArrowRight") {{ stop(); show(step + 1); }}
  if (e.key === "ArrowLeft" && step > 0) {{ stop(); show(step - 1); }}
}});
// Let a notebook keep scrolling when the mouse wheel is over the figure.
addEventListener("wheel", (e) => frameElement?.dispatchEvent(new WheelEvent("wheel", e)), {{passive: true}});
// Grow or shrink the surrounding frame to fit the drawing and caption at any width.
function fit() {{ if (frameElement) frameElement.style.height = document.body.offsetHeight + "px"; }}
addEventListener("load", fit);
addEventListener("resize", fit);
show(0);
</script></html>"""


def embed_file(spec: dict, frames: list[str]) -> str:
    """Wrap the player in an iframe, so its styles can't clash with a notebook or web page."""
    height = round(spec["height"] * 900 / spec["width"]) + 100  # starting height; the page then resizes it to fit
    return (
        f'<iframe title="{escape(spec["title"])}" aria-label="{escape(summary(spec))}" '
        f'srcdoc="{escape(player_page(spec, frames), quote=True)}" '
        f'style="width:100%;max-width:{spec["width"] + 60}px;height:{height}px;border:1px solid #dde2ea;border-radius:8px">'
        "</iframe>\n"
    )


def draw(spec: dict, png: Path) -> tuple[list[str], str]:
    """Have Excalidraw draw each step and the finished drawing, and save the PNG."""
    elements, files = prepare_images(with_ids(spec["elements"]), spec["_folder"])
    args = {"url": EXCALIDRAW, "elements": elements, "files": files, "width": spec["width"], "height": spec["height"]}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=SCALE)
        page.goto(LOADER_PAGE)
        result = page.evaluate(DRAW_JS, args)
        page.set_content(f'<body style="margin:0;background:#fff">{result["final"]}</body>')
        page.evaluate("document.fonts.ready")  # wait for the hand-drawn font before capturing
        page.locator("svg").first.screenshot(path=png)
        browser.close()
    return result["frames"], result["final"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="archive diagrams build", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spec", type=Path, help="diagram spec (.toml)")
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.spec)
    except (OSError, tomllib.TOMLDecodeError, SpecError) as err:
        sys.exit(f"Could not read the spec: {err}")
    folder = diagrams_folder()
    name = spec["name"]
    svg, png, embed = svg_path(folder, name), png_path(folder, name), embed_path(folder, name)
    for path in (svg, png, embed):
        path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Drawing {len(spec['steps'])} steps of {name} with Excalidraw...")
    frames, final = draw(spec, png)
    svg.write_text(final, encoding="utf-8")
    embed.write_text(embed_file(spec, frames), encoding="utf-8")
    for path in (embed, svg, png):
        print(f"    saved {path}")
    return 0
