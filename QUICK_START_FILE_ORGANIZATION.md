# Quick Start: File Organization Feature

## What It Does

After identifying documents, the scope takeoff pipeline automatically:
1. Creates organized folder structure
2. Splits drawing PDFs into individual sheets (one file per sheet)
3. Copies specs, schedules, and addenda as-is
4. Tracks everything in the database

## Example Output

**Before** (original files):
```
Project/
├── Architectural Plans.pdf (50 pages)
├── Specifications.pdf (200 pages)
└── Addendum 1.pdf
```

**After** (organized):
```
Project/
├── Architectural Plans.pdf (original, unchanged)
├── Specifications.pdf (original, unchanged)
├── Addendum 1.pdf (original, unchanged)
└── Extracted-Data/
    └── Organized/
        ├── Specs/
        │   └── Specifications.pdf
        ├── Drawings/
        │   ├── A101 - Floor Plan.pdf
        │   ├── A102 - Floor Plan.pdf
        │   ├── A200 - Exterior Elevations.pdf
        │   ├── A201 - Exterior Elevations.pdf
        │   └── ... (50 separate sheet files)
        └── Addenda/
            └── Addendum 1.pdf
```

## How to Use

### Option 1: Run Full Takeoff (Recommended)

```bash
# Via API
curl -X POST http://localhost:5003/api/project/<project_id>/scope-takeoff

# Via Python
python3 -c "
from modules.scope_takeoff import run_scope_takeoff
result = run_scope_takeoff('Bidding/Project-Name')
print(f\"Organized {result['organization_stats']['total_sheets']} sheets\")
"
```

### Option 2: Test the Feature

```bash
# Test just the organizer
python3 test_file_organization.py "Bidding/Project-Name" organizer

# Test full pipeline
python3 test_file_organization.py "Bidding/Project-Name" full
```

### Option 3: Use Organizer Directly

```python
from modules.scope_takeoff.file_organizer import organize_project_files

documents = [
    {'path': 'plans.pdf', 'doc_type': 'drawing', 'filename': 'plans.pdf'},
    {'path': 'specs.pdf', 'doc_type': 'spec', 'filename': 'specs.pdf'},
]

result = organize_project_files('path/to/project', documents)
print(result['stats'])
```

## Check Results

### View Organized Folder

```bash
ls -la "Bidding/Project-Name/Extracted-Data/Organized/Drawings/"
```

### Query Database

```python
from modules.database import get_organized_files

# All files
all_files = get_organized_files('project-name')

# Just drawings
drawings = get_organized_files('project-name', doc_type='drawing')

for f in drawings:
    print(f"{f['sheet_number']} - {f['sheet_title']}")
```

### Check Takeoff Result

```python
from modules.scope_takeoff import run_scope_takeoff
import json

result = run_scope_takeoff('path/to/project')

# Organization stats
print(json.dumps(result['organization_stats'], indent=2))

# First 5 organized files
for file in result['organized_files'][:5]:
    print(f"{file['doc_type']}: {file['organized_path']}")
```

## What Gets Split vs. Copied

| Document Type | Action | Why |
|--------------|--------|-----|
| Drawings | Split into sheets | Each sheet needs to be separate for takeoff |
| Specs | Copy as-is | Spec book stays together as one document |
| Schedules | Copy as-is | Usually single or few pages, no need to split |
| Addenda | Copy as-is | Keep addenda intact for reference |

## Troubleshooting

### No sheets extracted from drawings
- Check if PyMuPDF is installed: `pip3 install PyMuPDF`
- Without PyMuPDF, drawings are copied as-is (not split)

### Sheet numbers not detected
- Organizer falls back to: `Sheet-001`, `Sheet-002`, etc.
- Check drawing quality and text layer

### Database errors
- File organization continues even if database fails
- Check `result['errors']` for details

### Files not organized
- Only recognized types are organized: `spec`, `drawing`, `schedule`, `addendum`
- Unknown types remain in original location
- Check `result['documents']` to see how files were classified

## Performance

Typical timings:
- 10 PDFs, 50 sheets: ~3-5 seconds
- 30 PDFs, 150 sheets: ~10-15 seconds
- PDF splitting: ~0.1-0.2 seconds per sheet

## What's Tracked in Database

Each organized file gets a database record with:
- Original path
- New path in Organized/ folder
- Document type
- Sheet number (for drawings)
- Sheet title (for drawings)
- Page number in original PDF (for drawings)
- Timestamp

## Integration with Existing Pipeline

No changes needed to your workflow:
1. Run scope takeoff as usual
2. File organization happens automatically in Phase 1
3. All other phases work the same
4. Result includes organization data

## Files Modified

- `/modules/scope_takeoff/takeoff_pipeline.py` - Added organization call
- `/modules/scope_takeoff/file_organizer.py` - NEW module

## Files Created

- `/modules/scope_takeoff/file_organizer.py` - Organization logic
- `/test_file_organization.py` - Test script
- `/FILE_ORGANIZATION.md` - Full documentation
- `/IMPLEMENTATION_SUMMARY.md` - Implementation details
- This quick start guide

## Need Help?

See full documentation in:
- `FILE_ORGANIZATION.md` - Complete feature documentation
- `IMPLEMENTATION_SUMMARY.md` - Technical implementation details
