# Catalog

Records about every file in the **JBPHH DW Archive & Registry** Shared Drive. The files
themselves live on the Drive, in `raw/`, `web-captures/` and `derived/`. These tables say what
each file is, where it came from, and how files relate.

This folder is the only place catalog rows are edited. `uv run --env-file .env archive publish`
copies them to the Drive's `registry/`, where tools such as the Evidence Tracer read them.
Never edit the Drive's copy; the next publish replaces it.

`uv run archive validate` checks these files against the rules below. GitHub runs it on every
push, so a file that breaks a rule fails the checks.

Scope so far: Zone I1 (Red Hill Housing): its emergency response documents (Nov 2021 to Mar
2022), and its LTM and EDWM documents as `link_only`.

## Conventions

- **Times are UTC**, written in ISO 8601: `2026-10-31T07:25:23Z`.
- **A date without a time** (`2026-02-07`) means only the day was recorded.
- **A blank cell** means unknown, not yet done, or not applicable. The `notes` column says
  which when it matters.
- **One row per thing.** No merged cells, no totals rows, no formatting that carries meaning.
- **Edit in VS Code or a text editor, not Excel**, which silently reformats dates and IDs.
  Close the file in other programs before running a command that writes it.

## documents.csv

One row per file or web page in scope. The ID column is `doc_id`.

**Source:** built by A. Ceria for Zone I1, manually, from I1's zone page, the Navy and DOH I1
library listings, and documents cited by other documents. DOC-0170 to DOC-0349 (I1's LTM and
EDWM documents and the monitoring dashboard, all `link_only`) were added by `archive merge`
from `reports/2026-11-19-discover-I1.csv`. Files downloaded 2026-10-31, except DOC-0144
(2026-11-23).
Checked 2026-11-17: `archive inventory --zone I1` matched all 123 library rows to the live
listings (`reports/2026-11-17-inventory-I1.csv`).

**Who writes it:** people, and `archive download` (retrieval columns). `archive discover`
proposes new rows in a review file in `reports/`. `archive merge` writes the ones you
accept.

**Updates:** rows are never deleted and a `doc_id` is never reused. After a change, commit the
file and run `archive publish`.

