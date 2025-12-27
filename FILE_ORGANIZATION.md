# File Organization Feature

## Overview

The scope takeoff pipeline now automatically organizes project documents into a structured folder hierarchy after identifying document types in Phase 1.

## Folder Structure

All organized files are placed in the project's `Extracted-Data/Organized/` directory:

```
<Project Folder>/
└── Extracted-Data/
    └── Organized/
        ├── Specs/           # Specification documents
        ├── Drawings/        # Individual drawing sheets
        ├── Schedules/       # Door/window schedules
        └── Addenda/         # Addendum documents
```

## Features

### 1. Document Classification

Documents are automatically classified during Phase 1 (IDENTIFY) based on:
- Image resolution (drawings typically have higher DPI)
- Sheet number detection (A101, S200, etc.)
- Filename patterns (spec, addendum, schedule, etc.)
- Text content analysis

### 2. Drawing Sheet Splitting

**Drawing PDFs are automatically split into individual sheets:**
- Each page becomes a separate PDF file
- Files are named by sheet number and title: `A101 - Floor Plan.pdf`
- Sheet numbers are extracted from the drawing itself
- Sheet titles are derived from the drawing or inferred from numbering

Example:
```
Original: Architectural Plans.pdf (50 pages)
↓
Organized/Drawings/
  ├── A101 - Floor Plan.pdf
  ├── A102 - Floor Plan.pdf
  ├── A200 - Exterior Elevations.pdf
  ├── A201 - Exterior Elevations.pdf
  ├── A600 - Door Schedule.pdf
  └── ...
```

### 3. Spec and Schedule Handling

**Specification and schedule documents are copied as-is:**
- Spec books are NOT split (they remain as complete documents)
- Schedule pages are copied to Schedules/ folder
- Addenda are copied to Addenda/ folder

### 4. Database Tracking

All organized files are tracked in the SQLite database with:
- Original file path
- Organized file path
- Document type (spec, drawing, schedule, addendum)
- Sheet number (for drawings)
- Sheet title (for drawings)
- Page number (1-indexed from original PDF)

Database table: `organized_files`

## Implementation

### Key Files

1. **`modules/scope_takeoff/file_organizer.py`**
   - `FileOrganizer` class - Main organization logic
   - `organize_project_files()` - Entry point function
   - Handles PDF splitting and file copying

2. **`modules/scope_takeoff/takeoff_pipeline.py`**
   - Updated `phase_identify()` to call file organizer
   - Added `_organize_files()` method
   - Added `organized_files` and `organization_stats` to `TakeoffResult`

3. **`modules/database.py`**
   - `save_organized_file()` - Save file record to database
   - `get_organized_files()` - Retrieve organized files for a project
   - Table: `organized_files`

### Workflow

```
Phase 1: IDENTIFY
├── 1. Scan project folder for PDFs
├── 2. Analyze each PDF (DPI, text, sheet numbers)
├── 3. Classify document type
├── 4. ✨ NEW: Organize files into folders
│   ├── Create folder structure
│   ├── Split drawings into individual sheets
│   ├── Copy specs/schedules/addenda as-is
│   └── Save records to database
└── 5. Continue to Phase 2...
```

## Usage

### Through API

```bash
POST /api/project/<project_id>/scope-takeoff
```

The takeoff will automatically organize files during Phase 1.

Result includes:
```json
{
  "status": "ok",
  "result": {
    "organized_files": [...],
    "organization_stats": {
      "specs": 1,
      "drawings": 2,
      "total_sheets": 45,
      "schedules": 0,
      "addenda": 3
    },
    ...
  }
}
```

### Programmatically

```python
from modules.scope_takeoff import run_scope_takeoff

result = run_scope_takeoff("path/to/project")

# Access organized files
organized_files = result['organized_files']
for file_record in organized_files:
    print(f"{file_record['doc_type']}: {file_record['organized_path']}")
    if file_record['sheet_number']:
        print(f"  Sheet: {file_record['sheet_number']}")
```

### Direct File Organizer

```python
from modules.scope_takeoff.file_organizer import organize_project_files

# After phase_identify() has classified documents
documents = [
    {
        'path': '/path/to/plans.pdf',
        'doc_type': 'drawing',
        'filename': 'plans.pdf',
        ...
    },
    ...
]

result = organize_project_files(project_folder, documents)

print(f"Organized {result['stats']['total_sheets']} sheets")
```

### Database Access

```python
from modules.database import get_organized_files

# Get all organized files for a project
files = get_organized_files('project-name')

# Get only drawings
drawings = get_organized_files('project-name', doc_type='drawing')

for file_record in drawings:
    print(f"{file_record['sheet_number']} - {file_record['sheet_title']}")
    print(f"  Path: {file_record['organized_path']}")
```

## Configuration

No additional configuration required. The feature is enabled by default.

### Requirements

- **PyMuPDF (fitz)** - Required for PDF splitting
  - If not available, drawings are copied as-is without splitting
  - Already listed in `requirements.txt`

## Testing

Use the provided test script:

```bash
# Test just the file organizer
python3 test_file_organization.py "Bidding/Project-Name" organizer

# Test full pipeline integration
python3 test_file_organization.py "Bidding/Project-Name" full
```

## Performance

- **Small projects** (< 10 PDFs): ~1-2 seconds
- **Medium projects** (10-30 PDFs): ~3-5 seconds
- **Large projects** (30+ PDFs, 100+ sheets): ~10-15 seconds

PDF splitting is fast but adds ~0.1-0.2 seconds per sheet.

## Error Handling

The organizer is designed to be resilient:

1. **Missing PyMuPDF**: Falls back to copying entire files
2. **Unreadable PDFs**: Skipped with error logged
3. **Extraction failure**: Original file copied as fallback
4. **Database errors**: Organization continues, just not tracked in DB
5. **Unknown doc types**: Not organized (remain in original location)

Errors are logged in `result['errors']` array.

## Future Enhancements

Potential improvements:

1. **Smart merging** - Combine related sheets (e.g., all elevations)
2. **OCR integration** - Better sheet number extraction for scanned drawings
3. **Custom organization rules** - User-defined folder structure
4. **Duplicate detection** - Skip files that are already organized
5. **Metadata extraction** - Extract more info (discipline, building, etc.)

## Notes

- Original files are **never modified or deleted**
- Organized files are **copies** of the originals
- Re-running takeoff will **overwrite** existing organized files
- Database tracks all versions (future: version history)
