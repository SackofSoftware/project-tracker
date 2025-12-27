# PlanHub-Local Project Matcher

The `planhub_matcher.py` module provides intelligent matching between PlanHub leads and local bidding folder projects. This helps identify when a PlanHub project corresponds to a local folder that's already been downloaded.

## Features

### 1. Auto-Matching
Automatically matches projects using fuzzy string matching with the following criteria:

- **Project Name Similarity** (max 0.6 points)
  - Uses `difflib.SequenceMatcher` to compare project names
  - Threshold: 0.8 similarity required
  - Example: "RIC Track Support Bldg." matches "RIC Track Support Building" (0.898 similarity)

- **Location Match** (0.3 points)
  - Exact match required for both city AND state
  - Case-insensitive comparison
  - Example: "Providence, RI" matches "Providence, RI"

- **Bid Date Proximity** (0.1 points)
  - Bid dates must be within 7 days of each other
  - Handles multiple date formats (YYYY-MM-DD and MM/DD/YYYY)

**Confidence Threshold**: Projects must score >= 0.8 to be considered a match.

### 2. Manual Linking
Users can manually link any PlanHub project to a local project:

- Links stored in `static/data/planhub_links.json`
- Manual links always take precedence over auto-matches
- Manual links have confidence score of 1.0

### 3. Match Suggestions
For each PlanHub project, get the top N most likely local matches (even below auto-match threshold):

- Useful for UI to present options to users
- Default: top 3 suggestions
- Minimum score: 0.3

## Usage

### Basic Matching

```python
from modules.planhub.planhub_reader import load_planhub_projects
from modules.bidding.bidding_reader import BiddingFolderReader
from modules.planhub.planhub_matcher import PlanHubLocalMatcher

# Load projects
planhub_projects = load_planhub_projects()
reader = BiddingFolderReader("/path/to/bidding/folder")
local_projects = reader.read_all_projects()

# Initialize matcher
matcher = PlanHubLocalMatcher()

# Find all matches
matches = matcher.find_matches(planhub_projects, local_projects)

for match in matches:
    print(f"PlanHub {match['planhub_id']} -> Local {match['local_id']}")
    print(f"Confidence: {match['confidence']}, Type: {match['match_type']}")
```

### Manual Linking

```python
# Link a PlanHub project to a local project
matcher.link_projects(
    planhub_id="510142",  # or "planhub-510142"
    local_id="ric-track-support-building"
)

# Get the link
local_id = matcher.get_link("510142")  # Returns "ric-track-support-building"

# Remove a link
matcher.unlink_project("510142")
```

### Match Suggestions

```python
# Get top 3 suggestions for a PlanHub project
suggestions = matcher.get_match_suggestions(
    planhub_project=planhub_projects[0],
    local_projects=local_projects,
    limit=3
)

for sug in suggestions:
    print(f"{sug['local_title']} - Confidence: {sug['confidence']}")
    print(f"  Name similarity: {sug['match_details']['name_similarity']:.2f}")
    print(f"  Location match: {sug['match_details']['location_match']}")
    print(f"  Date match: {sug['match_details']['bid_date_match']}")
```

### Best Match for Single Project

```python
# Find best match for one PlanHub project
match = matcher.get_best_match(
    planhub_project=planhub_projects[0],
    local_projects=local_projects
)

if match:
    print(f"Found match: {match['local_id']} (confidence: {match['confidence']})")
else:
    print("No match found")
```

### Unmatched Projects

```python
# Get PlanHub projects with no local match
unmatched = matcher.get_unmatched_planhub_projects(
    planhub_projects,
    local_projects
)

print(f"Found {len(unmatched)} unmatched PlanHub projects")
```

### Statistics

```python
# Get matching statistics
stats = matcher.get_match_stats(planhub_projects, local_projects)

print(f"Total PlanHub projects: {stats['total_planhub']}")
print(f"Total local projects: {stats['total_local']}")
print(f"Matched: {stats['total_matches']}")
print(f"  - Manual: {stats['manual_matches']}")
print(f"  - Auto: {stats['auto_matches']}")
print(f"Unmatched: {stats['unmatched_planhub']}")
print(f"Match rate: {stats['match_rate']}")
```

## Data Structures

### PlanHub Project
Expected fields:
- `id` or `project_id`: Project identifier
- `project_name` or `title`: Project name
- `city`: City location
- `state`: State abbreviation
- `bid_date` or `bid_due_date`: Bid date (YYYY-MM-DD or MM/DD/YYYY)

### Local Project
Expected fields:
- `id`: Project identifier
- `title` or `folder`: Project name
- `location`: Dict with `city` and `state` keys
- `bid_date`: Bid date (YYYY-MM-DD format)

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

## File Storage

Manual links are stored in `static/data/planhub_links.json`:

```json
{
  "510142": "ric-track-support-building",
  "509331": "chick-fil-a-seabrook"
}
```

## Testing

Run the module directly to test with sample data:

```bash
python3 modules/planhub/planhub_matcher.py
```

Or test with real project data:

```bash
cd /path/to/project-tracker
python3 -c "
from modules.planhub.planhub_reader import load_planhub_projects
from modules.bidding.bidding_reader import BiddingFolderReader
from modules.planhub.planhub_matcher import PlanHubLocalMatcher
import os
from dotenv import load_dotenv

load_dotenv()

planhub_projects = load_planhub_projects()
reader = BiddingFolderReader(os.getenv('BIDDING_FOLDER'))
local_projects = reader.read_all_projects()

matcher = PlanHubLocalMatcher()
matches = matcher.find_matches(planhub_projects, local_projects)
stats = matcher.get_match_stats(planhub_projects, local_projects)

print(f'Found {len(matches)} matches')
print(f'Match rate: {stats[\"match_rate\"]:.1%}')
"
```

## API Integration

To integrate into the Flask API, add endpoints like:

```python
@app.route('/api/planhub/matches', methods=['GET'])
def get_planhub_matches():
    """Get all PlanHub-Local matches"""
    planhub_projects = load_planhub_projects()
    local_projects = get_local_projects()

    matcher = PlanHubLocalMatcher()
    matches = matcher.find_matches(planhub_projects, local_projects)

    return jsonify(matches)

@app.route('/api/planhub/link', methods=['POST'])
def link_planhub_project():
    """Manually link a PlanHub project to local project"""
    data = request.json
    planhub_id = data.get('planhub_id')
    local_id = data.get('local_id')

    matcher = PlanHubLocalMatcher()
    success = matcher.link_projects(planhub_id, local_id)

    return jsonify({'success': success})

@app.route('/api/planhub/suggest/<planhub_id>', methods=['GET'])
def get_match_suggestions(planhub_id):
    """Get match suggestions for a PlanHub project"""
    planhub_projects = load_planhub_projects()
    local_projects = get_local_projects()

    # Find the PlanHub project
    ph_proj = next((p for p in planhub_projects
                   if p.get('project_id') == planhub_id), None)

    if not ph_proj:
        return jsonify({'error': 'Project not found'}), 404

    matcher = PlanHubLocalMatcher()
    suggestions = matcher.get_match_suggestions(ph_proj, local_projects, limit=5)

    return jsonify(suggestions)
```

## Notes

- The matcher handles None values gracefully (no crashes on missing location data)
- PlanHub IDs are normalized (removes "planhub-" prefix if present)
- Case-insensitive string matching throughout
- Whitespace is normalized in string comparisons
- Date parsing handles multiple formats automatically
