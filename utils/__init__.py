"""
Shared utilities for Project Tracker Flask application.

This module provides centralized access to:
- Configuration settings
- Module instances (bidding_reader, status_tracker, etc.)
- Project cache management
- Common helper functions
"""

import os
import sys
import json
import threading
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# =============================================================================
# OS-AWARE PATH HELPER
# =============================================================================

def get_platform_path(env_var: str, required: bool = False) -> str:
    """
    Get the appropriate path based on the current platform.
    Checks for {env_var}_MAC on macOS, falls back to {env_var}.

    Args:
        env_var: Environment variable name
        required: If True, raise error when not set

    Returns:
        Path string or empty string if not set

    Raises:
        ValueError: If required=True and path not set
    """
    is_mac = sys.platform == "darwin"

    if is_mac:
        # Try Mac-specific env var first, then fall back to base var
        mac_var = f"{env_var}_MAC"
        path = os.getenv(mac_var) or os.getenv(env_var, "")
    else:
        path = os.getenv(env_var, "")

    if required and not path:
        raise ValueError(
            f"Required environment variable {env_var} is not set. "
            f"Please copy .env.example to .env and configure your paths."
        )

    return path

# =============================================================================
# CONFIGURATION
# =============================================================================

BIDDING_FOLDER = get_platform_path("BIDDING_FOLDER", required=True)
BRAD_PROJECTS_FOLDER = get_platform_path("BRAD_PROJECTS_FOLDER")
CURRENT_PROJECTS_FOLDER = get_platform_path("CURRENT_PROJECTS_FOLDER")

# List of all project folders to scan (only include configured paths)
ALL_PROJECT_FOLDERS = [
    (label, path) for label, path in [
        ("bidding", BIDDING_FOLDER),
        ("brad", BRAD_PROJECTS_FOLDER),
        ("current", CURRENT_PROJECTS_FOLDER),
    ] if path
]
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
_email_reader = None
_email_matcher = None


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


def get_email_reader():
    """Get or create EmailMonitorReader instance"""
    global _email_reader
    if _email_reader is None:
        from modules.email_monitor import EmailMonitorReader
        _email_reader = EmailMonitorReader()
    return _email_reader


