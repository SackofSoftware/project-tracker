# Project Tracker

Division 8 project tracking dashboard combining ProjectDog.com scraping with local bidding folder data.

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/project-tracker.git
   cd project-tracker
   ```

2. **Install dependencies**
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your paths and credentials
   ```

4. **Required Configuration**
   At minimum, you must set:
   - `BIDDING_FOLDER` - Path to your main bidding projects folder

5. **Optional Configuration**
   - API keys for AI features (OpenRouter, OpenAI)
   - Database paths for PlanHub, GovWin integrations
   - Email monitor path for bid invite tracking

## Quick Start

```bash
# After completing setup above
python3 app.py
```

Dashboard runs at http://localhost:5003

## Configuration

Environment variables in `.env` (see `.env.example` for full list):
- `BIDDING_FOLDER` - **Required** - Path to local bidding folder
- `PROJECTDOG_EMAIL` - Login email for projectdog.com
- `PROJECTDOG_PASSWORD` - Login password
- `SYNC_INTERVAL_HOURS` - Hours between automatic ProjectDog syncs (default: 24)
- `OPENROUTER_API_KEY` - For AI-powered project briefs
- `PLANHUB_DB_PATH` - Path to PlanHub database
- `GOV_DB_PATH` - Path to GovWin database
- `EMAIL_MONITOR_PATH` - Path to email monitor output

## Architecture

### Data Sources

1. **ProjectDog.com** - Scraped using Selenium
   - Logs in with credentials
   - Selects Division 8 checkbox
   - Parses search results
   - Cached to `static/data/projectdog_projects.json`

2. **Local Bidding Folder** - JSON file reader
   - Reads `projects.json` (main project list)
   - Scans subdirectories for `extracted_project_data.json` files
   - Normalizes data to common format

### Modules

- `modules/scraper/` - ProjectDog.com scraper using Selenium
- `modules/bidding/` - Local bidding folder reader
- `modules/sync/` - Background sync scheduler (APScheduler)

### API Endpoints

#### Project Data
- `GET /api/projects` - All projects from all sources
- `GET /api/projects/local` - Local bidding projects only
- `GET /api/projects/projectdog` - ProjectDog projects only
- `GET /api/projects/upcoming?days=30` - Projects with upcoming bid dates
- `GET /api/project/<project_id>` - Single project details
- `GET /api/project/<project_id>/brief` - AI-generated project brief

#### Project Brief Endpoint
`GET /api/project/<project_id>/brief` generates an AI-powered comprehensive project summary:

**Query Parameters:**
- `format=json|text` - Response format (default: json)
- `use_lm_studio=true|false` - Try LM Studio at localhost:1234 first (default: true)
- `force_openrouter=true|false` - Skip LM Studio, use OpenRouter directly (default: false)

**What it includes:**
- Project metadata (name, address, owner, architect, dates)
- Division 8 scope from specifications
- Window/door counts and types from extracted data
- Drawing classifications by discipline
- Estimate status (takeoff completion)
- Vendor quotes summary
- Available documents checklist
- Next steps recommendations

**Examples:**
```bash
# Get brief in JSON format with full context
curl http://localhost:5003/api/project/21-27-neptune/brief

# Get brief as plain text
curl http://localhost:5003/api/project/21-27-neptune/brief?format=text

# Force OpenRouter (skip LM Studio)
curl http://localhost:5003/api/project/21-27-neptune/brief?force_openrouter=true
```

**AI Provider Priority:**
1. LM Studio (localhost:1234) - if `use_lm_studio=true`
2. OpenRouter (amazon/nova-lite-v1) - if OPENROUTER_API_KEY set
3. Simple text-based brief - if no AI available

#### Status & Sync
- `GET /api/stats` - Dashboard statistics
- `GET /api/sync/status` - Background sync status
- `POST /api/sync/trigger` - Trigger immediate ProjectDog sync
- `POST /api/refresh` - Refresh local project data

## Development

The scraper uses Chrome WebDriver (managed by webdriver-manager).
For debugging the scraper, set `headless=False` in the scraper call.

## PlanHub Scraper Integration

The project-tracker includes an integrated PlanHub scraper for automated lead discovery and extraction.

### Configuration

Environment variables in `.env`:
- `PLANHUB_DB_PATH` - Path to planhub.db SQLite database (default: `/Users/andrewhawes/NEECS Dropbox/Andrew Hawes/Python/planhub_scraper/planhub.db`)
- `PLANHUB_SYNC_INTERVAL_HOURS` - Hours between automatic scraper runs (default: 24)
- `PLANHUB_SCRAPER_MODE` - Scraping mode: `discover`, `fast`, or `full` (default: fast)

### Scraper Modes

1. **discover** - Lead discovery only (finds new projects, no data extraction)
   - Fast, just updates the leads database
   - Use when you want to find new projects without scraping details

2. **fast** - Parallel extraction with 4 workers (~2.3 sec/lead)
   - Extracts Project Info and Files tabs
   - Best for regular automated syncs
   - Recommended for production use

3. **full** - Comprehensive 6-tab extraction (slower)
   - Extracts all tabs: Project Info, Files, GCs, Market Intelligence, Q&A, Estimates
   - More complete data but slower
   - Use when you need maximum detail

### Database

The scraper uses SQLite (`planhub.db`) with three tables:
- `leads` - Project data with JSON columns for structured info
- `project_files` - Document metadata (files not downloaded)
- `pagination_state` - Discovery progress tracking for resume capability

**Current Status (as of integration):**
- Total leads: 282
- Queued for extraction: 244
- Completed: 0
- Locked/Skipped: 38

