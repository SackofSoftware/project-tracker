# Scope Blueprint Documentation

Flask Blueprint for document classification and scope analysis APIs.

**File Location:** `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/project-tracker/routes/scope.py`

## Overview

The Scope Blueprint handles all document classification and scope analysis endpoints for the project-tracker application. It provides both synchronous and asynchronous endpoints for analyzing project specifications and drawings.

## Features

### Division 8 Scope Extraction
- Extracts Division 08 (Openings) content from specification PDFs
- Identifies door, window, hardware, and glazing sections
- Supports both synchronous and asynchronous processing
- Thread-safe async state management

### Drawing Discipline Analysis
- Identifies drawing sheets by discipline (Architectural, Structural, MEP, etc.)
- Classifies sheets according to NCS (National CAD Standard) codes
- Supports both synchronous and asynchronous processing
- Thread-safe async state management

### Full Scope Analysis
- Combines specifications and drawings data
- Provides comprehensive project scope overview
- Includes file organization and quote detection

## API Endpoints

### Division 8 Scope - Synchronous
```
GET /api/project/<project_id>/scope/division8
```
Extracts Division 8 content from spec PDFs synchronously. May timeout on large projects.

**Response:**
```json
{
  "project_id": "string",
  "project_name": "string",
  "division8_scope": [
    {
      "source_file": "string",
      "division": "08",
      "title": "string",
      "start_page": 0,
      "end_page": 0,
      "sections": [
        {
          "section_id": "string",
          "title": "string",
          "page": 0,
          "excerpt": "string"
        }
      ]
    }
  ],
  "spec_files_found": 0,
  "spec_files_processed": 0
}
```

### Division 8 Scope - Async

**Start Analysis:**
```
POST /api/project/<project_id>/scope/division8/analyze
```
Starts Division 8 analysis in background thread.

**Response:**
```json
{
  "status": "started",
  "project_id": "string",
  "message": "Division 8 analysis started in background"
}
```

**Check Status:**
```
GET /api/project/<project_id>/scope/division8/status
```

**Response:**
```json
{
  "status": "running|complete|error|not_started",
  "progress": 0.5,
  "error": "string (if status=error)"
}
```

**Get Results:**
```
GET /api/project/<project_id>/scope/division8/result
```

**Response:** Same as synchronous endpoint

### Drawing Disciplines - Synchronous
```
GET /api/project/<project_id>/scope/drawings
```
Analyzes drawing PDFs to identify disciplines synchronously. May timeout on large projects.

**Response:**
```json
{
  "project_id": "string",
  "project_name": "string",
  "summary": {
    "A": {"count": 0, "name": "Architectural"},
    "S": {"count": 0, "name": "Structural"}
  },
  "sheets": [
    {
      "source_file": "string",
      "sheet_id": "string",
      "discipline_code": "string",
      "discipline_name": "string",
      "sheet_type": "string",
      "sheet_title": "string",
      "confidence": 0.0,
      "method": "string"
    }
  ],
  "drawing_files_found": 0,
  "available_disciplines": {}
}
```

### Drawing Disciplines - Async

**Start Analysis:**
```
POST /api/project/<project_id>/scope/drawings/analyze
```

**Check Status:**
```
GET /api/project/<project_id>/scope/drawings/status
```

**Get Results:**
```
GET /api/project/<project_id>/scope/drawings/result
```

(Responses follow same pattern as Division 8 async endpoints)

### Full Scope Analysis
```
GET /api/project/<project_id>/scope/full
```
Returns comprehensive scope analysis combining specs, drawings, and file organization.

**Response:**
```json
{
  "project_id": "string",
  "project_name": "string",
  "project_folder": "string",
  "file_summary": {},
  "quotes_found": 0,
  "quotes": [],
  "endpoints": {
    "division8_scope": "/api/project/{id}/scope/division8",
    "drawing_disciplines": "/api/project/{id}/scope/drawings",
    "file_organization": "/api/project/{id}/files"
  },
  "doc_classification_available": true
}
```

## Dependencies

### Required
- `flask`: Web framework
- `utils`: Project utilities (find_project_by_id, get_project_folder_path, BIDDING_FOLDER)
- `modules.files`: FileOrganizer for file scanning

### Optional
- `modules.doc_classification`: Document analysis (extract_divisions_from_pdf, identify_sheets_in_pdf, summarize_disciplines, DISCIPLINE_CODES)
  - If not available, all endpoints return 503 Service Unavailable

## State Management

### Division 8 Analysis State
```python
_division8_status = {}  # project_id -> {status, progress, result, error}
_division8_lock = threading.Lock()
```

**Status Structure:**
- `status`: "running" | "complete" | "error" | "not_started"
- `progress`: Float 0.0-1.0
- `result`: Analysis results (when status=complete)
- `error`: Error message (when status=error)

### Drawings Analysis State
```python
_drawings_status = {}  # project_id -> {status, progress, result, error}
_drawings_lock = threading.Lock()
```

**Status Structure:** Same as Division 8

## Thread Safety

All async operations use threading locks to ensure thread-safe access to status dictionaries:
- Status reads/writes are protected by locks
- Background threads update progress safely
- Multiple concurrent requests for the same project are prevented (409 Conflict)

## Error Handling

### 404 Not Found
- Project not found
- Project folder not found
- No analysis found for result endpoint

### 400 Bad Request
- Analysis not complete when requesting results

### 409 Conflict
- Analysis already in progress

### 503 Service Unavailable
- Document classification module not available (missing dependencies)

## Blueprint Registration

The blueprint is registered in `/routes/__init__.py`:

```python
from .scope import scope_bp
app.register_blueprint(scope_bp)
```

## Module Structure

```
routes/
├── __init__.py           # Blueprint registration
├── scope.py              # This blueprint
└── SCOPE_BLUEPRINT_README.md  # This file
```

## Usage Examples

### Synchronous Analysis
```bash
# Get Division 8 scope
curl http://localhost:5003/api/project/my-project/scope/division8

# Get drawing disciplines
curl http://localhost:5003/api/project/my-project/scope/drawings

# Get full scope
curl http://localhost:5003/api/project/my-project/scope/full
```

### Async Analysis
```bash
# Start Division 8 analysis
curl -X POST http://localhost:5003/api/project/my-project/scope/division8/analyze

# Check status
curl http://localhost:5003/api/project/my-project/scope/division8/status

# Get results (when complete)
curl http://localhost:5003/api/project/my-project/scope/division8/result
```

## Performance Notes

### Synchronous Endpoints
- Division 8: Processes up to 5 PDFs, max 200 pages each
- Drawings: Processes up to 10 PDFs
- May timeout on very large projects (use async for large projects)

### Async Endpoints
- Run in background threads
- No timeout limits
- Progress tracking available
- Results cached in memory (lost on server restart)

## Future Enhancements

Potential improvements:
- [ ] Persistent result storage (database or file cache)
- [ ] WebSocket support for real-time progress updates
- [ ] Configurable PDF/page limits
- [ ] Batch analysis of multiple projects
- [ ] Result export (PDF reports, Excel summaries)
- [ ] Vision API integration for better sheet identification
- [ ] Division 8 content extraction beyond just section identification
