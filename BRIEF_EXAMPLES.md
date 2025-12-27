# Project Brief Examples

## Example 1: 21-27 Neptune Project

### Text Format Output
```
PROJECT SUMMARY
21-27 Neptune
Address: Neptune Blvd, Lynn MA

Owner: TBD
Architect: TBD

This project includes Division 8 work with 13 windows, 7 doors, and 0 storefronts.

SCHEDULE
Start: TBD | Duration: TBD | Bid Date: TBD

DIVISION 8 SCOPE

Windows:
  • Rehau Window System 4500: 2 units
  • Rehau Window System 4500 Operable Plan Detail: 0 units
  • Rehau Tilt Turn Window System 4500: 6 units
  • Rehau Window Handle: 1 units
  • 400 SERIES ANDERSEN: 45 units

Doors:
  • Hollow Metal: 27 units
  • 16 gauge steel: 0 units
  • Rehau Integral Mullion: 3 units

DOCUMENTS AVAILABLE
✓ Specs: 0 files
✓ Drawings: 0 files
✓ Schedules: 3 files (Door Schedule.pdf, HW Schedule.pdf, Hardware Schedule.pdf)
✓ Quotes: 0 files
✗ Missing: Specifications, Drawings

ESTIMATE STATUS
No takeoff spreadsheets found
Quotes Received: 3 quotes from 2 vendors
Total Quote Value: $112,700.00

NEXT STEPS
• Review specifications and drawings
• Complete takeoff if not done
• Request quotes from qualified vendors
• Prepare bid package
```

### JSON Format Output (Context Data)
```json
{
  "status": "ok",
  "project_id": "21-27-neptune",
  "project_name": "21-27 Neptune",
  "brief": "[full text brief as above]",
  "context": {
    "project_metadata": {
      "name": "21-27 Neptune",
      "address": null,
      "owner": null,
      "architect": null,
      "bid_date": null,
      "source": "local_extracted",
      "project_code": null
    },
    "openings_data": {
      "total_windows": 13,
      "total_doors": 7,
      "total_storefronts": 0,
      "windows": [
        {
          "mark": "W1",
          "qty": 5,
          "width": "3'-0\"",
          "height": "4'-6\"",
          "type": "Rehau Tilt Turn Window System 4500"
        },
        {
          "mark": "1",
          "qty": 13,
          "width": "6'-0\"",
          "height": "5'-0\"",
          "type": "400 SERIES ANDERSEN"
        }
      ],
      "doors": [
        {
          "mark": "D2",
          "qty": 8,
          "width": "3'-0\"",
          "height": "7'-0\"",
          "material": "Hollow Metal",
          "fire_rating": "90 MIN",
          "hardware_set": "Lever + Closer",
          "type": "Vision Glass Door"
        }
      ]
    },
    "estimate_status": {
      "has_estimate": false
    },
    "quotes_data": {
      "has_quotes": true,
      "total_quotes": 3,
      "quotes_with_pricing": 2,
      "total_value": 112700.0,
      "vendors": ["Vendor A", "Vendor B"],
      "quotes": [...]
    },
    "available_documents": {
      "specs": [],
      "drawings": [],
      "schedules": [
        "Door Schedule.pdf",
        "HW Schedule.pdf",
        "Hardware Schedule.pdf"
      ],
      "addendums": [],
      "quotes": [],
      "other": [
        "TWI Supply Agreement.pdf",
        "Project_Summary.pdf"
      ]
    },
    "division_8_scope": {},
    "errors": []
  }
}
```

## Example 2: Gardner School Project

