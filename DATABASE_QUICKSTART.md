# Database Quick Start Guide

## Installation

```bash
# Install SQLAlchemy
pip3 install -r requirements.txt
```

## Initialize Database

```python
from modules.database import db

# Create all tables
db.init_db()
```

## Migrate Existing JSON Data

### Command Line

```bash
# Full migration (recommended)
python3 -m modules.database.migrate \
  --bidding-folder "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Bob Projects/Bidding"

# Skip ProjectDog (if file is too large)
python3 -m modules.database.migrate \
  --bidding-folder "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Bob Projects/Bidding" \
  --skip-projectdog

# Only static data (no local projects)
python3 -m modules.database.migrate --skip-local
```

### Python

```python
from modules.database.migrate import migrate_from_json

# Full migration
stats = migrate_from_json(
    bidding_folder="/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Bob Projects/Bidding"
)

# Check results
print(stats)
```

## Common Queries

```python
from modules.database import queries

# Get all projects
projects = queries.get_all_projects()

# Get specific project
project = queries.get_project('project-slug')

# Search projects
results = queries.search_projects('boston')

# Get upcoming bids (next 30 days)
upcoming = queries.get_upcoming_projects(days=30)

# Get project status
status = queries.get_project_status('project-slug')

# Get Division 8 scope
scope = queries.get_division8_scope('project-slug')

# Get project files
files = queries.get_project_files('project-slug')

# Get vendors
vendors = queries.get_all_vendors()

# Get quotes for a project
quotes = queries.get_project_quotes('project-slug')

# Get dashboard stats
stats = queries.get_dashboard_stats()
```

## Database Location

```
/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/project-tracker/data/project_tracker.db
```

## Run Examples

```bash
python3 -m modules.database.example
```

## Full Documentation

See `/modules/database/README.md` for complete documentation.

## Database Schema

### Main Tables
- `projects` - Core project data
- `project_status` - Bid decisions, estimates, proposals
- `project_files` - File classifications
- `division8_scope` - RAG-analyzed Division 8 scope
- `vendors` - Vendor database
- `vendor_quotes` - Vendor quotes
- `projectdog_projects` - ProjectDog scraped data
- `planhub_links` - PlanHub mappings
- `project_notes` - User notes
- `project_tags` - Project tags
- `competitors` - Competitor tracking
- `extracted_project_data` - Raw AI-extracted data

## Migration What Gets Imported

### From `static/data/`:
- `projectdog_projects.json` → `projectdog_projects` table
- `planhub_links.json` → `planhub_links` table
- `project_status.json` → `projects`, `project_status`, `project_notes`, `project_tags`, `competitors` tables
- `vendors.json` → `vendors` table

### From each project folder:
- `extracted_project_data.json` → `extracted_project_data` table (+ updates `projects`)
- `division8_rag_analysis.json` → `division8_scope` table
- `.file_classifications.json` → `project_files` table

## Backward Compatibility

During the transition period:
1. Keep existing JSON files as backup
2. Database reads from SQLite
3. Can fall back to JSON if needed
4. Migration can be re-run safely (upserts, not duplicates)

## Troubleshooting

### Check Database Health
```python
from modules.database.db import check_database
print(check_database())
```

### Migration Errors
```python
from modules.database.migrate import migrate_from_json
stats = migrate_from_json(bidding_folder="/path/to/bidding")
print(stats['errors'])  # See specific errors
```

### Reset Database (CAUTION - DELETES ALL DATA!)
```python
from modules.database.db import reset_db
reset_db()  # Drops all tables and recreates them
```
