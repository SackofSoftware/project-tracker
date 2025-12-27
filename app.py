#!/usr/bin/env python3
"""
Project Tracker
Division 8 project dashboard combining ProjectDog.com and local bidding data
With internal workflow tracking (proposals, estimates, bid decisions)
"""

import os
import json
import time
import threading
import requests
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory

from dotenv import load_dotenv
load_dotenv()

from modules.scraper import ProjectDogScraper, scrape_projectdog
from modules.bidding import BiddingFolderReader
from modules.sync import BackgroundSync
from modules.tracking import ProjectStatusTracker
from modules.thumbnails import ThumbnailGenerator
from modules.notes import SmartNotesProcessor
from modules.estimates import EstimateReader
from modules.vendors import VendorManager
from modules.quotes import QuoteReader
from modules.files import FileOrganizer
from modules.planhub.planhub_reader import load_planhub_projects
from modules.planhub.planhub_matcher import PlanHubLocalMatcher
from modules.planhub.planhub_sync import sync_planhub

# Import utility functions (including refresh_all_projects with GovWin integration)
from utils import refresh_all_projects as utils_refresh_all_projects

# Import database-centric modules (API v2)
try:
    from modules.database.db import init_db, run_migrations
    from modules.database.project_repository import get_repository
    from modules.sync import init_scheduler, stop_scheduler, get_scheduler_status
    DATABASE_AVAILABLE = True
except ImportError as e:
    print(f"Database modules not available: {e}")
    DATABASE_AVAILABLE = False

# Import CSI Masterformat prompt builder for enhanced briefs
try:
    from modules.brief.prompt_builder import (
        build_division8_brief,
        get_section_description,
        load_division_context,
        load_manufacturer_specs
    )
    PROMPT_BUILDER_AVAILABLE = True
except ImportError as e:
    print(f"Prompt builder module not available: {e}")
    PROMPT_BUILDER_AVAILABLE = False

# Import document classification modules (for specs and drawings analysis)
try:
    from modules.doc_classification import (
        extract_divisions_from_pdf,
        identify_sheets_in_pdf,
        summarize_disciplines,
        DISCIPLINE_CODES
    )
    DOC_CLASSIFICATION_AVAILABLE = True
except ImportError as e:
    print(f"Doc classification module not available: {e}")
    DOC_CLASSIFICATION_AVAILABLE = False

# Import extraction modules (optional - may not have dependencies installed)
try:
    from modules.extraction.extraction_agents import ExtractionOrchestrator
    from modules.extraction.rag_engine import RAGEngine
    from modules.extraction.config import PROJECTS_DIR as EXTRACTION_PROJECTS_DIR
    EXTRACTION_AVAILABLE = True
except ImportError as e:
    print(f"Extraction module not available: {e}")
    EXTRACTION_AVAILABLE = False

app = Flask(__name__)


# Custom Jinja2 template filter for date formatting (mm/dd/yy)
@app.template_filter('format_date')
def format_date_filter(date_str):
    """Convert various date formats to mm/dd/yy"""
    if not date_str or date_str == 'None' or date_str == '':
        return ''

    try:
        # Try ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        if isinstance(date_str, str) and '-' in date_str and len(date_str) >= 10:
            parts = date_str[:10].split('-')
            if len(parts) == 3 and len(parts[0]) == 4:
                return f"{parts[1]}/{parts[2]}/{parts[0][2:]}"

        # Try MM/DD/YYYY format
        if isinstance(date_str, str) and '/' in date_str:
            parts = date_str.split('/')
            if len(parts) == 3:
                if len(parts[2]) == 4:  # MM/DD/YYYY
                    return f"{parts[0]}/{parts[1]}/{parts[2][2:]}"
                elif len(parts[2]) == 2:  # Already mm/dd/yy
                    return date_str

        # Try datetime object
        if isinstance(date_str, datetime):
            return date_str.strftime('%m/%d/%y')

        return str(date_str)
    except Exception:
        return str(date_str)


# =====================================================================
# CSI TAG TEMPLATE FILTERS
# =====================================================================

