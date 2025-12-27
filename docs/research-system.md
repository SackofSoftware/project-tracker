# Company Research System

AI-powered company research using vision models to extract structured data from websites.

## Overview

The research system uses a **hybrid Vision + HTML scraping approach** to gather comprehensive company information:

1. **Google Search** finds the official company website
2. **Playwright** takes full-page screenshots (capturing footers with addresses)
3. **Vision Models** (Gemma 3 4B) analyze screenshots and extract structured data
4. **HTML Parsing** discovers navigation structure, dropdowns, and links
5. **LLM** generates a polished company summary
6. **Database** stores everything as structured artifacts (Claims with Evidence)

**Cost: ~$0.002-0.005 per company**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        RESEARCH PIPELINE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. FIND WEBSITE                                                 │
│     └─ Google Custom Search API → Filter out Yelp/LinkedIn/etc  │
│                                                                  │
│  2. DISCOVER STRUCTURE                                           │
│     └─ Fetch HTML → Parse nav/header → Categorize links:        │
│        • team: /team, /people, /staff, /leadership              │
│        • contact: /contact, /locations                          │
│        • portfolio: /portfolio, /projects, /gallery, /work      │
│        • about: /about, /company, /history                      │
│        • services: /services, /capabilities                     │
│                                                                  │
│  3. SCREENSHOT PAGES (Full-page to capture footers)             │
│     └─ Homepage → About → Team → Contact → Portfolio            │
│                                                                  │
│  4. VISION EXTRACTION                                            │
│     └─ Each screenshot → Vision Model → Structured JSON:        │
│        • Company name, tagline, description                     │
│        • Founded year, headquarters address                     │
│        • Phone, email, certifications                           │
│        • Leadership names and titles                            │
│        • Portfolio projects with types                          │
│                                                                  │
│  5. RECURSIVE EXPLORATION                                        │
│     └─ Team page → Find individual staff links → Visit each     │
│     └─ Portfolio page → Find project links → Visit top 3        │
│                                                                  │
│  6. AGGREGATE DATA                                               │
│     └─ Merge all sources → Deduplicate → Build unified profile  │
│                                                                  │
│  7. GENERATE SUMMARY                                             │
│     └─ GPT-4.1-nano → 6-8 sentence professional summary         │
│                                                                  │
│  8. CREATE CLAIMS                                                │
│     └─ Each fact → Claim with Evidence (source URL)             │
│                                                                  │
│  9. SAVE TO DATABASE                                             │
│     └─ Company profile + Research session + Claims + Evidence   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Extracted

### Company Profile
| Field | Source | Description |
|-------|--------|-------------|
| `company_name` | Homepage vision | Official company name |
| `website` | Google Search | Official website URL |
| `founded` | About page vision | Year founded |
| `headquarters` | Contact vision / Footer | Full address |
| `phone` | Contact / Footer | Main phone number |
| `email` | Contact / Footer | Main email |
| `description` | About page vision | Company description |
| `company_summary` | LLM generated | 6-8 sentence summary |
| `certifications` | Homepage/About vision | WBE, MBE, LEED, etc. |
| `leadership` | Team page vision | Executives with titles/bios |
| `staff` | Team page vision | Other staff members |
| `portfolio` | Portfolio vision | Projects with types |
| `social_links` | HTML parsing | LinkedIn, Facebook, etc. |

### Structured Artifacts

**Claims** - Discrete, verifiable facts:
```json
{
  "claim_text": "Company was founded in 1998",
  "claim_type": "experience",
  "confidence": 0.85,
  "support_type": "direct",
  "evidence": [{
    "source_url": "https://company.com/about",
    "source_title": "Company Website",
    "evidence_text": "Founded in 1998..."
  }]
}
```

**Claim Types:**
- `contact` - Phone, email, address
- `experience` - Founded year, history
- `certification` - WBE, LEED, etc.
- `leadership` - Executives and their roles

---

## Vision Prompts

The system uses flexible prompts that allow the model to extract any relevant data:

### Homepage Prompt
```
Analyze this company website homepage. Extract ALL visible information.

Required fields (use null if not found):
- company_name, tagline, description
- founded, headquarters, phone, email

Many homepages contain "About Us" info - look for:
- History/founding story, certifications, leadership names

IMPORTANT: Check the FOOTER area for address, phone, and contact info.

Return as JSON with all information found.
```

### Contact Page Prompt
```
Analyze this contact page. Extract ALL contact information visible.

Look for:
- address: Full street address (street, city, state, zip)
- headquarters: Main office location
- phone, email, fax, office_hours
- branches: Any additional office locations

IMPORTANT: Check the footer area carefully for address information.
```

### Team Page Prompt
```
Analyze this team/staff page. List ALL people shown.

For each person, extract:
- name, title, email, phone, department, bio snippet

Return JSON: {"people": [...], "departments": [...], "total_count": X}
```

### Portfolio Prompt
```
Analyze this portfolio/projects page. Extract information about ALL projects.

For each project:
- name, type (healthcare, education, commercial, etc.)
- location, size, client, status, year, description

Return JSON: {"projects": [...], "specialties": [...], "total_projects_shown": X}
```

---

## Models Used

| Purpose | Model | Cost |
|---------|-------|------|
| Vision extraction | `google/gemma-3-4b-it:free` | FREE |
| Vision fallback | `google/gemini-2.0-flash-lite-001` | $0.0002/image |
| Summary generation | `openai/gpt-4.1-nano` | ~$0.001/summary |
| Website search | Google Custom Search API | FREE (100/day) |

