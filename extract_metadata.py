import pdfplumber
from datetime import datetime

def extract_pdf_metadata(pdf_path):
    """
    Extract metadata information from a PDF file using pdfplumber
    
    Args:
        pdf_path (str): Path to the PDF file
    
    Returns:
        dict: Dictionary containing metadata information
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Get the metadata dictionary
            metadata = pdf.metadata
            
            # Convert creation and modification dates to readable format if they exist
            if metadata.get('CreationDate'):
                try:
                    # PDF dates are in format: D:YYYYMMDDHHMMSS
                    date_str = metadata['CreationDate']
                    if date_str.startswith('D:'):
                        date_str = date_str[2:]
                    # Parse the date string
                    created_date = datetime.strptime(date_str[:14], '%Y%m%d%H%M%S')
                    metadata['CreationDate_Formatted'] = created_date.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, IndexError):
                    metadata['CreationDate_Formatted'] = "Could not parse date format"
            
            if metadata.get('ModDate'):
                try:
                    date_str = metadata['ModDate']
                    if date_str.startswith('D:'):
                        date_str = date_str[2:]
                    mod_date = datetime.strptime(date_str[:14], '%Y%m%d%H%M%S')
                    metadata['ModDate_Formatted'] = mod_date.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, IndexError):
                    metadata['ModDate_Formatted'] = "Could not parse date format"
            
            return metadata
            
    except FileNotFoundError:
        print(f"Error: File '{pdf_path}' not found.")
        return None
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return None

def display_metadata(metadata):
    """
    Display metadata in a readable format
    
    Args:
        metadata (dict): Metadata dictionary
    """
    if not metadata:
        print("No metadata available.")
        return
    
    print("PDF Metadata Information:")
    print("=" * 40)
    
    # Common metadata fields to display
    common_fields = [
        'Title', 'Author', 'Subject', 'Keywords', 'Creator',
        'Producer', 'CreationDate', 'CreationDate_Formatted',
        'ModDate', 'ModDate_Formatted'
    ]
    
    for field in common_fields:
        if field in metadata and metadata[field]:
            print(f"{field:25}: {metadata[field]}")
    
    # Display any additional metadata fields
    print("\nAdditional Metadata:")
    print("-" * 20)
    for key, value in metadata.items():
        if key not in common_fields and value:
            print(f"{key:25}: {value}")

# Main execution
if __name__ == "__main__":
    pdf_file = "./M_Nat_Triples_2025-4.pdf"
    
    print(f"Extracting metadata from: {pdf_file}")
    print("=" * 50)
    
    metadata = extract_pdf_metadata(pdf_file)
    
    if metadata:
        display_metadata(metadata)
    else:
        print("Failed to extract metadata.")