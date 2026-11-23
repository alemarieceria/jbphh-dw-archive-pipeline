# Pipeline plan

The one place to see what this pipeline is for, how it is organized, and what is done.
Written by A. Ceria. Update a stage's **Status** line whenever its work changes.

Last updated: 2026-11-23.

## Goal

Archive every public document from the **emergency response phase (Nov 2021 – Mar 2022)**
of the JBPHH drinking water flushing zones, in a way anyone can rerun and check:

- every document is found, downloaded once, fingerprinted, and recorded in the catalog
- anyone can prove a zone is complete by running one check
- the Evidence Tracer and researchers find documents through the catalog

## Decisions

| Topic | Decision | Why |
| --- | --- | --- |
| Scope | Emergency response documents are downloaded. LTM, EDWM and post-EDWM documents are cataloged as `link_only` (not downloaded) so the apps can point to them. 19 flushing zones: A1, A2, A3, B1, C1, C2, C3, D1, D2, D3, D4, E1, F1, F2, G1, H1, H2, H3, I1. Zone I1 first. In the `zones` column, `all` means the 19 flushing zones plus J1 (Manana Housing). | The funder's focus is the emergency response, but the apps must still point users to later phases. DOH amended the advisory for "all 19 zones and Manana Housing" (Mar 18, 2022), so `all` includes J1, even though J1's zone page has no emergency response section. J1 has no emergency response documents; its EDWM and post-EDWM documents are cataloged as `link_only`. |
| Files (PDFs, page captures) | Google Shared Drive, organized by website | The team can open them without tools. A document can belong to several zones, so zones are a catalog column, not folders. |
| Catalog (records about files) | CSV files in this repo (`catalog/`), published read-only to the Drive's `registry/` | Every change has a history and a reviewable diff; no synced-drive write problems; readable in any text editor. |
| Discrepancy log | CSV in this repo (`catalog/discrepancies.csv`); teammates submit findings through a Google Form; `archive findings import` turns responses into proposed rows for review | History and review, without teammates needing Git. |
| Database | None for the archive. The Evidence Tracer gets its own Neon database later and loads the published catalog into it. | The catalog is small and changed by one process; a database would add upkeep without solving a current problem. |
| Code | One Python package with one command: `uv run archive <step> --zone I1` | Easier to learn than many scripts; `uv run archive --help` lists every step. |
| Tools | Python + uv, httpx (downloads), Playwright (diagrams; page captures later), pytest + ruff, GitHub with automated checks, Excalidraw stepped diagrams | All in use. |
| Wayback backups | Automated: `archive wayback` checks for an existing backup and, if none, saves the page with archive.org's Save Page Now service (free archive.org account; keys in `.env`). Results go in `catalog/wayback.csv`. | Every source page gets an independent public copy without manual work. |
| Viewing sources | `archive publish` writes `derived/zone-index/<zone>.csv`: every document for a zone, with its link, Wayback link and captures. A notebook only if capture previews are needed. | Opens in Drive or Excel without Python. |
| Tests | Every step ships with unit tests that run offline on saved pages. Archive checks (`inventory`, `verify`) run against the real Drive and website and write dated reports. A step is done only when both pass. | Accuracy must be provable, not assumed. |

## The workflow

Steps 4 to 7 are the loop run for each zone. Steps 3, 8 and 9 are shared by all zones.
Each step gets a section, with a stepped diagram, in `notebooks/workflows.ipynb`.

| Step | What it answers | Status |
| --- | --- | --- |
| 1. How to read the notebook | How to view and run the documentation | Done: the notebook's first section explains how to view and run it |
| 2. The big picture | How the steps fit together | Partial: `archive-big-picture` maps how the pieces connect today; `archive-pipeline` (planned) shows how the archive will run, step by step. Both stay. The big picture is redrawn as the map of every component once we know whether the results database belongs on it. |
| 3. Scope | Which zones, which dates, zone versus system-wide documents | Done: decided above; `catalog/zones.csv` lists the 20 zones with their zone page and library listing links |
| 4. Discovery | Which documents exist for a zone, and how do we know we have them all? | Partial: `archive discover --zone I1` reads the zone pages and I1's Navy, DOH and LTM listings and proposes rows in a review file; `archive inventory --zone I1` checks the Navy and DOH listings (see below). Not yet: the EDWM listing and other zones. |
| 5. Cataloging | Turning found documents into reviewed catalog rows | Partial: I1's first 169 rows were built manually; `archive merge` added 180 more; `archive discover` proposes rows in a review file and `archive merge` applies the accepted ones. `archive validate` checks the catalog on every push. |
| 6. Collection | Downloading files, capturing web pages, Wayback backups | Partial: downloads automated; page captures and Wayback done manually |
| 7. Validation | Is the archive complete and unchanged? | Partial: `archive inventory` checks a zone's Navy and DOH listings against the catalog; `archive validate` checks that the catalog follows its rules; no `archive verify` yet |
| 8. Storage | What lives where, publishing, backups, permissions | Partial: the catalog is in this repo (`catalog/documents.csv`); `archive publish` copies it to the Drive's `registry/`; no zone indexes yet |
| 9. Keeping it current | Documents added to or removed from the website later | Not started |
| 10. Use | Evidence Tracer, researchers, discrepancy log | Partial: the Tracer reads the catalog; log exists on the Drive |
| 11. Archiving a zone, start to finish | Every command in order, and the "done" checklist | Not started |

