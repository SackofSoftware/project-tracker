"""
PlanHub Scraper Configuration
Auto-discovers leads from paginated list, skips locked projects, extracts all data.
"""
from pathlib import Path
import os
import re

# Base paths
BASE_DIR = Path(__file__).parent
SESSION_DIR = BASE_DIR / "session"

# Database path - required from environment
_db_path_env = os.getenv('PLANHUB_DB_PATH')
if not _db_path_env:
    raise ValueError("PLANHUB_DB_PATH environment variable not set. Copy .env.example to .env and configure.")
DB_PATH = Path(_db_path_env)

HTML_FALLBACK_DIR = BASE_DIR / "html_fallback"

# Session file for Playwright
SESSION_FILE = SESSION_DIR / "planhub_state.json"

# PlanHub URLs
LOGIN_URL = "https://access.planhub.com/signin"
LEADS_LIST_URL = "https://subcontractor.planhub.com/leads/list?type=planhub"
BASE_URL = "https://subcontractor.planhub.com"

# Scraping settings
REQUEST_DELAY = 3           # seconds between page requests (after each lead)
PAGE_LOAD_TIMEOUT = 60000   # ms - Angular apps need longer
ELEMENT_WAIT_TIMEOUT = 15000  # ms for individual elements (headless needs longer)
MAX_RETRIES = 3
HEADLESS = True             # True for scraping (needs ~10s load time), False for login/debug

# ==============================================
# VISION LLM SETTINGS
# ==============================================
VISION_ENABLED = True           # Use vision model for page analysis
VISION_USE_LOCAL = True         # Try LM Studio (localhost:1234) first
VISION_DEBUG_SCREENSHOTS = True # Save screenshots to debug folder
SCREENSHOT_DIR = BASE_DIR / "debug_screenshots"

# ==============================================
# SELECTORS - PlanHub Angular App
# ==============================================

# Login page (access.planhub.com)
LOGIN_SELECTORS = {
    "email_input": "input[type='email'], input[name='email'], input[formcontrolname='email']",
    "password_input": "input[type='password'], input[name='password']",
    "submit_button": "button[type='submit']",
    "login_form": "form",
}

# Login validation
LOGIN_VALIDATION = {
    "logged_in_indicator": ".profile-menu, [qa-locator='profile-menu'], mat-toolbar",
    "login_page_indicator": "input[type='email'], .login-form",
}

# Leads list page
LEADS_LIST_SELECTORS = {
    # Lead items - the Angular component containing each lead
    "lead_item": ".lead-name",
    "lead_item_container": "planhub-lead-item",  # The Angular component wrapper

    # Locked project indicators (SKIP these)
    "locked_icon": "mat-icon[svgicon='lead-locked']",
    "locked_by_title": "[title='Locked']",

    # Pagination
    "next_page": "button[qa-locator*='next-page']",
    "prev_page": "button[qa-locator*='prev-page'], button[qa-locator*='previous-page']",

    # Page loading indicator
    "loading_spinner": "mat-spinner, .mat-progress-spinner",

    # Lead list container
    "lead_list": ".lead-list, .list-body",
}

# Project detail page tabs
TAB_SELECTORS = {
    "project_info": "[qa-locator='link-to-Project Info']",
    "project_files": "[qa-locator='link-to-Project Files']",
    "general_contractors": "[qa-locator='link-to-General Contractors']",
    "market_intelligence": "[qa-locator='link-to-Market Intelligence']",
    "project_qa": "[qa-locator='link-to-Project Q&A']",
    "material_estimates": "[qa-locator='link-to-Material Estimates']",
}

# Tab URL paths
TAB_PATHS = {
    'project_info': 'project-info',
    'project_files': 'project-files',
    'general_contractors': 'general-contractors',
    'market_intelligence': 'market-intelligence',
    'project_qa': 'project-q-a',
    'material_estimates': 'material-estimates',
}

# Project Info tab selectors
PROJECT_INFO_SELECTORS = {
    "bid_due_date": ".project__bid-due-date-value",
    "time_remaining": ".project__time-remaining",
    "project_header": ".project__header, planhub-project-details-redesign-header",
    "mat_form_fields": "mat-form-field",
    "project_name": "h1, .project-name, .lead-title, .lead-name span",
}

# Project Files tab selectors
PROJECT_FILES_SELECTORS = {
    "file_table": "table, mat-table, .files-table",
    "file_row": "tr:not(:first-child), mat-row, .file-row",
    "file_name": ".file-name, td:first-child, mat-cell:first-child",
    "no_files": ".no-files, .empty-state",
}

# General Contractors tab selectors
GC_SELECTORS = {
    "gc_container": ".general-contractors, .contractors-list, .gc-list",
    "gc_card": ".contractor-card, .gc-card, mat-card, .connection",
    "gc_name": ".contractor-name, .gc-name, .company-name, h3, h4",
    "gc_contact": ".contact-name, .contact",
    "gc_phone": ".phone, [href^='tel:']",
    "gc_email": ".email, [href^='mailto:']",
}

# Market Intelligence selectors
MARKET_INTEL_SELECTORS = {
    "container": ".market-intelligence, app-market-intelligence, [qa-locator='link-to-Market Intelligence']",
    "activity_section": ".activity-wrapper, .competitive-advantage",
    "sub_trade_row": ".sub-trade-row",
}

# Project Q&A selectors
QA_SELECTORS = {
    "qa_container": ".qa-list, .questions-list, .project-qa",
    "qa_item": ".qa-item, .question-item, .question-answer",
    "question": ".question-text, .question",
    "answer": ".answer-text, .answer",
}

# Material Estimates selectors
MATERIAL_SELECTORS = {
    "container": ".material-estimates, .estimates-section",
    "estimate_item": ".estimate-item, .material-item",
}


# ==============================================
# Helper Functions
# ==============================================

def extract_lead_id(url: str) -> str:
    """Extract lead ID from URL like /leads/details/12345/project-info"""
    if not url:
        return None
    match = re.search(r'/leads/details/(\d+)', url)
    return match.group(1) if match else None


def get_project_tab_url(lead_id: str, tab: str) -> str:
    """Generate URL for a specific project tab"""
    path = TAB_PATHS.get(tab, 'project-info')
    return f"{BASE_URL}/leads/details/{lead_id}/{path}"


def is_login_redirect(url: str) -> bool:
    """Check if URL indicates a login redirect"""
    return any(x in url.lower() for x in ['signin', 'login', 'access.planhub'])


def ensure_dirs():
    """Ensure required directories exist"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    HTML_FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
