# Pipeline plan

The one place to see what this pipeline is for, how it is organized, and what is done.
Written by A. Ceria. Update a stage's **Status** line whenever its work changes.

Last updated: 2026-11-16.

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
| Tools | Python + uv, httpx (downloads), Playwright (page captures, diagrams), pytest + ruff, GitHub with automatic checks, Excalidraw stepped diagrams | All already in use. |
| Wayback backups | Automatic: `archive wayback` checks for an existing backup and, if none, saves the page with archive.org's Save Page Now service (free archive.org account; keys in `.env`). Results go in `catalog/wayback.csv`. | Every source page gets an independent public copy without hand work. |
| Viewing sources | `archive publish` writes `derived/zone-index/<zone>.csv`: every document for a zone, with its link, Wayback link and captures. A notebook only if capture previews are needed. | Opens in Drive or Excel without Python. |
| Tests | Every step ships with unit tests that run offline on saved pages. Archive checks (`inventory`, `verify`) run against the real Drive and website and write dated reports. A step is done only when both pass. | Accuracy must be provable, not assumed. |

## The workflow

Steps 4 to 7 are the loop run for each zone. Steps 3, 8 and 9 are shared by all zones.
Each step gets a section, with a stepped diagram, in `notebooks/workflows.ipynb`.

| Step | What it answers | Status |
| --- | --- | --- |
| 1. How to read the notebook | How to view and run the documentation | Not started |
| 2. The big picture | How the steps fit together | Partial: `archive-big-picture` maps how the pieces connect today; `archive-pipeline` (planned) shows how the archive will run, step by step. Both stay; the big picture is redrawn when the catalog moves (item 6 of the order of work). |
| 3. Scope | Which zones, which dates, zone versus system-wide documents | Partial: decided above; `catalog/zones.csv` not yet made |
| 4. Discovery | Which documents exist for a zone, and how do we know we have them all? | Partial (see below) |
| 5. Cataloging | Turning found documents into reviewed catalog rows | Partial: I1's 169 rows were built by hand; no script |
| 6. Collection | Downloading files, capturing web pages, Wayback backups | Partial: downloads automated; page captures and Wayback by hand |
| 7. Validation | Is the archive complete and unchanged? | Partial: Navy I1 listing checked by hand; no scripts |
| 8. Storage | What lives where, publishing, backups, permissions | Partial: Drive in use; catalog not yet moved to this repo |
| 9. Keeping it current | Documents added to or removed from the website later | Not started |
| 10. Use | Evidence Tracer, researchers, discrepancy log | Partial: the Tracer reads the catalog; log exists on the Drive |
| 11. Archiving a zone, start to finish | Every command in order, and the "done" checklist | Not started |

### 4. Discovery

- **Sources:** every section of each zone page (emergency response, LTM, EDWM, PEM), the Navy and DoH library listings (`.../searchresults.aspx?dsn=pub&category=JBPHH&subcategory=<Navy or DoH>%20Flushing%20Zone%20<zone>`), the LTM and EDWM libraries, and files linked from other sites.
- **Listings:** sort by System Filename and show 100 per page. The default sort skips and repeats files between pages. Plain HTTP works; no browser needed.
- **Cited documents** (plans, DOH directives) are found by reading other documents. Each catalog row records where it was found, so it can be checked even though it cannot be counted.
- **Phase rule:** phase comes from the document's stage label (Immediate, Stage 2 and Stage 4 are emergency response). The Nov 20, 2021 – Mar 31, 2022 window only flags mismatches. Event dates, such as each zone's amendment date, go in `catalog/timeline.csv`, not `zones.csv`.
- **Shared documents** are archived once and list every zone they belong to.
- **Known facts (2026-11-05):** the Navy I1 listing shows 109 documents, and all 109 library IDs match catalog rows and are downloaded. The DoH I1 listing shows 14, and the catalog has 14 rows (IDs not yet checked one by one). Each result's library ID is in its link (`aFile2925` = `pub_002925.pdf`).

### 5–7. Status details