### Text Format Output
```
PROJECT SUMMARY
The Gardner School - Hingham MA
Private elementary school renovation and addition

Owner: TBD
Architect: TBD

This project includes Division 8 work with 13 windows, 21 doors, and 1 storefronts.

SCHEDULE
Start: TBD | Duration: TBD | Bid Date: 2025-05-28

DIVISION 8 SCOPE

Specification Sections:
  • 081113: Steel Doors and Frames
  • 084113: Aluminum-Framed Entrances and Storefronts
  • 085313: Vinyl Windows

Windows:
  • Fixed: 12 units
  • Operable: 2 units

Doors:
  • HM Door: 2 units
  • Glass: 2 units
  • Double HM Door: 1 units

DOCUMENTS AVAILABLE
✓ Specs: 2 files
✓ Drawings: 1 files
✓ Schedules: 5 files
✓ Quotes: 0 files

ESTIMATE STATUS
Takeoff Complete: 131 openings in 4 files
No vendor quotes found

NEXT STEPS
• Review specifications and drawings
• Complete takeoff if not done
• Request quotes from qualified vendors
• Prepare bid package
```

## Using the Endpoint

### Command Line (curl)
```bash
# Get brief in text format
curl "http://localhost:5003/api/project/21-27-neptune/brief?format=text&use_lm_studio=false"

# Get brief in JSON format with full context
curl "http://localhost:5003/api/project/21-27-neptune/brief" | python3 -m json.tool

# Save brief to file
curl -o brief.txt "http://localhost:5003/api/project/21-27-neptune/brief?format=text"
```

### Python
```python
import requests

# Get brief
response = requests.get(
    "http://localhost:5003/api/project/21-27-neptune/brief",
    params={"use_lm_studio": "false"}
)

if response.status_code == 200:
    data = response.json()
    print(data['brief'])

    # Access context
    print(f"Windows: {data['context']['openings_data']['total_windows']}")
    print(f"Doors: {data['context']['openings_data']['total_doors']}")

    # Check for quotes
    if data['context']['quotes_data']['has_quotes']:
        print(f"Quote Value: ${data['context']['quotes_data']['total_value']:,.2f}")
```

### JavaScript/TypeScript
```typescript
async function getProjectBrief(projectId: string) {
  const response = await fetch(
    `http://localhost:5003/api/project/${projectId}/brief?use_lm_studio=false`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch brief: ${response.statusText}`);
  }

  const data = await response.json();
  return {
    brief: data.brief,
    windows: data.context.openings_data.total_windows,
    doors: data.context.openings_data.total_doors,
    hasQuotes: data.context.quotes_data.has_quotes,
    quoteValue: data.context.quotes_data.total_value
  };
}

// Usage
const brief = await getProjectBrief('21-27-neptune');
console.log(brief.brief);
```

## AI Provider Behavior

### When LM Studio is Running
If LM Studio is running on localhost:1234, the endpoint will:
1. Send the prompt to LM Studio
2. Use its response for a more natural, conversational brief
3. Fall back to OpenRouter if LM Studio times out

### When Using OpenRouter
If `force_openrouter=true` or LM Studio is unavailable:
1. Sends prompt to OpenRouter API (amazon/nova-lite-v1)
2. Returns AI-generated brief with better formatting
3. Falls back to simple text if API fails

### When No AI Available
If neither LM Studio nor OpenRouter is available:
1. Uses the `generate_simple_brief()` function
2. Creates structured text from context data
3. Still includes all relevant information
4. More template-based, less conversational

## Brief Quality Indicators

The quality of the brief depends on available data:

**Best Quality:**
- extracted_project_data.json present
- Specification PDFs with Division 08
- Takeoff spreadsheets
- Vendor quote PDFs
- AI provider available

**Good Quality:**
- extracted_project_data.json present
- Some documents available
- Simple text generation

**Limited Quality:**
- Only basic project metadata
- No extracted data
- Missing documents
- Still provides useful structure

## Performance Notes

- **Fast** (< 1 second): Simple brief without spec extraction
- **Moderate** (1-3 seconds): With spec PDF parsing
- **Slower** (3-10 seconds): With AI generation
- **Timeout**: Set to 30 seconds for AI calls

## Common Use Cases

1. **Pre-bid Review**: Quick summary before deciding to bid
2. **Team Briefing**: Share project overview with estimators
3. **Client Updates**: Generate status reports
4. **Bid Preparation**: Checklist of what's needed
5. **Project Handoff**: Document knowledge transfer
6. **Dashboard Integration**: Display summaries in UI