---

## API Endpoints

### Companies
```
GET    /api/research/companies              # List all companies
POST   /api/research/companies              # Create new company
GET    /api/research/companies/<id>         # Get full profile
PUT    /api/research/companies/<id>         # Update company
DELETE /api/research/companies/<id>         # Delete company
```

### Research
```
POST   /api/research/start                  # Start research session
       Body: {company_name, website_url?, location?}

GET    /api/research/session/<id>           # Get session status/results
GET    /api/research/session/<id>/stream    # SSE for real-time progress
```

### Claims
```
GET    /api/research/companies/<id>/claims  # Get all claims for company
PUT    /api/research/claims/<id>            # Update claim (verification)
```

### Utilities
```
POST   /api/research/quick                  # Quick scrape (no DB save)
POST   /api/research/import-companies       # Import from companies.json
```

---

## Usage Examples

### Python - Direct Scraping
```python
from modules.research import scrape_company_sync

result = scrape_company_sync(
    company_name="South Coast Improvement",
    location="Marion, MA",
    website_url="https://southcoastimprovement.com/",  # Optional
    max_staff_pages=10
)

print(result['aggregated'])  # Unified company profile
print(result['portfolio_data'])  # Portfolio/projects
print(result['pages_visited'])  # URLs visited
```

### Python - Full Research Pipeline
```python
from modules.research import research_company_sync

result = research_company_sync(
    company_name="NEL Corporation",
    location="New Hampshire",
    max_staff_pages=5,
    save_to_db=True
)

print(f"Status: {result['status']}")
print(f"Claims: {len(result['claims'])}")
print(f"Summary: {result['summary']}")
```

### API - Start Research
```bash
curl -X POST http://localhost:5003/api/research/start \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Kaplan Construction", "location": "Boston, MA"}'
```

### API - Quick Research
```bash
curl -X POST http://localhost:5003/api/research/quick \
  -H "Content-Type: application/json" \
  -d '{"company_name": "DDC Construction", "website_url": "https://ddc-construction.com"}'
```

---

## Database Schema

```sql
-- Company profile
companies (
    id, name, company_type, website, phone, email,
    headquarters, founded, employee_count, description,
    company_summary, certifications (JSON), leadership (JSON),
    staff (JSON), portfolio (JSON), social_links (JSON),
    research_status, last_researched
)

-- Research session tracking
research_sessions (
    id, company_id, query, status, started_at, completed_at,
    current_stage, progress_pct, sources_used (JSON)
)

-- Structured claims
research_claims (
    id, session_id, company_id, claim_text, claim_type,
    confidence, support_type
)

-- Evidence for claims
research_evidence (
    id, claim_id, evidence_text, source_url, source_title,
    source_type, accessed_at
)
```

---

## Configuration

Environment variables in `.env`:

```bash
# Google Custom Search (free tier: 100/day)
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CX=your_search_engine_id

# OpenRouter for vision/LLM models
OPENROUTER_API_KEY=your_openrouter_key
```

---

## Page Flow

```
┌──────────────────────────────────────────────────────────────────┐
│  /research                                                        │
├────────────────────┬─────────────────────────────────────────────┤
│                    │                                              │
│  SIDEBAR           │  MAIN PANEL                                  │
│                    │                                              │
│  Companies         │  [Quick Research Input]                      │
│  ────────────      │  ┌────────────────────────────────────────┐ │
│  ● Kaplan [✓]      │  │ Enter company name...         [Search] │ │
│  ○ South Coast     │  └────────────────────────────────────────┘ │
│  ○ NEL Corp        │                                              │
│  ○ DDC             │  [Company Profile Card]                      │
│                    │  ┌────────────────────────────────────────┐ │
│  [+ Add Company]   │  │ [Overview] [Team] [Portfolio] [Claims] │ │
│                    │  ├────────────────────────────────────────┤ │
│  Stats             │  │                                        │ │
│  ────────────      │  │  Summary: Kaplan Construction,         │ │
│  Total: 20         │  │  founded in 1976, is a distinguished...│ │
│  Researched: 3     │  │                                        │ │
│                    │  │  Website: kaplanconstructs.com         │ │
│                    │  │  Phone: (617) 555-1234                 │ │
│                    │  │  Founded: 1976                         │ │
│                    │  │                                        │ │
│                    │  │  Certifications: [WBE] [LEED]          │ │
│                    │  │                                        │ │
│                    │  └────────────────────────────────────────┘ │
│                    │                                              │
└────────────────────┴─────────────────────────────────────────────┘
```

---

## Why Vision + HTML Hybrid?

1. **Vision catches what HTML misses** - Dynamically rendered content, images with text, complex layouts

2. **HTML catches what vision misses** - Navigation structure, dropdown menus, link URLs

3. **Footers contain gold** - Full-page screenshots capture address/phone in footers that many scrapers miss

4. **Flexible extraction** - Vision models adapt to any website design without custom selectors

5. **Recursive discovery** - HTML parsing finds individual staff/project pages, vision extracts the details

---

## Cost Breakdown

For a typical company research:

| Step | Calls | Cost |
|------|-------|------|
| Google Search | 1 | FREE |
| Screenshots | 5-10 | FREE (Playwright) |
| Vision Analysis | 5-10 | FREE (Gemma 3 4B) |
| Summary Generation | 1 | ~$0.001 |
| **Total** | | **~$0.001-0.005** |

At $0.005/company, researching 100 companies costs ~$0.50.