### 4. Discovery

- **Sources:** every section of each zone page (emergency response, LTM, EDWM, PEM), the Navy and DoH library listings (`.../searchresults.aspx?dsn=pub&category=JBPHH&subcategory=<Navy or DoH>%20Flushing%20Zone%20<zone>`), the LTM and EDWM libraries, the Document Library page and its 2022 Public Notices page, and files linked from other sites.
- **Listings:** sort by System Filename and show 100 per page. The default sort skips and repeats files between pages. Plain HTTP works; no browser needed.
- **Cited documents** (plans, DOH directives) are found by reading other documents. Each catalog row records where it was found, so it can be checked even though it cannot be counted.
- **Phase rule:** phase comes from the document's stage label (Immediate, Stage 2 and Stage 4 are emergency response). The Nov 20, 2021 – Mar 31, 2022 window only flags mismatches. Event dates, such as each zone's amendment date, go in `catalog/timeline.csv`, not `zones.csv`.
- **Shared documents** are archived once and list every zone they belong to.
- **Known facts (2026-11-17, from `archive inventory --zone I1`):** the Navy I1 listing shows 109 documents and the DoH I1 listing 14. All 123 library IDs match `done` catalog rows, one by one. Each result's library ID is in its link (`aFile2925` = `pub_002925.pdf`).

**`archive discover --zone <zone>` (built 2026-11-17)**
- **Reads:** all 20 zone pages, so each document lists every zone that posts it; then every
  section of the chosen zone's page, and its Navy, DOH and LTM listings. A listing link is
  matched by its `subcategory`, because the zone page wraps listing links in a frame link.
  The EDWM listing and the Document Library cover all zones, so a later all-zone pass reads
  them. The Document Library's Aiea-Halawa Shaft items get `status` `excluded`, because
  they're about a different water source. Cited documents and files on other sites stay
  manual (`found_via` = `cited` or `other_site`).
- **Proposes values** from the section and link text: "Immediate", "Stage 2" and "Stage 4"
  are emergency response; "Stage 5" and "Period 1" to "Period 7" are LTM (`ltm_p1` to
  `ltm_p7`); "Quarter 1" to "Quarter 4" are EDWM (`edwm_q1` to `edwm_q4`). A file posted on
  several zone pages gets one row listing every zone that posts it.
