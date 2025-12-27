# PlanHub-Local Matcher Module - Summary

## Overview

Created a comprehensive project matching module at `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/project-tracker/modules/planhub/planhub_matcher.py` that intelligently matches PlanHub leads with local bidding folder projects.

## Files Created

1. **`planhub_matcher.py`** - Main matcher module (522 lines)
   - Core matching logic with fuzzy string matching
   - Manual linking support
   - Match suggestions
   - Statistics and reporting

2. **`README_MATCHER.md`** - Comprehensive documentation
   - Usage examples
   - API reference
   - Data structure specifications
   - Integration guide

3. **`example_matcher_usage.py`** - Working example script
   - Demonstrates all key features
   - Can be run directly for testing

4. **`static/data/planhub_links.json`** - Manual links storage
   - JSON file storing user-defined project links
   - Created automatically on first use

## Key Features Implemented

### 1. Auto-Matching Algorithm

**Scoring System (0-1.0 scale):**
- **Project Name Similarity**: 0-0.6 points
  - Uses `difflib.SequenceMatcher`
  - Requires ≥0.8 similarity to contribute to score
  - Case-insensitive with whitespace normalization

- **Location Match**: 0.3 points
  - Both city AND state must match exactly
  - Case-insensitive

- **Bid Date Proximity**: 0.1 points
  - Dates must be within 7 days
  - Handles multiple date formats (ISO and MM/DD/YYYY)

**Matching Threshold:** ≥0.8 confidence required for auto-match

### 2. Manual Linking System

- Store/retrieve manual project links
- Links persist in `static/data/planhub_links.json`
- Manual links always override auto-matches
- Manual links have confidence=1.0

**API:**
- `link_projects(planhub_id, local_id)` - Create link
- `unlink_project(planhub_id)` - Remove link
- `get_link(planhub_id)` - Retrieve link

### 3. Match Suggestions

Get top N most likely matches for any PlanHub project:
- Returns matches even below auto-match threshold (≥0.3)
- Useful for UI to present options to users
- Includes detailed scoring breakdown

### 4. Robust Data Handling

- Handles None/missing values gracefully
- Normalizes PlanHub IDs (strips "planhub-" prefix)
- Supports multiple date formats
- Works with different location data structures

## Class: PlanHubLocalMatcher

### Main Methods

```python
# Find all matches
matches = matcher.find_matches(planhub_projects, local_projects)

# Find best match for single project
match = matcher.get_best_match(planhub_project, local_projects)

# Get match suggestions
suggestions = matcher.get_match_suggestions(planhub_project, local_projects, limit=3)

# Manual linking
matcher.link_projects(planhub_id, local_id)
matcher.unlink_project(planhub_id)
local_id = matcher.get_link(planhub_id)

# Utilities
unmatched = matcher.get_unmatched_planhub_projects(planhub_projects, local_projects)
stats = matcher.get_match_stats(planhub_projects, local_projects)
```

## Data Structures

### Match Result
```python
{
    'planhub_id': '510142',
    'local_id': 'ric-track-support-building',
    'confidence': 0.939,
    'match_type': 'auto',  # or 'manual'
    'match_details': {
        'name_similarity': 0.898,
        'location_match': True,
        'bid_date_match': True
    }
}
```

### Match Suggestion
```python
{
    'local_id': 'project-id',
    'local_title': 'Project Title',
    'local_folder': 'Project Folder Name',
    'confidence': 0.654,
    'match_details': {
        'name_similarity': 0.721,
        'location_match': False,
        'bid_date_match': True
    }
}
```

## Testing

All functionality tested and working:
- ✅ Auto-matching with real project data
- ✅ Manual linking (create/retrieve/delete)
- ✅ Match suggestions
- ✅ Statistics generation
- ✅ Graceful handling of None values
- ✅ Date format parsing
- ✅ Case-insensitive matching
- ✅ PlanHub ID normalization

### Run Tests

```bash
# Run built-in test with sample data
python3 modules/planhub/planhub_matcher.py

# Run example with real project data
python3 modules/planhub/example_matcher_usage.py
```

## Integration Steps

To integrate into the Flask dashboard:

1. **Import the matcher:**
   ```python
   from modules.planhub.planhub_matcher import PlanHubLocalMatcher
   ```

2. **Add API endpoints** (examples in README_MATCHER.md):
   - `GET /api/planhub/matches` - Get all matches
   - `POST /api/planhub/link` - Create manual link
   - `DELETE /api/planhub/link/<planhub_id>` - Remove link
   - `GET /api/planhub/suggest/<planhub_id>` - Get suggestions

3. **Update frontend** to display:
   - Matched icon/badge on PlanHub projects
   - Link to local project folder
   - Manual linking UI for unmatched projects
   - Match suggestions dropdown

## Current Status

- ✅ Module fully implemented and tested
- ✅ Documentation complete
- ✅ Example usage script working
- ✅ Manual links file storage working
- ⏳ API endpoints not yet created (ready for integration)
- ⏳ UI integration pending

## Example Output

```
PlanHub-Local Project Matcher Example
======================================================================

1. Loading projects...
   Loaded 20 PlanHub projects
   Loaded 117 local projects

2. Finding matches...
   Found 1 matches

   - PlanHub: RIC Track Support Bldg.
     Local:   RIC Track Support Building
     Confidence: 0.939
     Type: auto

3. Statistics:
   Total PlanHub projects: 20
   Total local projects: 117
   Total matches: 1
     - Manual: 0
     - Auto: 1
   Unmatched PlanHub: 19
   Match rate: 5.0%
```

## Notes

- The current dataset has limited overlap (20 PlanHub vs 117 local projects)
- Most PlanHub projects are missing city/state data (empty strings)
- This reduces auto-match success but suggestions still work
- Manual linking provides fallback for edge cases
- Algorithm can be tuned by adjusting weights and thresholds
