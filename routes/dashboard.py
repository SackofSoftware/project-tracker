"""
Dashboard Routes Blueprint

Handles main UI pages: dashboard, project detail, vendors.
"""

from flask import Blueprint, render_template, jsonify

from utils import (
    get_all_projects,
    find_project_by_id,
    get_bidding_reader,
    get_status_tracker,
    get_background_sync,
    _last_refresh
)

from modules.scope import get_scope_cards

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/api/loading-status')
def loading_status():
    """Check if initial data load is in progress"""
    try:
        # Import from app module
        import app as app_module
        loading = getattr(app_module, '_loading_in_progress', False)
        done = getattr(app_module, '_initial_load_done', False)
        count = len(getattr(app_module, '_all_projects', []))
        return jsonify({
            'loading': loading,
            'done': done,
            'project_count': count
        })
    except Exception as e:
        return jsonify({'loading': False, 'done': True, 'project_count': 0, 'error': str(e)})


# =============================================================================
# MAIN DASHBOARD
# =============================================================================

@dashboard_bp.route('/')
def index():
    """Main dashboard view - shows only active (non-archived) projects"""
    from utils import _last_refresh
    from datetime import datetime

    bidding_reader = get_bidding_reader()
    status_tracker = get_status_tracker()
    background_sync = get_background_sync()

    all_projects = get_all_projects()

    # Filter to active projects only (not archived)
    # Also load archived status from database for projects
    from modules.database.db import get_session
    from modules.database.models import Project as DBProject

    archived_ids = set()
    with get_session() as session:
        archived = session.query(DBProject.id).filter(DBProject.archived == True).all()
        archived_ids = {row[0] for row in archived}

    # Filter out archived projects
    projects = [p for p in all_projects if p.get('id') not in archived_ids
                and p.get('project_code') not in archived_ids]

    # Filter out projects with past bid dates and archive them
    from datetime import date
    from zoneinfo import ZoneInfo
    eastern = ZoneInfo('America/New_York')
    today = datetime.now(eastern).date().isoformat()

    def is_future_or_no_date(p):
        bid_date = p.get('bid_date')
        if not bid_date:
            return True  # No bid date = keep on dashboard
        if isinstance(bid_date, str):
            return bid_date >= today
        if hasattr(bid_date, 'isoformat'):
            return bid_date.isoformat() >= today
        return True

    # Only show projects with future bid dates (or no bid date)
    projects = [p for p in projects if is_future_or_no_date(p)]

    # Sort by bid date (soonest first), projects without bid dates at the end
    def get_bid_date_sort_key(p):
        bid_date = p.get('bid_date')
        if not bid_date:
            return '9999-12-31'  # No bid date goes to the end
        if isinstance(bid_date, str):
            return bid_date
        return bid_date.isoformat() if hasattr(bid_date, 'isoformat') else str(bid_date)

    projects = sorted(projects, key=get_bid_date_sort_key)

    # Check which projects have local folders that exist
    from pathlib import Path
    for p in projects:
        folder_path = p.get('folder_path')
        if folder_path and Path(folder_path).exists():
            p['has_local_folder'] = True
        else:
            p['has_local_folder'] = False

    # Separate won/awarded projects for dedicated section
    won_projects = [p for p in all_projects if p.get('bid_decision') == 'awarded']
    # Remove won from main projects list (they show in their own section)
    projects = [p for p in projects if p.get('bid_decision') != 'awarded']

    stats = bidding_reader.get_summary_stats()
    upcoming = bidding_reader.get_upcoming_bids(30)
    tracking_stats = status_tracker.get_summary_stats()

    # Separate by source
    local_projects = [p for p in projects if p.get('source') in ('local_bidding', 'local_extracted', 'local')]
    projectdog_projects = [p for p in projects if p.get('source') == 'projectdog']
    planhub_projects = [p for p in projects if p.get('source') == 'planhub']

    # Count "new" PlanHub leads - those not linked to any existing project
    # Projects with source='planhub' are standalone (unmatched) leads
    planhub_new_count = len(planhub_projects)

    # Separate by type
    dcam_projects = [p for p in projectdog_projects if p.get('is_dcam')]
    rfq_projects = [p for p in projectdog_projects if p.get('is_rfq')]
    regular_projects = [p for p in projectdog_projects if not p.get('is_dcam') and not p.get('is_rfq')]

    # Count archived for stats display
    archived_count = len(archived_ids)

    # Extract GC companies for filter dropdown (alphabetical order)
    from collections import Counter
    gc_counter = Counter()
    for p in projects:
        # Handle single gc_company
        gc = p.get('gc_company')
        if gc:
            gc_counter[gc] += 1
        # Handle multiple gc_companies (new format)
        gcs = p.get('gc_companies', [])
        for gc_info in gcs:
            if isinstance(gc_info, dict):
                gc_counter[gc_info.get('company', '')] += 1
            elif isinstance(gc_info, str):
                gc_counter[gc_info] += 1
    # Sort alphabetically (case-insensitive)
    gc_companies = sorted(gc_counter.items(), key=lambda x: x[0].lower())

    return render_template(
        'dashboard.html',
        projects=projects,
        won_projects=won_projects,
        local_projects=local_projects,
        projectdog_projects=projectdog_projects,
        planhub_projects=planhub_projects,
        planhub_new_count=planhub_new_count,
        dcam_projects=dcam_projects,
        rfq_projects=rfq_projects,
        regular_projects=regular_projects,
        upcoming_bids=upcoming[:10],
        stats=stats,
        tracking_stats=tracking_stats,
        last_refresh=_last_refresh,
        sync_status=background_sync.get_status(),
        archived_count=archived_count,
        gc_companies=gc_companies
    )


