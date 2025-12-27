# Async Scope Analysis Endpoints Implementation

## Summary

Successfully implemented async processing for scope analysis endpoints in the Flask app to prevent timeouts when processing large PDF projects.

## Changes Made

### 1. Added Thread-Safe Status Tracking (Lines 769-773)

```python
# Scope analysis state tracking (thread-safe)
_division8_status = {}  # project_id -> {status, progress, result, error}
_division8_lock = threading.Lock()
_drawings_status = {}  # project_id -> {status, progress, result, error}
_drawings_lock = threading.Lock()
```

### 2. Updated Synchronous Endpoints

Both synchronous endpoints were updated with documentation noting they may timeout for large projects and should use async endpoints instead:

- **Division 8 Endpoint** (Line 1153): `/api/project/<project_id>/scope/division8`
- **Drawings Endpoint** (Line 1581): `/api/project/<project_id>/scope/drawings`

### 3. New Division 8 Async Endpoints

#### POST `/api/project/<project_id>/scope/division8/analyze` (Line 1283)
- Starts Division 8 analysis in background thread
- Returns immediately with status "started"
- Thread-safe duplicate detection (returns 409 if already running)
- Progress tracking from 0 to 1.0

#### GET `/api/project/<project_id>/scope/division8/status` (Line 1412)
- Returns current analysis status
- Possible statuses: `not_started`, `running`, `complete`, `error`
- Includes progress percentage when running

#### GET `/api/project/<project_id>/scope/division8/result` (Line 1421)
- Returns analysis result when complete
- Returns 404 if no analysis found
- Returns 400 if analysis not complete
- Result format matches synchronous endpoint

### 4. New Drawings Async Endpoints

#### POST `/api/project/<project_id>/scope/drawings/analyze` (Line 1437)
- Starts drawings discipline analysis in background thread
- Returns immediately with status "started"
- Thread-safe duplicate detection (returns 409 if already running)
- Progress tracking from 0 to 1.0

#### GET `/api/project/<project_id>/scope/drawings/status` (Line 1558)
- Returns current analysis status
- Possible statuses: `not_started`, `running`, `complete`, `error`
- Includes progress percentage when running

#### GET `/api/project/<project_id>/scope/drawings/result` (Line 1567)
- Returns analysis result when complete
- Returns 404 if no analysis found
- Returns 400 if analysis not complete
- Result format matches synchronous endpoint

## Implementation Pattern

The implementation follows the existing extraction endpoint pattern:

1. **Status Dictionary**: Each analysis type has its own status dictionary and lock
2. **Background Thread**: Processing happens in a separate thread
3. **Progress Tracking**: Progress updates from 0.0 to 1.0 during processing
4. **Thread Safety**: All status dictionary access is protected by locks
5. **Error Handling**: Exceptions are caught and stored in status with 'error' state

## Usage Example

### JavaScript/Frontend

```javascript
// Start Division 8 analysis
const startResponse = await fetch(`/api/project/${projectId}/scope/division8/analyze`, {
  method: 'POST'
});

if (startResponse.ok) {
  // Poll for status
  const pollInterval = setInterval(async () => {
    const statusResponse = await fetch(`/api/project/${projectId}/scope/division8/status`);
    const status = await statusResponse.json();

    console.log(`Progress: ${(status.progress * 100).toFixed(0)}%`);

    if (status.status === 'complete') {
      clearInterval(pollInterval);

      // Get result
      const resultResponse = await fetch(`/api/project/${projectId}/scope/division8/result`);
      const result = await resultResponse.json();

      console.log('Division 8 Scope:', result);
    } else if (status.status === 'error') {
      clearInterval(pollInterval);
      console.error('Analysis failed:', status.error);
    }
  }, 1000); // Poll every second
}
```

### Python Test Script

A test script is provided: `test_async_endpoints.py`

```bash
# Test both endpoints for a project
python3 test_async_endpoints.py "project-id"

# Test only Division 8
python3 test_async_endpoints.py "project-id" division8

# Test only drawings
python3 test_async_endpoints.py "project-id" drawings
```

## API Response Formats

### Start Response (POST analyze)
```json
{
  "status": "started",
  "project_id": "project-123",
  "message": "Division 8 analysis started in background"
}
```

### Status Response (GET status)
```json
{
  "status": "running",
  "progress": 0.65
}
```

### Result Response (GET result) - Division 8
```json
{
  "project_id": "project-123",
  "project_name": "Example Project",
  "division8_scope": [
    {
      "source_file": "specs/divisions.pdf",
      "division": "08",
      "title": "Openings",
      "start_page": 45,
      "end_page": 72,
      "sections": [
        {
          "section_id": "081113",
          "title": "Hollow Metal Doors and Frames",
          "page": 46,
          "excerpt": "..."
        }
      ]
    }
  ],
  "spec_files_found": 3,
  "spec_files_processed": 2
}
```

### Result Response (GET result) - Drawings
```json
{
  "project_id": "project-123",
  "project_name": "Example Project",
  "summary": {
    "total_sheets": 45,
    "by_discipline": {
      "Architectural": 15,
      "Structural": 10,
      "Mechanical": 12,
      "Electrical": 8
    }
  },
  "sheets": [...],
  "drawing_files_found": 5,
  "available_disciplines": {...}
}
```

## Backward Compatibility

The original synchronous endpoints remain functional:
- `/api/project/<project_id>/scope/division8` (synchronous)
- `/api/project/<project_id>/scope/drawings` (synchronous)

They now include documentation warning about potential timeouts and recommending async endpoints for large projects.

## Performance Characteristics

- **Division 8 Analysis**: Processes up to 5 spec PDFs, max 200 pages each
- **Drawings Analysis**: Processes up to 10 drawing PDFs
- **Progress Updates**: Real-time progress tracking (0.0 to 1.0)
- **Timeout Prevention**: Background thread prevents HTTP timeout
- **Concurrency Control**: Prevents duplicate analysis for same project

## Testing

1. Start the Flask app: `python3 app.py`
2. Use the test script: `python3 test_async_endpoints.py <project_id>`
3. Monitor console output for progress updates
4. Verify results match synchronous endpoint format

## Files Modified

- `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/project-tracker/app.py`
  - Added status dictionaries and locks (lines 769-773)
  - Updated synchronous endpoint documentation (lines 1153-1168, 1581-1599)
  - Added 6 new async endpoints (lines 1283-1577)

## Files Created

- `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/project-tracker/test_async_endpoints.py`
  - Test script for validating async endpoints
  - Demonstrates proper usage pattern
  - Includes progress polling example