# Tag category mapping for CSS classes
TAG_CATEGORIES = {
    # Doors
    "Hollow Metal Doors": "doors", "Hollow Metal Frames": "doors",
    "Aluminum Doors": "doors", "Aluminum Frames": "doors",
    "Stainless Doors": "doors", "Wood Doors": "doors",
    "FRP Doors": "doors", "Composite Doors": "doors",
    "Access Doors": "doors", "Sliding Glass Doors": "doors",
    "Coiling Doors": "doors", "Overhead Coiling Doors": "doors",
    "Security Grilles": "doors", "Folding Doors": "doors",
    "Sectional Doors": "doors", "Traffic Doors": "doors",
    "Detention Doors": "doors",
    # Storefront
    "Storefront": "storefront", "Entrances": "storefront",
    "All-Glass Entrances": "storefront", "Automatic Entrances": "storefront",
    "Revolving Entrances": "storefront", "Balanced Doors": "storefront",
    # Curtain Wall
    "Curtain Wall": "curtainwall", "Structural Glass Curtain Wall": "curtainwall",
    "Sloped Curtain Wall": "curtainwall", "Unitized Curtain Wall": "curtainwall",
    "Point-Supported Curtain Wall": "curtainwall", "Window Wall": "curtainwall",
    "Translucent Assemblies": "curtainwall",
    # Windows
    "Windows": "windows", "Aluminum Windows": "windows",
    "Steel Windows": "windows", "Wood Windows": "windows",
    "Vinyl Windows": "windows", "Composite Windows": "windows",
    "Fiberglass Windows": "windows",
    # Skylights
    "Skylights": "skylights", "Roof Windows": "skylights",
    "Unit Skylights": "skylights", "Metal-Framed Skylights": "skylights",
    # Hardware
    "Door Hardware": "hardware", "Access Control": "hardware",
    "Window Hardware": "hardware", "Special Function Hardware": "hardware",
    "Hardware Accessories": "hardware",
    # Glazing
    "Glazing": "glazing", "Glass Glazing": "glazing",
    "Float Glass": "glazing", "Decorative Glass": "glazing",
    "Insulating Glass": "glazing", "Laminated Glass": "glazing",
    "Tempered Glass": "glazing", "Fire-Rated Glass": "glazing",
    "Spandrel Glass": "glazing", "Mirrors": "glazing",
    "Plastic Glazing": "glazing", "Window Film": "glazing",
    # Specialty
    "Detention Windows": "specialty", "Security Windows": "specialty",
    "Blast-Resistant Windows": "specialty", "Bullet-Resistant Windows": "specialty",
    "Sound Control Windows": "specialty", "Pass Windows": "specialty",
    "Blast-Resistant Doors": "specialty", "Bullet-Resistant Doors": "specialty",
    "Vault Doors": "specialty", "Security Doors": "specialty",
    "Bullet-Resistant Glazing": "specialty", "Ballistic Glazing": "specialty",
    "Security Glazing": "specialty", "Electrochromic Glazing": "specialty",
    # Louvers
    "Louvers": "louvers", "Fixed Louvers": "louvers",
    "Operable Louvers": "louvers", "Equipment Screens": "louvers",
    "Vents": "louvers",
}

# Ultra-short names for compact card display
SHORT_NAMES = {
    # Doors
    "Hollow Metal Doors": "HM", "Hollow Metal Frames": "HMF",
    "Blast-Resistant Doors": "Blast", "Bullet-Resistant Doors": "Ballistic",
    "Coiling Doors": "Coil", "Overhead Coiling Doors": "Coil",
    "Sliding Glass Doors": "Slide",
    # Windows
    "Aluminum Windows": "AL Win", "Vinyl Windows": "VIN Win",
    "Wood Windows": "Wood", "Composite Windows": "Comp Win",
    "Fiberglass Windows": "FG Win", "Blast-Resistant Windows": "Blast Win",
    "Bullet-Resistant Windows": "Ballistic Win", "Sound Control Windows": "Sound Win",
    # Storefront & Entrances
    "Storefront": "SF", "Entrances": "ENT",
    "Automatic Entrances": "Auto ENT", "Revolving Entrances": "REV",
    "All-Glass Entrances": "AG ENT",
    # Curtain Wall
    "Curtain Wall": "CW", "Unitized Curtain Wall": "UCW",
    "Structural Glass Curtain Wall": "SG CW", "Point-Supported Curtain Wall": "PS CW",
    # Glazing
    "Glazing": "GLZ", "Insulating Glass": "IG", "Laminated Glass": "LAM",
    "Tempered Glass": "TEMP", "Fire-Rated Glass": "FR GLZ",
    "Bullet-Resistant Glazing": "Ballistic", "Electrochromic Glazing": "Smart",
    # Other
    "Metal-Framed Skylights": "SKY", "Skylights": "SKY",
    "Translucent Assemblies": "Trans", "Door Hardware": "HW", "Access Control": "Access",
}


@app.template_filter('tag_category')
def tag_category_filter(tag_name):
    """Get CSS category class for a scope tag."""
    return TAG_CATEGORIES.get(tag_name, 'other')


@app.template_filter('tag_short')
def tag_short_filter(tag_name):
    """Get shortened display name for a scope tag."""
    return SHORT_NAMES.get(tag_name, tag_name)


@app.template_filter('safe_join')
def safe_join_filter(value, separator=', '):
    """
    Safely join a value with separator.
    - If value is a list/tuple, joins the items
    - If value is a string, returns it as-is (prevents character-by-character iteration)
    - If value is None/empty, returns empty string
    """
    if not value:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        # Filter out None/empty values and convert to strings
        items = [str(item) for item in value if item]
        return separator.join(items)
    return str(value)


@app.template_filter('ensure_list')
def ensure_list_filter(value):
    """
    Ensure value is a list for iteration.
    - If already a list, returns it
    - If a string, wraps it in a list
    - If None/empty, returns empty list
    """
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return [value]


# =============================================================================
# BLUEPRINT REGISTRATION (Modular Routes)
# =============================================================================
# Note: These blueprints handle a subset of routes. Over time, more routes
# will be migrated from this file to the routes/ directory.

try:
    from routes import register_blueprints
    register_blueprints(app)
    print("Registered route blueprints from routes/")
except ImportError as e:
    print(f"Warning: Could not load route blueprints: {e}")
    print("Falling back to routes defined in app.py")

# Register API v2 blueprints (database-centric)
try:
    from routes.api_v2 import api_v2_bp
    app.register_blueprint(api_v2_bp)
    print("Registered API v2 blueprints (database-centric)")
