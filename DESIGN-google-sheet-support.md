# Design: Google Sheet Support for Fixture Parsing

## Background

The bowls.org.hk fixtures page has begun migrating some competition fixtures
from PDF files to Google Sheets. As of April 2026, the affected competitions
are:

| Competition              | Old Format | New Format     |
|--------------------------|------------|----------------|
| Men's National Singles   | PDF        | Google Sheet   |
| Women's National Singles | PDF        | Google Sheet   |
| All other competitions   | PDF        | PDF (unchanged)|

The Google Sheets contain the same logical data as the PDFs — fixture tables
with rounds and a player list — but spread across multiple tabs instead of
multiple pages within a single PDF.

## Design Decisions

1. **Option B (no refactor):** The existing PDF parser (`parse_fixtures`) is
   left completely untouched.  A new `parse_fixtures_from_sheet()` function is
   added alongside it with its own self-contained logic.  This avoids any risk
   of regressing the working PDF flow.

2. **Content-based tab classification:** Tabs inside a Google Sheet are
   classified by inspecting their content, not their name — the same approach
   used for PDF pages:
   - Header row starting with **"Club"** → Player List table
   - Header row starting with **"Ref"**  → Fixture / Round table

3. **Game-format agnostic:** The sheet parser handles Singles, Pairs, Triples,
   and Fours by dynamically detecting the number of player columns between
   "Ref" and the first "Club" column, identical to the PDF parser.

4. **No new dependencies.** `requests` and `BeautifulSoup` are already used.

## Architecture

```
bowls.org.hk fixtures page
        │
        ├── PDF link  ──► download ──► pdfplumber ──► parse_fixtures()
        │                                                    │
        └── Sheet link ──► gviz API ──► BeautifulSoup ──► parse_fixtures_from_sheet()
                                                             │
                                              ┌──────────────┘
                                              ▼
                                    (same output format)
                                              │
                                              ▼
                                   build_tournament_tree()
                                              │
                                              ▼
                                     compressed JSON .gz
```

Both paths produce the identical data structures so that
`build_tournament_tree()` and all downstream logic are unchanged.

## Phases

### Phase 1 – Detect Google Sheet links (`ExtractLBA_Files.py`)

Add `sheets_by_category` alongside the existing `pdfs_by_category`.  When
scanning `<a>` tags in the fixtures table, also match hrefs containing
`docs.google.com/spreadsheets`.  Apply the same game-name filter.

### Phase 2 – Tab enumeration (`ExtractLBA_Files.py` / `fixture_parser.py`)

Given a Google Sheet URL:

1. Extract the spreadsheet ID from the URL.
2. Fetch the sheet's HTML page with `requests.get()`.
3. Parse tab names and `gid` values from the HTML source.
4. Return a list of `(tab_name, gid)` tuples.

### Phase 3 – Change detection for sheets (`ExtractLBA_Files.py`)

For each Google Sheet entry:

1. Fetch every tab's content via the `gviz/tq` endpoint.
2. Concatenate all content, compute an MD5 hash.
3. Compare against a stored hash file in `archive/` (e.g.
   `M-Nat-Singles.sheet_hash`).
4. If unchanged, skip.  If changed, proceed to parsing.
5. Use `datetime.now()` as the update date (no PDF ModDate available).

### Phase 4 – Sheet parser (`fixture_parser.py`)

New function `parse_fixtures_from_sheet(sheet_id)`:

1. Enumerate all tabs (Phase 2 logic).
2. For each tab, fetch data via `gviz/tq?tqx=out:html&gid=GID`.
3. Parse the HTML `<table>` into a list-of-rows using BeautifulSoup.
4. Classify by content:
   - First cell of header row is "Club" → player list; extract players, club,
     skip, home_green → append to global `teams`.
   - First cell of header row contains "Ref" → fixture table; dynamically find
     Club / Venue columns; extract round name + deadline from preceding rows;
     parse fixture rows → append to `fixtures`.
5. Return `fixtures` (same format as `parse_fixtures()`).

### Phase 5 – Update `main()` in `fixture_parser.py`

If argument 1 is a Google Sheet URL, extract the sheet ID and call
`parse_fixtures_from_sheet()`.  Otherwise, call the existing
`parse_fixtures()`.  Everything after (tournament tree, gzip export) is
unchanged.

### Phase 6 – Processing loop for sheets (`ExtractLBA_Files.py`)

After the existing PDF processing loop, iterate over `sheets_by_category`:

1. Run change detection.
2. If changed, call `fixture_parser.py` with the sheet URL + output `.gz` path.
3. Derive `base_name` from the link description (e.g. "National Singles" →
   `M-Nat-Singles` or `W-Nat-Singles`).
4. Add entry to `pdf_info` / `fixture_list.json`.
5. Copy output to `local_data`.

## Files Modified

| File                          | Changes                                    |
|-------------------------------|--------------------------------------------|
| `docker/ExtractLBA_Files.py`  | Sheet detection, tab enum, change detect, processing loop |
| `docker/fixture_parser.py`    | `parse_fixtures_from_sheet()`, `main()` routing |
| `ExtractLBA_Files.py` (root)  | Same as docker version                     |
| `fixture_parser.py` (root)    | Same as docker version                     |

## Unchanged

- `build_tournament_tree()` and all tree/path logic
- HTML / frontend files
- Docker infrastructure (`dockerfile`, `docker-compose.yml`)
- All PDF-based game processing
- Output format (compressed JSON `.gz`)
