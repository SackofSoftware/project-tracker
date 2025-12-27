"""
Shared utilities for Project Tracker Flask application.

This module provides centralized access to:
- Configuration settings
- Module instances (bidding_reader, status_tracker, etc.)
- Project cache management
- Common helper functions
"""

import os
import json
import threading
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

BIDDING_FOLDER = os.getenv("BIDDING_FOLDER", "")
PROJECTDOG_EMAIL = os.getenv("PROJECTDOG_EMAIL", "")
PROJECTDOG_PASSWORD = os.getenv("PROJECTDOG_PASSWORD", "")
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))
DATA_DIR = Path(__file__).parent.parent / "static" / "data"

# =============================================================================
# MODULE INSTANCES (lazy-loaded)
# =============================================================================

_bidding_reader = None
_background_sync = None
_status_tracker = None
_planhub_matcher = None
_thumbnail_gen = None
_smart_notes = None
_vendor_manager = None


def get_bidding_reader():
    """Get or create BiddingFolderReader instance"""
    global _bidding_reader
    if _bidding_reader is None:
        from modules.bidding import BiddingFolderReader
        _bidding_reader = BiddingFolderReader(BIDDING_FOLDER)
    return _bidding_reader


def get_background_sync():
    """Get or create BackgroundSync instance"""
    global _background_sync
    if _background_sync is None:
        from modules.sync import BackgroundSync
        _background_sync = BackgroundSync(sync_interval_hours=SYNC_INTERVAL)
    return _background_sync


def get_status_tracker():
    """Get or create ProjectStatusTracker instance"""
    global _status_tracker
    if _status_tracker is None:
        from modules.tracking import ProjectStatusTracker
        _status_tracker = ProjectStatusTracker(str(DATA_DIR))
    return _status_tracker


def get_planhub_matcher():
    """Get or create PlanHubLocalMatcher instance"""
    global _planhub_matcher
    if _planhub_matcher is None:
        from modules.planhub.planhub_matcher import PlanHubLocalMatcher
        _planhub_matcher = PlanHubLocalMatcher(str(DATA_DIR))
    return _planhub_matcher


def get_thumbnail_gen():
    """Get or create ThumbnailGenerator instance"""
    global _thumbnail_gen
    if _thumbnail_gen is None:
        from modules.thumbnails import ThumbnailGenerator
        _thumbnail_gen = ThumbnailGenerator(str(DATA_DIR / "thumbnails"))
    return _thumbnail_gen


def get_smart_notes():
    """Get or create SmartNotesProcessor instance"""
    global _smart_notes
    if _smart_notes is None:
        from modules.notes import SmartNotesProcessor
        _smart_notes = SmartNotesProcessor()
    return _smart_notes


def get_vendor_manager():
    """Get or create VendorManager instance"""
    global _vendor_manager
    if _vendor_manager is None:
        from modules.vendors import VendorManager
        _vendor_manager = VendorManager(str(DATA_DIR))
    return _vendor_manager


# =============================================================================
# PROJECT CACHE
# =============================================================================

_all_projects = []
_last_refresh = None
_projects_lock = threading.Lock()


class DebouncedRefresh:
    """
    Debounced refresh mechanism to coalesce multiple rapid refresh calls.
    """
    def __init__(self, refresh_func, delay=0.5):
        self.refresh_func = refresh_func
        self.delay = delay
        self.timer = None
        self.lock = threading.Lock()

    def trigger(self, immediate=False):
        with self.lock:
            if self.timer:
                self.timer.cancel()

            if immediate:
                self.refresh_func()
            else:
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


def merge_project_with_status(project: dict) -> dict:
    """Merge project data with internal status tracking"""
    status_tracker = get_status_tracker()
    project_id = project.get('project_code') or project.get('id') or project.get('folder', '').lower().replace(' ', '-')
    status = status_tracker.get_status(project_id)

    if status:
        project['internal_status'] = status
        project['bid_decision'] = status.get('bid_decision')
        project['has_proposal'] = status.get('proposal', {}).get('generated', False)
        project['has_internal_estimate'] = status.get('estimate', {}).get('created', False)
        project['internal_estimate_total'] = status.get('estimate', {}).get('total')
        project['tags'] = status.get('tags', [])
        project['csi_tags'] = status.get('csi_tags', [])
        project['archived'] = status.get('archived', False)
        project['archived_reason'] = status.get('archived_reason')
        project['status'] = status  # Full status object for templates
    else:
        project['internal_status'] = None
        project['bid_decision'] = None
        project['has_proposal'] = False
        project['has_internal_estimate'] = False
        project['internal_estimate_total'] = None
        project['tags'] = []
        project['csi_tags'] = []
        project['archived'] = False
        project['archived_reason'] = None
        project['status'] = None

    return project


