# Quick Reference: Hybrid Sheet Identification

## What Changed?

The sheet identifier now **verifies** that sheet numbers match actual content.

### Before:
- A-201 → "Elevations" (always, based on NCS)
- No verification of actual content
- Assumes all projects follow NCS standards

### After:
- A-201 → Checks both number AND content
- If content has "floor plan" keywords → Flags for review
- If content has "elevation" keywords → High confidence match
- Confidence scores reflect agreement/disagreement

---

## Key Functions

### 1. detect_sheet_type_from_content(text: str)
```python
# Returns (sheet_type, confidence)
result = detect_sheet_type_from_content("First Floor Plan Level 1")
# Returns: ("Plans", 1.0)
```

### 2. identify_sheet_hybrid(sheet_id: str, text: str)
```python
# Combines sheet number + content analysis
result = identify_sheet_hybrid("A-201", "North Elevation South Elevation")
# result.confidence = 0.95 (agreement)
# result.needs_review = False

result = identify_sheet_hybrid("A-201", "First Floor Plan")
# result.confidence = 0.5 (disagreement)
# result.needs_review = True
# result.content_prediction = "Plans"
```

### 3. identify_sheet_from_text(text: str)
```python
# Now automatically uses hybrid approach
result = identify_sheet_from_text(pdf_page_text)
```

---

## New Fields in SheetIdentification

```python
@dataclass
class SheetIdentification:
    # ... existing fields ...
    needs_review: bool = False              # NEW: Flags disagreements
    content_prediction: Optional[str] = None # NEW: Content-based prediction
```

---

## Confidence Levels

| Scenario | Confidence | Needs Review |
|----------|-----------|--------------|
| Sheet number + content agree | 95% | False |
| Sheet number only (no content match) | 70% | False |
| Sheet number + content disagree | 50% | **True** |
| No sheet ID found | 30% | False |

---

## Content Keywords Reference

**Plans**: floor plan, roof plan, site plan, framing plan, level 1, level 2, first floor, second floor, ground floor, basement plan, mezzanine

**Elevations**: elevation, exterior elevation, interior elevation, north elevation, south elevation, east elevation, west elevation, facade, front elevation

**Sections**: section, cross section, building section, wall section, longitudinal section, transverse section, section cut

**Details**: detail, enlarged, typical detail, construction detail, enlarged plan, enlarged section, partial plan

**Schedules**: schedule, door schedule, window schedule, finish schedule, hardware schedule, equipment schedule, room schedule, fixture schedule

**Diagrams**: diagram, riser, schematic, one-line, riser diagram, schematic diagram, system diagram

---

## Example: Checking for Discrepancies

```python
from modules.doc_classification.drawing_discipline_identifier import identify_sheets_in_pdf

# Process entire PDF
results = identify_sheets_in_pdf("drawings.pdf", use_vision=False)

# Find sheets that need review
flagged_sheets = [r for r in results if r.needs_review]

for sheet in flagged_sheets:
    print(f"⚠️  {sheet.sheet_id}")
    print(f"   Sheet number says: {sheet.sheet_type}")
    print(f"   Content says: {sheet.content_prediction}")
    print(f"   → Manual review recommended!")
```

---

## Testing

Run the test suite to see examples:

```bash
python3 test_hybrid_identification.py
```

This demonstrates:
- ✅ Agreement cases (95% confidence)
- ⚠️ Disagreement cases (50% confidence, flagged)
- How the system handles various sheet types

---

## Backward Compatibility

✅ All existing code continues to work
✅ No breaking changes to API
✅ New fields have default values
✅ Enhanced accuracy is automatic
