import html
from pathlib import Path

import pytest

from jbphh_archive.diagrams.build_stepper import SpecError, embed_file, image_size, load_spec, prepare_images, with_ids

SPECS = Path(__file__).resolve().parents[1] / "docs" / "diagrams" / "specs"
SCREENSHOTS = SPECS.parent / "screenshots"

MINIMAL = """
name = "demo"
title = "Demo"
width = 400
height = 200

[[steps]]
caption = "First"

[[steps]]
caption = "Second"

[[elements]]
step = 1
type = "rectangle"
x = 0
y = 0
width = 100
height = 50

[[elements]]
step = 2
type = "text"
x = 0
y = 80
text = "Hello"
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "spec.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_every_spec_in_the_repo_is_valid():
    specs = sorted(SPECS.glob("*.toml"))
    assert specs, "expected at least one spec"
    for path in specs:
        spec = load_spec(path)
        assert spec["name"] == path.stem


def test_minimal_spec_loads(tmp_path):
    spec = load_spec(write(tmp_path, MINIMAL))
    assert [s["caption"] for s in spec["steps"]] == ["First", "Second"]


def test_step_without_caption_is_rejected(tmp_path):
    with pytest.raises(SpecError, match="step 2 has no caption"):
        load_spec(write(tmp_path, MINIMAL.replace('caption = "Second"', 'caption = ""')))


def test_element_step_out_of_range_is_rejected(tmp_path):
    with pytest.raises(SpecError, match="element 2 needs `step` between 1 and 2"):
        load_spec(write(tmp_path, MINIMAL.replace("step = 2", "step = 3")))


def test_step_with_nothing_to_show_is_rejected(tmp_path):
    with pytest.raises(SpecError, match=r"no elements appear in step\(s\) 2"):
        load_spec(write(tmp_path, MINIMAL.replace("step = 2", "step = 1")))


def test_elements_get_fixed_ids():
    assert [e["id"] for e in with_ids([{"step": 1}, {"step": 2}])] == ["e1", "e2"]


def test_embed_file_holds_every_frame_and_caption(tmp_path):
    spec = load_spec(write(tmp_path, MINIMAL))
    frames = ['<svg id="one"></svg>', '<svg id="two"></svg>']
    page = html.unescape(embed_file(spec, frames).split('srcdoc="')[1].split('" style=')[0])
    for svg in frames:
        assert svg in page  # drawn straight into the page, so embedded fonts load everywhere
    assert '["First", "Second"]' in page
    assert "Step 1: First Step 2: Second" in page  # screen-reader description


MARKED = """
[[elements]]
step = 1
type = "marked"
x = 0
y = 120
text = "a=[Navy]&b=[I1]"
marks = [{ step = 2, strokeColor = "#005a8c" }, { step = 2, strokeColor = "#00704f" }]
"""


def test_marked_text_counts_toward_its_marks_steps(tmp_path):
    spec = MINIMAL.replace('step = 2\ntype = "text"', 'step = 1\ntype = "text"') + MARKED
    assert len(load_spec(write(tmp_path, spec))["elements"]) == 3  # step 2 is covered by the marks


def test_marked_text_needs_one_mark_per_bracket(tmp_path):
    spec = MINIMAL + MARKED.replace(', { step = 2, strokeColor = "#00704f" }', "")
    with pytest.raises(SpecError, match=r"2 \[bracketed\] part\(s\) but 1 mark\(s\)"):
        load_spec(write(tmp_path, spec))


def test_marked_text_rejects_unpaired_brackets(tmp_path):
    spec = MINIMAL + MARKED.replace("a=[Navy]", "a=[Navy")
    with pytest.raises(SpecError, match="brackets"):
        load_spec(write(tmp_path, spec))


IMAGE = """
[[elements]]
step = 2
type = "image"
src = "shot.png"
x = 0
y = 0
width = 200
"""


def test_image_size_reads_png_and_jpeg():
    png = next(SCREENSHOTS.glob("*.png")).read_bytes()
    assert image_size(png) > (0, 0)
    jpeg = b"\xff\xd8\xff\xe0\x00\x04\x00\x00\xff\xc0\x00\x11\x08\x01\x2c\x02\x80" + bytes(12)
    assert image_size(jpeg) == (640, 300)
    with pytest.raises(SpecError, match="PNG or JPEG"):
        image_size(b"GIF89a")


def test_image_gets_its_file_and_keeps_its_proportions(tmp_path):
    shot = next(SCREENSHOTS.glob("*.png"))
    (tmp_path / "shot.png").write_bytes(shot.read_bytes())
    spec = load_spec(write(tmp_path, MINIMAL + IMAGE))
    elements, files = prepare_images(spec["elements"], spec["_folder"])
    image = elements[-1]
    width, height = image_size(shot.read_bytes())
    assert image["height"] == round(200 * height / width)
    assert "src" not in image and files[image["fileId"]]["dataURL"].startswith("data:image/png;base64,")


def test_missing_image_file_is_rejected(tmp_path):
    with pytest.raises(SpecError, match="image file not found: shot.png"):
        load_spec(write(tmp_path, MINIMAL + IMAGE))
