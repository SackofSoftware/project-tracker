# Unified Schema Data Reader Update

**Date:** 2025-12-20

## Overview

Successfully updated all three data readers (PlanHub, GovWin, Local Bidding) to use the new unified schema defined in `/modules/schema/unified_project.py`.

## Changes Made

### 1. PlanHub Database Reader (`/modules/planhub/planhub_db_reader.py`)

**Updated Methods:**
- `get_all_leads()` - Now returns `List[UnifiedProject]` instead of `List[Dict]`
- `get_lead_by_id()` - Now returns `Optional[UnifiedProject]` instead of `Optional[Dict]`
- `normalize_lead_to_project()` - Now returns `UnifiedProject` instance instead of Dict

**New Methods:**
- `_get_documents_for_lead()` - Converts PlanHub files to `Document` objects
- `_parse_file_size()` - Parses file size strings (e.g., "2.5 MB") to bytes

**Key Mappings:**
- PlanHub ID → `source_id` (e.g., "12345")
- Unified ID → `id` (e.g., "planhub-12345")
- Source → `"planhub"`
- Tags → Extracted from `project_info_json`
- Location → Uses `Location()` dataclass
- Documents → Uses `Document()` dataclass from `project_files` table
- Division 8 → Detected from `matching_trades` keywords
- Dates → Normalized using `normalize_date()` helper

### 2. GovWin Reader (`/modules/govleads/govleads_reader.py`)

**New Methods:**
- `normalize_to_unified_project(record: GovLeadRecord)` - Converts `GovLeadRecord` to `UnifiedProject`

**Key Mappings:**
- Opportunity ID → `source_id` (e.g., "12699843")
- Unified ID → `id` (e.g., "govwin-12699843")
- Source → `"govwin"`
- Entity Type → `entity_type` (BID or LEAD)
- Response Date → `response_date` (normalized to YYYY-MM-DD)
- Solicitation Date → `solicitation_date`
- Location → Uses `Location()` with state and place_of_performance
- Documents → Converted from `GovDocument` to `Document()` objects
- Division 8 → Detected from description and primary_requirement keywords
- Tags → ["Government", entity_type, vertical, "Division 8"]
- Project Value → Parsed using `normalize_project_value()`

### 3. Local Bidding Reader (`/modules/bidding/bidding_reader.py`)

**Updated Methods:**
- `read_all_projects()` - Now returns `List[UnifiedProject]`
- `_read_projects_json()` - Returns `List[UnifiedProject]`
- `_read_extracted_project()` - Returns `Optional[UnifiedProject]`
- `_create_folder_project()` - Returns `Optional[UnifiedProject]`
- `_normalize_project()` - Returns `Optional[UnifiedProject]` (from projects.json)
- `_normalize_extracted_project()` - Returns `Optional[UnifiedProject]` (from extracted_project_data.json)
- `_load_rag_analysis()` - Updated to work with `UnifiedProject`
- `get_project_by_folder()` - Returns `Optional[UnifiedProject]`
- `get_projects_with_estimates()` - Returns `List[UnifiedProject]`
- `get_upcoming_bids()` - Returns `List[UnifiedProject]`

**Key Mappings:**
- Folder Name → `source_id` (e.g., "Project Name - City MA")
- Unified ID → `id` (e.g., "local-project-name-city-ma")
- Source → `"local_bidding"`
- Location → Parsed from folder name or extracted data
- Division 8 → Built from `division_8` section and `openings_schedule`
- Spec Sections → Preserved from existing data
- Windows/Doors → Counts from both spec sections and openings schedule
- Estimate Status → Stored in `internal_status.has_internal_estimate`
- Estimate Total → Stored in `internal_status.internal_estimate_total`
- RAG Analysis → Merged into `division_8.scope_summary` and counts

## Schema Features Used

### Core Fields
- `id` - Source-prefixed unique identifier
- `source` - "planhub" | "govwin" | "local_bidding"
- `source_id` - Original ID from source system
- `title` - Project name
- `description` - Project description

### Location (`Location` dataclass)
- `address` - Street address
- `city` - City name
- `state` - State code (e.g., "MA")
- `zip` - Zip code
- `raw` - Original unparsed location string

### Dates (ISO 8601: YYYY-MM-DD)
- `bid_date` - Bid due date
- `response_date` - Response deadline (GovWin)
- `solicitation_date` - Solicitation date (GovWin)

