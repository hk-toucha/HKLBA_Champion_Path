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

# Remove files from archive that are no longer present on the webpage
for file in os.listdir(archive_dir):
    if file not in current_file_names:
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
import subprocess
import platform
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
    print(f"\n{category.capitalize()} Competitions:")
    for desc, href in pdfs:
        file_name = os.path.basename(urlparse(urljoin(url, href)).path)
        print(f"- {desc}: {file_name}")
