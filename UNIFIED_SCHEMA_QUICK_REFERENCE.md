# Unified Schema Quick Reference

## Reading Projects

### PlanHub
```python
from modules.planhub.planhub_db_reader import PlanHubDatabaseReader

reader = PlanHubDatabaseReader()

# Get all completed leads
projects = reader.get_all_leads(status_filter=['done'])

# Get single lead
project = reader.get_lead_by_id('12345')
```

### GovWin
```python
from modules.govleads.govleads_reader import GovLeadsReader

reader = GovLeadsReader()

# Get all records
records = reader.read_all_leads()

# Convert to UnifiedProject
project = reader.normalize_to_unified_project(records[0])
```

### Local Bidding
```python
from modules.bidding.bidding_reader import BiddingFolderReader

reader = BiddingFolderReader("/path/to/bidding/folder")

# Get all projects
projects = reader.read_all_projects()

# Get by folder name
project = reader.get_project_by_folder("Project Name - City MA")

# Get upcoming bids
upcoming = reader.get_upcoming_bids(days=30)

# Get projects with estimates
estimated = reader.get_projects_with_estimates()
```

## Working with UnifiedProject

### Accessing Fields
```python
# Identity
project.id                # "planhub-12345"
project.source            # "planhub" | "govwin" | "local_bidding"
project.source_id         # Original ID from source

# Basic Info
project.title             # Project name
project.description       # Description text
project.url               # Link to source system

# Location (Location dataclass)
project.location.address
project.location.city
project.location.state
project.location.zip

# Dates (ISO 8601: YYYY-MM-DD)
project.bid_date
project.response_date
project.solicitation_date

# Project Details
project.owner
project.architect
project.general_contractors  # List[str]
project.project_value        # Float
project.project_value_str    # Original string
project.project_size         # e.g., "50,000 SF"

# Classification
project.project_type         # "Renovation" | "New Construction" | etc.
project.sector              # "Commercial" | "Retail" | etc.
project.entity_type         # "BID" | "LEAD" (GovWin)
project.tags                # List[str]

# Division 8
project.is_division_8                      # Boolean
project.division_8.scope_summary           # Text summary
project.division_8.spec_sections           # List[str]
project.division_8.matching_trades         # List[str]
project.division_8.windows                 # Dict with count, types
project.division_8.doors                   # Dict with count, types
project.division_8.hardware                # List[str]
project.division_8.glazing                 # List[str]
project.division_8.storefront              # Boolean
project.division_8.curtain_wall            # Boolean

# Documents
for doc in project.documents:
    doc.id
    doc.title
    doc.type              # "spec" | "drawing" | "addendum"
    doc.url               # Download URL
    doc.local_path        # Local file path
    doc.file_size         # Bytes
    doc.downloaded        # Boolean
    doc.upload_date

# Source-Specific Flags
project.is_sub_bidding    # PlanHub
project.is_gc_awarded     # PlanHub
project.is_active         # GovWin

# Internal Status
project.internal_status.has_internal_estimate
project.internal_status.internal_estimate_total
project.internal_status.bid_decision
project.internal_status.archived

# Metadata
project.created_at
project.updated_at
project.last_sync
```

### Helper Methods
```python
# Get effective bid date (with override support)
date = project.get_effective_bid_date()

# Get formatted location string
location = project.get_display_location()  # "Boston, MA"

# Check if bid is upcoming
is_upcoming = project.is_upcoming(days=30)

# Check if has meaningful Division 8 content
has_div8 = project.has_division_8_content()

# Convert to dict for JSON serialization
data = project.to_dict()

# Create from dict
project = UnifiedProject.from_dict(data)
```

## Converting to Dict for APIs

```python
# Single project
return jsonify(project.to_dict())

# List of projects
return jsonify([p.to_dict() for p in projects])

# With filtering
division_8_projects = [p for p in projects if p.is_division_8]
return jsonify([p.to_dict() for p in division_8_projects])
```

## Common Patterns

### Filter by Division 8
```python
div8_projects = [p for p in projects if p.is_division_8]
```

### Filter by Date Range
```python
from datetime import datetime, timedelta

today = datetime.now().date()
cutoff = today + timedelta(days=30)

upcoming = [
    p for p in projects
    if p.bid_date and datetime.strptime(p.bid_date, '%Y-%m-%d').date() <= cutoff
]
```

### Filter by State
```python
ma_projects = [p for p in projects if p.location.state == 'MA']
```

### Filter by Source
```python
planhub_projects = [p for p in projects if p.source == 'planhub']
govwin_projects = [p for p in projects if p.source == 'govwin']
local_projects = [p for p in projects if p.source == 'local_bidding']
```

### Group by Location
```python
from collections import defaultdict

by_state = defaultdict(list)
for p in projects:
    if p.location.state:
        by_state[p.location.state].append(p)
```

### Count Windows/Doors
```python
total_windows = sum(
    p.division_8.windows.get('count', 0)
    for p in projects
    if p.is_division_8
)
```

### Find Projects with Documents
```python
with_specs = [p for p in projects if any(d.type == 'spec' for d in p.documents)]
with_drawings = [p for p in projects if any(d.type == 'drawing' for d in p.documents)]
```

## Schema Import

```python
from modules.schema.unified_project import (
    UnifiedProject,
    Location,
    Document,
    Division8Scope,
    LinkedSource,
    InternalStatus,
    normalize_date,
    normalize_project_value,
    merge_division_8_scopes
)
```

## Validation Example

```python
def validate_project(project: UnifiedProject) -> bool:
    """Validate that project has minimum required fields"""
    if not project.id:
        return False
    if not project.source:
        return False
    if not project.title:
        return False
    return True
```

## Merging Projects from Multiple Sources

```python
from modules.schema.unified_project import merge_division_8_scopes

# Merge Division 8 scopes from multiple sources
merged_scope = merge_division_8_scopes([
    planhub_project.division_8,
    local_project.division_8
])

# Link projects together
planhub_project.linked_sources.append(LinkedSource(
    source="local_bidding",
    id=local_project.id,
    confidence=0.95,
    match_reason="Name and location match"
))
```

## Testing

```bash
# Run comprehensive tests
python3 test_unified_readers.py

# Test individual readers in Python
python3 -c "
from modules.planhub.planhub_db_reader import PlanHubDatabaseReader
reader = PlanHubDatabaseReader()
projects = reader.get_all_leads(status_filter=['done'])
print(f'Loaded {len(projects)} PlanHub projects')
"
```
