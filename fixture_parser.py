import pdfplumber
import re
from tabulate import tabulate
import sys
import os
import requests
from bs4 import BeautifulSoup

# Global list to store teams
teams = []
nodes = {}

def get_default_pdf_path():
    """Get the path to the default PDF in the same directory as the script"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_filename = "W_Nat_Triples_2025-1.pdf"
    default_filename = "M-Indoor-Pairs-2025-9.pdf"
    return os.path.join(script_dir, default_filename)

def extract_deadline(first_row):
    """Search all columns in the first row for deadline information"""
    if not first_row:
        return "TBC"

    deadline_pattern = re.compile(
        r'Completion.*:\s*(\d{1,2}\s+[A-Za-z]+,\s+\d{4})|^\s*(\d{1,2}\s+[A-Za-z]+,\s+\d{4})'
    )

    for cell in first_row:
        if not cell:
            continue
        match = re.search(deadline_pattern.pattern, cell, re.IGNORECASE)
        if match:
            # Return the first matched group that isn't None
            return next(g for g in match.groups() if g is not None)
    return "TBC"

def parse_fixtures(pdf_path):
    fixtures = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # tables = page.extract_tables({
            #     "vertical_strategy": "lines",
            #     "horizontal_strategy": "lines",
            #     "intersection_y_tolerance": 15,
            #     "intersection_x_tolerance": 15
            # })
            # Extract tables using "lines" strategy
            tables = page.extract_tables({
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "intersection_y_tolerance": 15,
                "intersection_x_tolerance": 15
            })

            # Detect if the last row is incomplete due to missing bottom border
            for idx, table in enumerate(tables):
                if str(table[0][0]).strip().lower() == "club":
                # This is the player table, check if last row is incomplete
                # if the last row has empty cells, we should try to parse the page's table with veritical_strategy and horizontal_strategy set to "text"
                    if any(
                        cell is None or 
                        str(cell).strip() == "" or 
                        '\n' in str(cell) or 
                        'page' in str(cell).lower()
                        for cell in table[-1]
                    ):
                        #remove the last row of the table if club column is empty. In Women's triples case, the last row is the total number of payers
                        if table[-1][0] is None or str(table[-1][0]).strip() == "":
                            table = table[:-1]
                            tables[idx] = table
                        # Re-extract the table with "text" strategy
                        alt_tables = page.extract_tables({
                            "vertical_strategy": "lines",
                            "horizontal_strategy": "text",
                            "snap_tolerance": 1,  # Increase tolerance for snapping text to grid
                            "join_tolerance": 5,  # Increase tolerance for joining nearby text
                            "intersection_y_tolerance": 0,
                            "intersection_x_tolerance": 15
                        })
                        # if the last row in alt_tables doesn't have empty cells, replace the original table's last row with it
                        if alt_tables:
                            alt_table = alt_tables[0]
                            # loop through the alt_table from bottom, assign the first non-empty row to table's last row
                            for r in range(len(alt_table)-1, -1, -1):
                                if all(cell is not None and str(cell).strip() != "" and '\n' not in str(cell) for cell in alt_table[r]):
                                    # Only replace the last row if the cell values are different
                                    if table[-1] != alt_table[r]:
                                        table[-1] = alt_table[r]
                                    break

            if not tables:
                continue

            for table in tables:

                # remove all the text in the table that are non-ascii characters
                # this is required because some PDFs have non-ascii characters that interfere with parsing e.g. \u2060 before the player names
                for r in range(len(table)): 
                    for c in range(len(table[r])):
                        if table[r][c]:
                            table[r][c] = re.sub(r'[^\x00-\x7F]', '', str(table[r][c]))

                if len(table) < 3:  # Need header row + column headers + at least one fixture
                    continue

                # Paring the player table
                # if the header row first column is CLUB and last column is HOME GREEN, this is the player table
                if str(table[0][0]).strip().lower() == "club":
                    # This is the player table
                    for row in table[1:]:
                        if len(row) < 2:
                            continue
                        club_name = str(row[0] or "").strip()
                        # home green is the last column but the column header is arbitrary
                        home_green_col = -1
                        # Determine player columns dynamically based on headers
                        header_row = table[0]
                        # Find first player column: header contains 'lead' or 'player'
                        first_player_col = next(
                            (i for i, h in enumerate(header_row) if h and any(x in h.strip().lower() for x in ('lead', 'player'))),
                            1  # fallback to 1 if not found
                        )
                        # Find last player column: header (from end) contains 'player' or 'skip'
                        last_player_col = len(header_row) - 1 - next(
                            (i for i, h in enumerate(reversed(header_row)) if h and any(x in h.strip().lower() for x in ('player', 'skip'))),
                            0  # fallback to last column if not found
                        )
                        # Players are from first_player_col up to and including last_player_col
                        players = [str(cell or "").strip() for cell in row[first_player_col:last_player_col+1]]
                        # replace any '\n' characters in players with space
                        players = [re.sub(r'\n', ' ', p) for p in players if p]
                        # trim any leading or trailing whitespace in players
                        players = [p.strip() for p in players if p.strip()]
                        # The key player is the last in the list (if any)
                        skip = players[-1] if players else ""
                        # replace any '\n' characters in skip with space
                        skip = re.sub(r'\n', ' ', skip)
                        skip = skip.strip()
                        home_green = str(row[home_green_col] or "").strip() if home_green_col < len(row) else ""
                        if club_name:
                            teams.append({
                                "players": players,
                                "club": club_name,
                                "player": skip,
                                "home_green": home_green
                            })

                else:
                    # Try to extract round info and deadline from the text above the table
                    first_row = table[0]
                    current_round = "Unknown Round"
                    current_deadline = "TBC"

                    # Only look at one line above the table to search round info
                    round_text = ""
                    if hasattr(page, "extract_text"):
                        page_text = page.extract_text() or ""
                        if first_row and first_row[0]:
                            idx = page_text.find(str(first_row[0]))
                            if idx > 0:
                                # Get the last line before the table
                                prev_text = page_text[:idx].rstrip().splitlines()
                                if prev_text:
                                    round_text = prev_text[-1]
                    # Try to extract round info from just that line
                    round_match = re.search(r'(Round \d+|Quarter Finals|Semi Finals|Final)', round_text, re.IGNORECASE)
                    if round_match:
                        current_round = round_match.group(1)
                    else:
                        # Fallback: try to extract from first row
                        if first_row:
                            round_match = re.search(r'(Round \d+|Quarter Finals|Semi Finals|Final)', first_row[0] or "", re.IGNORECASE)
                            if round_match:
                                current_round = round_match.group(1)

                    # Try to extract deadline from round_text
                    deadline_match = re.search(
                        r'Completion.*:\s*(\d{1,2}\s+[A-Za-z]+,\s+\d{4})|(?:Round.*?|Final.*?)(\d{1,2}\s+[A-Za-z]+,\s+\d{4})',
                        round_text,
                        re.IGNORECASE
                    )
                    if deadline_match:
                        current_deadline = next(g for g in deadline_match.groups() if g is not None)
                    else:
                        # Fallback: extract from first row
                        current_deadline = extract_deadline(first_row)

                    # Find the header row containing "ref" in the first column.
                    # Some PDFs have annotation/info rows above the actual header,
                    # so scan all rows instead of only checking rows 0 and 1.
                    headers = None
                    fixturestart_row = None
                    for hdr_idx in range(len(table)):
                        cell0 = table[hdr_idx][0]
                        if cell0 and "ref" in str(cell0).lower():
                            headers = [h.strip() if h else "" for h in table[hdr_idx]]
                            fixturestart_row = hdr_idx + 1
                            break

                    if headers is None:
                        continue

                    try:
                        # Find column indices
                        if "ref" in headers[0].lower():
                            ref_col = 0
                        # round_match is determined by the 1st data row of ref_col. If the value is \d+, take the 1st digit, other it could be "QF\s*n", "SF\*n", "Final"
                        ref_value = str(table[fixturestart_row][ref_col] or "")
                        round_match = re.search(r'(\d+|QF\s*\d*|SF\s*\d*|Final)', ref_value, re.IGNORECASE)
                        if round_match:
                            val = round_match.group(1)
                            if val.isdigit():
                                current_round = f"{val[0]}"
                            elif val.upper().startswith("QF"):
                                current_round = "Quarter Finals"
                            elif val.upper().startswith("SF"):
                                current_round = "Semi Finals"
                            elif val.lower() == "final":
                                current_round = "Final"

                        # Find the first "Club" column (case-insensitive) for home team
                        home_club_col = next((i for i, h in enumerate(headers) if "club" in h.lower()), None)
                        players_col_num = home_club_col - ref_col
                        # find the away team club column by searching for the next "Club" after home_club_col. Search "Club" with case insensitive
                        away_club_col = next((i for i, h in enumerate(headers) if "club" in h.lower() and i > home_club_col), None)
                        away_players_col_start = away_club_col - players_col_num
                        venue_col = next((i for i, h in enumerate(headers) if h.lower() == "venue"), None)
                        if venue_col is None:
                            venue_col = away_club_col + 1
                    except ValueError:
                        continue

                    # Process fixture rows starting from third row
                    for row in table[fixturestart_row:]:
                        if len(row) <= max(ref_col, venue_col):
                            continue

                        home_club = str(row[home_club_col] or "").strip()
                        away_club = str(row[away_club_col] or "").strip()
                        home_key_player = str(row[home_club_col - 1] or "").strip()
                        away_key_player = str(row[away_club_col - 1] or "").strip()
                        ref = str(row[ref_col] or "").replace(" ", "").strip()
                        if not ref:
                            continue

                        # Home team players (from Ref+1 to home_club_col-1)
                        home_players = []
                        for i in range(ref_col + 1, home_club_col):
                            if i < len(row) and row[i]:
                                home_players.append(str(row[i]).strip())
                        home_team = ", ".join(filter(None, home_players))

                        # Away team players (from vs_col+1 to away_club_col-1)
                        away_players = []
                        for i in range(away_players_col_start + 1, away_club_col):
                            if i < len(row) and row[i]:
                                away_players.append(str(row[i]).strip())
                        away_team = ", ".join(filter(None, away_players)) or "Bye"

                        # Venue
                        venue = str(row[venue_col] if venue_col < len(row) else "").strip()
                        venue = re.sub(r'\([^)]*\)', '', venue).strip()

                        fixtures.append([
                            current_round,
                            ref,
                            home_team,
                            home_key_player,
                            home_club,
                            away_team,
                            away_key_player,
                            away_club,
                            venue,
                            current_deadline
                        ])

    return fixtures


# ---------------------------------------------------------------------------
# Google Sheet parsing (Option B: self-contained, PDF parser untouched)
# ---------------------------------------------------------------------------

def extract_sheet_id(url):
    """Extract the spreadsheet ID from a Google Sheets URL."""
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url)
    return m.group(1) if m else None


def get_sheet_tabs(sheet_id):
    """Enumerate all tab names from a public Google Sheet.

    Fetches the Sheet's HTML page and scrapes tab names from the
    docs-sheet-tab-caption elements rendered in the bottom bar.

    Returns a list of tab name strings.
    """
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit?usp=sharing"
    resp = requests.get(url)
    resp.raise_for_status()
    html = resp.text

    tabs = []

    # Primary: scrape .docs-sheet-tab-caption elements
    soup = BeautifulSoup(html, 'html.parser')
    for el in soup.select('.docs-sheet-tab-caption'):
        name = el.get_text(strip=True)
        if name and name not in tabs:
            tabs.append(name)

    if tabs:
        return tabs

    # Fallback: regex for tab captions (handles entities like &amp;)
    for m in re.finditer(r'docs-sheet-tab-caption[^>]*>([^<]+)<', html):
        import html as html_mod
        name = html_mod.unescape(m.group(1)).strip()
        if name and name not in tabs:
            tabs.append(name)

    if not tabs:
        tabs.append("Sheet1")

    return tabs


def fetch_sheet_tab_as_table(sheet_id, sheet_name):
    """Fetch one tab's data via the gviz HTML endpoint and return as
    a list of rows (each row a list of cell strings).

    Uses the sheet name parameter to select the tab.  The gviz endpoint
    returns a simple HTML <table> which we parse with BeautifulSoup.
    Works for public sheets without authentication.
    """
    from urllib.parse import quote
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/gviz/tq?tqx=out:html&sheet={quote(sheet_name)}"
    )
    resp = requests.get(url)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')
    html_table = soup.find('table')
    if not html_table:
        return []

    rows = []
    for tr in html_table.find_all('tr'):
        cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
        if cells:
            rows.append(cells)
    return rows


def _sheet_extract_deadline(first_row):
    """Search all columns in a row for deadline information (sheet version)."""
    if not first_row:
        return "TBC"
    deadline_pattern = re.compile(
        r'Completion.*:\s*(\d{1,2}\s+[A-Za-z]+,\s+\d{4})|'
        r'(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4})'
    )
    for cell in first_row:
        if not cell:
            continue
        match = re.search(deadline_pattern.pattern, cell, re.IGNORECASE)
        if match:
            return next(g for g in match.groups() if g is not None)
    return "TBC"


def _parse_sheet_player_table(table):
    """Parse a player-list table from a Google Sheet tab.

    Appends to the global ``teams`` list, identical to what the PDF parser
    does for tables whose first header cell is "Club".

    The gviz HTML output may merge the spreadsheet title into the first
    header cell, so column indices are detected dynamically by scanning
    for known keywords (Ref, Player, Lead, Skip, Home Green, etc.).
    """
    header_row = table[0]

    ref_col = None
    home_green_col = None
    player_cols = []
    club_col = None

    PLAYER_KEYWORDS = ('lead', 'player', 'second', 'third', 'skip')

    for i, h in enumerate(header_row):
        val = str(h or "").strip().lower()
        if val == "ref":
            ref_col = i
        elif val == "home green" or val == "home":
            home_green_col = i
        elif val in PLAYER_KEYWORDS:
            player_cols.append(i)
        elif val == "club":
            club_col = i

    if club_col is None and ref_col is not None and ref_col > 0:
        club_col = ref_col - 1

    if not player_cols:
        if ref_col is not None and home_green_col is not None:
            player_cols = list(range(ref_col + 1, home_green_col))
        elif ref_col is not None:
            player_cols = [ref_col + 1]

    print(f"     Column mapping: club={club_col}, ref={ref_col}, "
          f"players={player_cols}, home_green={home_green_col}")

    for row in table[1:]:
        if len(row) < 2:
            continue
        club_name = str(row[club_col] or "").strip() if club_col is not None and club_col < len(row) else ""
        players = [str(row[c] or "").strip() for c in player_cols if c < len(row)]
        players = [re.sub(r'\n', ' ', p) for p in players if p]
        players = [p.strip() for p in players if p.strip()]
        skip = players[-1] if players else ""
        skip = re.sub(r'\n', ' ', skip).strip()
        home_green = ""
        if home_green_col is not None and home_green_col < len(row):
            home_green = str(row[home_green_col] or "").strip()
        if club_name:
            teams.append({
                "players": players,
                "club": club_name,
                "player": skip,
                "home_green": home_green,
            })


def _parse_sheet_fixture_table(table, preamble_rows):
    """Parse a fixture table from a Google Sheet tab.

    ``preamble_rows`` are the rows above the header that may contain round
    and deadline information.

    Returns a list of fixture lists in the same format as ``parse_fixtures``.
    """
    fixtures = []
    current_round = "Unknown Round"
    current_deadline = "TBC"

    # Try to extract round info and deadline from the preamble rows
    # AND the header row itself (gviz may merge the preamble into it).
    all_text_rows = list(preamble_rows) + [table[0]] if table else list(preamble_rows)
    preamble_text = " ".join(
        " ".join(str(c or "") for c in row) for row in all_text_rows
    )
    round_match = re.search(
        r'(Round \d+|Quarter Finals?|Semi Finals?|Final)',
        preamble_text, re.IGNORECASE
    )
    if round_match:
        current_round = round_match.group(1)

    deadline_match = re.search(
        r'Completion.*:\s*(\d{1,2}\s+[A-Za-z]+,\s+\d{4})|'
        r'(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4})',
        preamble_text, re.IGNORECASE
    )
    if deadline_match:
        current_deadline = next(g for g in deadline_match.groups() if g is not None)
    else:
        current_deadline = _sheet_extract_deadline(table[0] if table else [])

    # Find the header row: scan for a row where any cell contains "ref"
    headers = None
    fixturestart_row = None
    for hdr_idx in range(len(table)):
        cells_lower = [str(c or "").strip().lower() for c in table[hdr_idx]]
        if any("ref" in c for c in cells_lower):
            headers = [h.strip() if h else "" for h in table[hdr_idx]]
            fixturestart_row = hdr_idx + 1
            break

    if headers is None:
        return fixtures

    # The gviz HTML output may merge the preamble text into the first
    # header cells.  Normalize by extracting the last word of each cell
    # so "...Round 1 Ref" → "ref", "...10:00am (Provisional) Club" → "club".
    header_keywords = []
    for h in headers:
        words = h.split()
        header_keywords.append(words[-1].lower() if words else "")

    try:
        ref_col = next(
            (i for i, k in enumerate(header_keywords) if k == "ref"), 0
        )

        if current_round == "Unknown Round":
            ref_value = str(table[fixturestart_row][ref_col] or "")
            round_match = re.search(
                r'(\d+|QF\s*\d*|SF\s*\d*|Final)', ref_value, re.IGNORECASE
            )
            if round_match:
                val = round_match.group(1)
                if val.isdigit():
                    current_round = f"{val[0]}"
                elif val.upper().startswith("QF"):
                    current_round = "Quarter Finals"
                elif val.upper().startswith("SF"):
                    current_round = "Semi Finals"
                elif val.lower() == "final":
                    current_round = "Final"

        home_club_col = next(
            (i for i, k in enumerate(header_keywords) if k == "club"), None
        )
        players_col_num = home_club_col - ref_col
        away_club_col = next(
            (i for i, k in enumerate(header_keywords)
             if k == "club" and i > home_club_col), None
        )
        away_players_col_start = away_club_col - players_col_num
        venue_col = next(
            (i for i, k in enumerate(header_keywords) if k == "venue"), None
        )
        if venue_col is None:
            venue_col = away_club_col + 1
    except (ValueError, TypeError):
        return fixtures

    for row in table[fixturestart_row:]:
        if len(row) <= max(ref_col, venue_col):
            continue

        cell0 = str(row[ref_col] or "").strip()
        cell0_lower = cell0.lower()

        # Skip repeated header rows (e.g., "Ref" row appearing again)
        if cell0_lower == "ref":
            continue

        # Detect mid-table round separators (e.g., "Semi Finals", "Quarter Finals")
        # Only treat as a separator if the rest of the row is mostly empty
        # (fixture data rows have player info in cells 1+).
        round_sep = re.match(
            r'^(Round \d+|Quarter Finals?|Semi Finals?|Final)$',
            cell0, re.IGNORECASE
        )
        non_empty_after = sum(1 for c in row[1:] if str(c or "").strip())
        if round_sep and non_empty_after <= 2:
            current_round = round_sep.group(1)
            deadline_cells = " ".join(str(c or "") for c in row)
            dl = re.search(
                r'(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+,?\s+\d{4})',
                deadline_cells
            )
            if dl:
                current_deadline = dl.group(1)
            continue

        # Skip non-fixture rows (Umpire, Markers, etc.)
        if cell0_lower.startswith(("umpire", "marker", "note")):
            continue

        home_club = str(row[home_club_col] or "").strip()
        away_club = str(row[away_club_col] or "").strip()
        home_key_player = str(row[home_club_col - 1] or "").strip()
        away_key_player = str(row[away_club_col - 1] or "").strip()
        ref = cell0.replace(" ", "").strip()
        if not ref:
            continue

        home_players = []
        for i in range(ref_col + 1, home_club_col):
            if i < len(row) and row[i]:
                home_players.append(str(row[i]).strip())
        home_team = ", ".join(filter(None, home_players))

        away_players = []
        for i in range(away_players_col_start + 1, away_club_col):
            if i < len(row) and row[i]:
                away_players.append(str(row[i]).strip())
        away_team = ", ".join(filter(None, away_players)) or "Bye"

        venue = str(row[venue_col] if venue_col < len(row) else "").strip()
        venue = re.sub(r'\([^)]*\)', '', venue).strip()

        fixtures.append([
            current_round,
            ref,
            home_team,
            home_key_player,
            home_club,
            away_team,
            away_key_player,
            away_club,
            venue,
            current_deadline,
        ])

    return fixtures


def parse_fixtures_from_sheet(sheet_id):
    """Parse fixtures and player list from a public Google Sheet.

    Enumerates all tabs, fetches each as an HTML table, classifies by
    content (player list vs fixture table), and returns a fixtures list
    in the same format as ``parse_fixtures()``.  Player data is appended
    to the global ``teams`` list as a side-effect.
    """
    fixtures = []
    tab_list = get_sheet_tabs(sheet_id)

    print(f"Found {len(tab_list)} tab(s) in Google Sheet {sheet_id}:")
    for name in tab_list:
        print(f"  - {name}")

    for tab_name in tab_list:
        print(f"Processing tab: {tab_name}")
        raw_rows = fetch_sheet_tab_as_table(sheet_id, tab_name)
        if not raw_rows:
            print(f"  Skipping empty tab: {tab_name}")
            continue

        # Strip non-ASCII characters (same as PDF parser)
        for r in range(len(raw_rows)):
            for c in range(len(raw_rows[r])):
                if raw_rows[r][c]:
                    raw_rows[r][c] = re.sub(r'[^\x00-\x7F]', '', str(raw_rows[r][c]))

        # Classify the tab by content
        # The gviz HTML output merges the preamble text (title, rules, round
        # heading) into a single giant first header cell.  The actual data
        # starts from the second row onward, where row 0 of the data is the
        # column header (Ref | Player | Club ...) or (Club | Player | ...).
        #
        # Strategy: scan rows for the classification markers.

        is_player_table = False
        is_fixture_table = False
        header_idx = None

        for idx, row in enumerate(raw_rows):
            cells_lower = [str(c or "").strip().lower() for c in row]

            if any("home green" in c for c in cells_lower):
                is_player_table = True
                header_idx = idx
                break

            cell0 = cells_lower[0] if cells_lower else ""
            if cell0 == "club":
                is_player_table = True
                header_idx = idx
                break
            if "ref" in cell0 or any(c == "ref" for c in cells_lower):
                is_fixture_table = True
                header_idx = idx
                break

        if is_player_table:
            print(f"  -> Player list table detected")
            _parse_sheet_player_table(raw_rows[header_idx:])

        elif is_fixture_table:
            print(f"  -> Fixture table detected")
            preamble = raw_rows[:header_idx] if header_idx else []
            tab_fixtures = _parse_sheet_fixture_table(
                raw_rows[header_idx:], preamble
            )
            fixtures.extend(tab_fixtures)
            print(f"     {len(tab_fixtures)} fixtures extracted")

        else:
            print(f"  -> Unrecognised tab content, skipping")

    return fixtures



def print_fixtures(fixtures):
    if not fixtures:
        print("No fixtures found in the PDF")
        return

    headers = ["Round", "Ref", "Home Team", "Home Key Player", "Home Club", "Away Team", "Away Key Player", "Away Club", "Venue", "Deadline"]
    chunk_size = 50  # Rows per chunk

    print("\nLAWN BOWLS FIXTURES - COMPLETE SCHEDULE")
    print(f"Total fixtures found: {len(fixtures)}")

    chunk_size = min(chunk_size, len(fixtures)) - 1

    for i in range(0, len(fixtures), chunk_size):
        chunk = fixtures[i:i + chunk_size]
        print(tabulate(
            chunk,
            headers=headers,
            tablefmt="grid",
            maxcolwidths=[15, 8, 30, 30, 20, 15, 30, 30, 20, 15],
            stralign="left"
        ))

        remaining = len(fixtures) - (i + chunk_size)
        if remaining > 0:
            input(f"\nShowing {i+1}-{i+len(chunk)} of {len(fixtures)}. Press Enter for more...")
            print("\n" + "="*80 + "\n")


def build_tournament_tree(fixtures):
    """Build a tree structure representing the tournament progression"""

    global nodes
    roundmax = 0
    for fixture in fixtures:
        ref = fixture[1]
        # find the numerical round number from fixture[0] and assign to roundnum
        # Extract round number if fixture[0] is a digit, else set to None
        try:
            roundnum = int(fixture[0]) if str(fixture[0]).isdigit() else None
        except Exception:
            roundnum = None
        # keep roundmax as the highest round number seen
        roundmax = max(roundmax, roundnum) if roundnum is not None else roundmax
        nodes[ref] = {
            'round': fixture[0],
            'roundnum': roundnum,
            'home_team': fixture[2],
            'home_key_player': fixture[3],
            'home_club': fixture[4],
            'away_team': fixture[5],
            'away_key_player': fixture[6],
            'away_club': fixture[7],
            'venue': fixture[8],
            'deadline': fixture[9],
            'ref': ref
        }

        ref = fixture[1]

        if "W / O" in str(fixture[2]):
            source_ref = re.search(r'W\s?/\s?O\s?(\d+|QF\s?\d+|SF\s?\d+)', fixture[2])
            # strip any space in source_ref.group(1)
            if source_ref:
                nodes[ref]['home_source'] = source_ref.group(1).replace(" ", "")

        if "W / O" in str(fixture[5]):
            source_ref = re.search(r'W\s?/\s?O\s?(\d+|QF\s?\d+|SF\s?\d+)', fixture[5])
            if source_ref:
                nodes[ref]['away_source'] = source_ref.group(1).replace(" ", "")

    for fixture in fixtures:
        ref = fixture[1]
        if "Quarter Finals" in fixture[0]:
            nodes[ref]['roundnum'] = roundmax + 1
        elif "Semi Finals" in fixture[0]:
            nodes[ref]['roundnum'] = roundmax + 2
        elif "Final" in fixture[0]:
            nodes[ref]['roundnum'] = roundmax + 3

    # sort the nodes by roundnum by descending order
    nodes = dict(sorted(nodes.items(), key=lambda item: (item[1]['roundnum'] if item[1]['roundnum'] is not None else 0, item[0]), reverse=True))
    top_round = list(nodes.values())[0]['roundnum']
    # if there are more than one node with the same top_round, run build_home_away_teams for each of them
    tree = 0
    for ref, node in nodes.items():
        if node['roundnum'] == top_round:
            tree += 1
            path = []
            build_home_away_teams("", path.copy() , tree, ref)
    # stop loop when the node has smaller roundnum than top_round
        elif node['roundnum'] < top_round:
            break

    # build_home_away_teams("", list(nodes.keys())[0])
    # sort the teams by team's HA value in alphabetical order, with 'H' before 'A', and if equal, by number of 'H' descending
    teams.sort(key=lambda x: (x.get('HA', ''), -x.get('HA', '').count('H')))

    return nodes

def find_team_by_player(club, skip):
    for team in teams:
        if team['club'] == club and team['player'] == skip:
            return team
        if team['club'] == club:
            for player in team['players']:
                if player == skip:
                    return team
    return None


def build_home_away_teams(ha, path, tree, ref):
    # recursively call build_home_away_teams first by following the home_source and then away_source until the home_team and away_team are not "W / O <ref>"
    if ref not in nodes:
        return ("Unknown", "Unknown")

    home_team = nodes[ref].get('home_team', "Unknown")
    away_team = nodes[ref].get('away_team', "Unknown")
    home_team_club = nodes[ref].get('home_club', "Unknown")
    home_team_skip = nodes[ref].get('home_key_player', "Unknown")
    away_team_club = nodes[ref].get('away_club', "Unknown")
    away_team_skip = nodes[ref].get('away_key_player', "Unknown")

    # terminate if home_team contains no "W / O" or "Bye"
    if "W / O" in home_team:
        home_source = nodes[ref].get('home_source')
        if home_source:
            ha = ha + 'H'
            path.append((nodes[ref]['round'], nodes[ref]['ref'], nodes[ref]['deadline']))
            build_home_away_teams(ha, path.copy(), tree, home_source)
    else:
        # find the team in teams list by team club and team_skip and assign ha to the teams 'HA'
        team = find_team_by_player(home_team_club, home_team_skip)
        # if team found, assign ha to the teams 'HA'
        if team:
            ha = ha + 'H'
            team['HA'] = ha
            path.append((nodes[ref]['round'], nodes[ref]['ref'], nodes[ref]['deadline']))
            team['path'] = path.copy()
            team['tree'] = tree
            

    #strip 'H' from ha
    ha = ha[:-1]
    # remove the last element from team['path']
    path = path[:-1]

    if "W / O" in away_team:
        away_source = nodes[ref].get('away_source')
        if away_source:
            ha = ha + 'A'
            path.append((nodes[ref]['round'], nodes[ref]['ref'], nodes[ref]['deadline']))
            build_home_away_teams(ha, path.copy(), tree, away_source)
    else:

        # find the team in teams list by team club and team_skip and assign ha to the teams 'HA'
        team = find_team_by_player(away_team_club, away_team_skip)
        # if team found, assign ha to the teams 'HA'
        if team:
            ha = ha + 'A'
            team['HA'] = ha
            path.append((nodes[ref]['round'], nodes[ref]['ref'], nodes[ref]['deadline']))
            team['path'] = path.copy()
            team['tree'] = tree

    return


def find_player_path(tree, player_name="C L Fung"):
    """Find the player's path through the tournament tree"""
    player_matches = []
    for ref, node in tree.items():
        if player_name in node['home_team'] or player_name in node['away_team']:
            player_matches.append((ref, node))

    if not player_matches:
        print(f"Player {player_name} not found in any matches")
        return []

    path = []
    current_match = None

    round_order = ["Round 1", "Round 2", "Round 3", "Round 4", "Round 5", 
                  "Quarter Finals", "Semi Finals", "Final"]

    for round_name in round_order:
        for ref, node in player_matches:
            if node['round'] == round_name:
                current_match = (ref, node)
                path.append(current_match)
                break
        if current_match:
            break

    if not current_match:
        return []

    while True:
        next_match = None
        current_ref = current_match[0]

        for ref, node in tree.items():
            if node['home_source'] == current_ref or node['away_source'] == current_ref:
                team_in_match = (
                    current_match[1]['home_team'] in (node['home_team'], node['away_team']) or
                    current_match[1]['away_team'] in (node['home_team'], node['away_team'])
                )
                if team_in_match:
                    next_match = (ref, node)
                    break

        if not next_match:
            break

        path.append(next_match)
        current_match = next_match

    return path