- **Catalog:** 169 rows for I1; 160 downloaded, 9 still to find (7 governing documents, 2 Navy communications).
- **Discrepancy log:** 18 findings (FND-0001 to FND-0018); 6 confirmed, 12 to verify.
- **Page captures** to automate with Playwright: PDF, single-file web page (MHTML) and PNG per page.
- **Wayback:** automatic (see Decisions). Needs an archive.org account before the step is built.

### 10. The Evidence Tracer connection

The Tracer (separate repo) reads `ARCHIVE_ROOT/registry/documents.csv`. It relies on the
catalog's column names, doc_ids that never change, fingerprints, and the `duplicate_of`
rule. Changing any of these means updating the Tracer in the same round of work. Adding a
zone should need no Tracer code changes.

## Catalog design (decided 2026-11-10)

**Vocabulary.** One value per idea, whatever the source calls it:
- `phase`: emergency_response, ltm, edwm, post_edwm
- `stage` (emergency response only): immediate, stage_1 to stage_4
- `period` (monitoring only): ltm_p1 to ltm_p7, edwm_q1 to edwm_q4, pem
Values come from the site's link text and section, then the file name, then the
document's title page. Disagreements are flagged, never picked silently. The Recovery
Plan's own stage names mean something else and are not used; "phase" is never used
for its zone groups.

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

**document_links.csv:** `doc_id`, `related_doc_id`, `relation`
(corrects, supports, summarizes, supersedes, part_of).

**timeline.csv:** one row per dated event, each citing the doc_ids that state it.
`basis` ranks trust: sample_data > stated > announced. Advisory events use DOH's
wording (amended, lifted).

**Who writes what**
- Discovery: website facts, only when a row is created; afterwards only `last_seen_utc`.
  Differences go to a report.
- Discovery proposes, you decide: group, doc_type, producer, publisher, phase, stage,
  period, zones, sdg, package_or_validation_level
- Download and verify: retrieved_utc, sha256, local_path, `status` → done
- Extraction: sample dates
- People only: priority, in_team_folder, duplicate_of, revision, notes, and the statuses
  to_find, unavailable, excluded
- `doc_id` is assigned on approval and never reused. Rows are never deleted.

Review files are safe to open in Google Sheets or Excel: merge reads only the decision
and editable columns, and refuses to run if the catalog changed since the proposal.

**Not in the catalog:** sample types and methods describe single samples, so they live
in `derived/`.

**GitHub Actions:** tests and ruff on every push; catalog validation on every catalog
change; a weekly inventory of the live site as a dated report. Downloads and
fingerprint checks run locally against the Drive.

## Target structure

```
jbphh-dw-archive-pipeline/
├── catalog/            master records: documents, document_links, timeline, zones, wayback,
│                       discrepancies (+ README)
├── reports/            dated inventory and verify reports
├── src/jbphh_archive/  cli, config, catalog, discover, inventory, download, capture,
│                       wayback, verify, publish, findings, diagrams/
├── tests/              unit tests, with fixtures/ (saved pages, small catalogs)
├── notebooks/          workflows.ipynb, zones.ipynb
└── docs/               this plan, diagrams/ (specs, svgs, pngs, embeds, screenshots)

Shared Drive: raw/, web-captures/, registry/ (published, read-only), reports/ (published),
derived/ (including derived/zone-index/)
```

## Order of work

1. **Restructure** this repo into `src/jbphh_archive/` with one `archive` command; move
   `scripts/` code in, with tests proving nothing changed.
2. **Big picture:** keep `archive-big-picture` as the map of every component and
   `archive-pipeline` as the step-by-step view; redraw the big picture when the catalog
   moves (item 6). Add the step outline above to `notebooks/workflows.ipynb`.
3. **Scope and Discovery for I1:** `catalog/zones.csv`, then `archive inventory --zone I1`
   (listings and zone page against the catalog), checked against the known I1 facts.
4. **Cataloging:** `archive discover --zone I1` proposes rows; it should reproduce I1's
   existing rows.
5. **Collection:** `archive capture`, then `archive wayback`, then the sources view in
   `notebooks/zones.ipynb`.
6. **Validation and storage:** `archive verify`; move the catalog into `catalog/`;
   `archive publish`.
7. **Discrepancy workflow:** the Google Form and `archive findings import`.
8. **Pilot a second zone**, then the rest.
