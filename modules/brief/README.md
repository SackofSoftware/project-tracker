# AI Project Brief Module

This module builds rich prompts for generating AI project briefs using CSI Masterformat context and manufacturer product databases.

## Quick Start

```python
from modules.brief.prompt_builder import build_division8_brief

project = {
    "title": "Hospital Addition",
    "location": "Boston, MA",
    "scope": "Curtain wall and storefront",
    "specifications": "Kawneer 1600 curtain wall, YKK 25T entrances"
}

# Generate prompt for AI brief generation
prompt = build_division8_brief(project)

# Use prompt with your AI model
# brief = ai_model.generate(prompt)
```

## Core Functions

### 1. `get_section_description(section_id)`
Look up CSI section descriptions. Handles multiple formats.

```python
from modules.brief.prompt_builder import get_section_description

# All these formats work:
desc1 = get_section_description("08 41 13")
desc2 = get_section_description("084113")
desc3 = get_section_description("08-41-13")

print(desc1)  # "Aluminum-Framed Entrances and Storefronts"
```

### 2. `load_division_context(division)`
Load comprehensive CSI data for a division.

```python
from modules.brief.prompt_builder import load_division_context

context = load_division_context("08")

print(context["division_name"])        # "Openings"
print(context["all_sections_count"])   # 546 sections
print(len(context["common_sections"])) # 11 common sections

# Access common sections
for section in context["common_sections"]:
    print(f"{section['section_number']}: {section['title']}")
```

### 3. `load_manufacturer_specs(manufacturers)`
Search product database for manufacturer specifications.

```python
from modules.brief.prompt_builder import load_manufacturer_specs

specs = load_manufacturer_specs(["Kawneer", "YKK"])

print(specs["found_manufacturers"])  # ["Kawneer", "YKK AP"]
print(specs["total_products"])       # 20 products

# Access products by manufacturer
kawneer_products = specs["products_by_manufacturer"]["Kawneer"]
for product in kawneer_products[:3]:
    print(f"- {product['name']}")
    print(f"  {product['description']['summary']}")
```

### 4. `build_brief_prompt(project_context, ...)`
Build a complete AI prompt with full context.

```python
from modules.brief.prompt_builder import build_brief_prompt

project = {
    "title": "Bank Branch Renovation",
    "location": "Falmouth, MA",
    "value": "$2.5M",
    "bid_date": "2025-01-15",
    "description": "Replace all storefront and interior glazing",
    "scope": "Division 8 scope includes curtain wall, entrances, interior glazing",
    "specifications": "Section 08 44 13: Kawneer 1600 Wall System"
}

# Auto-detects sections (08 44 13) and manufacturers (Kawneer)
prompt = build_brief_prompt(project)

# Or provide custom context
from modules.brief.prompt_builder import load_division_context, load_manufacturer_specs

div_context = load_division_context("08")
mfr_specs = load_manufacturer_specs(["Kawneer", "EFCO"])

prompt = build_brief_prompt(
    project_context=project,
    division_context=div_context,
    manufacturer_specs=mfr_specs,
    include_examples=True
)
```

### 5. `build_division8_brief(project_context)`
Convenience function for Division 8 (most common use case).

```python
from modules.brief.prompt_builder import build_division8_brief

# Simplest approach - handles everything automatically
prompt = build_division8_brief(project)
```

## Auto-Detection Features

The module automatically extracts information from project text:

### Section Detection
Finds CSI section numbers in any format:
- "Section 08 41 13 specifies..."
- "Per 084113..."
- "See section 08-44-13"

### Manufacturer Detection
Searches for known manufacturers in text:
- Direct names: "Kawneer", "YKK AP"
- Abbreviations: "YKK" matches "YKK AP"
- Partial matches: "kawneer" (case-insensitive)

Database includes 15 manufacturers:
- Kawneer
- YKK AP
- EFCO
- Wausau Window and Wall Systems
- Tubelite
- Marvin Windows and Doors
- Pella Windows and Doors
- And 8 more...

## Project Context Format

The `project_context` dictionary can include any of these keys:

```python
{
    "title": "Project name",
    "location": "City, State",
    "value": "Project value",
    "bid_date": "YYYY-MM-DD",
    "description": "Brief description",
    "scope": "Detailed scope",
    "specifications": "Spec text with sections and manufacturers",
    "notes": "Additional notes",
    "manufacturers": "List of manufacturers" or ["Mfr1", "Mfr2"],
    "products": "Product specifications"
}
```

All fields are optional. More fields = richer prompt context.

## Data Sources

### CSI Masterformat Database
- **File:** `CSI_Masterformat/Masterformat_Subsection_List.json`
- **Content:** 546 Division 8 sections with titles
- **Format:** `[{"subsection_number": "08 41 13", "subsection_title": "..."}]`