except ImportError as e:
    print(f"Warning: Could not load API v2 blueprints: {e}")


# Configuration
BIDDING_FOLDER = os.getenv("BIDDING_FOLDER", "")
if not BIDDING_FOLDER:
    raise RuntimeError("BIDDING_FOLDER environment variable not set. Copy .env.example to .env and configure.")
PROJECTDOG_EMAIL = os.getenv("PROJECTDOG_EMAIL", "")
PROJECTDOG_PASSWORD = os.getenv("PROJECTDOG_PASSWORD", "")
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))
PLANHUB_SYNC_INTERVAL = int(os.getenv("PLANHUB_SYNC_INTERVAL_HOURS", "24"))
DATA_DIR = Path(__file__).parent / "static" / "data"

# Initialize modules
bidding_reader = BiddingFolderReader(BIDDING_FOLDER)
background_sync = BackgroundSync(sync_interval_hours=SYNC_INTERVAL, planhub_sync_interval_hours=PLANHUB_SYNC_INTERVAL)
status_tracker = ProjectStatusTracker(str(DATA_DIR))
planhub_matcher = PlanHubLocalMatcher(str(DATA_DIR))
thumbnail_gen = ThumbnailGenerator(str(DATA_DIR / "thumbnails"))
smart_notes = SmartNotesProcessor()
vendor_manager = VendorManager(str(DATA_DIR))

# Project cache with thread safety
_all_projects = []
_last_refresh = None
_projects_lock = threading.Lock()


class DebouncedRefresh:
    """
    Debounced refresh mechanism to coalesce multiple rapid refresh calls.
    Delays refresh execution by a configurable delay after the last call.
    Thread-safe for use with background sync.
    """
    def __init__(self, refresh_func, delay=0.5):
        """
        Args:
            refresh_func: The function to call for refresh
            delay: Delay in seconds before executing refresh (default: 0.5)
        """
        self.refresh_func = refresh_func
        self.delay = delay
        self.timer = None
        self.lock = threading.Lock()

    def trigger(self, immediate=False):
        """
        Trigger a refresh, debounced by default.

        Args:
            immediate: If True, execute refresh immediately without debouncing
        """
        with self.lock:
            # Cancel any pending timer
            if self.timer:
                self.timer.cancel()

            if immediate:
                # Execute immediately
                self.refresh_func()
            else:
                # Schedule delayed execution
                self.timer = threading.Timer(self.delay, self.refresh_func)
                self.timer.start()


def load_projectdog_cache() -> list:
    """Load cached ProjectDog projects from file"""
    cache_file = DATA_DIR / "projectdog_projects.json"
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                return data.get('projects', [])
        except Exception as e:
            print(f"Error loading ProjectDog cache: {e}")
    return []


# Global sync progress tracking
_sync_progress = {
    "stage": "idle",
    "message": "",
    "projects_found": 0,
    "projects_with_docs": 0,
    "current_project": 0,
    "total_projects": 0,
    "current_project_name": "",
    "error": None
}

def get_sync_progress():
    """Get current sync progress"""
    return _sync_progress.copy()

def sync_projectdog():
    """Sync function for background scheduler with progress tracking"""
    global _sync_progress

    if not PROJECTDOG_EMAIL or not PROJECTDOG_PASSWORD:
        print("ProjectDog credentials not configured, skipping sync")
        _sync_progress = {"stage": "error", "message": "Credentials not configured", "error": "Missing PROJECTDOG_EMAIL or PROJECTDOG_PASSWORD"}
        return

    try:
        from modules.scraper.projectdog_scraper import ProjectDogScraper

        _sync_progress = {"stage": "initializing", "message": "Starting browser...", "projects_found": 0, "projects_with_docs": 0, "current_project": 0, "total_projects": 0, "current_project_name": "", "error": None}
        print("="*60)
        print("PROJECTDOG SYNC STARTED")
        print("="*60)

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Note: headless=False required because ProjectDog detects headless Chrome
        scraper = ProjectDogScraper(PROJECTDOG_EMAIL, PROJECTDOG_PASSWORD, headless=False)
        scraper._init_driver()

        # Login
        _sync_progress["stage"] = "login"
        _sync_progress["message"] = "Logging in to ProjectDog..."
        print("[1/5] Logging in to ProjectDog...")

        if not scraper.login():
            _sync_progress = {"stage": "error", "message": "Login failed", "error": "Could not log in to ProjectDog"}
            print("ERROR: Login failed!")
            scraper._close_driver()
            return

        print("      Login successful!")

        # Search
        _sync_progress["stage"] = "searching"
        _sync_progress["message"] = "Searching Division 8 projects..."
        print("[2/5] Searching Division 8 projects...")

        projects = scraper.search_division8()

        projects_with_docs = [p for p in projects if p.get('has_documents') and p.get('project_code')]
        go_projects = [p for p in projects if not p.get('has_documents')]

        _sync_progress["projects_found"] = len(projects)
        _sync_progress["projects_with_docs"] = len(projects_with_docs)
        _sync_progress["message"] = f"Found {len(projects)} projects ({len(projects_with_docs)} with docs, {len(go_projects)} GO)"

        print(f"      Found {len(projects)} total projects")
        print(f"      - {len(projects_with_docs)} with documents (code)")
        print(f"      - {len(go_projects)} without documents (GO)")

        # Fetch details for projects with documents
        _sync_progress["stage"] = "fetching_details"
        _sync_progress["total_projects"] = len(projects_with_docs)
        print(f"[3/5] Fetching details for {len(projects_with_docs)} projects with documents...")

        for i, project in enumerate(projects_with_docs):
            project_code = project.get('project_code')
            title = project.get('title', '')[:40]

            _sync_progress["current_project"] = i + 1
            _sync_progress["current_project_name"] = title
            _sync_progress["message"] = f"({i+1}/{len(projects_with_docs)}) {title}"

            print(f"      [{i+1}/{len(projects_with_docs)}] {project_code}: {title}")

            # Get detail page info
            details = scraper.get_project_details(project_code)
            project.update(details)

            # Get document recipients
            recipients = scraper.get_document_recipients(project_code)
            project['document_recipients'] = recipients
            print(f"               Found {len(recipients)} document recipients")

            # Get document links
            documents = scraper.get_document_links(project_code)
            project['documents'] = documents
            print(f"               Found {len(documents)} downloadable documents")

            time.sleep(1)  # Rate limiting

        # Save results
        _sync_progress["stage"] = "saving"
        _sync_progress["message"] = "Saving results..."
        print("[4/5] Saving results...")

        scraper.projects = projects
        scraper.save_results(str(DATA_DIR / "projectdog_projects.json"))

        # Cleanup
        scraper._close_driver()

        # Refresh project list
        _sync_progress["stage"] = "refreshing"
        _sync_progress["message"] = "Refreshing dashboard..."
        print("[5/5] Refreshing project list...")

        debounced_refresh.trigger(immediate=True)

        _sync_progress["stage"] = "complete"
        _sync_progress["message"] = f"Sync complete! {len(projects)} projects"

        print("="*60)
        print(f"SYNC COMPLETE: {len(projects)} projects")
        print(f"  - {len(projects_with_docs)} with documents")
        print(f"  - {len(go_projects)} GO projects")
        print(f"  - {sum(1 for p in projects if p.get('is_rfq'))} RFQ projects")
        print("="*60)

    except Exception as e:
        import traceback
        _sync_progress = {"stage": "error", "message": str(e), "error": str(e)}
        print(f"SYNC ERROR: {e}")
        traceback.print_exc()