### Manual Operations

**Trigger immediate sync:**
```bash
POST /api/planhub/sync/trigger
```

**Check scraper status:**
```bash
GET /api/planhub/sync/status
```

**Reset discovery (start pagination over):**
```bash
POST /api/planhub/scraper/reset
```

### Background Sync

The scraper runs automatically on a schedule (default: every 24 hours) using the configured `PLANHUB_SCRAPER_MODE`. Check sync status:

```bash
GET /api/sync/status
```

### Data Flow

1. Scraper discovers leads from PlanHub.com → stores in `planhub.db`
2. Background sync extracts project data → updates database
3. `PlanHubDatabaseReader` reads completed leads (`status='done'`)
4. Data normalized to project-tracker format
5. `PlanHubLocalMatcher` deduplicates with local bidding projects
6. Merged into unified dashboard

### Division 8 Trade Matching

The PlanHub matcher has been enhanced with Division 8 trade awareness to improve match accuracy between PlanHub leads and local Division 8 projects.

**Matching Algorithm:**
- **Base scoring** (unchanged):
  - Name similarity: 0-0.7 points (bonus for very high matches >0.8)
  - Location match: 0.20 points (city + state)
  - Bid date proximity: 0.10 points (within 7 days)

- **NEW - Division 8 scoring:**
  - **+0.25 bonus**: Both projects are Division 8 with trade overlap (Jaccard similarity × 0.25)
  - **-0.15 penalty**: One is Division 8, other isn't (prevents false matches)
  - **No change**: Both non-Division 8 projects

**Trade Overlap Calculation:**
- Uses Jaccard similarity between PlanHub `matching_trades` and local `spec_sections`
- Example: PlanHub has ["Windows", "Doors"], local has "08 51 00 - Windows" and "08 11 00 - Doors"
- Keyword overlap: {windows, doors} ∩ {metal, doors, windows, frames} = {windows, doors}
- Higher overlap → higher bonus (up to 0.25 points)

**Division 8 Detection:**
- PlanHub: Checks `is_division_8` flag or `matching_trades` for keywords (window, door, glazing, storefront, etc.)
- Local: Checks `division_8.spec_sections` or `division_8.windows/doors` counts

**Example Impact:**
```
Both Division 8 with 75% trade overlap: 1.287 score (gets 0.188 bonus)
Both non-Division 8: 1.100 score (baseline)
Division 8 mismatch: 0.950 score (gets -0.15 penalty)
```

Auto-match threshold: 0.65 (unchanged)

**Testing:**
```bash
python3 test_div8_matcher.py  # Run Division 8 matcher tests
```

### Tag-Based Filtering

PlanHub projects include tags from `project_info_json` that enable advanced filtering and prioritization.

**Available Tags** (from database analysis of 282 projects):
- **Sub Bidding** (230 projects, 82%) - Projects accepting subcontractor bids
- **Commercial** (244 projects, 87%) - Commercial sector classification
- **Renovation** (88 projects, 31%) - Renovation work
- **New Construction** (31 projects, 11%) - New construction projects
- **Retail** (41 projects, 15%) - Retail sector
- **GC Awarded** (8 projects, 3%) - General contractor already selected
- **Industrial** (1 project, <1%) - Industrial sector

**Tag Classification:**

Each project is automatically classified into:
- **`project_type`**: "Renovation", "New Construction", "Tenant Build-Out", "Addition", or "Unknown"
- **`sector`**: "Commercial", "Retail", "Industrial", "Education", "Healthcare", "Hospitality", or "Unknown"
- **`is_sub_bidding`**: Boolean - whether project accepts subcontractor bids
- **`is_gc_awarded`**: Boolean - whether GC is already selected (lower priority)

**Filter API Endpoint:**

```bash
POST /api/planhub/filter
Content-Type: application/json

{
  "require_sub_bidding": true,       # Only "Sub Bidding" projects
  "exclude_gc_awarded": true,        # Exclude "GC Awarded" projects
  "division_8_only": true,           # Only Division 8 scope
  "project_type": "Renovation",      # Filter by type
  "sector": "Retail",                # Filter by sector
  "state": "MA",                     # Filter by state
  "tags": ["Retail", "Renovation"]   # Must have ALL listed tags
}
```

**Response:**
```json
{
  "total": 282,
  "filtered": 36,
  "filters_applied": {...},
  "projects": [...]
}
```

**Example Queries:**

```bash
# Get only Sub Bidding projects in Retail sector
curl -X POST http://localhost:5003/api/planhub/filter \
  -H "Content-Type: application/json" \
  -d '{"require_sub_bidding": true, "sector": "Retail"}'

# Get MA renovations, exclude GC awarded
curl -X POST http://localhost:5003/api/planhub/filter \
  -H "Content-Type: application/json" \
  -d '{"state": "MA", "project_type": "Renovation", "exclude_gc_awarded": true}'

# Get Division 8 projects only
curl -X POST http://localhost:5003/api/planhub/filter \
  -H "Content-Type: application/json" \
  -d '{"division_8_only": true}'
```

**Testing:**
```bash
python3 test_tag_filtering.py  # Run tag extraction and filtering tests
```

### Playwright Setup

The scraper requires Playwright with Chromium:

```bash
pip3 install playwright
playwright install chromium
```

### Standalone Usage

The scraper module can still be used independently:

```bash
cd modules/planhub_scraper
python3 scraper.py discover  # Find new leads
python3 scraper.py status    # Show statistics
python3 fast_scraper.py      # Extract data
```
