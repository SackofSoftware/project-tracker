# Async Scope Analysis API Reference

Quick reference for the new async scope analysis endpoints.

## Division 8 Analysis

### Start Analysis
```
POST /api/project/<project_id>/scope/division8/analyze
```

**Response:**
```json
{
  "status": "started",
  "project_id": "project-123",
  "message": "Division 8 analysis started in background"
}
```

**Error Codes:**
- `503` - Document classification module not available
- `404` - Project not found
- `409` - Analysis already in progress

### Check Status
```
GET /api/project/<project_id>/scope/division8/status
```

**Response (Running):**
```json
{
  "status": "running",
  "progress": 0.65
}
```

**Response (Complete):**
```json
{
  "status": "complete",
  "progress": 1.0,
  "result": { ... }
}
```

**Response (Error):**
```json
{
  "status": "error",
  "error": "Error message here"
}
```

**Response (Not Started):**
```json
{
  "status": "not_started",
  "project_id": "project-123"
}
```

### Get Result
```
GET /api/project/<project_id>/scope/division8/result
```

**Response:**
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
          "excerpt": "Section text excerpt..."
        }
      ]
    }
  ],
  "spec_files_found": 3,
  "spec_files_processed": 2
}
```

**Error Codes:**
- `404` - No analysis found for this project
- `400` - Analysis not complete yet

## Drawings Analysis

### Start Analysis
```
POST /api/project/<project_id>/scope/drawings/analyze
```

**Response:**
```json
{
  "status": "started",
  "project_id": "project-123",
  "message": "Drawings analysis started in background"
}
```

**Error Codes:**
- `503` - Document classification module not available
- `404` - Project not found
- `409` - Analysis already in progress

### Check Status
```
GET /api/project/<project_id>/scope/drawings/status
```

**Response (Running):**
```json
{
  "status": "running",
  "progress": 0.45
}
```

**Response (Complete):**
```json
{
  "status": "complete",
  "progress": 1.0,
  "result": { ... }
}
```

**Response (Error):**
```json
{
  "status": "error",
  "error": "Error message here"
}
```

**Response (Not Started):**
```json
{
  "status": "not_started",
  "project_id": "project-123"
}
```

### Get Result
```
GET /api/project/<project_id>/scope/drawings/result
```

**Response:**
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
    },
    "disciplines_found": ["A", "S", "M", "E"]
  },
  "sheets": [
    {
      "source_file": "drawings/architectural.pdf",
      "sheet_id": "A-101",
      "discipline_code": "A",
      "discipline_name": "Architectural",
      "sheet_type": "Floor Plan",
      "sheet_title": "First Floor Plan",
      "confidence": 0.95,
      "method": "title_block"
    }
  ],
  "drawing_files_found": 5,
  "available_disciplines": { ... }
}
```

**Error Codes:**
- `404` - No analysis found for this project
- `400` - Analysis not complete yet

## Synchronous Endpoints (Legacy)

These endpoints still work but may timeout for large projects:

```
GET /api/project/<project_id>/scope/division8
GET /api/project/<project_id>/scope/drawings
```

## Common Usage Pattern

### JavaScript Example

```javascript
async function analyzeProject(projectId, type) {
  // Start analysis
  const start = await fetch(`/api/project/${projectId}/scope/${type}/analyze`, {
    method: 'POST'
  });

  if (!start.ok) {
    const error = await start.json();
    throw new Error(error.error);
  }

  // Poll for completion
  while (true) {
    await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second

    const status = await fetch(`/api/project/${projectId}/scope/${type}/status`);
    const data = await status.json();

    if (data.status === 'complete') {
      // Get result
      const result = await fetch(`/api/project/${projectId}/scope/${type}/result`);
      return await result.json();
    } else if (data.status === 'error') {
      throw new Error(data.error);
    }

    // Update UI with progress
    console.log(`Progress: ${(data.progress * 100).toFixed(0)}%`);
  }
}

// Use it
analyzeProject('project-123', 'division8')
  .then(result => console.log('Division 8 Scope:', result))
  .catch(error => console.error('Analysis failed:', error));
```

### Python Example

```python
import requests
import time

def analyze_project(project_id, analysis_type):
    base_url = "http://localhost:5003"

    # Start analysis
    response = requests.post(
        f"{base_url}/api/project/{project_id}/scope/{analysis_type}/analyze"
    )
    response.raise_for_status()

    # Poll for completion
    while True:
        time.sleep(1)

        status_response = requests.get(
            f"{base_url}/api/project/{project_id}/scope/{analysis_type}/status"
        )
        status = status_response.json()

        if status['status'] == 'complete':
            # Get result
            result_response = requests.get(
                f"{base_url}/api/project/{project_id}/scope/{analysis_type}/result"
            )
            return result_response.json()

        elif status['status'] == 'error':
            raise Exception(status['error'])

        # Show progress
        print(f"Progress: {status['progress']:.0%}")

# Use it
result = analyze_project('project-123', 'division8')
print('Division 8 Scope:', result)
```

## Testing

Use the provided test script:

```bash
# Test both endpoints
python3 test_async_endpoints.py project-123

# Test only Division 8
python3 test_async_endpoints.py project-123 division8

# Test only drawings
python3 test_async_endpoints.py project-123 drawings
```

## Performance Notes

- **Division 8**: Processes up to 5 spec PDFs, max 200 pages each
- **Drawings**: Processes up to 10 drawing PDFs
- **Progress**: Updated in real-time (0.0 to 1.0)
- **Concurrency**: One analysis per project at a time
- **Timeout**: No HTTP timeout (runs in background)