def refresh_all_projects():
    """Refresh the combined project list (thread-safe) with deduplication"""
    global _all_projects, _last_refresh
    from modules.planhub.planhub_reader import load_planhub_projects
    from modules.planhub.planhub_matcher import PlanHubLocalMatcher

    bidding_reader = get_bidding_reader()
    projects = []

    # Load local bidding projects
    local_projects = bidding_reader.read_all_projects()
    local_projects = [merge_project_with_status(p) for p in local_projects]
    projects.extend(local_projects)

    # Load ProjectDog cached projects
    pd_projects = load_projectdog_cache()
    for p in pd_projects:
        p['source'] = 'projectdog'
    pd_projects = [merge_project_with_status(p) for p in pd_projects]
    projects.extend(pd_projects)

    # Load PlanHub projects with deduplication
    try:
        planhub_projects = load_planhub_projects()
        matcher = PlanHubLocalMatcher()
        matches = matcher.find_matches(planhub_projects, local_projects)
        matched_planhub_ids = {m['planhub_id'] for m in matches}

        # Merge matched PlanHub data into local projects
        for match in matches:
            local_id = match['local_id']
            planhub_id = match['planhub_id']

            for p in projects:
                if p.get('id') == local_id:
                    for ph in planhub_projects:
                        ph_id = ph.get('project_id') or ph.get('id', '').replace('planhub-', '')
                        if ph_id == planhub_id:
                            p['planhub_linked'] = True
                            p['planhub_id'] = planhub_id
                            p['planhub_match_confidence'] = match['confidence']
                            p['general_contractors'] = ph.get('general_contractors', [])
                            p['planhub_urls'] = ph.get('planhub_urls', {})
                            p['matching_trades'] = ph.get('matching_trades', [])
                            if not p.get('bid_date') and ph.get('bid_date'):
                                p['bid_date'] = ph.get('bid_date')
                            break
                    break

        # Add unmatched PlanHub projects
        for p in planhub_projects:
            ph_id = p.get('project_id') or p.get('id', '').replace('planhub-', '')
            if ph_id not in matched_planhub_ids:
                p = merge_project_with_status(p)
                projects.append(p)

    except Exception as e:
        print(f"Error loading PlanHub projects: {e}")

    with _projects_lock:
        _all_projects = projects
        _last_refresh = datetime.now()

    return projects


# Initialize debounced refresh
debounced_refresh = DebouncedRefresh(refresh_all_projects, delay=0.5)


def get_all_projects(force_refresh: bool = False) -> list:
    """Get all projects from all sources (thread-safe)"""
    global _all_projects, _last_refresh

    with _projects_lock:
        needs_refresh = force_refresh or not _all_projects

    if needs_refresh:
        refresh_all_projects()

    with _projects_lock:
        return list(_all_projects)


def find_project_by_id(project_id: str, projects: list = None) -> dict:
    """
    Find a project by ID using consistent matching logic.
    """
    if projects is None:
        projects = get_all_projects()

    search_id_normalized = project_id.lower().replace(' ', '-').replace(',', '')

    for p in projects:
        if p.get('project_code') == project_id:
            return p
        if p.get('id') == project_id:
            return p
        folder = p.get('folder', '')
        if folder.lower().replace(' ', '-').replace(',', '') == search_id_normalized:
            return p

    return None


def get_project_folder_path(project_id: str):
    """Get the full folder path for a project"""
    project = find_project_by_id(project_id)

    if not project:
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

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)
    return project_path, project


# =============================================================================
# SYNC PROGRESS TRACKING
# =============================================================================

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


def set_sync_progress(progress: dict):
    """Update sync progress"""
    global _sync_progress
    _sync_progress = progress
