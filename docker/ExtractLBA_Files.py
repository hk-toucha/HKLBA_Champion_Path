import hashlib
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse
import shutil
import re
import pdfplumber
from datetime import datetime
import json
import subprocess
import platform

# Define the URL
url = "https://www.bowls.org.hk/fixtures-a-conditions-of-play/"

# Define directories
archive_dir = "archive"
download_dir = "downloads"

os.makedirs(archive_dir, exist_ok=True)
os.makedirs(download_dir, exist_ok=True)

# Fetch the webpage
response = requests.get(url)
response.raise_for_status()  # Raise error if request fails

# Parse the HTML
soup = BeautifulSoup(response.text, 'html.parser')

# Dictionary to hold PDFs by category
pdfs_by_category = {
    "men": [],
    "women": [],
    "mixed": []
}

# Dictionary to hold Google Sheets by category
sheets_by_category = {
    "men": [],
    "women": [],
    "mixed": []
}

SUPPORTED_GAMES = [
    'National Singles', 'National Pairs', 'National Triples', 'National Fours',
    'Indoor Singles', 'Indoor Pairs', '2-4-2 Pairs', 'Novice Singles',
    'Novice Pairs', 'Novice Triples',
    'Mixed Pairs', 'Angela Chau Memorial Mixed Triples', 'Mixed Fours',
]

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
print(f"Starting processing website pdf: {now}")

# Find tables
tables = soup.find_all('table')
for table in tables:
    rows = table.find_all('tr')
    if not rows:
        continue

    # Assume first row is header
    header_row = rows[0]
    headers = header_row.find_all(['th', 'td'])
    if not headers:
        continue

    # Map categories to columns
    col_category = [None] * len(headers)
    for idx, header in enumerate(headers):
        text = header.text.lower().strip()
        if "men" in text:
            col_category[idx] = "men"
        elif "women" in text:
            col_category[idx] = "women"
        elif "mixed" in text:
            col_category[idx] = "mixed"

    if all(c is None for c in col_category):
        continue  # No categories found

    # Process data rows
    for row in rows[1:]:
        cells = row.find_all(['th', 'td'])
        if len(cells) < 2:
            continue  # Not enough columns to process

        # Helper: classify a link as PDF or Google Sheet and append to the
        # appropriate category list.
        def collect_link(a_tag, category):
            href = a_tag['href']
            desc = a_tag.text.strip() or f"{category.capitalize()} fixture"
            if not any(game in desc for game in SUPPORTED_GAMES):
                return
            if href.endswith('.pdf'):
                pdfs_by_category[category].append((desc, href))
            elif 'docs.google.com/spreadsheets' in href:
                sheets_by_category[category].append((desc, href))

        # 1st column: Men, 3rd: Women, 5th: Mixed (if exists)
        # Men
        men_cell = cells[0]
        for a in men_cell.find_all('a', href=True):
            collect_link(a, "men")

        # Women
        if len(cells) > 2:
            women_cell = cells[2]
            for a in women_cell.find_all('a', href=True):
                collect_link(a, "women")

        # Mixed
        if len(cells) > 4:
            mixed_cell = cells[4]
            for a in mixed_cell.find_all('a', href=True):
                collect_link(a, "mixed")

# Collect all current PDF file names
current_file_names = set()

