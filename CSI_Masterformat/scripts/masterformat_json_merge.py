import os
import json
import re
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# Set the path to your output folder via environment variable
MASTERFORMAT_DIR = os.getenv("MASTERFORMAT_DIR", "")
if not MASTERFORMAT_DIR:
    print("Error: Set MASTERFORMAT_DIR environment variable")
    import sys
    sys.exit(1)
input_dir = Path(MASTERFORMAT_DIR) / "Divisions" / "out"
output_file = input_dir / "Masterformat_Merged.json"

# Pattern to match files like Masterformat Division 01.json to Masterformat Division 48.json
pattern = re.compile(r"Masterformat Division (\d{2})\.json")

# Gather files
json_files = []
for file in input_dir.glob("Masterformat Division *.json"):
    match = pattern.match(file.name)
    if match:
        division_num = int(match.group(1))
        json_files.append((division_num, file))

# Sort by division number
json_files.sort(key=lambda x: x[0])

# Merge JSON content
merged_data = {}

for division_num, file_path in json_files:
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            merged_data[f"Division {division_num:02}"] = data
        except json.JSONDecodeError as e:
            print(f"Skipping {file_path.name} due to JSON error: {e}")

# Save to one file
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(merged_data, f, indent=2)

print(f"✅ Merged {len(merged_data)} divisions into {output_file}")
