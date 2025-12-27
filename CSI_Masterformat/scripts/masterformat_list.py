import os
import re
import json
from pathlib import Path
import pdfplumber

from dotenv import load_dotenv
load_dotenv()

# Input/output - use environment variable
MASTERFORMAT_DIR = os.getenv("MASTERFORMAT_DIR", "")
if not MASTERFORMAT_DIR:
    print("Error: Set MASTERFORMAT_DIR environment variable")
    import sys
    sys.exit(1)
input_dir = Path(MASTERFORMAT_DIR) / "Divisions"
output_file = input_dir / "masterformat_sections_sorted.json"

# Regex: supports ## ## ## or ## ## ##.##
pattern = re.compile(r'\b(0[1-9](?: \d{2}){2}(?:\.\d{2})?)\s+([^\d][^\n]+)')

sections = []

# Process PDFs
for pdf_file in input_dir.glob("*.pdf"):
    print(f"📄 Reading {pdf_file.name}")
    try:
        with pdfplumber.open(pdf_file) as pdf:
            text = " ".join(page.extract_text() for page in pdf.pages if page.extract_text())

        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace

        for match in pattern.findall(text):
            section_number = match[0].strip()
            title = match[1].strip()

            # Filter excessive title junk
            if len(title) > 150:
                title = title.split("See:")[0].split("Includes:")[0].strip()

            sections.append({
                "section_number": section_number,
                "title": title
            })

    except Exception as e:
        print(f"❌ Error with {pdf_file.name}: {e}")

# Sort numerically, even with decimal sections
def sort_key(item):
    try:
        parts = item["section_number"].replace('.', ' ').split()
        return tuple(map(int, parts))
    except:
        return (999, 999, 999, 999)

sections_sorted = sorted(sections, key=sort_key)

# Output JSON
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(sections_sorted, f, indent=2)

print(f"✅ Saved {len(sections_sorted)} sorted sections to {output_file}")
