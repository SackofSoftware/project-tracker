# Drawing Discipline Identifier

Identifies construction drawing disciplines from sheet numbers and title blocks using the U.S. National CAD Standard (NCS).

## Overview

Construction drawings use standardized sheet numbering that encodes:
- **Discipline** (Architectural, Structural, Mechanical, etc.)
- **Sheet Type** (Plans, Elevations, Details, Schedules, etc.)
- **Sequence Number**

This module extracts and decodes this information using:
1. **Text-based parsing** - Regex patterns on extracted PDF text
2. **Vision-based analysis** - LM Studio with Qwen3-VL for title block reading

## Source

Based on: `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/DrawingReview/python-backend/app/pdf_analyzer.py`

## Files

| File | Purpose |
|------|---------|
| `drawing_discipline_identifier.py` | Complete identification module |

## NCS Sheet Numbering Format

Standard format: `[DISCIPLINE]-[TYPE][SEQUENCE][MODIFIER]`

Example: **A-201** = Architectural, Elevations, Sheet 01

### Discipline Codes

| Code | Discipline | Notes |
|------|------------|-------|
| **G** | General | Cover sheets, legends |
| **C** | Civil | Site, grading, utilities |
| **L** | Landscape | Planting, irrigation |
| **S** | Structural | Framing, foundations |
| **A** | Architectural | Plans, elevations, details |
| AD | Architectural Demolition | Demo plans |
| AE | Architectural Existing | As-built conditions |
| AF | Architectural Finishes | Finish schedules |
| **I** | Interiors | Interior design |
| **F/FP** | Fire Protection | Sprinkler, suppression |
| **P** | Plumbing | Domestic water, sanitary |
| **M** | Mechanical | HVAC, ventilation |
| **E** | Electrical | Power, systems |
| EL | Electrical Lighting | Lighting plans |
| EP | Electrical Power | Power plans |
| **T** | Telecommunications | Data, A/V, security |

### Sheet Type Codes (Second Digit)

| Code | Type | Description |
|------|------|-------------|
| 0xx | General | Cover, legends, code summaries |
| 1xx | Plans | Floor plans, site plans, framing |
| 2xx | Elevations | Interior or exterior elevations |
| 3xx | Sections | Building or wall sections |
| 4xx | Large-scale | Enlarged plans, sections |
| 5xx | Details | Construction details |
| 6xx | Schedules | Door, window, finish schedules |
| 7xx | User-defined | Project-specific content |
| 9xx | 3D/Renderings | Isometric, perspectives |

## Usage

### Basic Text-Based Identification

```python
from doc_classification import (
    extract_discipline_from_sheet_id,
    identify_sheet_from_text,
    identify_sheets_in_pdf
)

# Parse a known sheet ID
code, name, sheet_type = extract_discipline_from_sheet_id("A-201")
print(f"Discipline: {name}")  # "Architectural"
print(f"Type: {sheet_type}")  # "Elevations (interior or exterior)"

# Identify from extracted text
text = """
NORTH ELEVATION
Scale: 1/4" = 1'-0"
...
Project Name: Example Building
A-201
"""
result = identify_sheet_from_text(text)
print(f"Sheet: {result.sheet_id}")        # "A-201"
print(f"Discipline: {result.discipline_name}")  # "Architectural"
print(f"Confidence: {result.confidence}")  # 0.7
```

### Process Entire Drawing Set

```python
from doc_classification import identify_sheets_in_pdf, summarize_disciplines

# Text-only identification (fast, no LM Studio required)
results = identify_sheets_in_pdf("/path/to/drawings.pdf", use_vision=False)

# Vision-based identification (requires LM Studio running)
results = identify_sheets_in_pdf(
    "/path/to/drawings.pdf",
    use_vision=True,
    lm_studio_url="http://localhost:1234/v1/chat/completions"
)

# Get discipline summary
summary = summarize_disciplines(results)
print(f"Total sheets: {summary['total_sheets']}")
print(f"By discipline: {summary['by_discipline']}")
# {'Architectural': 45, 'Structural': 12, 'Mechanical': 18, ...}
```

### Vision-Based Title Block Reading

```python
from doc_classification import (
    create_titleblock_crop,
    identify_sheet_with_vision
)

# Create high-res title block crop
create_titleblock_crop(
    pdf_path="/path/to/drawings.pdf",
    page_num=5,
    output_path="/tmp/titleblock.jpg",
    dpi=300
)

# Identify using vision model
result = identify_sheet_with_vision(
    "/tmp/titleblock.jpg",
    lm_studio_url="http://localhost:1234/v1/chat/completions",
    model="qwen3-vl-4b-instruct-mlx"
)

print(f"Sheet: {result.sheet_id}")
print(f"Title: {result.sheet_title}")
print(f"Confidence: {result.confidence}")
```

## Data Classes

### SheetIdentification