def sync_email_monitor():
    """Sync function for Email Monitor background refresh"""
    try:
        from modules.email_monitor import (
            EmailMonitorReader,
            EmailProjectMatcher,
            EmailStatusUpdater
        )

        print("=" * 60)
        print("EMAIL MONITOR SYNC STARTED")
        print("=" * 60)

        reader = EmailMonitorReader()
        matcher = EmailProjectMatcher()
        status_updater = EmailStatusUpdater(status_tracker)

        # Get all emails
        emails = reader.read_all_emails()
        print(f"Read {len(emails)} emails from Email Monitor")

        # Get local projects for matching
        local_projects = bidding_reader.read_all_projects()
        print(f"Matching against {len(local_projects)} local projects")

        # Find matches
        matches = matcher.find_matches(emails, local_projects)
        print(f"Found {len(matches)} email-project matches")

        # Group emails by matched project for status updates
        projects_emails = {}
        for match in matches:
            project_id = match['project_id']
            email_id = match['email_id']

            # Find the email
            email = next((e for e in emails if e.id == email_id), None)
            if email:
                if project_id not in projects_emails:
                    projects_emails[project_id] = []
                projects_emails[project_id].append(email.email_type)

        # Process status updates
        if projects_emails:
            batch_result = status_updater.batch_process(projects_emails)
            print(f"Status updates: {batch_result['updated_count']} projects updated")

        # Trigger project refresh
        debounced_refresh.trigger(immediate=True)

        print("=" * 60)
        print(f"EMAIL SYNC COMPLETE: {len(matches)} matches")
        print("=" * 60)

    except Exception as e:
        import traceback
        print(f"EMAIL SYNC ERROR: {e}")
        traceback.print_exc()


def merge_project_with_status(project: dict) -> dict:
    """Merge project data with internal status tracking"""
    project_id = project.get('project_code') or project.get('id') or project.get('folder', '').lower().replace(' ', '-')
    status = status_tracker.get_status(project_id)

    if status:
        project['internal_status'] = status
        project['bid_decision'] = status.get('bid_decision')
        project['has_proposal'] = status.get('proposal', {}).get('generated', False)
        project['has_internal_estimate'] = status.get('estimate', {}).get('created', False)
        project['internal_estimate_total'] = status.get('estimate', {}).get('total')
        project['tags'] = status.get('tags', [])
        project['archived'] = status.get('archived', False)
        project['archived_reason'] = status.get('archived_reason')
    else:
        project['internal_status'] = None
        project['bid_decision'] = None
        project['has_proposal'] = False
        project['has_internal_estimate'] = False
        project['internal_estimate_total'] = None
        project['tags'] = []
        project['archived'] = False
        project['archived_reason'] = None

    return project


def refresh_all_projects():
    """Refresh the combined project list (thread-safe) with deduplication - delegates to utils version with GovWin integration"""
    global _all_projects, _last_refresh
    projects = utils_refresh_all_projects()

    # Update app.py's global cache as well
    with _projects_lock:
        _all_projects = projects
        _last_refresh = datetime.now()

    return projects