| Column | Format | Description | Filled by |
|---|---|---|---|
| `doc_id` | `DOC-0001` | Stable ID. Never reuse or renumber, even if a row is dropped. | `archive merge`, when you accept a proposed row; manually for a row you add yourself |
| `group` | vocabulary | Where the item came from or what role it plays: `zone_page_er`, `navy_lab_collection`, `doh_lab_collection`, `governing`, `doh_decision`, `public_communication`, `web_page`; `zone_page_ltm` and `zone_page_edwm` (links in a zone page's LTM or EDWM section, including its listing link), `ltm_lab_collection` (LTM listing results), `source_water` (Waiawa Shaft files, posted on every zone page). | Manually (proposed by `archive discover`) |
| `title_as_posted` | text | Title exactly as the source shows it. | Manually (proposed by `archive discover`) |
| `source_url` | URL | Where to get it. Blank if not found yet. | Manually (proposed by `archive discover`) |
| `original_filename` | text | Filename on the source, when known before download. Library files are `pub_00NNNN.pdf`. | Manually (proposed by `archive discover`), or `archive download` when blank |
| `library_id` | text | ID in the jbphh-safewaters document library, for library files. Blank if not a library file. | Manually (proposed by `archive discover`) |
| `producer` | text | Organization that created the document (lab, validator, agency). Blank if not yet confirmed. | Manually (later proposed by `archive discover`) |
| `publisher` | org ID | Stakeholder Directory org ID of the issuing organization (for example `idwst`, `doh`). The most specific one that exists; if only its parent exists, use the parent and say so in `notes`. Blank if not set yet. | Manually (later proposed by `archive discover`) |
| `doc_type` | vocabulary | `lab_report`, `lab_report_bundle`, `data_validation_report`, `data_validation_checklist`, `data_review_report`, `data_table`, `summary_report`, `results_crosstab`, `removal_action_report`, `plan`, `plan_addendum`, `plan_and_results`, `sop`, `guidance`, `technical_memo`, `regulatory_directive`, `regulatory_advisory`, `regulatory_memo`, `press_release`, `fact_sheet`, `map`, `graphic`, `transcript`, `library_listing`, `web_page`. | Manually (proposed by `archive discover`) |
| `date_as_listed` | date | Date shown in the title or listing. **Not** necessarily when it was posted or created. | Manually (proposed by `archive discover`) |
| `zones` | list | Flushing zones the document covers, separated by `; ` (for example `I1` or `I1; D1`). `all` for system-wide documents such as plans and directives. | Manually (proposed by `archive discover`) |
| `phase` | vocabulary | Which part of the response the document belongs to: `emergency_response` (the emergency response, Nov 2021 to Mar 2022), `ltm` (Long Term Monitoring), `edwm` (Extended Drinking Water Monitoring), `post_edwm` (monitoring after EDWM; the site calls it "Post-EDWM", or PEM), or `monitoring` (covers more than one of the 3 monitoring phases, such as the Drinking Water Monitoring Dashboard). | Manually (proposed by `archive discover`) |
| `stage` | list | Emergency response stage, from the vocabulary: `immediate`, `stage_1` to `stage_4`, separated by `; `. Blank for monitoring documents, or not set yet. | Manually (proposed by `archive discover`) |
| `period` | vocabulary | Monitoring period: `ltm_p1` to `ltm_p7`, `edwm_q1` to `edwm_q4`, `pem`. Blank for emergency response documents, or not set yet. | Manually (proposed by `archive discover`) |
| `size_listed` | text | File size as the library lists it. | Manually (proposed by `archive discover`) |
| `sdg` | text | Lab job or sample delivery group number, normalized (for example `810-12077-2`). For DOH files, the lab report number. | Manually (proposed by `archive discover`) |
| `package_or_validation_level` | text | For lab reports, the data package level (`Level 2`, `Level 3`, `Level 4`). For validation files, the validation stage (`S2AVEM`, `S4VEM`, `Stage 2A`). | Manually (proposed by `archive discover`) |
| `revision` | text | Revision as labeled (`Revision 1`), or `duplicate upload (2)` for files the library lists twice. | Manually |
| `duplicate_of` | doc_id | Filled when this file is byte-identical to another registered file (same SHA-256). Points to the copy to use. **Tools must skip rows with this filled**, so each file is processed once; the duplicate stays archived as evidence of what was posted. Blank if not a duplicate. | Manually |
| `priority` | vocabulary | `core` (evidence chain and governing documents), `supporting` (communications, fact sheets, maps), `context` (background such as transcripts). | Manually |
| `in_team_folder` | `yes` / `no` | Whether the team's existing I1 folder should already have it, for cross-checking. | Manually |
| `status` | vocabulary | `to_find` (no URL yet), `to_download` (file), `to_capture` (web page), `link_only` (cataloged and linked, not downloaded: LTM, EDWM and post-EDWM documents), `done`, `unavailable`, `excluded` (found but out of scope; the reason goes in `notes`). | Manually (`to_find`, `to_download`, `to_capture`, `unavailable`, `excluded`); `archive discover` proposes `link_only`; `archive download` sets `done` |
| `retrieved_utc` | datetime | When the file was downloaded or captured. Blank if not collected yet. | `archive download`; manually for the 12 manually captured web pages |
| `sha256` | text | The file's SHA-256 fingerprint. Proves the archived file hasn't changed. When `local_path` lists several files, one fingerprint per file, separated by `; `, in the same order. Blank if not collected yet. | `archive download`; `archive fingerprint` for files saved another way, such as the 12 manually captured web pages |
| `local_path` | text | Path inside the Shared Drive, for example `raw/jbphh-safewaters/pub_002925.pdf`. When one item has several files (a web page saved as PDF and HTML, or a listing split across pages), paths are separated by `; `. Blank if not collected yet. | `archive download`; manually for the 12 manually captured web pages |
| `notes` | text | Known issues, context, and anything still to verify. | Manually |
| `found_via` | vocabulary | How the document was found: `zone_page`, `navy_listing`, `doh_listing`, `ltm_listing`, `edwm_listing`, `cited`, `other_site`. Blank for rows built before `archive discover`. | `archive discover`, written by `archive merge`; manually for `cited` |
| `found_on` | URL or doc_id | The page where it was found, or for `cited`, the `doc_id` of the document that cites it. Blank for rows built before `archive discover`. | `archive discover`, written by `archive merge`; manually for `cited` |
| `first_seen_utc` | datetime | When `archive discover` first saw it on the source. Blank if never seen by `archive discover`. | `archive discover`, written by `archive merge` |
| `last_seen_utc` | datetime | The last time `archive discover` saw it on the source. If this stops updating, the site removed the document. Blank if never seen by `archive discover`. | `archive discover`, written by `archive merge` |

## document_links.csv

One row per link between two documents. Each row reads as a sentence: `doc_id`, `relation`,
`related_doc_id` ("DOC-0052 same_results DOC-0053", "DOC-0082 supports DOC-0053"). The ID
columns are `doc_id` and `related_doc_id` together.

**Which lab report data processing reads:** for each batch (SDG), the lowest package level
confirmed to hold the same results as the higher ones: the `doc_id` of a `same_results` row.
Point researchers to the higher level for the raw instrument data (such as chromatograms and
calibrations). Two levels are never assumed to hold the same results; each pair is compared
first. A report that another report supersedes is not read.

**Source:** made by A. Ceria for Zone I1's lab reports, manually, by comparing each batch's
reports. Each row's `notes` says how and when it was checked.

**Who writes it:** people, manually. **Updates:** add a row only after the link is checked. If a
link turns out wrong, fix the row and keep the old value in `notes`, dated.

| Column | Format | Description | Filled by |
|---|---|---|---|
| `doc_id` | doc_id | The document the sentence starts with. For `same_results`, the lower package level; for `supersedes`, the newer revision. A row in `documents.csv` whose `duplicate_of` is blank. | Manually |
| `related_doc_id` | doc_id | The document the sentence ends with. Another row in `documents.csv` whose `duplicate_of` is blank. | Manually |
| `relation` | vocabulary | `same_results` (two package levels of one batch, such as Level 2 and Level 4, whose results were compared and match), `supersedes` (a newer revision replaces an older one), `corrects` (fixes an error in the other), `supports` (backs it up, such as a validation report for a lab report), `summarizes` (sums up its results), `part_of` (is one piece of the other). | Manually |
| `notes` | text | How the link was checked, dated (for example "2026-11-24: cover pages compared; results on pages 3–8 match."). Never blank. | Manually |

## zones.csv

One row per zone: the 19 flushing zones plus J1 (Manana Housing). Says where each zone's
documents are listed on the Safe Waters site. Event dates, such as a zone's amendment date,
go in `timeline.csv`, not here. Made from the Safe Waters site's Water System Zone Map and the
20 zone pages, checked 2026-11-17.

The ID column is `zone_id`. **Who writes it:** people, manually. **Updates:** when the site's
zone map or a zone page changes, edit the row and date the change in `notes`.

| Column | Format | Description | Filled by |
|---|---|---|---|
| `zone_id` | `I1` | Zone ID as the site writes it. | Manually |
| `name` | text | Area names as the site's Water System Zone Map shows them. | Manually |
| `emergency_response` | `yes` / `no` | Whether the zone has emergency response documents. Only J1 is `no`. | Manually |
| `zone_page_url` | URL | The zone's page, as linked from the Water System Zone Map. | Manually |
| `page_last_updated` | date | The zone page's "Last Updated" date, as `YYYY-MM-DD`. | Manually |
| `navy_listing_url`, `doh_listing_url`, `ltm_listing_url` | URL | The zone's Navy, DOH and LTM library listings. Blank when the zone has none. | Manually |
| `notes` | text | Known issues, with the date they were checked. Blank means no known issues. | Manually |

## communities.csv

One row per community in a zone, as the zone page lists it under "Communities". A community in
several zones (such as Aliamanu Military Reservation) has one row per zone. The ID columns are
`zone_id` and `community` together. Copied from the 20 live zone pages on 2026-11-17 by a
one-time script; no `archive` command writes it yet.

**Who writes it:** people, manually. **Updates:** when a zone page's communities or counts
change, edit its rows and that zone's `page_last_updated` in `zones.csv`.

| Column | Format | Description | Filled by |
|---|---|---|---|
| `zone_id` | `I1` | The zone, from `zones.csv`. | Manually |
| `community` | text | Community name as the zone page writes it. Each name is also in that zone's `name` in `zones.csv`. | Manually |
| `homes` | whole number | Homes the zone page gives for this community; the count sits next to its community's name. Blank when the page gives no count (never `0`). | Manually |
| `notes` | text | Known issues. "No home count on the zone page." when `homes` is blank. | Manually |

The other registry tables (`wayback_captures.csv`, `wayback_page_history.csv`) stay in the
Drive's `registry/` until `archive wayback` is built, and are described in its `README.md`.