def print_player_path(path):
    if not path:
        print("No tournament path found for this player")
        return

    print("\nTOURNAMENT PATH FOR PLAYER")
    headers = ["Round", "Ref", "Home Team", "Away Team", "Venue", "Deadline"]

    for i, (ref, node) in enumerate(path):
        print(f"\nStage {i+1}: {node['round']}")
        print(tabulate(
            [[node['round'], ref, node['home_team'], node['away_team'], node['venue'], node['deadline']]],
            headers=headers,
            tablefmt="grid",
            maxcolwidths=[15, 8, 30, 30, 20, 15],
            stralign="left"
        ))

        if i < len(path) - 1:
            print("\n    ↓ Advances to ↓")

def main():
    # argument 1 is the PDF path or Google Sheet URL
    if len(sys.argv) > 1:
        source = sys.argv[1]
    else:
        source = get_default_pdf_path()
        print(f"Using default PDF: {source}")

    is_sheet = 'docs.google.com/spreadsheets' in source

    # argument 2 is the output file
    output_file = None
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    elif is_sheet:
        sheet_id = extract_sheet_id(source)
        output_file = f"{sheet_id}_teams.json.gz"
        print(f"Using default output file: {output_file}")
    else:
        output_file = source.replace('.pdf', '_teams.json.gz')
        print(f"Using default output file: {output_file}")

    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if is_sheet:
        sheet_id = extract_sheet_id(source)
        if not sheet_id:
            print(f"Error: could not extract sheet ID from {source}")
            return
        print(f"Parsing Google Sheet: {sheet_id}")
        fixtures = parse_fixtures_from_sheet(sheet_id)
    else:
        if not os.path.exists(source):
            print(f"Error: PDF file not found at {source}")
            return
        fixtures = parse_fixtures(source)

    tournament_tree = build_tournament_tree(fixtures)

    import json
    import gzip

    with gzip.open(output_file, 'wt', encoding='utf-8') as f:
        json.dump([team for team in teams], f, ensure_ascii=False, separators=(',', ':'))


if __name__ == "__main__":
    main()