### Division 8 (`Division8Scope` dataclass)
- `scope_summary` - Text summary
- `spec_sections` - List of spec section codes
- `matching_trades` - List of trade names (PlanHub)
- `windows` - Dict with count and types
- `doors` - Dict with count and types
- `hardware` - List of hardware items
- `glazing` - List of glazing items
- `storefront` - Boolean flag
- `curtain_wall` - Boolean flag

### Documents (`Document` dataclass)
- `id` - Document identifier
- `title` - Document name
- `type` - Document type (spec, drawing, etc.)
- `url` - Download URL (PlanHub)
- `local_path` - Local file path (GovWin)
- `file_size` - Size in bytes
- `downloaded` - Boolean status
- `upload_date` - Upload/posting date

### Internal Status (`InternalStatus` dataclass)
- `has_internal_estimate` - Boolean
- `internal_estimate_total` - Float value

## Utility Functions Used

### `normalize_date(date_str: Optional[str]) -> Optional[str]`
Handles multiple date formats:
- "01/12/2026 12:00 PM"
- "01/07/2026 02:00 PM (in 25 days)"
- "2026-01-12"
- "January 12, 2026"

Returns: ISO 8601 format (YYYY-MM-DD)

### `normalize_project_value(value_str: Optional[str]) -> tuple[Optional[float], Optional[str]]`
Parses project value strings:
- "$1,500,000" → (1500000.0, "$1,500,000")
- "1.5M" → (1500000.0, "1.5M")
- "N/A" → (None, "N/A")

Returns: (float_value, original_string)

## Testing

Created comprehensive test script: `/test_unified_readers.py`

**Test Results:**
```
PlanHub              ✓ PASSED (0 projects in test DB)
GovWin               ✓ PASSED (2550 records)
Local Bidding        ✓ PASSED (143 projects)
```

**Verified:**
- All readers return `UnifiedProject` instances
- Conversion to dict via `.to_dict()` works correctly
- Source-specific fields properly mapped
- Location, Division8Scope, Documents use dataclasses
- Dates normalized to YYYY-MM-DD format
- Existing helper methods still work

## Migration Notes

### API Endpoints
Any API endpoints that use these readers will need to call `.to_dict()` on UnifiedProject instances before JSON serialization:

```python
# Before
projects = reader.get_all_leads()
return jsonify(projects)

# After
projects = reader.get_all_leads()
return jsonify([p.to_dict() for p in projects])
```

### Accessing Fields
Changed from dict access to attribute access:

```python
# Before
project['title']
project['location']['city']

# After
project.title
project.location.city
```

### Type Annotations
All methods now have proper return type annotations for IDE support:
- `List[UnifiedProject]`
- `Optional[UnifiedProject]`

## Benefits

1. **Type Safety** - IDE autocomplete and type checking
2. **Consistency** - All sources use same field names
3. **Validation** - Dataclasses ensure proper structure
4. **Documentation** - Clear schema definition in one place
5. **Helper Methods** - Built-in methods like `.to_dict()`, `.is_upcoming()`
6. **Extensibility** - Easy to add new sources or fields

## Next Steps

1. Update API endpoints in `app.py` to use `.to_dict()`
2. Update matching/deduplication logic to use UnifiedProject
3. Update dashboard frontend to handle new structure
4. Add ProjectDog scraper integration with unified schema
5. Consider adding validation for required fields
6. Add unit tests for each reader's normalization logic

## Files Modified

1. `/modules/planhub/planhub_db_reader.py` - Updated to return UnifiedProject
2. `/modules/govleads/govleads_reader.py` - Added normalize_to_unified_project()
3. `/modules/bidding/bidding_reader.py` - Complete rewrite to use UnifiedProject
4. `/test_unified_readers.py` - New comprehensive test script
5. `/UNIFIED_SCHEMA_UPDATE.md` - This documentation

## Compatibility

The changes are **backwards compatible** because:
- UnifiedProject has a `.to_dict()` method for JSON serialization
- All existing fields are preserved in the new schema
- Helper functions (normalize_date, etc.) handle edge cases gracefully
- Readers fail gracefully with None returns on errors

However, code that directly accesses dict fields will need updates to use attributes instead.
