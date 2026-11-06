# Pipeline plan

The one place to see what this pipeline is for, how it is organized, and what is done.
Written by A. Ceria. Update a stage's **Status** line whenever its work changes.

Last updated: 2026-11-05.

## Goal

Archive every public document from the **emergency response phase (Nov 2021 – Mar 2022)**
of the JBPHH drinking water flushing zones, in a way anyone can rerun and check:

- every document is found, downloaded once, fingerprinted, and recorded in the catalog
- anyone can prove a zone is complete by running one check
- the Evidence Tracer and researchers find documents through the catalog

## Decisions

| Topic | Decision | Why |
| --- | --- | --- |
| Scope | Emergency response phase only. 19 zones: A1, A2, A3, B1, C1, C2, C3, D1, D2, D3, D4, E1, F1, F2, G1, H1, H2, H3, I1. Zone I1 first. | J1 is left out: it was added later, during the EDWM phase, and has no emergency response documents. |
| Files (PDFs, page captures) | Google Shared Drive, organized by website | The team can open them without tools. A document can belong to several zones, so zones are a catalog column, not folders. |
| Catalog (records about files) | CSV files in this repo (`catalog/`), published read-only to the Drive's `registry/` | Every change has a history and a reviewable diff; no synced-drive write problems; readable in any text editor. |
| Discrepancy log | CSV in this repo (`catalog/discrepancies.csv`); teammates submit findings through a Google Form; `archive findings import` turns responses into proposed rows for review | History and review, without teammates needing Git. |
| Database | None for the archive. The Evidence Tracer gets its own Neon database later and loads the published catalog into it. | The catalog is small and changed by one process; a database would add upkeep without solving a current problem. |
| Code | One Python package with one command: `uv run archive <step> --zone I1` | Easier to learn than many scripts; `uv run archive --help` lists every step. |
| Tools | Python + uv, httpx (downloads), Playwright (listings, page captures, diagrams), pytest + ruff, GitHub with automatic checks, Excalidraw stepped diagrams | All already in use. |
| Wayback backups | Automatic: `archive wayback` checks for an existing backup and, if none, saves the page with archive.org's Save Page Now service (free archive.org account; keys in `.env`). Results go in `catalog/wayback.csv`. | Every source page gets an independent public copy without hand work. |
| Viewing sources | `notebooks/zones.ipynb` shows, per zone, each source page with its Wayback link and its captures, read from the catalog. `archive publish` reruns it so its saved output is never stale and can be read on GitHub without running anything. | People who don't run code can still see every link and capture. |
| Tests | Every step ships with unit tests that run offline on saved pages. Archive checks (`inventory`, `verify`) run against the real Drive and website and write dated reports. A step is done only when both pass. | Accuracy must be provable, not assumed. |

## The workflow

Steps 4 to 7 are the loop run for each zone. Steps 3, 8 and 9 are shared by all zones.
Each step gets a section, with a stepped diagram, in `notebooks/workflows.ipynb`.

| Step | What it answers | Status |
| --- | --- | --- |
| 1. How to read the notebook | How to view and run the documentation | Not started |
| 2. The big picture | How the steps fit together | Partial: `archive-big-picture` diagram exists but needs redrawing to match this plan |
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

- **Sources per zone:** the library's Navy and DoH listings (`.../searchresults.aspx?dsn=pub&category=JBPHH&subcategory=<Navy or DoH>%20Flushing%20Zone%20<zone>`), and the zone page's emergency response section.
- **Cited documents** (plans, DOH directives) are found by reading other documents. Each catalog row records where it was found, so it can be checked even though it cannot be counted.
- **Phase rule:** a document is in scope if it is dated within the zone's emergency response period. Each zone's dates go in `catalog/zones.csv` (each zone's response ended on a different date).
- **Shared documents** are archived once and list every zone they belong to.
- **Known facts (2026-11-05):** the Navy I1 listing shows 109 documents, and all 109 library IDs match catalog rows and are downloaded. The DoH I1 listing shows 14, and the catalog has 14 rows (IDs not yet checked one by one). Paging needs a browser (the address does not change between pages). Each result's library ID is in its link (`aFile2925` = `pub_002925.pdf`).

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

## Target structure

```
jbphh-dw-archive-pipeline/
├── catalog/            master records: documents, zones, wayback, discrepancies (+ README)
├── reports/            dated inventory and verify reports
├── src/jbphh_archive/  cli, config, catalog, discover, inventory, download, capture,
│                       wayback, verify, publish, findings, diagrams/
├── tests/              unit tests, with fixtures/ (saved pages, small catalogs)
├── notebooks/          workflows.ipynb, zones.ipynb
└── docs/               this plan, diagrams/ (specs, screenshots)

Shared Drive: raw/, web-captures/, registry/ (published, read-only), reports/ (published),
docs/diagrams/, derived/
```

## Order of work

1. **Restructure** this repo into `src/jbphh_archive/` with one `archive` command; move
   `scripts/` code in, with tests proving nothing changed.
2. **Big picture:** redraw it to match this plan; set up `notebooks/workflows.ipynb` with
   the step outline above.
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
