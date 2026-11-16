# Diagrams

Every diagram of the archive lives here. `notebooks/workflows.ipynb` shows them all.

| Folder | What it holds |
| --- | --- |
| `specs/` | the source of each stepped (Back / Next) diagram |
| `svgs/` | each drawing, editable in VS Code's Excalidraw extension |
| `pngs/` | each drawing as an image, for Word and Google Docs |
| `embeds/` | the Back / Next players |
| `screenshots/` | screenshots used inside stepped diagrams |

How to edit and rebuild them is in the main [README](../../README.md#diagrams).

## Style rules

Every diagram follows these rules, so a reader who has learned one can read the others.

**Look.** Colors from the Red Hill tools design system, a `#fbf8f3` background, clean lines
(Excalidraw's "sloppiness" set to none) and Excalidraw's hand-drawn font.

**Colors mean the same thing in every diagram.**

| Meaning | Fill | Border |
| --- | --- | --- |
| Automatic step | `#e4ece7` | `#1f5c4a` |
| Step you do by hand | `#f8efe7` | `#8c4a35`, thick (4) |
| Where data comes from or goes | `#e6eef6` | `#2d5b85` |
| Where data is stored | `#dcd6cc` | `#443f38`, thick (3) |
| Automatic checks | white | `#625b53`, dashed (3) |
| Panel (a column, a group, the legend) | white | `#625b53` |
| Note | `#eeeae2` | `#625b53` |

The blue and the tan are not in the design system; they are used only in diagrams. Every
diagram whose colors carry meaning has a legend listing the ones it uses. A screenshot
walkthrough (`listing-check-by-hand`) uses these colors only to pair each highlight with
its label, so it has no legend.

**Arrows** are `#443f38` and show data moving, or the order of steps in a step-by-step
diagram. The legend says which. In a screenshot walkthrough, each arrow takes its
callout's color.

**Text** is `#1c1a17`. Subtitles, footers, notes and arrow labels are `#443f38`. Links are
`#1f5c4a`. Color goes on borders and fills, not on text.

**Sizes**

| Text | Size |
| --- | --- |
| Title, centered at the top | 36 |
| Subtitle, centered under the title, saying what the diagram is for | 22 |
| Footer line | 22 |
| Heading inside the drawing (a column, the legend) | 24 |
| Text in boxes and the legend | 20 |
| Notes and arrow labels | 18 |

Boxes have rounded corners. Highlights on screenshots are square, with a 3 border.

**Wording**

- Backticks for anything you type or that names something in the code or files: commands
  (`archive download`), options (`--apply`), folders (`raw/`), files (`documents.csv`),
  columns (`library_id`), status values (`to_download`, `done`, `link_only`) and the parts
  of a web address you change (`Navy`, `DoH`). A list of values, such as the 19 zone IDs,
  stays plain so it is easy to read.
- Double quotes for labels as they appear on a website: "Sort by System Filename",
  "Show 100 Items".
- Sentence case: "1. Public sources", not "1. PUBLIC SOURCES".
- One name for each thing: "Safe Waters site" (with `jbphh-safewaters.org` where the
  address matters), "DOH" (except `DoH` inside a web address), and each command by its
  name, never "script".
- Phases, stages and periods use the Vocabulary rule in
  [docs/pipeline-plan.md](../pipeline-plan.md#catalog-design-decided-2026-11-10).
