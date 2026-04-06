import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin, urlparse
import shutil
import re

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

        # 1st column: Men, 3rd: Women, 5th: Mixed (if exists)
        # Men
        men_cell = cells[0]
        for a in men_cell.find_all('a', href=True):
            if a['href'].endswith('.pdf'):
                desc = a.text.strip() or "Men PDF"
                # only process the following games 'National Singles', 'National Pairs', 'National Triples', 'National Fours', 'Indoor Singles', 'Indoor Pairs', '2-4-2 Pairs', 'Novice Singles', 'Novice Pairs', 'Novice Triples'
                if any(game in desc for game in [
                    'National Singles', 'National Pairs', 'National Triples', 'National Fours',
                    'Indoor Singles', 'Indoor Pairs', '2-4-2 Pairs', 'Novice Singles',
                    'Novice Pairs', 'Novice Triples']):
                    pdfs_by_category["men"].append((desc, a['href']))

        # Women
        if len(cells) > 2:
            women_cell = cells[2]
            for a in women_cell.find_all('a', href=True):
                if a['href'].endswith('.pdf'):
                    desc = a.text.strip() or "Women PDF"
                    # only process the following games 'National Singles', 'National Pairs', 'National Triples', 'National Fours', 'Indoor Singles', 'Indoor Pairs', '2-4-2 Pairs', 'Novice Singles', 'Novice Pairs', 'Novice Triples'
                    if any(game in desc for game in [
                        'National Singles', 'National Pairs', 'National Triples', 'National Fours',
                        'Indoor Singles', 'Indoor Pairs', '2-4-2 Pairs', 'Novice Singles',
                        'Novice Pairs', 'Novice Triples']):
                        pdfs_by_category["women"].append((desc, a['href']))

        # Mixed
        if len(cells) > 4:
            mixed_cell = cells[4]
            for a in mixed_cell.find_all('a', href=True):
                if a['href'].endswith('.pdf'):
                    desc = a.text.strip() or "Mixed PDF"
                    # only process the following games 'Mixed Pairs', 'Angela Chau Memorial Mixed Triples', 'Mixed Fours'
                    if any(game in desc for game in [
                        'Mixed Pairs', 'Angela Chau Memorial Mixed Triples', 'Mixed Fours']):
                        pdfs_by_category["mixed"].append((desc, a['href']))

# Collect all current PDF file names
current_file_names = set()

# Process each PDF
for category, pdfs in pdfs_by_category.items():
    for desc, href in pdfs:
        full_url = urljoin(url, href)
        file_name = os.path.basename(urlparse(full_url).path)
        current_file_names.add(file_name)
        
        archive_path = os.path.join(archive_dir, file_name)
        
        if os.path.exists(archive_path):
            print(f"Skipping {file_name} for {category} - {desc} (already exists in archive)")
            continue
        
        # Download to download directory
        download_path = os.path.join(download_dir, file_name)
        print(f"Downloading {file_name} for {category} - {desc}")
        resp = requests.get(full_url)
        resp.raise_for_status()
        with open(download_path, 'wb') as f:
            f.write(resp.content)
        
        # Move to archive directory
        shutil.copy2(download_path, archive_path)
        print(f"Copied {file_name} to archive")

# Remove files from archive that are no longer present on the webpage
for file in os.listdir(archive_dir):
    if file not in current_file_names:
        os.remove(os.path.join(archive_dir, file))
        print(f"Removed old file {file} from archive")
        

# for each of the files in the archive directory, use the pdfplumber to extract the creation date info. Generate a list of tuples (base_name, pdf file name, creation date) and sort the list by creation date descending
import pdfplumber
import datetime

def extract_creation_dates(archive_dir):
    creation_dates = []
    for file in os.listdir(archive_dir):
        if file.endswith(".pdf"):
            with pdfplumber.open(os.path.join(archive_dir, file)) as pdf:
                metadata = pdf.metadata
                mod_date = metadata.get("ModDate", None)
                if mod_date:
                    # Parse the creation date. The format is usually D:YYYYMMDDHHmmSS, e.g. "D:20250415160846+08'00'"
                    # Extract the date part from D:\d{8}
                    creation_date = re.search(r"D:(\d{8})", mod_date)
                    if creation_date.group(1):
                        creation_date = creation_date.group(1)
                        # convert to datetime object
                        creation_date = datetime.datetime.strptime(creation_date, "%Y%m%d")
                    # convert the creation_date to %Y-%m-%d format string
                        creation_date = creation_date.strftime("%Y-%m-%d")
                        base_name = re.match(r"^(.*?)[-_]\d{4}.*\.pdf$", file)
                        if base_name:
                            creation_dates.append((base_name.group(1), file, creation_date))
    # Sort by creation date descending
    creation_dates.sort(key=lambda x: x[2], reverse=True)
    return creation_dates

creation_dates = extract_creation_dates(archive_dir)



# for each of the updated files from the download directory, call the fixture_parser.py script with the file path as argument and .\data\filename.gz as output path
import subprocess
import json
for file in os.listdir(download_dir):
    file_path = os.path.join(download_dir, file)
    # modify the file name as follows: file name is xxx[-_]yyyy[-_].*.pdf. We just want to keep the xxx part where xxx could have [-_] in between
    base_name = re.match(r"^(.*?)[-_]\d{4}.*\.pdf$", file)
    if base_name:
        output_path = os.path.join("./data", f"{base_name.group(1)}.gz")
    else:
        output_path = os.path.join("./data", f"{file}.gz")
    os.makedirs("data", exist_ok=True)
    print(f"Processing {file} with fixture_parser.py")
    subprocess.run(["python", "fixture_parser.py", file_path, output_path], check=True)

# if the processed gz file is empty and return status is 0, scp the file to the remove web server
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        print(f"Uploading {output_path} to remote server")
        subprocess.run(["scp", "-o", "StrictHostKeyChecking=no", "-i", r"C:\Users\user\OneDrive\Documents\putty\privatekey_ssh", output_path, "clfung@34.96.239.108:/var/www/html/data/"], check=True)

    # output the creation_dates list to a file "games_fixtures.json" in json format under the output_path directory
with open(os.path.join("./data", "games_fixtures.json"), "w") as f:
    json.dump(creation_dates, f, default=str)

# remove all the files in the download directory
for file in os.listdir(download_dir):
    file_path = os.path.join(download_dir, file)
    if os.path.isfile(file_path):
        os.remove(file_path)

# Print extracted information
print("\nExtracted PDFs:")
for category, pdfs in pdfs_by_category.items():
    print(f"\n{category.capitalize()} Competitions:")
    for desc, href in pdfs:
        file_name = os.path.basename(urlparse(urljoin(url, href)).path)
        print(f"- {desc}: {file_name}")