# =============================================================================
# PROJECT DETAIL PAGE
# =============================================================================

@dashboard_bp.route('/project/<project_id>')
def project_detail(project_id):
    """Project Command Center view - new 3-column layout (default)"""
    status_tracker = get_status_tracker()

    project = find_project_by_id(project_id)

    if not project:
        return render_template('error.html', message='Project not found'), 404

    status = status_tracker.get_status(project_id)

    # Merge extracted data from status into project
    if status:
        if status.get('division_8_scope'):
            project['division_8'] = status['division_8_scope']

        if status.get('architect') and not project.get('architect'):
            project['architect'] = status['architect']
        if status.get('owner') and not project.get('owner'):
            project['owner'] = status['owner']
        if status.get('extracted_bid_date') and not project.get('bid_date'):
            project['bid_date'] = status['extracted_bid_date']
        if status.get('is_dcam_extracted'):
            project['is_dcam'] = True
        if status.get('extracted_data'):
            project['has_extracted_data'] = True

    # Generate scope cards from aggregator
    scope_cards = get_scope_cards(project_id, project, status)

    # Get full folder path for display
    from utils import get_project_folder_path
    full_path, _ = get_project_folder_path(project_id)
    if full_path and full_path.exists():
        project['full_folder_path'] = str(full_path)
        # Create shortened display path (just last 2 parts)
        parts = full_path.parts
        if len(parts) >= 2:
            project['folder_display'] = '/'.join(parts[-2:])
        else:
            project['folder_display'] = full_path.name
    else:
        project['full_folder_path'] = None
        project['folder_display'] = None

    return render_template(
        'project_detail.html',
        project=project,
        project_id=project_id,
        status=status,
        scope_cards=scope_cards
    )


@dashboard_bp.route('/project/<project_id>/legacy')
def project_detail_legacy(project_id):
    """Legacy project detail view (traditional layout)"""
    status_tracker = get_status_tracker()

    project = find_project_by_id(project_id)

    if not project:
        return render_template('error.html', message='Project not found'), 404

    status = status_tracker.get_status(project_id)

    # Merge extracted data from status into project
    if status:
        if status.get('division_8_scope'):
            project['division_8'] = status['division_8_scope']

        if status.get('architect') and not project.get('architect'):
            project['architect'] = status['architect']
        if status.get('owner') and not project.get('owner'):
            project['owner'] = status['owner']
        if status.get('extracted_bid_date') and not project.get('bid_date'):
            project['bid_date'] = status['extracted_bid_date']
        if status.get('is_dcam_extracted'):
            project['is_dcam'] = True
        if status.get('extracted_data'):
            project['has_extracted_data'] = True

    # Generate scope cards from aggregator
    scope_cards = get_scope_cards(project_id, project, status)

    return render_template(
        'project_detail_legacy.html',
        project=project,
        project_id=project_id,
        status=status,
        scope_cards=scope_cards
    )


