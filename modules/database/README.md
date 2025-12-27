# Database Module

Centralized SQLite database for Project Tracker, replacing scattered JSON files.

## Overview

This module provides a complete SQLAlchemy-based database solution that consolidates all project data from multiple JSON sources into a single, efficient SQLite database.

## Database Location

`/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/project-tracker/data/project_tracker.db`

## Quick Start

### 1. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Initialize Database

```python
from modules.database import db

# Create all tables
db.init_db()
```

### 3. Migrate Existing JSON Data

```bash
# From command line
python3 -m modules.database.migrate --bidding-folder "/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Bob Projects/Bidding"

# Or in Python
from modules.database.migrate import migrate_from_json

migrate_from_json(
    bidding_folder="/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Bob Projects/Bidding"
)
```

### 4. Query Data

```python
from modules.database import queries

# Get all projects
projects = queries.get_all_projects()

# Get specific project
project = queries.get_project('21-27-neptune')

# Get upcoming projects (next 30 days)
upcoming = queries.get_upcoming_projects(days=30)

# Search projects
results = queries.search_projects('boston')

# Get Division 8 scope
scope = queries.get_division8_scope('21-27-neptune')
```

## Database Schema

### Core Tables

#### `projects`
Core project information including contact details, dates, and requirements.

**Key fields:**
- `id` - Project slug (primary key)
- `folder_path` - Path to local project folder
- `title`, `address`, `city`, `state`
- `owner_name`, `architect_name`, `engineer_name`
- `bid_date`, `sub_bid_date`, `estimated_value`
- `dcam_required`, `prevailing_wage`, `mbe_goal_percent`

#### `project_status`
Bid decisions, proposals, estimates, and document status.

**Key fields:**
- `bid_decision` - 'bid', 'no-bid', 'pending'
- `bid_decision_reason`, `bid_decision_date`
- `proposal_generated`, `proposal_submitted`
- `estimate_created`, `estimate_total`
- Estimate breakdown: `windows_total`, `doors_total`, `hardware_total`, etc.
- `documents_acquired`, `has_specs`, `has_drawings`

#### `project_files`
File classifications for all project documents.

**Key fields:**
- `name`, `path`, `file_type`
- `pages`, `size_mb`, `dimensions`
- `sheet_number`, `sheet_title`, `discipline`
- `classified_by` - 'heuristic', 'llm', 'user'

#### `division8_scope`
AI-extracted Division 8 scope from specifications.

**Key fields:**
- `scope_summary`, `confidence`
- `windows_count`, `windows_types`, `windows_notes`
- `metal_door_count`, `wood_door_count`, `doors_notes`
- `storefront_description`, `storefront_sf_estimate`
- `hardware_groups`, `hardware_manufacturers`
- `glass_specs`, `exclusions`

### Vendor Tables

#### `vendors`
Vendor database with contact information.

**Key fields:**
- `name`, `contact_name`, `email`, `phone`
- `address`, `city`, `state`
- `company_type` - 'manufacturer', 'distributor', 'subcontractor'
- `specialties`, `certifications`

#### `vendor_quotes`
Vendor quotes linked to projects and vendors.

**Key fields:**
- `project_id`, `vendor_id`
- `quote_number`, `quote_date`, `category`
- `amount`, `unit_price`, `quantity`, `unit`
- `status` - 'pending', 'received', 'accepted', 'rejected'

### External Data Tables

#### `projectdog_projects`
Projects scraped from ProjectDog.com.

**Key fields:**
- `project_code` (unique)
- `title`, `is_rfq`, `is_dcam`
- `bid_date`, `sub_bid_date`, `estimated_value`
- `city`, `state`
- `has_documents`, `documents`, `document_recipients`

#### `planhub_links`
Mapping between PlanHub IDs and local project folders.

**Key fields:**
- `planhub_id` (unique)
- `project_id` - Local project slug

### Supporting Tables

#### `project_notes`
User notes on projects.

#### `project_tags`
Tags for categorizing projects.

#### `competitors`
Competitors tracked per project.

#### `extracted_project_data`
Raw JSON cache of AI-extracted project data.

## Usage Examples

### Creating Projects

```python
from modules.database import queries

# Create a new project
project = queries.create_project(
    project_id='new-school-project',
    data={
        'title': 'New Elementary School',
        'address': '123 Main St',
        'city': 'Boston',
        'state': 'MA',
        'source': 'local',
        'bid_date': datetime(2025, 12, 15)
    }
)
```

### Updating Project Status

```python
from modules.database import queries

# Update project status
status = queries.create_or_update_status(
    project_id='new-school-project',
    data={
        'bid_decision': 'bid',
        'bid_decision_reason': 'Good scope, competitive opportunity',
        'estimate_created': True,
        'estimate_total': 125000.00,
        'windows_total': 45000.00,
        'doors_total': 60000.00,
        'hardware_total': 20000.00
    }
)
```

### Working with Vendors

