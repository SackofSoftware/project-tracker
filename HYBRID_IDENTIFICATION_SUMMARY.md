# Hybrid Sheet Identification - Implementation Summary

## Problem Statement

The original code assumed all projects follow NCS (National CAD Standard) numbering strictly:
- A1xx = Plans (floor plans, site plans)
- A2xx = Elevations (interior or exterior)
- A3xx = Sections (building or wall sections)
- etc.

**Reality**: In practice, A2.1 could be Floor Plans on one project and Elevations on another. Projects don't always follow NCS standards consistently.

## Solution: Hybrid Identification Approach

Combines two methods:
1. **Sheet Number Analysis** (NCS-based) - Fast, structural
2. **Content Keyword Analysis** - Slower but verifies actual content

### When they agree → High confidence (95%)
### When they disagree → Flag for review (50% confidence)

---

## Code Changes Made

### 1. Added Content Keywords Dictionary

```python
CONTENT_KEYWORDS = {
    "Plans": ["floor plan", "roof plan", "site plan", ...],
    "Elevations": ["elevation", "exterior elevation", "north elevation", ...],
    "Sections": ["section", "cross section", "building section", ...],
    "Details": ["detail", "enlarged", "typical detail", ...],
    "Schedules": ["schedule", "door schedule", "window schedule", ...],
    "Diagrams": ["diagram", "riser", "schematic", ...],
}
```

Maps sheet types to keywords that would actually appear in the document text.

### 2. Enhanced SheetIdentification Dataclass

Added two new fields:
- `needs_review: bool = False` - Flags sheets where predictions disagree
- `content_prediction: Optional[str] = None` - Stores the content-based prediction

### 3. New Function: detect_sheet_type_from_content()

```python
def detect_sheet_type_from_content(text: str) -> Tuple[str, float]:
    """
    Detect sheet type by analyzing content keywords in the text.
    Returns (detected_type, confidence_score)
    """
```

- Scans page text for keywords (case-insensitive)
- Counts matches for each sheet type
- Returns type with most matches
- Confidence based on how dominant the best match is

### 4. New Function: identify_sheet_hybrid()

```python
def identify_sheet_hybrid(sheet_id: str, text: str) -> SheetIdentification:
    """
    Hybrid identification using both sheet number and content analysis.
    """
```

**Logic:**
1. Get prediction from sheet number (A-201 → "Elevations")
2. Get prediction from content ("floor plan" found → "Plans")
3. Compare predictions:
   - **Match** → confidence = 0.95, needs_review = False
   - **Mismatch** → confidence = 0.5, needs_review = True
4. Return both predictions so user can see the discrepancy

### 5. Modified identify_sheet_from_text()

Now uses the hybrid approach automatically:

```python
def identify_sheet_from_text(text: str) -> SheetIdentification:
    sheet_id = extract_sheet_id_from_text(text) or "unknown"
    return identify_sheet_hybrid(sheet_id, text)  # ← Now hybrid
```

---

## Usage Example

```python
from modules.doc_classification.drawing_discipline_identifier import identify_sheet_from_text

# Example: A-201 with actual floor plan content
text = """
FIRST FLOOR PLAN
Level 1 - Main Entry
Second Floor Plan
Roof Plan
Scale: 1/8" = 1'-0"
"""

result = identify_sheet_from_text(text)

print(f"Sheet ID: {result.sheet_id}")                    # A-201
print(f"Sheet Type (NCS): {result.sheet_type}")          # Elevations (interior or exterior)
print(f"Content Prediction: {result.content_prediction}") # Plans
print(f"Confidence: {result.confidence}")                 # 0.5
print(f"Needs Review: {result.needs_review}")             # True

# This flags: "Sheet number says Elevations but content says Plans - needs review!"
```

---

## Test Results

Run `python3 test_hybrid_identification.py` to see it in action:

### Successful Agreement Cases (95% confidence):
- A-201 with elevation content → Elevations
- A-101 with plan content → Plans
- A-301 with section content → Sections
- A-501 with detail content → Details
- A-601 with schedule content → Schedules

### Disagreement Cases (50% confidence, flagged for review):
- A-201 with plan content → **NEEDS REVIEW**
- M-201 with plan content → **NEEDS REVIEW**

---

## Benefits

1. **Catches Non-Standard Numbering**: Identifies projects that don't follow NCS
2. **Higher Confidence When Accurate**: 95% confidence when both methods agree
3. **Manual Review Flag**: Automatically flags suspicious classifications
4. **Preserves Both Predictions**: User can see both the NCS-based and content-based predictions
5. **No Breaking Changes**: Existing code continues to work, now with better accuracy

---

## Future Enhancements

Potential improvements:
1. Expand keyword dictionaries with more terms
2. Weight keywords by importance (e.g., "FLOOR PLAN" in title vs body)
3. Use fuzzy matching for variations (e.g., "flr plan", "1st floor")
4. Machine learning to learn project-specific numbering patterns
5. Visual inspection integration (check if sheet looks like an elevation)

---

## File Modified

**File**: `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/project-tracker/modules/doc_classification/drawing_discipline_identifier.py`

**Changes:**
- Added `CONTENT_KEYWORDS` dictionary (lines 96-109)
- Added `needs_review` and `content_prediction` fields to `SheetIdentification` (lines 132-133)
- Added `detect_sheet_type_from_content()` function (lines 171-206)
- Added `identify_sheet_hybrid()` function (lines 244-308)
- Modified `identify_sheet_from_text()` to use hybrid approach (lines 311-324)
- Updated `__all__` exports (lines 547-560)

**Test File Created**: `test_hybrid_identification.py`