# Initialize debounced refresh with 500ms delay
debounced_refresh = DebouncedRefresh(refresh_all_projects, delay=0.5)


_loading_in_progress = False
_initial_load_done = False

def get_all_projects(force_refresh: bool = False) -> list:
    """Get all projects from all sources (thread-safe)"""
    global _all_projects, _last_refresh, _loading_in_progress, _initial_load_done

    with _projects_lock:
        needs_refresh = force_refresh or not _all_projects

    # For initial load, return empty immediately and load in background
    if needs_refresh and not _initial_load_done and not _loading_in_progress:
        _loading_in_progress = True
        import threading
        def bg_load():
            global _loading_in_progress, _initial_load_done
            try:
                refresh_all_projects()
                _initial_load_done = True
            finally:
                _loading_in_progress = False
        threading.Thread(target=bg_load, daemon=True).start()
        return []  # Return empty list immediately

    # For force refresh, do it synchronously
    if force_refresh:
        refresh_all_projects()

    with _projects_lock:
        return list(_all_projects)  # Return a copy for thread safety


def is_loading() -> bool:
    """Check if initial data load is in progress"""
    return _loading_in_progress


def find_project_by_id(project_id: str, projects: list = None) -> dict:
    """
    Find a project by ID using consistent matching logic.
    Matches against: project_code, id, or normalized folder name.

    Args:
        project_id: The identifier to search for
        projects: Optional list of projects (uses get_all_projects() if None)

    Returns:
        The matching project dict, or None if not found
    """
    if projects is None:
        projects = get_all_projects()

    # Normalize the search ID for folder matching
    search_id_normalized = project_id.lower().replace(' ', '-').replace(',', '')

    for p in projects:
        # Match by project_code (ProjectDog projects)
        if p.get('project_code') == project_id:
            return p
        # Match by id (local projects)
        if p.get('id') == project_id:
            return p
        # Match by normalized folder name
        folder = p.get('folder', '')
        if folder.lower().replace(' ', '-').replace(',', '') == search_id_normalized:
            return p

    return None


def _get_project_folder_path(project_id: str):
    """Helper to get the full folder path for a project"""
    project = find_project_by_id(project_id)

    if not project:
        # Try matching by folder name directly on filesystem
        try:
            for folder in os.listdir(BIDDING_FOLDER):
                if folder.lower().replace(' ', '-').replace(',', '') == project_id.lower():
                    return Path(BIDDING_FOLDER) / folder, {"name": folder, "folder": folder}
        except OSError:
            pass
        return None, None

    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return None, project

    # Build full path
    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)
    return project_path, project


# ==================== PROJECT APIs ====================