```python
@dataclass
class SheetIdentification:
    sheet_id: str          # "A-201"
    discipline_code: str   # "A"
    discipline_name: str   # "Architectural"
    sheet_type: str        # "Elevations (interior or exterior)"
    sheet_title: str       # "North Elevation"
    confidence: float      # 0.0-1.0
    method: str            # "text" or "vision"
```

## Functions

| Function | Purpose |
|----------|---------|
| `extract_discipline_from_sheet_id(sheet_id)` | Parse discipline from sheet number |
| `extract_sheet_id_from_text(text)` | Find sheet ID in extracted text |
| `identify_sheet_from_text(text)` | Full identification from text |
| `identify_sheet_with_vision(image_path)` | Vision model identification |
| `create_titleblock_crop(pdf_path, page_num, output_path)` | Create title block image |
| `identify_sheets_in_pdf(pdf_path)` | Process entire PDF |
| `summarize_disciplines(results)` | Aggregate discipline counts |

## Title Block Location

Construction drawings place title blocks in the **bottom-right corner**. The module:

1. Converts page at 300 DPI
2. Crops to **bottom 50%** and **rightmost 15%**
3. Sends crop to vision model for analysis

```
┌─────────────────────────────────┐
│                                 │
│       Drawing Content           │
│                                 │
│                                 │
├─────────────────────────┬───────┤
│                         │ Title │  ← Vision model
│    (ignored)            │ Block │    reads this area
│                         │       │
└─────────────────────────┴───────┘
```

## Vision Model Prompt

The vision model receives this prompt for title block analysis:

```
You are an expert in reading construction document title blocks
following U.S. National CAD Standard (NCS).

DISCIPLINE CODES:
- G: General, C: Civil, L: Landscape, S: Structural
- A: Architectural, AD: Arch Demolition, AE: Arch Existing
- F: Fire Protection, P: Plumbing, M: Mechanical
- E: Electrical, EL: Electrical Lighting, EP: Electrical Power
- T: Telecommunications, Z: Shop Drawings

OUTPUT FORMAT (JSON only):
{
  "Sheet_ID": "A-201",
  "Discipline": "Architectural",
  "Sheet_Title": "Exterior Elevations",
  "Confidence": 0.94
}
```

## Requirements

### Text-Only Mode
```
pdfplumber
```

### Vision Mode (additional)
```
pdf2image
Pillow
requests
```

Plus LM Studio running with a vision model (e.g., `qwen3-vl-4b-instruct-mlx`)

## Integration with Project Tracker

```python
# In project-tracker app.py
from modules.doc_classification import (
    identify_sheets_in_pdf,
    summarize_disciplines
)

def analyze_drawing_set(pdf_path: str, use_vision: bool = False):
    """Analyze drawing set and return discipline breakdown."""
    results = identify_sheets_in_pdf(pdf_path, use_vision=use_vision)
    summary = summarize_disciplines(results)

    return {
        "total_sheets": summary["total_sheets"],
        "disciplines": summary["by_discipline"],
        "sheet_types": summary["by_sheet_type"],
        "sheets": summary["sheets"]
    }
```

## Example Output

### summarize_disciplines() Result

```json
{
  "total_sheets": 87,
  "by_discipline": {
    "Architectural": 42,
    "Structural": 15,
    "Mechanical": 12,
    "Electrical": 10,
    "Plumbing": 5,
    "Fire Protection": 3
  },
  "by_sheet_type": {
    "Plans (floor plans, site plans, framing plans)": 35,
    "Details (construction details)": 22,
    "Schedules/Diagrams (equipment, doors, windows)": 12,
    "Sections (building or wall sections)": 10,
    "Elevations (interior or exterior)": 8
  },
  "sheets": [
    {"sheet_id": "G-001", "discipline": "General", "title": "Cover Sheet", "confidence": 0.9},
    {"sheet_id": "A-101", "discipline": "Architectural", "title": "First Floor Plan", "confidence": 0.85},
    {"sheet_id": "A-201", "discipline": "Architectural", "title": "Exterior Elevations", "confidence": 0.88}
  ]
}
```

## Confidence Levels

| Level | Meaning |
|-------|---------|
| 0.9+ | High confidence - clear sheet ID found |
| 0.7-0.9 | Good confidence - sheet ID parsed from text |
| 0.5-0.7 | Moderate - partial match or inference |
| < 0.5 | Low confidence - best guess |

## Comparison: Text vs Vision

| Aspect | Text-Only | Vision |
|--------|-----------|--------|
| Speed | Fast (~0.1s/page) | Slow (~3-5s/page) |
| Dependencies | pdfplumber only | LM Studio + vision model |
| Accuracy | Good for clear text | Better for scanned/complex |
| Title extraction | Basic pattern matching | Full title block reading |
| Offline | Yes | Requires LM Studio |

## Notes

- Text-based extraction works best when PDFs have selectable text
- Vision mode requires LM Studio running on localhost:1234
- For scanned drawings or low-quality PDFs, vision mode is recommended
- The title block crop focuses on bottom-right where most firms place title blocks
- Some firms use non-standard locations - vision mode handles these better
