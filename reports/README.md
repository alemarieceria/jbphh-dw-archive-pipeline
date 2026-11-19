# Reports

Dated files written by the archive's checks. Each run writes a new file named with that day's
date (UTC for `archive discover`). Running a check again on the same day rewrites that day's file.

## Inventory report: `<date>-inventory-<zone>.csv`

Written by `archive inventory --zone <zone>`. One row per result on the zone's Navy and DOH
listings, plus one row per catalog row a listing should show but doesn't.

| Column | Description |
|---|---|
| `listing` | `navy` or `doh`. |
| `library_id`, `title`, `filename` | The result as the listing shows it. |
| `doc_id`, `catalog_status` | The matching catalog row. Blank if there is none. |
| `result` | `matched`; `not_in_catalog` (listed, no catalog row); `not_on_listing` (catalog row, not listed); `no_listing` (`zones.csv` has no link); `listing_unavailable` (still "Application Error" after 3 tries). |

## Discover review file: `<UTC date>-discover-<zone>.csv`

Written by `archive discover --zone <zone>`. It proposes catalog rows and never changes the
catalog. You can look at it in Google Sheets or Excel, but make your edits in VS Code: a
spreadsheet program can rewrite dates when it saves (Excel turns `2022-04-26` into
`4/26/2022`). If that happens, `archive merge` stops and names the rows. Fill in only
`decision`, and correct a proposed value if it's wrong. `archive merge` reads only those and
refuses to run if the catalog changed since the file was made.

**Rows**, in this order:

| `row_type` | One row per | What it shows |
|---|---|---|
| `run` | run | When it ran (`last_seen_utc`) and the catalog's fingerprint (`catalog_sha256`) |
| `zone_page` | zone page (all 20) | The page's "Last Updated" (`page_last_updated`); flagged if it differs from `zones.csv` |
| `source` | source: the zone page, then the Navy, DOH and LTM listings | How many documents it shows (`count`) and one `decision` for all its unflagged rows. Its document rows follow it. |
| `document` | document seen, or expected but not seen | Its `result` and proposed values |

**How to review**

1. On each `source` row, check that `count` matches what the site shows, then write `accept`
   in its `decision`. That covers every unflagged row below it.
2. On each row with a `flag`, read the flag and write `accept` or `reject` in its own `decision`.
3. A blank `decision` means not decided yet.
4. Run `uv run archive merge reports/<file>` to see what would change. If it looks right, run
   it again with `--apply`, commit `catalog/documents.csv`, and run `archive publish`.

For a `new` row, `accept` adds it to the catalog with the next `doc_id`, and `reject` leaves it
out. For a `matched` row, `accept` fills its discovery columns (`found_via`, `found_on`,
`first_seen_utc`) and `stage` if they're blank, and updates `last_seen_utc`. For a `changed`
row, `accept` also takes the site's new value and keeps the old one in `notes`, dated; for
`zones`, the site's zones are added to the catalog's. For a `missing` row, `accept` adds a
dated note; rows are never deleted. A `decision` filled in on an unflagged row overrides its
source row's.

**Columns**

| Column | Description |
|---|---|
| `row_type` | `run`, `zone_page`, `source` or `document` (see above). |
| `source` | Where the row was found: `zone_page`, `navy_listing`, `doh_listing` or `ltm_listing`. |
| `result` | Documents: `matched` (in the catalog, as the site shows it), `changed` (in the catalog, but the site shows something different), `new`, `missing` (in the catalog, but not on a source that should show it). Sources: `read`, `unavailable` (still "Application Error" after 3 tries), `no_listing` (`zones.csv` has no link). |
| `flag` | Why the row needs its own decision: a link outside the page's sections, a `changed` value (with the catalog's value), a `missing` row, a stage or period the link text and its bold line disagree on, or an SDG ending in a zone ID. Blank when the source row's decision covers it. |
| `decision` | `accept` or `reject`, filled by the reviewer. |
| `count` | Source rows only: how many documents the source shows. |
| `section` | The bold line on the zone page above the link ("Quarter 2 - Samples Collected …"). Blank for listing results. |
| `link_text` | The link or listing result text, as the site shows it. |
| `doc_id` | The catalog row, for `matched`, `changed` and `missing` rows. Blank for `new` rows; `archive merge` assigns one. |
| `group` to `period`, `status` | Proposed values, with the same names and vocabulary as `catalog/documents.csv` (see `catalog/README.md`). A `new` row gets every value discover can propose. An existing row shows what the site shows (`title_as_posted`, `source_url`, `original_filename`, `library_id`, `date_as_listed`, `size_listed`, `zones`) and, where the catalog's `stage` is blank, the proposed `stage`. Its other values stay the catalog's. |
| `found_via`, `found_on`, `first_seen_utc`, `last_seen_utc` | The discovery columns, as `catalog/README.md` describes them. An existing row keeps the catalog's value where it has one. |
| `page_last_updated` | Zone page rows only: the page's "Last Updated", as `YYYY-MM-DD`. |
| `catalog_sha256` | Run row only: the fingerprint of `catalog/documents.csv` when the file was made. |