```python
from modules.database import queries

# Get or create vendor
vendor = queries.get_or_create_vendor(
    name='Acme Windows Inc',
    vendor_data={
        'contact_name': 'John Smith',
        'email': 'john@acmewindows.com',
        'phone': '617-555-1234',
        'specialties': ['windows', 'storefront']
    }
)

# Add a quote
quote = queries.add_vendor_quote({
    'project_id': 'new-school-project',
    'vendor_id': vendor.id,
    'category': 'windows',
    'amount': 42000.00,
    'status': 'received'
})
```

### Adding Files

```python
from modules.database import queries

# Add multiple files at once
files = queries.bulk_add_files(
    project_id='new-school-project',
    files_data=[
        {
            'name': 'Architectural Drawings.pdf',
            'path': '/path/to/file.pdf',
            'file_type': 'drawing_set',
            'pages': 48,
            'size_mb': 12.5
        },
        {
            'name': 'Specifications.pdf',
            'path': '/path/to/specs.pdf',
            'file_type': 'specification',
            'pages': 156,
            'size_mb': 3.2
        }
    ]
)
```

### Searching and Filtering

```python
from modules.database import queries

# Get projects by source
local_projects = queries.get_projects_by_source('local')
projectdog_projects = queries.get_projects_by_source('projectdog')

# Get upcoming bids (next 30 days)
upcoming = queries.get_upcoming_projects(days=30)

# Search projects
results = queries.search_projects('elementary school')
```

### Using Sessions

For multiple operations, use a session to batch database operations:

```python
from modules.database.db import get_session

with get_session() as session:
    # Create project
    project = queries.create_project(
        'batch-project',
        {'title': 'Batch Project'},
        session=session
    )

    # Add status
    status = queries.create_or_update_status(
        'batch-project',
        {'bid_decision': 'bid'},
        session=session
    )

    # Add notes
    queries.add_project_note(
        'batch-project',
        'This is a test project',
        session=session
    )

    # All operations committed together when context exits
```

## Migration Details

The migration script (`migrate.py`) handles:

1. **Static Data Files** (`static/data/`)
   - `projectdog_projects.json` - ProjectDog scraped projects
   - `planhub_links.json` - PlanHub mappings
   - `project_status.json` - All project statuses
   - `vendors.json` - Vendor database

2. **Per-Project Files** (in each project folder)
   - `extracted_project_data.json` - AI-extracted metadata
   - `division8_rag_analysis.json` - Division 8 scope analysis
   - `.file_classifications.json` - File classifications

### Migration Options

```bash
# Full migration
python3 -m modules.database.migrate --bidding-folder "/path/to/bidding"

# Skip ProjectDog (useful if file is too large)
python3 -m modules.database.migrate --skip-projectdog

# Skip local projects (only import static data)
python3 -m modules.database.migrate --skip-local

# Combine options
python3 -m modules.database.migrate --skip-projectdog --skip-local
```

## Database Management

### Check Database Health

```python
from modules.database.db import check_database

health = check_database()
print(health)
# {
#     'status': 'healthy',
#     'path': '/path/to/database.db',
#     'tables': ['projects', 'project_status', ...],
#     'table_count': 13,
#     'connection': 'ok'
# }
```

### Reset Database (CAUTION!)

```python
from modules.database.db import reset_db

# This will DROP ALL TABLES and recreate them
# ALL DATA WILL BE LOST!
reset_db()
```

## Best Practices

1. **Use Sessions for Batch Operations**: When performing multiple related operations, use `get_session()` context manager to batch commits.

2. **Let Queries Handle Sessions**: Most query functions can work with or without a provided session, making them flexible.

3. **Foreign Key Integrity**: SQLite foreign keys are enabled, so deleting a project will cascade delete all related data.

4. **JSON Fields**: Use JSON fields for flexible arrays and objects (e.g., `windows_types`, `hardware_groups`).

5. **Date Parsing**: The migration script handles multiple date formats automatically.

6. **Backward Compatibility**: Keep JSON files during transition period for rollback capability.

## Performance

- **Write-Ahead Logging (WAL)**: Enabled for better concurrency
- **Foreign Key Indexes**: All foreign keys are indexed
- **Connection Pooling**: Static pool for SQLite single-file access
- **Batch Operations**: Use `bulk_save_objects()` for large imports

## Troubleshooting

### Migration Errors

Check the migration summary for specific errors:

```python
from modules.database.migrate import migrate_from_json

stats = migrate_from_json(bidding_folder="/path/to/bidding")
print(stats['errors'])
```

### Database Locked

If you get "database is locked" errors:
- Close all other connections to the database
- WAL mode helps, but SQLite still has limits
- Use sessions properly (always close them)

### Large JSON Files

If `projectdog_projects.json` is too large:
- Use `--skip-projectdog` flag
- Import it separately with pagination
- Consider splitting the file

## Future Enhancements

Potential improvements:
- [ ] Add full-text search indexes
- [ ] Add database backup/restore utilities
- [ ] Add database vacuum/optimization commands
- [ ] Add more complex query builders
- [ ] Add database versioning/migrations (Alembic)
- [ ] Add data export to JSON (for backup)