# =============================================================================
# PROJECT TAGS API
# =============================================================================

@dashboard_bp.route('/api/project/<project_id>/tags')
def api_project_tags_get(project_id):
    """
    Get project tags (classification tags like 'Sub Bidding', 'Commercial', 'Renovation').
    These are distinct from scope/CSI tags which describe Division 8 work.
    """
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Get tags from project data (typically from PlanHub)
    tags = project.get('tags', [])

    # Also include derived classification info
    return jsonify({
        "status": "ok",
        "project_id": project_id,
        "tags": tags,
        "project_type": project.get('project_type'),  # Renovation, New Construction, etc.
        "sector": project.get('sector'),  # Commercial, Retail, Industrial, etc.
        "is_sub_bidding": project.get('is_sub_bidding', False),
        "is_gc_awarded": project.get('is_gc_awarded', False),
        "source": project.get('source', 'unknown')
    })


@dashboard_bp.route('/api/project/<project_id>/tags', methods=['PUT', 'POST'])
def api_project_tags_set(project_id):
    """
    Update project tags. Stores in status tracker for persistence.
    """
    from utils import get_status_tracker

    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    data = request.json or {}
    tags = data.get('tags', [])

    if not isinstance(tags, list):
        return jsonify({"error": "tags must be a list"}), 400

    status_tracker = get_status_tracker()
    status_tracker.update_status(project_id, {'project_tags': tags})

    return jsonify({
        "status": "ok",
        "project_id": project_id,
        "tags": tags
    })


@dashboard_bp.route('/api/project-tags/options')
def api_project_tags_options():
    """Get all possible project tag options (from PlanHub taxonomy)"""
    return jsonify({
        "status": "ok",
        "project_types": ["Renovation", "New Construction", "Tenant Build-Out", "Addition"],
        "sectors": ["Commercial", "Retail", "Industrial", "Education", "Healthcare", "Hospitality"],
        "classification_tags": ["Sub Bidding", "GC Awarded", "Commercial", "Renovation", "New Construction", "Retail", "Industrial"]
    })


@dashboard_bp.route('/api/project-tags/in-use')
def api_project_tags_in_use():
    """
    Get all unique project type tags currently in use with counts.
    Used to dynamically populate the Project Type filter dropdown.
    Only counts active projects (not archived, future bid dates).
    """
    from collections import Counter
    from datetime import datetime
    from zoneinfo import ZoneInfo

    all_projects = get_all_projects()

    # Get archived project IDs
    from modules.database.db import get_session
    from modules.database.models import Project as DBProject
    archived_ids = set()
    with get_session() as session:
        archived = session.query(DBProject.id).filter(DBProject.archived == True).all()
        archived_ids = {row[0] for row in archived}

    # Get today's date for bid date filtering
    eastern = ZoneInfo('America/New_York')
    today = datetime.now(eastern).date().isoformat()

    def is_active_project(p):
        # Check if archived
        if p.get('id') in archived_ids or p.get('project_code') in archived_ids:
            return False
        # Check if won (shown in separate section)
        if p.get('bid_decision') == 'awarded':
            return False
        # Check bid date (must be future or no date)
        bid_date = p.get('bid_date')
        if bid_date:
            if isinstance(bid_date, str):
                if bid_date < today:
                    return False
            elif hasattr(bid_date, 'isoformat'):
                if bid_date.isoformat() < today:
                    return False
        return True

    # Filter to active projects only
    active_projects = [p for p in all_projects if is_active_project(p)]

    tag_counts = Counter()
    for project in active_projects:
        tags = project.get('tags', [])
        if isinstance(tags, list):
            for tag in tags:
                if tag and isinstance(tag, str):
                    tag_counts[tag] += 1

    # Sort by count descending, then alphabetically
    sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))

    return jsonify({
        "status": "ok",
        "tags": {tag: count for tag, count in sorted_tags},
        "total_projects": len(active_projects)
    })


# =============================================================================
# VENDORS PAGE
# =============================================================================

@dashboard_bp.route('/vendors')
def vendors_page():
    """Vendor management page"""
    return render_template('vendors.html')