def get_email_matcher():
    """Get or create EmailProjectMatcher instance"""
    global _email_matcher
    if _email_matcher is None:
        from modules.email_monitor import EmailProjectMatcher
        _email_matcher = EmailProjectMatcher(str(DATA_DIR))
    return _email_matcher


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
        # Preserve source tags, merge with any status tags
        source_tags = project.get('tags', [])
        status_tags = status.get('tags', [])
        project['tags'] = source_tags if source_tags else status_tags
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
        # Don't overwrite source tags if they exist
        if 'tags' not in project:
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
    from modules.govleads import GovLeadsReader
    from modules.bidding import BiddingFolderReader

    projects = []
    local_projects = []

    # Load projects from ALL configured folders (bidding, brad, current)
    for folder_label, folder_path in ALL_PROJECT_FOLDERS:
        if folder_path and Path(folder_path).exists():
            try:
                reader = BiddingFolderReader(folder_path)
                folder_projects = reader.read_all_projects()
                for p in folder_projects:
                    p_dict = p.to_dict() if hasattr(p, 'to_dict') else p
                    # Add source folder label for tracking
                    p_dict['source_folder'] = folder_label
                    p_dict['folder_path'] = folder_path
                    p_dict = merge_project_with_status(p_dict)
                    local_projects.append(p_dict)
                print(f"Loaded {len(folder_projects)} projects from {folder_label} ({folder_path})")
            except Exception as e:
                print(f"Error loading projects from {folder_label}: {e}")
        else:
            print(f"Skipping {folder_label}: folder not found at {folder_path}")

    projects.extend(local_projects)

    # Auto-detect active projects and update status
    try:
        from modules.tracking.activity_detector import ActivityDetector

        status_tracker = get_status_tracker()
        # Cache activity detectors per folder path
        detectors = {}

        for p in local_projects:
            # Get folder name from source_id or folder field
            folder_name = p.get('source_id') or p.get('folder')
            folder_path = p.get('folder_path') or BIDDING_FOLDER
            if not folder_name or not folder_path:
                continue

            # Get or create detector for this folder path
            if folder_path not in detectors:
                detectors[folder_path] = ActivityDetector(folder_path)
            detector = detectors[folder_path]

            # Detect activity indicators
            indicators = detector.detect_activity(folder_name)

            # Add activity indicators to project data
            if indicators.activity_score > 0:
                p['activity_indicators'] = {
                    'has_takeoffs': indicators.has_takeoffs,
                    'takeoff_count': indicators.takeoff_count,
                    'has_quotes': indicators.has_quotes,
                    'quote_count': indicators.quote_count,
                    'has_schedules': indicators.has_schedules,
                    'schedule_count': indicators.schedule_count,
                    'has_recent_activity': indicators.has_recent_activity,
                    'days_since_activity': indicators.days_since_activity,
                    'activity_score': indicators.activity_score,
                    'is_active_bid': detector.is_active_bid(indicators)
                }

                # Auto-create status if active but no status exists
                if detector.is_active_bid(indicators):
                    project_id = p.get('id')
                    status = status_tracker.get_status(project_id)

                    if not status:
                        # Create new status entry
                        status_tracker.create_project_status(project_id, p.get('title'))
                        status_tracker.update_bid_decision(
                            project_id,
                            decision="bid",
                            reason="Auto-detected: Active work found in folder"
                        )
                        status_tracker.add_tag(project_id, "active_bid")

                    elif not status.get('bid_decision'):
                        # Update existing entry without bid_decision
                        status_tracker.update_bid_decision(
                            project_id,
                            decision="bid",
                            reason="Auto-detected: Active work found in folder"
                        )
                        status_tracker.add_tag(project_id, "active_bid")

    except Exception as e:
        print(f"Error in activity detection: {e}")

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
                            # EXISTING: Backward compat flags
                            p['planhub_linked'] = True
                            p['planhub_id'] = planhub_id
                            p['planhub_match_confidence'] = match['confidence']

                            # NEW: Add to linked_sources array
                            if 'linked_sources' not in p:
                                p['linked_sources'] = []
                            p['linked_sources'].append({
                                'source': 'planhub',
                                'id': planhub_id,
                                'confidence': match['confidence'],
                                'match_reason': 'Auto-matched by PlanHub matcher'
                            })

                            # Merge PlanHub data
                            p['general_contractors'] = ph.get('general_contractors', [])
                            p['planhub_urls'] = ph.get('planhub_urls', {})
                            p['matching_trades'] = ph.get('matching_trades', [])
                            if not p.get('bid_date') and ph.get('bid_date'):
                                p['bid_date'] = ph.get('bid_date')
                            break
                    break

        # Add unmatched PlanHub projects
        for p in planhub_projects:
            # Convert UnifiedProject to dict if needed
            p_dict = p.to_dict() if hasattr(p, 'to_dict') else p
            ph_id = p_dict.get('project_id') or p_dict.get('id', '').replace('planhub-', '')
            if ph_id not in matched_planhub_ids:
                p_dict = merge_project_with_status(p_dict)
                projects.append(p_dict)

    except Exception as e:
        print(f"Error loading PlanHub projects: {e}")

    # Load GovWin projects with deduplication
    try:
        import os
        gov_db_path = os.getenv("GOV_DB_PATH")
        if gov_db_path:
            gov_reader = GovLeadsReader(gov_db_path)
            gov_leads = gov_reader.read_all_leads(include_documents=True)

            # Convert to unified format (returns UnifiedProject instances)
            govwin_projects = []
            for lead in gov_leads:
                unified = gov_reader.normalize_to_unified_project(lead)
                # Convert to dict for consistency with other sources
                unified_dict = unified.to_dict()
                unified_dict = merge_project_with_status(unified_dict)
                govwin_projects.append(unified_dict)

            # Find duplicates with existing projects using cross-source deduplication
            all_for_dedup = projects + govwin_projects
            duplicates = find_duplicate_projects(all_for_dedup, threshold=0.65)

            # Track which GovWin projects are matched
            matched_govwin_ids = set()

            # Merge duplicate GovWin data into primary projects
            for dup_group in duplicates:
                primary_source = dup_group['primary_source']
                dup_projects = dup_group['projects']

                # Find the primary project and GovWin projects in the group
                primary_proj = None
                govwin_proj = None

                for proj in dup_projects:
                    if proj.get('source') == primary_source:
                        primary_proj = proj
                    elif proj.get('source') == 'govwin':
                        govwin_proj = proj
                        matched_govwin_ids.add(proj.get('id'))

                # Merge GovWin data into primary project
                if primary_proj and govwin_proj:
                    # Find primary in projects list and enrich
                    for p in projects:
                        if p.get('id') == primary_proj.get('id'):
                            # Add linked source
                            if 'linked_sources' not in p:
                                p['linked_sources'] = []
                            p['linked_sources'].append({
                                'source': 'govwin',
                                'id': govwin_proj.get('source_id'),
                                'confidence': dup_group['match_details'][0]['score'] if dup_group['match_details'] else 0.65,
                                'match_reason': 'Auto-matched by cross-source deduplication'
                            })
                            # Add GovWin-specific data
                            p['govwin_linked'] = True
                            p['govwin_id'] = govwin_proj.get('source_id')
                            p['govwin_url'] = govwin_proj.get('url')
                            if govwin_proj.get('documents'):
                                p['govwin_documents'] = govwin_proj.get('documents', [])
                            # Merge tags
                            if 'tags' not in p:
                                p['tags'] = []
                            for tag in govwin_proj.get('tags', []):
                                if tag not in p['tags']:
                                    p['tags'].append(tag)
                            break

            # Don't add unmatched GovWin projects to main list - they stay in /forecasting leads section
            # Only matched ones get linked to existing projects above

            print(f"Loaded {len(gov_leads)} GovWin leads, {len(matched_govwin_ids)} matched to existing projects (unmatched stay in Leads)")

    except FileNotFoundError:
        print("GovWin database not found, skipping GovWin integration")
    except Exception as e:
        print(f"Error loading GovWin projects: {e}")
        import traceback
        traceback.print_exc()

    # Load Email Monitor projects with deduplication
    try:
        email_reader = get_email_reader()
        email_matcher = get_email_matcher()

        # Get all emails and email projects
        all_emails = email_reader.read_all_emails()
        email_projects = email_reader.get_email_projects()

        # Find matches between emails and local projects
        matches = email_matcher.find_matches(all_emails, local_projects)

        # Build set of matched email folders
        matched_email_folders = set()
        for match in matches:
            # Find which email project folder this match belongs to
            email_id = match['email_id']
            for email in all_emails:
                if email.id == email_id:
                    matched_email_folders.add(email.project_folder)
                    break

        # Enrich matched local projects with email data
        for ep in email_projects:
            email_folder = ep.get('email_folder')
            if email_folder in matched_email_folders:
                # Find the matching local project and enrich it
                folder_emails = [e for e in all_emails if e.project_folder == email_folder]
                folder_matches = [m for m in matches if any(
                    e.id == m['email_id'] for e in folder_emails
                )]

                if folder_matches:
                    # Get the project_id from the best match
                    best_match = max(folder_matches, key=lambda m: m.get('confidence', 0))
                    project_id = best_match['project_id']

                    # Find and enrich the local project
                    for p in projects:
                        if p.get('id') == project_id:
                            # EXISTING: Backward compat flags
                            p['email_linked'] = True
                            p['email_folder'] = email_folder

                            # NEW: Add to linked_sources array
                            if 'linked_sources' not in p:
                                p['linked_sources'] = []
                            p['linked_sources'].append({
                                'source': 'email_monitor',
                                'id': email_folder,
                                'confidence': best_match.get('confidence', 0.5),
                                'match_reason': 'Auto-matched by Email matcher'
                            })

                            # Merge email data
                            p['email_count'] = ep.get('email_count', 0)
                            p['email_types'] = ep.get('email_types', [])
                            p['email_platforms'] = ep.get('platforms', [])
                            p['latest_email'] = ep.get('latest_email')
                            p['email_status'] = ep.get('email_status')
                            # Use email bid date if local doesn't have one
                            if not p.get('bid_date') and ep.get('bid_date'):
                                p['bid_date'] = ep.get('bid_date')
                            break

        # Add unmatched email projects as new source
        for ep in email_projects:
            if ep.get('email_folder') not in matched_email_folders:
                ep = merge_project_with_status(ep)
                projects.append(ep)

    except Exception as e:
        print(f"Error loading Email Monitor projects: {e}")

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

    # Get the project subfolder name (stored in source_id or folder)
    subfolder = project.get('source_id') or project.get('folder')
    base_path = project.get('folder_path') or BIDDING_FOLDER

    if subfolder:
        # Combine base path with project subfolder
        project_path = Path(base_path) / subfolder
        if project_path.exists():
            return project_path, project

    # Fallback: check if folder_path itself is the full path
    if base_path and Path(base_path).is_absolute() and Path(base_path).exists():
        # Check if it's already the project folder (not just base)
        if Path(base_path).name != 'Bidding':
            return Path(base_path), project

    return None, project


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


