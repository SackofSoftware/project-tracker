# PlanHub Matcher - Quick Start

## 5-Minute Setup

### 1. Import and Initialize
```python
from modules.planhub.planhub_matcher import PlanHubLocalMatcher

matcher = PlanHubLocalMatcher()
```

### 2. Load Your Projects
```python
from modules.planhub.planhub_reader import load_planhub_projects
from modules.bidding.bidding_reader import BiddingFolderReader

planhub_projects = load_planhub_projects()
local_projects = BiddingFolderReader("/path/to/bidding").read_all_projects()
```

### 3. Find Matches
```python
matches = matcher.find_matches(planhub_projects, local_projects)
```

## Common Tasks

### Check if a PlanHub project is matched
```python
planhub_id = "510142"
local_id = matcher.get_link(planhub_id)

if local_id:
    print(f"Matched to: {local_id}")
else:
    # Try auto-match
    ph_proj = next(p for p in planhub_projects if p['project_id'] == planhub_id)
    match = matcher.get_best_match(ph_proj, local_projects)
    if match:
        print(f"Auto-matched to: {match['local_id']} (confidence: {match['confidence']})")
    else:
        print("No match found")
```

### Manually link two projects
```python
matcher.link_projects(
    planhub_id="510142",
    local_id="ric-track-support-building"
)
```

### Get suggestions for manual linking
```python
ph_proj = planhub_projects[0]
suggestions = matcher.get_match_suggestions(ph_proj, local_projects, limit=5)

for sug in suggestions:
    print(f"{sug['local_title']} - {sug['confidence']:.1%} match")
```

### Get all unmatched PlanHub projects
```python
unmatched = matcher.get_unmatched_planhub_projects(
    planhub_projects,
    local_projects
)

print(f"{len(unmatched)} PlanHub projects need review")
```

### View statistics
```python
stats = matcher.get_match_stats(planhub_projects, local_projects)
print(f"Match rate: {stats['match_rate']:.1%}")
print(f"Manual: {stats['manual_matches']}, Auto: {stats['auto_matches']}")
```

## Try the Example

Run the full example script:
```bash
python3 modules/planhub/example_matcher_usage.py
```

## Match Score Breakdown

A project needs **≥0.8 confidence** to auto-match:

| Factor | Points | Requirement |
|--------|--------|-------------|
| Name similarity | 0-0.6 | ≥80% similar |
| Location match | 0.3 | City + State exact |
| Date proximity | 0.1 | Within 7 days |

**Example:**
- Name: 0.54 (90% similar × 0.6)
- Location: 0.3 (both match)
- Date: 0.1 (3 days apart)
- **Total: 0.94** ✅ Auto-match

## Files

- **Code:** `modules/planhub/planhub_matcher.py`
- **Data:** `static/data/planhub_links.json` (auto-created)
- **Docs:** `modules/planhub/README_MATCHER.md`

## Next Steps

See `README_MATCHER.md` for:
- Full API reference
- Integration examples
- Flask endpoint templates
