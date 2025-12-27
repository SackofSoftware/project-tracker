# Project Brief Endpoint - Implementation Summary

## Overview
Added a new AI-powered endpoint to generate comprehensive project briefs for Division 8 (Openings) projects.

## Endpoint
`GET /api/project/<project_id>/brief`

## Features Implemented

### 1. Context Gathering (`gather_project_context` function)
Collects comprehensive project data from multiple sources:

- **Project Metadata**: Name, address, owner, architect, dates
- **Extracted Data**: Reads `extracted_project_data.json` for:
  - Window/door schedules with quantities and types
  - Division 8 scope information
  - Construction schedule details
- **Estimate Status**: Scans for takeoff spreadsheets using EstimateReader
- **Vendor Quotes**: Reads quote PDFs and extracts pricing using QuoteReader
- **Document Inventory**: Scans project folder for:
  - Specifications (PDFs with "spec", "division", "section")
  - Drawings (PDFs with "drawing", "sheet", "plan", "elevation")
  - Schedules (Excel files and schedule PDFs)
  - Quotes and addendums
- **Division 8 Specs**: Extracts Section 08xxxx from specification PDFs (if doc_classification available)

### 2. AI Brief Generation (`generate_project_brief` function)
Generates formatted project briefs using LLMs:

**AI Provider Priority:**
1. **LM Studio** (localhost:1234) - Primary, local inference
2. **OpenRouter** (amazon/nova-lite-v1) - Cloud fallback
3. **Simple text-based** - Non-AI fallback when APIs unavailable

**Brief Structure:**
```
PROJECT SUMMARY
[2-3 sentence overview of Division 8 work]

SCHEDULE
Start: [date] | Duration: [days] | Bid Date: [date]

DIVISION 8 SCOPE
[Spec sections, window/door types, manufacturers]

OPENINGS BREAKDOWN
Windows: [count and types]
Doors: [count and types]
Storefronts: [count if applicable]

DOCUMENTS AVAILABLE
✓ [Available docs]
✗ [Missing docs]

ESTIMATE STATUS
[Takeoff status, quote status, values]

NEXT STEPS
[Actionable recommendations]
```

### 3. Fallback Brief (`generate_simple_brief` function)
When AI is unavailable, generates a structured text brief using the gathered context data.

## Query Parameters

- `format=json|text` - Response format (default: json)
- `use_lm_studio=true|false` - Try LM Studio first (default: true)
- `force_openrouter=true|false` - Skip LM Studio (default: false)

## Response Formats

### JSON Format (default)
```json
{
  "status": "ok",
  "project_id": "21-27-neptune",
  "project_name": "21-27 Neptune",
  "brief": "[formatted text brief]",
  "context": {
    "project_metadata": {...},
    "openings_data": {...},
    "division_8_scope": {...},
    "estimate_status": {...},
    "quotes_data": {...},
    "available_documents": {...}
  },
  "errors": []
}
```

### Text Format (`?format=text`)
Returns plain text brief suitable for:
- Direct display in terminal
- Copy/paste into emails or documents
- Integration with other tools

## Usage Examples

```bash
# Basic usage (JSON with context)
curl http://localhost:5003/api/project/21-27-neptune/brief

# Plain text output
curl http://localhost:5003/api/project/21-27-neptune/brief?format=text

# Force OpenRouter (skip LM Studio)
curl http://localhost:5003/api/project/21-27-neptune/brief?force_openrouter=true

# Disable LM Studio, use OpenRouter or fallback
curl http://localhost:5003/api/project/21-27-neptune/brief?use_lm_studio=false
```

## Error Handling

- **Project not found**: Returns 404 with error message
- **Project folder missing**: Returns 404 with path information
- **Missing data**: Brief still generates with available data, marks items as "TBD"
- **AI failure**: Automatically falls back to next provider or simple brief
- **Document read errors**: Captured in `errors` array, doesn't fail the request

## Testing

Run the test suite:
```bash
cd /Users/andrewhawes/NEECS\ Dropbox/Andrew\ Hawes/Python/project-tracker
python3 test_brief_endpoint.py
```

## Integration Points

The endpoint integrates with existing modules:
- `EstimateReader` - Reads takeoff spreadsheets
- `QuoteReader` - Parses vendor quote PDFs
- `FileOrganizer` - Scans project documents
- `extract_divisions_from_pdf` - Extracts Division 8 specs (if available)

## Files Modified

1. **`app.py`** - Added three functions and one route:
   - `gather_project_context()` - Data collection
   - `generate_project_brief()` - AI generation
   - `generate_simple_brief()` - Fallback generation
   - `@app.route('/api/project/<project_id>/brief')` - Endpoint

2. **`CLAUDE.md`** - Updated API documentation

3. **`test_brief_endpoint.py`** (NEW) - Test suite

## Future Enhancements

Potential improvements:
1. Cache generated briefs with TTL
2. Add support for custom brief templates
3. Include photos/thumbnails in brief
4. Export briefs as PDF
5. Email brief to stakeholders
6. Compare briefs across multiple projects
7. Track brief generation history
8. Add real-time streaming for long-running AI generations