# =============================================================================
# CROSS-SOURCE DEDUPLICATION
# =============================================================================

def calculate_project_similarity(proj1: dict, proj2: dict) -> tuple[float, dict]:
    """
    Calculate similarity score between two projects from different sources.

    Args:
        proj1: First project dict
        proj2: Second project dict

    Returns:
        Tuple of (score, details_dict)
        Score ranges from 0.0 to 1.0
        Details dict contains breakdown of scoring
    """
    from difflib import SequenceMatcher

    score = 0.0
    details = {}

    # Name similarity (0-0.7 points)
    name1 = (proj1.get('title') or proj1.get('name') or proj1.get('folder') or '').lower()
    name2 = (proj2.get('title') or proj2.get('name') or proj2.get('folder') or '').lower()

    if name1 and name2:
        name_similarity = SequenceMatcher(None, name1, name2).ratio()
        details['name_similarity'] = round(name_similarity, 3)

        # Base score
        name_score = name_similarity * 0.7

        # Bonus for very high matches
        if name_similarity > 0.8:
            name_score += 0.15

        score += name_score
        details['name_score'] = round(name_score, 3)

    # Location match (up to 0.45 points total)
    loc1 = proj1.get('location', {})
    loc2 = proj2.get('location', {})

    if isinstance(loc1, dict) and isinstance(loc2, dict):
        # Normalize city names (handle abbreviations)
        def normalize_city(city_name):
            if not city_name:
                return ''
            city = str(city_name).lower().strip()
            # Common abbreviations
            city = city.replace(' st.', ' street').replace(' st,', ' street,')
            city = city.replace(' ave.', ' avenue').replace(' ave,', ' avenue,')
            city = city.replace(' rd.', ' road').replace(' rd,', ' road,')
            city = city.replace(' blvd.', ' boulevard')
            return city

        city1 = normalize_city(loc1.get('city') or '')
        city2 = normalize_city(loc2.get('city') or '')
        state1 = (loc1.get('state') or '').lower().strip()
        state2 = (loc2.get('state') or '').lower().strip()
        zip1 = (loc1.get('zip') or '').strip()
        zip2 = (loc2.get('zip') or '').strip()

        # Zip code match is VERY strong signal (+0.25 points)
        if zip1 and zip2 and zip1 == zip2:
            score += 0.25
            details['zip_match'] = True
            details['matched_zip'] = zip1

        # City + State exact match (+0.20 points)
        if city1 and city2 and state1 and state2:
            if city1 == city2 and state1 == state2:
                score += 0.20
                details['location_match'] = True
            # Fuzzy city match if states match
            elif state1 == state2:
                city_similarity = SequenceMatcher(None, city1, city2).ratio()
                if city_similarity > 0.85:
                    # Very close city names (typos, abbreviations)
                    score += 0.15
                    details['location_match'] = 'fuzzy_city'
                    details['city_similarity'] = round(city_similarity, 3)
                else:
                    # State only
                    score += 0.05
                    details['location_match'] = 'state_only'
        elif state1 and state2 and state1 == state2:
            score += 0.05
            details['location_match'] = 'state_only'

    # Bid date proximity (0.10 points if within 7 days)
    date1 = proj1.get('bid_date') or proj1.get('response_date')
    date2 = proj2.get('bid_date') or proj2.get('response_date')

    if date1 and date2:
        try:
            from datetime import datetime
            d1 = datetime.fromisoformat(date1) if isinstance(date1, str) else date1
            d2 = datetime.fromisoformat(date2) if isinstance(date2, str) else date2
            days_diff = abs((d1 - d2).days)
            details['days_diff'] = days_diff

            if days_diff <= 7:
                score += 0.10
                details['date_match'] = True
        except (ValueError, TypeError):
            pass

    # Division 8 scoring (bonus/penalty)
    is_div8_1 = proj1.get('is_division_8', False)
    is_div8_2 = proj2.get('is_division_8', False)

    if is_div8_1 and is_div8_2:
        # Both are Division 8 - check for trade overlap
        div8_1 = proj1.get('division_8', {})
        div8_2 = proj2.get('division_8', {})

        # Extract only string values from trades and sections
        trades1_raw = div8_1.get('matching_trades', [])
        trades1 = set(str(t) for t in trades1_raw if isinstance(t, str))

        sections1_raw = div8_1.get('spec_sections', [])
        sections1 = set(str(s) for s in sections1_raw if isinstance(s, str))

        trades2_raw = div8_2.get('matching_trades', [])
        trades2 = set(str(t) for t in trades2_raw if isinstance(t, str))

        sections2_raw = div8_2.get('spec_sections', [])
        sections2 = set(str(s) for s in sections2_raw if isinstance(s, str))

        # Extract keywords from spec sections
        keywords1 = set()
        for s in sections1:
            if isinstance(s, str):
                keywords1.update(s.lower().split())

        keywords2 = set()
        for s in sections2:
            if isinstance(s, str):
                keywords2.update(s.lower().split())

        # Combine trades and keywords
        all1 = trades1.union(keywords1)
        all2 = trades2.union(keywords2)

        if all1 and all2:
            # Jaccard similarity
            intersection = all1.intersection(all2)
            union = all1.union(all2)
            overlap = len(intersection) / len(union) if union else 0

            bonus = overlap * 0.25
            score += bonus
            details['div8_overlap'] = round(overlap, 3)
            details['div8_bonus'] = round(bonus, 3)

    elif is_div8_1 != is_div8_2:
        # One is Division 8, other isn't - penalty
        score -= 0.15
        details['div8_mismatch'] = True

    details['total_score'] = round(score, 3)
    return score, details