- **Values from titles:** for new library rows, `doc_type`, `sdg` and
  `package_or_validation_level` come from titles that follow a known pattern ("Laboratory
  Report, SDG DA22131, Level 4"); other titles leave them blank. Zone page links get
  `doc_type` from their text ("Data Summary" is `summary_report`, "Sampling Results" is
  `results_crosstab`, a listing link is `library_listing`).
- **Writes only a review file,** `reports/<UTC date>-discover-<zone>.csv`, never the catalog.
  Each document is `matched`, `new`, `changed` or `missing`. Each listing has one summary row
  whose `decision` covers all its rows; flagged rows get their own `decision`. Links outside
  the page's sections (such as the interactive map) are flagged.
- **Zones:** a document is flagged when the site posts it on a zone its `zones` doesn't
  cover. A zone in `zones` whose page doesn't post it is not flagged, because `zones` lists
  the zones a document covers.
- **Existing rows:** the first run fills `found_via`, `found_on` and `first_seen_utc` once for
  each row it matches. After that, only `last_seen_utc` changes.
- **`archive merge` (built 2026-11-18)** applies the approved decisions: a dry run first, then `--apply`. It
  assigns `doc_id`s, and it refuses to run if the catalog changed since the review file was
  made.
- **New `group` values**, added to `catalog/README.md` with the first rows that use them:
  `zone_page_ltm` and `zone_page_edwm` (links in those sections of a zone page, including its
  listing link), `zone_page_pem`, `ltm_lab_collection` (LTM listing results) and
  `source_water` (Waiawa Shaft files, posted on every zone page). `edwm_lab_collection`
  joins with the all-zone pass.
- **I1 check (2026-11-17):** the first run (`reports/2026-11-17-discover-I1.csv`) matches the
  count: 132 rows matched (9 from the zone page, 109 Navy, 14
  DOH); 37 expected gaps (cited documents and other sites); 179 new `link_only` proposals
  (14 LTM, 5 EDWM and 5 Waiawa Shaft links on the zone page, and 155 LTM listing results).
  Each run recounts from the live site.

### 5–7. Status details

- **Catalog:** 349 rows for I1. The first 169 were built manually: 161 collected (149 files
  downloaded, 12 web pages captured manually), 8 still to find (6 governing documents, 2 Navy
  communications), deferred until after data processing; none holds results data. DOC-0170 to
  DOC-0349 are monitoring documents cataloged as `link_only` by `archive merge`.
- **Discrepancy log:** 21 findings (FND-0001 to FND-0021); 9 confirmed, 12 to verify.
- **Page captures** to automate with Playwright: PDF, single-file web page (MHTML) and PNG per page.
  `archive capture` takes over the 12 pages captured manually and records a fingerprint for
  every capture, including the existing ones.
- **Wayback:** automated (see Decisions). The archive.org account and keys are set up; the
  step isn't built yet.

### 10. The Evidence Tracer connection

The Tracer (separate repo) reads `ARCHIVE_ROOT/registry/documents.csv`. It relies on the
catalog's column names, doc_ids that never change, fingerprints, and the `duplicate_of`
rule. Changing any of these means updating the Tracer in the same round of work. Adding a
zone should need no Tracer code changes.

## Catalog design (decided 2026-11-10)

**Vocabulary.** One value per idea, whatever the source calls it:
- `phase`: emergency_response, ltm, edwm, post_edwm; `monitoring` for an item that covers
  more than one monitoring phase (such as the Drinking Water Monitoring Dashboard)
- `stage` (emergency response only): immediate, stage_1 to stage_4. The Drinking Water
  Sampling Plan (Addendum 3) calls these "Steps": Step 1 to Step 4 are stage_1 to stage_4,
  and Steps 2a to 2d are all stage_2. Its Step 0 (shaft samples) has no stage, and Step 5 is
  the ltm phase.
- `period` (monitoring only): ltm_p1 to ltm_p7, edwm_q1 to edwm_q4, pem
Values come from the site's link text and section, then the file name, then the
document's title page. Disagreements are flagged, never picked silently. The Recovery
Plan's own stage names mean something else and are not used; "phase" is never used
for its zone groups.

**Data dictionary.** Every catalog file gets a section in `catalog/README.md` before its
first commit. The section says:
- for the file: what one row is and its ID column; where the data came from (source,
  method, and the date it was made or checked); who or what writes it; how it is updated
- for each column: its name and format; allowed values; what it means, including what a
  blank means; who fills it (a command or a person)

**New columns in documents.csv**
- `sample_start`, `sample_end`: computed from extracted sample data, never typed
- `stage`, `period`: from the vocabulary
- `publisher`: Directory org ID of the issuing organization. Use the most specific
  one that exists, else its parent, flagged. (`idwst` must be added to the Directory.)
  `producer` stays the lab or contractor.
- `found_via`, `found_on`, `first_seen_utc`, `last_seen_utc`: discovery bookkeeping;
  `last_seen_utc` going stale means the site removed the document
- `status` adds `link_only` and `excluded`

**Multi-value cells** (`zones`, `stage`) use `; `. One function parses them, and
validation rejects unknown values, duplicates and wrong separators.

**document_links.csv:** `doc_id`, `related_doc_id`, `relation`, `notes`. Each row reads as a
sentence, "doc_id relation related_doc_id". Relations: same_results, supersedes, corrects,
supports, summarizes, part_of. `same_results` is recorded only after two package levels of
one batch were compared and match; data processing reads the lowest level confirmed to hold
the same results. `notes` says how each link was checked.

**timeline.csv:** one row per dated event, each citing the doc_ids that state it.
`basis` ranks trust: sample_data > stated > announced. Advisory events use DOH's
wording (amended, lifted).

**Who writes what**
- Discovery: website facts, only when a row is created; afterwards only `last_seen_utc`.
  Differences go to a report.
- Discovery proposes, you decide: group, doc_type, producer, publisher, phase, stage,
  period, zones, sdg, package_or_validation_level. You review by listing: one decision
  per library listing (accept all its rows once its count matches), and flagged rows
  one by one.
- Download and verify: retrieved_utc, sha256, local_path, `status` → done
- Extraction: sample dates
- People only: priority, in_team_folder, duplicate_of, revision, notes, and the statuses
  to_find, unavailable, excluded
- `doc_id` is assigned on approval and never reused. Rows are never deleted.

Review files can be read in Google Sheets or Excel but are edited only in VS Code, because a
spreadsheet program can rewrite dates when it saves. Merge reads only the decision and
editable columns, checks the rows it adds or changes against the catalog rules, and refuses
to run if the catalog changed since the proposal.

**Not in the catalog:** sample types and methods describe single samples, so they live
in `derived/`.

**GitHub Actions:** tests, ruff and `archive validate` on every push; a weekly inventory of the live site as a dated report. Downloads and
fingerprint checks run locally against the Drive.

## Target structure

```
jbphh-dw-archive-pipeline/
├── catalog/            master records: documents, document_links, timeline, zones, communities,
│                       wayback, discrepancies (+ README)
├── reports/            dated inventory, discover and verify reports (+ README)
├── src/jbphh_archive/  cli, config, catalog, discover, inventory, download, capture,
│                       wayback, verify, publish, findings, diagrams/
├── tests/              unit tests, with fixtures/ (saved pages, small catalogs)
├── notebooks/          workflows.ipynb, zones.ipynb
└── docs/               this plan, diagrams/ (specs, svgs, pngs, embeds, screenshots)

Shared Drive: raw/, web-captures/, registry/ (published, read-only), reports/ (published),
derived/ (including derived/zone-index/)
```

## Order of work

Each item is done only when it has: unit tests that run offline; a real-world check with a
dated report, where one applies; a `catalog/README.md` section for any new catalog file or
column; and a stepped diagram in `notebooks/workflows.ipynb`. The other catalog files join
`catalog/` when the step that uses them is built.

**Finishing I1 (decided 2026-11-23).** Archiving I1 is done when these four steps are done;
then data processing starts. (1) The 8 documents still to find get a dated note saying they
are deferred. (2) `catalog/document_links.csv` records which lab file is current for each
batch (SDG). (3) Fingerprints for the 12 manually captured web pages; then
`archive verify --zone I1`. (4) Publish, and update this plan. Deferred until later:
`archive capture` (new dated PDF, MHTML and PNG captures), `archive wayback`, `stage` on the
40 non-lab rows, `publisher`, `timeline.csv`, the zone indexes, and the Drive's text about
captures.

1. **Restructure** (done): this repo into `src/jbphh_archive/` with one `archive` command;
   `scripts/` code moved in, with tests proving nothing changed.
2. **Big picture** (partial): keep `archive-big-picture` and `archive-pipeline` (the
   step-by-step view), and the step outline in `notebooks/workflows.ipynb`. Redraw the big
   picture as the map of every component once we know whether the results database
   belongs on it.
3. **Catalog, scope and inventory for I1** (done): `documents.csv` moved
   into `catalog/` and published to the Drive's `registry/`; `catalog/zones.csv`;
   `archive inventory --zone I1` matches all 123 Navy and DOH listing results to the catalog.
4. **Automated checks** (done): GitHub Actions runs the tests, ruff and `archive validate` on every
   push.
5. **Cataloging** (done): first add the new columns and statuses from "Catalog design"
   (`idwst` goes into the Directory first). Then `archive discover --zone I1` proposes rows,
   including LTM and EDWM documents as `link_only`; it should reproduce I1's existing rows.
   Catalog validation joins the automated checks. Done: the new columns and statuses,
   `archive discover --zone I1`, `archive merge`, and `archive validate`, which GitHub runs
   on every push.
6. **Collection:** `archive capture`, then `archive wayback` (building on the manual Wayback
   records in the Drive's `registry/`), then the sources view in `notebooks/zones.ipynb`.
   Update the Drive's `web-captures/README.txt`.
7. **Validation and storage:** `archive verify`; `archive publish` adds the zone indexes.
8. **Team and discrepancy workflow:** add the team to the Shared Drive as Viewers
   (downloading allowed); the Google Form and `archive findings import`; update the Drive's
   `START-HERE.md`.
9. **Pilot a second zone**, writing step 11's start-to-finish checklist along the way; then
   the remaining zones, following it.
10. **Keeping it current:** a weekly automated inventory of the live site, as a dated
    report; a stale `last_seen_utc` shows a document the site removed.