def gather_project_context(project_path: Path, project: dict) -> dict:
    """
    Gather comprehensive project context for AI brief generation.

    Args:
        project_path: Path to the project folder
        project: Project dict with metadata

    Returns:
        Dict with all available project context
    """
    context = {
        'project_metadata': {},
        'division_8_scope': {},
        'drawings_summary': {},
        'openings_data': {},
        'estimate_status': {},
        'quotes_data': {},
        'available_documents': {},
        'errors': []
    }

    # 1. Basic project metadata
    context['project_metadata'] = {
        'name': project.get('name') or project.get('folder'),
        'address': project.get('address'),
        'owner': project.get('owner'),
        'architect': project.get('architect'),
        'bid_date': project.get('bid_date'),
        'source': project.get('source'),
        'project_code': project.get('project_code')
    }

    # 2. Load extracted project data if available
    extracted_data_path = project_path / 'extracted_project_data.json'
    if extracted_data_path.exists():
        try:
            with open(extracted_data_path, 'r') as f:
                extracted = json.load(f)

                # Get openings schedule
                openings = extracted.get('openings_schedule', {})
                context['openings_data'] = {
                    'windows': openings.get('windows', []),
                    'doors': openings.get('doors', []),
                    'storefronts': openings.get('storefronts', []),
                    'total_windows': len(openings.get('windows', [])),
                    'total_doors': len(openings.get('doors', [])),
                    'total_storefronts': len(openings.get('storefronts', []))
                }

                # Get Division 8 scope
                context['division_8_scope'] = extracted.get('division_8', {})

                # Get schedule
                schedule = extracted.get('schedule', {})
                if schedule:
                    context['project_metadata'].update({
                        'construction_start': schedule.get('construction_start'),
                        'construction_duration': schedule.get('duration'),
                        'substantial_completion': schedule.get('substantial_completion')
                    })

        except Exception as e:
            context['errors'].append(f"Error reading extracted_project_data.json: {str(e)}")

    # 3. Check for estimate spreadsheets
    try:
        estimate_reader = EstimateReader(str(project_path))
        estimate_result = estimate_reader.read_all()

        if estimate_result.get('openings'):
            context['estimate_status'] = {
                'has_estimate': True,
                'total_openings': estimate_result.get('total_count', 0),
                'unique_marks': estimate_result.get('unique_marks', 0),
                'by_type': estimate_result.get('by_type', {}),
                'files': estimate_result.get('files_read', [])
            }
        else:
            context['estimate_status'] = {'has_estimate': False}
    except Exception as e:
        context['estimate_status'] = {'has_estimate': False, 'error': str(e)}

    # 4. Check for quotes
    try:
        quote_reader = QuoteReader(str(project_path))
        quote_result = quote_reader.read_all_quotes()

        if quote_result.get('quotes'):
            context['quotes_data'] = {
                'has_quotes': True,
                'total_quotes': quote_result.get('total_quotes', 0),
                'quotes_with_pricing': quote_result.get('quotes_with_pricing', 0),
                'total_value': quote_result.get('total_value', 0),
                'vendors': quote_result.get('vendors', []),
                'quotes': quote_result.get('quotes', [])
            }
        else:
            context['quotes_data'] = {'has_quotes': False}
    except Exception as e:
        context['quotes_data'] = {'has_quotes': False, 'error': str(e)}

    # 5. Scan for available documents
    docs = {
        'specs': [],
        'drawings': [],
        'schedules': [],
        'addendums': [],
        'quotes': [],
        'other': []
    }

    try:
        for file_path in project_path.rglob('*.pdf'):
            name_lower = file_path.name.lower()
            relative_path = str(file_path.relative_to(project_path))

            if any(p in name_lower for p in ['spec', 'division', 'section', 'manual']):
                docs['specs'].append(relative_path)
            elif any(p in name_lower for p in ['drawing', 'sheet', 'plan', 'elevation', 'arch', 'dwg']):
                docs['drawings'].append(relative_path)
            elif any(p in name_lower for p in ['schedule', 'door schedule', 'window schedule', 'hardware']):
                docs['schedules'].append(relative_path)
            elif any(p in name_lower for p in ['addend', 'revision']):
                docs['addendums'].append(relative_path)
            elif any(p in name_lower for p in ['quote', 'proposal', 'bid', 'pricing']):
                docs['quotes'].append(relative_path)
            else:
                docs['other'].append(relative_path)

        # Also check for Excel files
        for file_path in project_path.rglob('*.xlsx'):
            name_lower = file_path.name.lower()
            if not name_lower.startswith('~$'):  # Skip temp files
                docs['schedules'].append(str(file_path.relative_to(project_path)))

    except Exception as e:
        context['errors'].append(f"Error scanning documents: {str(e)}")

    context['available_documents'] = docs

    # 6. Check for Division 8 spec sections
    if DOC_CLASSIFICATION_AVAILABLE:
        try:
            spec_pdfs = [f for f in docs['specs'] if f][:3]  # Limit to 3 specs
            division8_sections = []

            for spec_file in spec_pdfs:
                try:
                    divisions = extract_divisions_from_pdf(
                        project_path / spec_file,
                        target_divisions=["08"],
                        max_pages=100
                    )

                    if "08" in divisions:
                        div8 = divisions["08"]
                        for section in div8.sections:
                            division8_sections.append({
                                'section_id': section.section_id,
                                'title': section.title,
                                'source_file': spec_file
                            })
                except:
                    pass

            if division8_sections:
                context['division_8_scope']['sections'] = division8_sections

        except Exception as e:
            context['errors'].append(f"Error extracting Division 8 specs: {str(e)}")

    return context