# use the pdfplumber module to create a function to extract latest update date from a PDF file
def extract_pdf_update_date(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            metadata = pdf.metadata
            if not metadata:
                return None

            # Extract and format CreationDate
            if 'ModDate' in metadata:
                date_str = metadata['ModDate']
                try:
                    # PDF date format: D:YYYYMMDDHHmmSSOHH'mm'
                    if date_str.startswith('D:'):
                        date_str = date_str[2:]
                    creation_date = datetime.strptime(date_str[:14], '%Y%m%d%H%M%S')
                    metadata['ModDate_Formatted'] = creation_date.strftime('%Y-%m-%d')
                except (ValueError, IndexError):
                    metadata['ModDate_Formatted'] = "Could not parse date format"

            return metadata['ModDate_Formatted']

    except FileNotFoundError:
        print(f"Error: File '{pdf_path}' not found.")
        return None
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return None

# Process each PDF
pdf_info = []  # to store tuples of (base_name, pdf file name, full_url, creation date)
for category, pdfs in pdfs_by_category.items():
    for desc, href in pdfs:
        full_url = urljoin(url, href)
        file_name = os.path.basename(urlparse(full_url).path)
        current_file_names.add(file_name)

        archive_path = os.path.join(archive_dir, file_name)
        download_path = os.path.join(download_dir, file_name)

        # Download to download directory
        print(f"Downloading {file_name} for {category} - {desc}")
        resp = requests.get(full_url)
        resp.raise_for_status()
        with open(download_path, 'wb') as f:
            f.write(resp.content)
        # calculate and compare the hash value fo the downloaded file and the archived file if exists
        if os.path.exists(archive_path):
            with open(archive_path, 'rb') as f:
                archive_hash = hashlib.md5(f.read()).hexdigest()
            download_hash = hashlib.md5(open(download_path, 'rb').read()).hexdigest()
            if download_hash == archive_hash:
                # remove the downloaded file
                os.remove(download_path)
                print(f"Skipping {file_name} for {category} - {desc} (already exists in archive)")
                #for each of the updated files from the download directory, call the extract_pdf_update_date() function with the file path as argument and print the output
                update_date = extract_pdf_update_date(archive_path)
                # store the list of tuples (base_name, pdf file name, full_url, creation date) in a list
                # base_name is the part of the file name before the first occurrence of - or _ followed by 4 digits
                base_name = re.match(r"^(.*?)[-_]\d{4}.*\.pdf$", file_name)
                if base_name:
                    base_name = base_name.group(1)
                pdf_info.append((base_name, file_name, full_url, update_date))
                continue

        # # Download to download directory
        # print(f"Downloading {file_name} for {category} - {desc}")
        # resp = requests.get(full_url)
        # resp.raise_for_status()
        # with open(download_path, 'wb') as f:
        #     f.write(resp.content)

        #for each of the updated files from the download directory, call the extract_pdf_update_date() function with the file path as argument and print the output
        update_date = extract_pdf_update_date(download_path)
        # store the list of tuples (base_name, pdf file name, full_url, creation date) in a list
        # base_name is the part of the file name before the first occurrence of - or _ followed by 4 digits
        base_name = re.match(r"^(.*?)[-_]\d{4}.*\.pdf$", file_name)
        if base_name:
            base_name = base_name.group(1)
        pdf_info.append((base_name, file_name, full_url, update_date))

        # Move to archive directory
        shutil.copy2(download_path, archive_path)
        print(f"Copied {file_name} to archive")

# ---------------------------------------------------------------------------
# Process Google Sheets (Phase 2, 3, 6)
# ---------------------------------------------------------------------------

def extract_sheet_id(sheet_url):
    m = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', sheet_url)
    return m.group(1) if m else None


def derive_base_name(category, desc):
    """Derive a file-system-friendly base name from the category and
    description, e.g. ('men', 'National Singles') -> 'M-Nat-Singles'."""
    prefix = {"men": "M", "women": "W", "mixed": "Mixed"}.get(category, category[0].upper())
    name = desc.strip()
    name = name.replace("National", "Nat")
    name = re.sub(r'\s+', '-', name)
    return f"{prefix}-{name}"


def fetch_sheet_content_hash(sheet_id):
    """Fetch all tabs of a Google Sheet via the gviz endpoint and return
    the MD5 hash of the concatenated content."""
    from fixture_parser import get_sheet_tabs, fetch_sheet_tab_as_table
    tabs = get_sheet_tabs(sheet_id)
    blob = ""
    for tab_name in tabs:
        rows = fetch_sheet_tab_as_table(sheet_id, tab_name)
        for row in rows:
            blob += "|".join(str(c or "") for c in row) + "\n"
    return hashlib.md5(blob.encode('utf-8')).hexdigest()


current_sheet_hash_files = set()

for category, sheet_list in sheets_by_category.items():
    for desc, href in sheet_list:
        sheet_id = extract_sheet_id(href)
        if not sheet_id:
            print(f"Could not extract sheet ID from {href}, skipping")
            continue

        base_name = derive_base_name(category, desc)
        hash_file_name = f"{base_name}.sheet_hash"
        current_sheet_hash_files.add(hash_file_name)
        archive_hash_path = os.path.join(archive_dir, hash_file_name)

        print(f"\nProcessing Google Sheet for {category} - {desc}")
        print(f"  Sheet ID: {sheet_id}")
        print(f"  Base name: {base_name}")

        current_hash = fetch_sheet_content_hash(sheet_id)
        print(f"  Content hash: {current_hash}")

        if os.path.exists(archive_hash_path):
            with open(archive_hash_path, 'r') as f:
                archived_hash = f.read().strip()
            if current_hash == archived_hash:
                print(f"  No changes detected, skipping")
                update_date = datetime.now().strftime('%Y-%m-%d')
                pdf_info.append((base_name, hash_file_name, href, update_date))
                continue

        with open(archive_hash_path, 'w') as f:
            f.write(current_hash)

        update_date = datetime.now().strftime('%Y-%m-%d')
        pdf_info.append((base_name, hash_file_name, href, update_date))

        output_path = os.path.join("./data", f"{base_name}.gz")
        os.makedirs("data", exist_ok=True)
        print(f"  Running fixture_parser.py with sheet URL")
        subprocess.run(
            ["python", "fixture_parser.py", href, output_path],
            check=True
        )

        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            os.makedirs("./local_data", exist_ok=True)
            shutil.copy2(output_path, os.path.join("./local_data", os.path.basename(output_path)))
            print(f"  Output: {output_path}")

# Remove files from archive that are no longer present on the webpage
# (keep both PDF files and sheet hash files that are still current)
for file in os.listdir(archive_dir):
    if file.endswith('.sheet_hash'):
        if file not in current_sheet_hash_files:
            os.remove(os.path.join(archive_dir, file))
            print(f"Removed old sheet hash {file} from archive")
    elif file not in current_file_names:
        os.remove(os.path.join(archive_dir, file))
        print(f"Removed old file {file} from archive")

# sort the pdf_info list of tuples by creation date in descending order (latest first)pdf_info.sort(key=lambda x: x[3] if x[3] else "", reverse=True)
pdf_info.sort(key=lambda x: x[3] if x[3] else "", reverse=True)
# output the pdf_info list of tuples (base_name, pdf file name, full_url, creation date) to a json file named fixture_list.json under the output_path directory
with open(os.path.join(download_dir, "fixture_list.json"), "w") as f:
    json.dump(pdf_info, f)
    # copy the fixture_list.json file to the ./data directory as well
shutil.copy2(os.path.join(download_dir, "fixture_list.json"), "./data/")

# for each of the updated files from the download directory, call the fixture_parser.py script with the file path as argument and .\data\filename.gz as output path
for file in os.listdir(download_dir):
    file_path = os.path.join(download_dir, file)
    if file.lower().endswith(".pdf"):
        # modify the file name as follows: file name is xxx[-_]yyyy[-_].*.pdf. We just want to keep the xxx part where xxx could have [-_] in between
        base_name = re.match(r"^(.*?)[-_]\d{4}.*\.pdf$", file)
        if base_name:
            output_path = os.path.join("./data", f"{base_name.group(1)}.gz")
        else:
            output_path = os.path.join("./data", f"{file}.gz")
        os.makedirs("data", exist_ok=True)
        print(f"Processing {file} with fixture_parser.py")
        subprocess.run(["python", "fixture_parser.py", file_path, output_path], check=True)
    elif file == "fixture_list.json":
        output_path = file_path

    # if the processed gz file is not empty and return status is 0, scp the file to the remove web server
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        print(f"Uploading {output_path} to remote server")
        # Use different private key path depending on OS
        if platform.system() == "Windows":
            private_key_path = "./privatekey"
        else:
            private_key_path = "/root/.ssh/privatekey"

        # No need to upload to Google Cloud server anymore

        # subprocess.run([
        #     "scp", "-o", "StrictHostKeyChecking=no", "-i", private_key_path,
        #     output_path, "clfung@34.96.239.108:/var/www/html/data/"
        # ], check=True)

        # copy to the local_data directory as well. Overwrite if exists already
        os.makedirs("./local_data", exist_ok=True)
        shutil.copy2(output_path, os.path.join("./local_data", os.path.basename(output_path)))

# remove all the files in the download directory
for file in os.listdir(download_dir):
    file_path = os.path.join(download_dir, file)
    if os.path.isfile(file_path):
        os.remove(file_path)

# Print extracted information
print("\nExtracted PDFs:")
for category, pdfs in pdfs_by_category.items():
    print(f"\n{category.capitalize()} Competitions (PDF):")
    for desc, href in pdfs:
        file_name = os.path.basename(urlparse(urljoin(url, href)).path)
        print(f"  - {desc}: {file_name}")

print("\nExtracted Google Sheets:")
for category, sheet_list in sheets_by_category.items():
    if sheet_list:
        print(f"\n{category.capitalize()} Competitions (Google Sheet):")
        for desc, href in sheet_list:
            sheet_id = extract_sheet_id(href)
            print(f"  - {desc}: {sheet_id}")
