# Specification Book Division Extractor

Extracts and identifies CSI MasterFormat divisions from construction specification PDFs.

## Overview

Construction specifications are organized using the CSI (Construction Specifications Institute) MasterFormat numbering system. This module parses spec book PDFs to identify:

- **Division headers** (e.g., "DIVISION 08 - OPENINGS")
- **Section numbers** (e.g., "08 71 00 - DOOR HARDWARE")
- **Section excerpts** for downstream analysis

## Source

Originally from: `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/construction_doc_summarizer/`

## Files

| File | Purpose |
|------|---------|
| `division_extractor.py` | Core extraction logic with regex patterns |
| `division_pipeline.py` | High-level helpers for multi-PDF processing |

## CSI MasterFormat Divisions

| Division | Name |
|----------|------|
| 00 | Procurement and Contracting Requirements |
| 01 | General Requirements |
| 02 | Existing Conditions |
| 03 | Concrete |
| 04 | Masonry |
| 05 | Metals |
| 06 | Wood, Plastics, and Composites |
| 07 | Thermal and Moisture Protection |
| **08** | **Openings** (doors, windows, hardware) |
| 09 | Finishes |
| 10 | Specialties |
| 11 | Equipment |
| 12 | Furnishings |
| 13 | Special Construction |
| 14 | Conveying Equipment |
| 21 | Fire Suppression |
| 22 | Plumbing |
| 23 | HVAC |
| 25 | Integrated Automation |
| 26 | Electrical |
| 27 | Communications |
| 28 | Electronic Safety and Security |
| 31 | Earthwork |
| 32 | Exterior Improvements |
| 33 | Utilities |

## Usage

### Basic Division Extraction

```python
from pathlib import Path
from doc_classification import extract_divisions_from_pdf

# Extract all divisions from a spec PDF
pdf_path = Path("/path/to/specs.pdf")
divisions = extract_divisions_from_pdf(pdf_path)

# Extract only specific divisions (e.g., Division 08 - Openings)
divisions = extract_divisions_from_pdf(pdf_path, target_divisions=["08"])

# Limit pages for testing
divisions = extract_divisions_from_pdf(pdf_path, max_pages=50)
```

### Accessing Division Content

```python
# Get Division 08 content
div_08 = divisions.get("08")

if div_08:
    print(f"Division: {div_08.division}")
    print(f"Title: {div_08.title}")
    print(f"Pages: {div_08.start_page} - {div_08.end_page}")
    print(f"Sections found: {len(div_08.sections)}")

    # List all sections
    for section in div_08.sections:
        print(f"  {section.section_id}: {section.title} (page {section.page})")
```

### Multi-PDF Processing

```python
from doc_classification.division_pipeline import (
    gather_division_content,
    build_division_dataframe,
    summarize_division_content
)

# Merge Division 08 from multiple spec volumes
pdf_paths = [
    Path("/path/to/specs_vol1.pdf"),
    Path("/path/to/specs_vol2.pdf"),
]

merged = gather_division_content(pdf_paths, division="08")
div_08 = merged.get("08")

# Convert to DataFrame for analysis
df = build_division_dataframe(div_08)
print(df[['section_id', 'title', 'page']])

# Get summary with top terms
summary = summarize_division_content(div_08)
print(f"Section count: {summary['section_count']}")
print(f"Top terms: {summary['top_terms']}")
```

## Data Classes

### SectionExcerpt

```python
@dataclass
class SectionExcerpt:
    section_id: str   # "08 71 00" (normalized, no spaces)
    title: str        # "DOOR HARDWARE"
    page: int         # Page number where found
    excerpt: str      # First ~20 lines of section text
```

### DivisionContent

```python
@dataclass
class DivisionContent:
    division: str              # "08"
    title: str                 # "OPENINGS"
    start_page: int           # First page of division
    end_page: int             # Last page of division
    sections: List[SectionExcerpt]  # All sections found
```

## Regex Patterns

The extractor uses these patterns to identify content:

```python
# Division headers: "DIVISION 08 - OPENINGS"
DIVISION_HEADER_RE = re.compile(r"DIVISION\s+(\d{2})\s+[-–]\s+(.+)", re.IGNORECASE)

# Section headers: "SECTION 08 71 00 - DOOR HARDWARE"
SECTION_HEADER_RE = re.compile(r"SECTION\s+(\d{2}\s+\d{2}\s+\d{2})(.*)", re.IGNORECASE)
```

## Output Files

When using the CLI or pipeline:

| File | Contents |
|------|----------|
| `division_08_summary.json` | Section counts, page ranges, top terms |
| `division_08_sections.csv` | Per-section ID, title, page, excerpt |

## Example Output

### division_08_summary.json

```json
{
  "division": "08",
  "title": "OPENINGS",
  "start_page": 234,
  "end_page": 298,
  "section_count": 12,
  "top_terms": [
    "door",
    "hardware",
    "frame",
    "aluminum",
    "glazing",
    "window",
    "closer",
    "hinge",
    "lockset",
    "weatherstrip"
  ]
}
```

### division_08_sections.csv

| section_id | title | page | excerpt |
|------------|-------|------|---------|
| 081113 | HOLLOW METAL DOORS AND FRAMES | 234 | SECTION 08 11 13... |
| 083113 | ACCESS DOORS AND FRAMES | 241 | SECTION 08 31 13... |
| 087100 | DOOR HARDWARE | 248 | SECTION 08 71 00... |
| 088000 | GLAZING | 262 | SECTION 08 80 00... |

## Dependencies

```
pdfplumber
pandas
```

## Integration with Project Tracker

```python
# In project-tracker app.py or a route handler
from modules.doc_classification import extract_divisions_from_pdf

def analyze_spec_book(pdf_path: str, division: str = "08"):
    """Extract specific division from spec book."""
    divisions = extract_divisions_from_pdf(
        Path(pdf_path),
        target_divisions=[division]
    )

    if division in divisions:
        content = divisions[division]
        return {
            "division": content.division,
            "title": content.title,
            "pages": f"{content.start_page}-{content.end_page}",
            "sections": [
                {"id": s.section_id, "title": s.title, "page": s.page}
                for s in content.sections
            ]
        }
    return None
```

## Common Division 08 Sections

For glazing/openings work, these sections are typically most relevant:

| Section | Name | Relevance |
|---------|------|-----------|
| 08 11 13 | Hollow Metal Doors and Frames | Door scope |
| 08 14 16 | Flush Wood Doors | Door scope |
| 08 31 13 | Access Doors and Frames | Access panels |
| 08 41 13 | Aluminum-Framed Entrances | Storefront |
| 08 44 13 | Glazed Aluminum Curtain Walls | Curtain wall |
| 08 51 13 | Aluminum Windows | Window scope |
| 08 71 00 | Door Hardware | Hardware scope |
| 08 80 00 | Glazing | Glass types |
| 08 87 00 | Glazing Surface Films | Window film |

## Notes

- The extractor works best with properly formatted spec books that follow CSI conventions
- OCR-scanned PDFs may have lower accuracy due to text extraction quality
- For large spec books (500+ pages), use `max_pages` parameter during development
- Section excerpts capture ~20 lines to provide context without overwhelming storage