def generate_project_brief(context: dict, use_lm_studio: bool = True) -> str:
    """
    Generate an AI project brief using LLM with CSI Masterformat enrichment.

    Args:
        context: Project context dict from gather_project_context()
        use_lm_studio: If True, try LM Studio first, fallback to OpenRouter

    Returns:
        Generated brief text
    """
    # Build CSI-enriched prompt if prompt_builder is available
    if PROMPT_BUILDER_AVAILABLE:
        # Create context dict for prompt_builder (maps our context to expected format)
        meta = context.get('project_metadata', {})
        div8 = context.get('division_8_scope', {})

        pb_context = {
            'title': meta.get('name', 'Unknown Project'),
            'location': meta.get('address', ''),
            'value': meta.get('value', ''),
            'bid_date': meta.get('bid_date', ''),
            'description': div8.get('scope_summary', ''),
            'scope': json.dumps(div8, indent=2),
            'specifications': ', '.join([
                s.get('section_id', '')
                for s in div8.get('sections', [])
            ])
        }

        # Build CSI-enriched base prompt with section descriptions and manufacturer data
        csi_prompt = build_division8_brief(pb_context)

        # Append additional project-specific data that prompt_builder doesn't cover
        prompt = f"""{csi_prompt}

ADDITIONAL PROJECT DATA:

OPENINGS DATA:
{json.dumps(context.get('openings_data', {}), indent=2)}

ESTIMATE STATUS:
{json.dumps(context.get('estimate_status', {}), indent=2)}

VENDOR QUOTES:
{json.dumps(context.get('quotes_data', {}), indent=2)}

AVAILABLE DOCUMENTS:
{json.dumps(context.get('available_documents', {}), indent=2)}

Based on all the above context (CSI section references, manufacturer products, and project data),
generate a comprehensive project brief that includes:
1. Project summary with Division 8 scope highlights
2. CSI specification sections identified (with descriptions)
3. Specified manufacturers and their products
4. Openings breakdown (windows, doors, storefronts)
5. Estimate and quote status
6. Key clarifications needed
7. Next steps for bid preparation"""
    else:
        # Fallback to original prompt if prompt_builder not available
        prompt = f"""You are a construction project analyst for a Division 8 (Openings) contractor specializing in doors, windows, storefronts, and glazing.

Generate a concise project brief based on the following information:

PROJECT METADATA:
{json.dumps(context['project_metadata'], indent=2)}

DIVISION 8 SCOPE:
{json.dumps(context['division_8_scope'], indent=2)}

OPENINGS DATA:
{json.dumps(context['openings_data'], indent=2)}

ESTIMATE STATUS:
{json.dumps(context['estimate_status'], indent=2)}

QUOTES:
{json.dumps(context['quotes_data'], indent=2)}

AVAILABLE DOCUMENTS:
{json.dumps(context['available_documents'], indent=2)}

Generate a brief following this structure:

PROJECT SUMMARY
[2-3 sentences summarizing the project scope, focusing on Division 8 work. Include key details about windows, doors, storefronts.]

SCHEDULE
Start: [date or TBD] | Duration: [days or TBD] | Bid Date: [date or TBD]

DIVISION 8 SCOPE
[List of spec sections if known, with brief descriptions]
[Window/door quantities and types]
[Key manufacturers or systems specified]

OPENINGS BREAKDOWN
Windows: [count and key types]
Doors: [count and key types]
Storefronts: [count if applicable]

DOCUMENTS AVAILABLE
✓ [List available document types]
✗ [List missing critical documents]

ESTIMATE STATUS
[Current status: Has takeoff? Has quotes? Quote value range?]

NEXT STEPS
[2-3 bullet points on what needs to be done]

Keep it concise, professional, and actionable. If information is missing, say "TBD" or "Not available"."""

    # Try LM Studio first
    if use_lm_studio:
        try:
            response = requests.post(
                "http://localhost:1234/v1/chat/completions",
                json={
                    "model": "local-model",
                    "messages": [
                        {"role": "system", "content": "You are a construction project analyst specializing in Division 8 (Openings) work."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
        except Exception as e:
            print(f"LM Studio call failed: {e}, falling back to OpenRouter")

    # Fallback to OpenRouter
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        # Return a simple text-based brief if no API available
        return generate_simple_brief(context)

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://project-tracker.local",
            },
            json={
                "model": "amazon/nova-lite-v1",
                "messages": [
                    {"role": "system", "content": "You are a construction project analyst specializing in Division 8 (Openings) work."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 2000
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            print(f"OpenRouter API error: {response.status_code} - {response.text}")
            return generate_simple_brief(context)

    except Exception as e:
        print(f"OpenRouter call failed: {e}")
        return generate_simple_brief(context)


def generate_simple_brief(context: dict) -> str:
    """Generate a simple text-based brief without AI when APIs are unavailable."""
    meta = context['project_metadata']
    openings = context['openings_data']
    estimate = context['estimate_status']
    quotes = context['quotes_data']
    docs = context['available_documents']
    div8 = context['division_8_scope']

    brief = f"""PROJECT SUMMARY
{meta.get('name', 'Unknown Project')}
{meta.get('address', 'Address not available')}

Owner: {meta.get('owner') or 'TBD'}
Architect: {meta.get('architect') or 'TBD'}

This project includes Division 8 work with {openings.get('total_windows', 0)} windows, {openings.get('total_doors', 0)} doors, and {openings.get('total_storefronts', 0)} storefronts.

SCHEDULE
Start: {meta.get('construction_start') or 'TBD'} | Duration: {meta.get('construction_duration') or 'TBD'} | Bid Date: {meta.get('bid_date') or 'TBD'}

DIVISION 8 SCOPE
"""

    # Add spec sections if available
    if div8.get('sections'):
        brief += "Specification Sections:\n"
        for section in div8['sections'][:10]:  # Limit to 10
            brief += f"  • {section.get('section_id')}: {section.get('title')}\n"

    # Add openings breakdown
    if openings.get('windows'):
        brief += f"\nWindows:\n"
        window_types = {}
        for w in openings['windows'][:10]:  # Limit display
            wtype = w.get('type', 'Unknown')
            qty = w.get('qty', 1)
            if wtype in window_types:
                window_types[wtype] += qty if qty else 0
            else:
                window_types[wtype] = qty if qty else 0
        for wtype, qty in list(window_types.items())[:5]:
            brief += f"  • {wtype}: {qty} units\n"

    if openings.get('doors'):
        brief += f"\nDoors:\n"
        door_types = {}
        for d in openings['doors'][:10]:
            dtype = d.get('material', 'Unknown')
            qty = d.get('qty', 1)
            if dtype in door_types:
                door_types[dtype] += qty if qty else 0
            else:
                door_types[dtype] = qty if qty else 0
        for dtype, qty in list(door_types.items())[:5]:
            brief += f"  • {dtype}: {qty} units\n"

    brief += f"""
DOCUMENTS AVAILABLE
✓ Specs: {len(docs.get('specs', []))} files
✓ Drawings: {len(docs.get('drawings', []))} files
✓ Schedules: {len(docs.get('schedules', []))} files
✓ Quotes: {len(docs.get('quotes', []))} files
"""

    # Check for missing documents
    missing = []
    if not docs.get('specs'):
        missing.append("Specifications")
    if not docs.get('drawings'):
        missing.append("Drawings")
    if not docs.get('schedules'):
        missing.append("Door/Window Schedules")

    if missing:
        brief += "✗ Missing: " + ", ".join(missing) + "\n"

    brief += f"""
ESTIMATE STATUS
"""

    if estimate.get('has_estimate'):
        brief += f"Takeoff Complete: {estimate.get('total_openings', 0)} openings in {len(estimate.get('files', []))} files\n"
    else:
        brief += "No takeoff spreadsheets found\n"

    if quotes.get('has_quotes'):
        brief += f"Quotes Received: {quotes.get('total_quotes', 0)} quotes from {len(quotes.get('vendors', []))} vendors\n"
        if quotes.get('total_value'):
            brief += f"Total Quote Value: ${quotes['total_value']:,.2f}\n"
    else:
        brief += "No vendor quotes found\n"

    brief += """
NEXT STEPS
• Review specifications and drawings
• Complete takeoff if not done
• Request quotes from qualified vendors
• Prepare bid package
"""

    return brief


# ==================== FULL PROJECT PIPELINE ====================

@app.route('/api/project/<project_id>/full-parse', methods=['POST'])
def api_project_full_parse(project_id):
    """
    Run the full project pipeline: Organize + Analyze.

    This is a two-phase process:
    1. ORGANIZE: Create standardized folder structure and categorize documents
       - Specs → Specs/Division-08-Openings, Specs/Other-Divisions, etc.
       - Drawings → Drawings/A-Architectural, Drawings/S-Structural, etc.
       - Schedules, Quotes, RFIs, etc.

    2. ANALYZE: Extract data from organized structure
       - Parse Division 8 specs for CSI sections
       - Detect manufacturers
       - Extract schedule data

    Query parameters:
    - use_ai: true/false (default: true) - Use AI for uncertain categorization
    - dry_run: true/false (default: false) - Don't move files, just report

    Returns organization stats and analysis results.
    """
    # Find project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Get project folder
    project_path, _ = _get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        from modules.project_pipeline import run_project_pipeline

        # Get parameters
        use_ai = request.args.get('use_ai', 'true').lower() == 'true'
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'

        # Run the pipeline
        result = run_project_pipeline(
            str(project_path),
            stream_callback=None,  # TODO: Add SSE streaming support
            use_ai=use_ai
        )

        return jsonify({
            "status": "ok",
            "project_id": project_id,
            "project_name": project.get('title') or project.get('folder'),
            "result": result
        })

    except ImportError as e:
        return jsonify({"error": f"Pipeline module not available: {e}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/project/<project_id>/organize', methods=['POST'])
def api_project_organize(project_id):
    """
    Run only the organization phase of the pipeline.

    This creates the standardized folder structure and moves files
    into appropriate directories based on content detection.

    Query parameters:
    - use_ai: true/false (default: false) - Use AI for uncertain files
    - dry_run: true/false (default: false) - Don't move files, just report
    """
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path, _ = _get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        from modules.project_pipeline import ProjectPipeline
        from dataclasses import asdict

        use_ai = request.args.get('use_ai', 'false').lower() == 'true'
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'

        pipeline = ProjectPipeline(str(project_path))
        result = pipeline.organize(use_ai=use_ai, dry_run=dry_run)

        return jsonify({
            "status": "ok",
            "project_id": project_id,
            "dry_run": dry_run,
            "result": asdict(result)
        })

    except ImportError as e:
        return jsonify({"error": f"Pipeline module not available: {e}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors"""
    if request.path.startswith('/api/'):
        return jsonify({"error": "Not found", "path": request.path}), 404
    return render_template('error.html', message='Page not found'), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    if request.path.startswith('/api/'):
        return jsonify({"error": "Internal server error"}), 500
    return render_template('error.html', message='An unexpected error occurred'), 500


# ==================== STARTUP ====================

def init_app():
    """Initialize the application"""
    global _loading_in_progress, _initial_load_done
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize database (instant - SQLite is fast)
    if DATABASE_AVAILABLE:
        try:
            print("Initializing database...")
            init_db()
            run_migrations()
            print("Database ready")

            # Start database-centric background sync scheduler
            # This replaces slow folder scanning with periodic incremental updates
            init_scheduler(app)
            print("Background sync scheduler started")
        except Exception as e:
            print(f"Database initialization warning: {e}")
            print("Falling back to file-based loading")

    # Load projects in background thread for fast startup
    # This loads from DB if available, otherwise falls back to folder scanning
    _loading_in_progress = True
    import threading
    def bg_load():
        global _loading_in_progress, _initial_load_done
        try:
            print("Background loading projects...")
            refresh_all_projects()
            _initial_load_done = True
            print(f"Background load complete: {len(_all_projects)} projects")
        except Exception as e:
            print(f"Background load error: {e}")
        finally:
            _loading_in_progress = False
    threading.Thread(target=bg_load, daemon=True).start()

    background_sync.set_sync_callback(sync_projectdog)
    background_sync.set_email_sync_callback(sync_email_monitor)
    background_sync.set_planhub_sync_callback(sync_planhub)
    background_sync.start()

    # Start job queue worker
    try:
        from modules.job_queue.worker import start_worker
        start_worker()
        print("Job queue worker started")
    except Exception as e:
        print(f"Warning: Could not start job worker: {e}")


init_app()


if __name__ == '__main__':
    print(f"\nProject Tracker Starting...")
    print(f"Bidding folder: {BIDDING_FOLDER}")
    print(f"ProjectDog credentials: {'configured' if PROJECTDOG_EMAIL else 'not configured'}")
    print(f"Projects loading in background...")
    print(f"\nDashboard: http://localhost:5003\n")

    app.run(host='0.0.0.0', port=5003, debug=True)