def find_duplicate_projects(projects: list, threshold: float = 0.55) -> list:
    """
    Find duplicate projects across different sources.

    Args:
        projects: List of project dicts from various sources
        threshold: Minimum similarity score to consider a match (default: 0.55)

    Returns:
        List of duplicate groups, each containing matched projects
    """
    duplicates = []
    seen_indices = set()

    for i, proj1 in enumerate(projects):
        if i in seen_indices:
            continue

        matches = [proj1]
        match_details = []

        for j, proj2 in enumerate(projects):
            if i >= j or j in seen_indices:
                continue

            # Don't match projects from the same source
            source1 = proj1.get('source')
            source2 = proj2.get('source')
            if source1 == source2:
                continue

            # Try new UnifiedProjectMatcher first
            try:
                from modules.schema.unified_project import dict_to_unified_project
                from modules.linking.unified_matcher import UnifiedProjectMatcher

                unified1 = dict_to_unified_project(proj1)
                unified2 = dict_to_unified_project(proj2)

                matcher = UnifiedProjectMatcher()
                result = matcher.match_projects(unified1, unified2, min_confidence=threshold)

                if result:
                    score, details = result
                    matches.append(proj2)
                    match_details.append({
                        'index': j,
                        'score': score,
                        'details': details
                    })
                    seen_indices.add(j)
            except Exception as e:
                # Fallback to old matcher if new one fails
                print(f"[Deduplication] UnifiedProjectMatcher failed, using fallback: {e}")
                score, details = calculate_project_similarity(proj1, proj2)

                if score >= threshold:
                    matches.append(proj2)
                    match_details.append({
                        'index': j,
                        'score': score,
                        'details': details
                    })
                    seen_indices.add(j)

        if len(matches) > 1:
            seen_indices.add(i)
            duplicates.append({
                'projects': matches,
                'match_details': match_details,
                'primary_source': determine_primary_source(matches)
            })

    return duplicates


def determine_primary_source(projects: list) -> str:
    """
    Determine which source should be the primary record.

    Priority: Local > PlanHub > GovWin > ProjectDog

    Args:
        projects: List of matched projects

    Returns:
        Primary source name
    """
    source_priority = {
        'local_bidding': 1,
        'local_extracted': 1,
        'planhub': 2,
        'email_monitor': 2.5,
        'govwin': 3,
        'projectdog': 4
    }

    best_source = None
    best_priority = 999

    for proj in projects:
        source = proj.get('source')
        priority = source_priority.get(source, 999)

        if priority < best_priority:
            best_priority = priority
            best_source = source

    return best_source