### Unified Products Database
- **File:** `CSI_Masterformat/division8_data/unified_products_database.json`
- **Content:** 667 products from 15 manufacturers
- **Includes:** Product names, categories, specifications, descriptions, performance data

## Integration Example

```python
# Example: Integrate with project tracker API

from modules.brief.prompt_builder import build_division8_brief
import requests

def generate_project_brief(project_id):
    # Get project data from API
    project = requests.get(f"/api/projects/{project_id}").json()

    # Build prompt with CSI context
    prompt = build_division8_brief(project)

    # Generate brief with AI model
    # (Replace with your actual AI integration)
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        json={
            "model": "claude-opus-4-5",
            "messages": [{"role": "user", "content": prompt}]
        }
    )

    brief = response.json()["content"][0]["text"]
    return brief

# Use it
brief = generate_project_brief(123)
print(brief)
```

## Prompt Output Structure

The generated prompt includes:

1. **Role Context:** "You are a construction estimator specializing in Division 8..."
2. **Project Context:** Title, location, value, bid date, description, scope
3. **CSI Division Reference:**
   - Sections identified in the project
   - Common Division 8 sections for reference
4. **Manufacturer Reference:**
   - Products from specified manufacturers
   - Product descriptions and specifications
5. **Task Instructions:** What the AI should generate
6. **Output Format:** Example structure for the brief

## Example Generated Prompt

```
You are a construction estimator assistant specializing in Division 08 (Openings) scope for a glazing contractor.

PROJECT CONTEXT:
Project: Bank Branch Renovation
Location: Falmouth, MA
Project Value: $2.5M
Bid Date: 2025-01-15
Description: Replace all storefront and interior glazing
Scope: Division 8 scope includes curtain wall, entrances, interior glazing

CSI DIVISION 08 REFERENCE:

Sections identified in this project:
- Section 08 44 13: glazed aluminum curtain walls

Common Division 8 sections for glazing contractors:
- Section 08 41 13: Aluminum-Framed Entrances and Storefronts
- Section 08 44 13: glazed aluminum curtain walls
- Section 08 80 00: field installed glazing
[etc...]

MANUFACTURER REFERENCE:

Kawneer products:
  - IR 521/521T/521UT Framing System (Storefront Framing)
  - Trifab® 451UT Framing System (Storefront Framing)
  - 1600 Wall System™ (Curtain Walls)
[etc...]

Generate a project brief that:
1. Summarizes the Division 8 scope in plain language
2. Identifies what's clearly specified vs needs clarification
3. Notes any potential scope gaps or coordination issues
4. Lists key quantities if available
5. Highlights the specified manufacturers and systems

Format the response as a structured brief...
```

## Testing

Run the built-in demo:

```bash
python3 modules/brief/prompt_builder.py
```

Or run custom tests:

```python
from modules.brief.prompt_builder import *

# Test all functions
assert get_section_description("08 41 13") != ""
assert load_division_context("08")["division_name"] == "Openings"
assert len(load_manufacturer_specs(["Kawneer"])["found_manufacturers"]) > 0

project = {"title": "Test", "scope": "Kawneer curtain wall"}
assert "Kawneer" in build_division8_brief(project)

print("All tests passed!")
```

## Performance Notes

- Data is cached after first load (no repeated file reads)
- 546 sections load in ~50ms
- 667 products load in ~100ms
- Auto-detection uses regex (very fast)
- Prompt generation: <10ms

## Error Handling

The module handles missing data gracefully:

```python
# Unknown section returns empty string (doesn't crash)
desc = get_section_description("99 99 99")
print(desc)  # ""

# Unknown manufacturer returns empty list
specs = load_manufacturer_specs(["FakeManufacturer"])
print(specs["found_manufacturers"])  # []

# Missing project fields are skipped
project = {"title": "Only Title"}
prompt = build_division8_brief(project)  # Works fine
```

## Troubleshooting

### Problem: "File not found" errors
**Solution:** Check that CSI_Masterformat directory is at project root:
```
project-tracker/
├── CSI_Masterformat/
│   ├── Masterformat_Subsection_List.json
│   └── division8_data/
│       └── unified_products_database.json
└── modules/
    └── brief/
        └── prompt_builder.py
```

### Problem: No manufacturers detected
**Solution:** Use exact or partial manufacturer names from database:
```python
# Check available manufacturers
from modules.brief.prompt_builder import _load_products
print(_load_products()["manufacturers"])
```

### Problem: No sections detected
**Solution:** Use standard CSI format in project text:
- Good: "Section 08 41 13", "084113", "08-41-13"
- Bad: "Section 8-41-13" (missing leading zero)

## Future Enhancements

Potential improvements:
- Support for other divisions (09, 07, etc.)
- Integration with live specification databases
- Product pricing integration
- PDF specification parsing
- Historical project comparison

## Support

For issues or questions:
1. Check this README
2. Run the demo script
3. Review function docstrings
4. Check the project CLAUDE.md file
