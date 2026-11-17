# Catalog

Records about every file in the **JBPHH DW Archive & Registry** Shared Drive. The files
themselves live on the Drive, in `raw/`, `web-captures/` and `derived/`. These tables say what
each file is, where it came from, and how files relate.

This folder is the only place catalog rows are edited. `uv run --env-file .env archive publish`
copies them to the Drive's `registry/`, where tools such as the Evidence Tracer read them.
Never edit the Drive's copy; the next publish replaces it.

Scope so far: Zone I1 (Red Hill Housing) emergency response, Nov 2021 to Mar 2022.

## Conventions

- **Times are UTC**, written in ISO 8601: `2026-10-31T07:25:23Z`.
- **A date without a time** (`2026-02-07`) means only the day was recorded.
- **A blank cell** means unknown, not yet done, or not applicable. The `notes` column says
  which when it matters.
- **One row per thing.** No merged cells, no totals rows, no formatting that carries meaning.
- **Edit in VS Code or a text editor, not Excel**, which silently reformats dates and IDs.
  Close the file in other programs before running a command that writes it.

## documents.csv

One row per file or web page in scope. Started as the collection list (what to download or
capture). Retrieval fields get filled in as each file lands in the archive.

| Column | Format | Description |
|---|---|---|
| `doc_id` | `DOC-0001` | Stable ID. Never reuse or renumber, even if a row is dropped. |
| `group` | vocabulary | Where the item came from or what role it plays: `zone_page_er`, `navy_lab_collection`, `doh_lab_collection`, `governing`, `doh_decision`, `public_communication`, `web_page`. |
| `title_as_posted` | text | Title exactly as the source shows it. |
| `source_url` | URL | Where to get it. Blank if not found yet. |
| `original_filename` | text | Filename on the source, when known before download. Library files are `pub_00NNNN.pdf`. |
| `library_id` | text | ID in the jbphh-safewaters document library, for library files. |
| `producer` | text | Organization that created the document (lab, validator, agency). Blank if not yet confirmed. |
| `doc_type` | vocabulary | `lab_report`, `lab_report_bundle`, `data_validation_report`, `data_validation_checklist`, `data_review_report`, `data_table`, `summary_report`, `results_crosstab`, `removal_action_report`, `plan`, `plan_addendum`, `plan_and_results`, `sop`, `guidance`, `technical_memo`, `regulatory_directive`, `regulatory_advisory`, `regulatory_memo`, `press_release`, `fact_sheet`, `map`, `graphic`, `transcript`, `library_listing`, `web_page`. |
| `date_as_listed` | date | Date shown in the title or listing. **Not** necessarily when it was posted or created. |
| `zones` | list | Flushing zones the document covers, separated by `; ` (for example `I1` or `I1; D1`). `all` for system-wide documents such as plans and directives. |
| `phase` | vocabulary | Response phase the document belongs to. So far always `emergency_response` (Nov 2021 to Mar 2022). |
| `size_listed` | text | File size as the library lists it. |
| `sdg` | text | Lab job or sample delivery group number, normalized (for example `810-12077-2`). For DOH files, the lab report number. |
| `package_or_validation_level` | text | For lab reports, the data package level (`Level 2`, `Level 3`, `Level 4`). For validation files, the validation stage (`S2AVEM`, `S4VEM`, `Stage 2A`). |
| `revision` | text | Revision as labeled (`Revision 1`), or `duplicate upload (2)` for files the library lists twice. |
| `duplicate_of` | doc_id | Filled when this file is byte-identical to another registered file (same SHA-256). Points to the copy to use. **Tools must skip rows with this filled**, so each file is processed once; the duplicate stays archived as evidence of what was posted. |
| `priority` | vocabulary | `core` (evidence chain and governing documents), `supporting` (communications, fact sheets, maps), `context` (background such as transcripts). |
| `in_team_folder` | `yes` / `no` | Whether the team's existing I1 folder should already have it, for cross-checking. |
| `status` | vocabulary | `to_find` (no URL yet), `to_download` (file), `to_capture` (web page), `done`, `unavailable`. |
| `retrieved_utc` | datetime | When the file was downloaded or captured. |
| `sha256` | text | File hash, recorded at download. Proves the archived file hasn't changed. |
| `local_path` | text | Path inside the Shared Drive, for example `raw/jbphh-safewaters/pub_002925.pdf`. When one item has several files (a web page saved as PDF and HTML, or a listing split across pages), paths are separated by `; `. |
| `notes` | text | Known issues, context, and anything still to verify. |

The other registry tables (`wayback_captures.csv`, `wayback_page_history.csv`) stay in the
Drive's `registry/` until `archive wayback` is built, and are described in its `README.md`.
