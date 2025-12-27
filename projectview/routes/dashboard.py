"""
Dashboard Routes Blueprint

Handles main UI pages: dashboard, project detail, vendors.
"""

from flask import Blueprint, render_template

from utils import (
    get_all_projects,
    find_project_by_id,
    get_bidding_reader,
    get_status_tracker,
    get_background_sync,
    _last_refresh
)

dashboard_bp = Blueprint('dashboard', __name__)


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

    stats = bidding_reader.get_summary_stats()
    upcoming = bidding_reader.get_upcoming_bids(30)
    tracking_stats = status_tracker.get_summary_stats()

    # Separate by source
    local_projects = [p for p in projects if p.get('source') in ('local_bidding', 'local_extracted', 'local')]
    projectdog_projects = [p for p in projects if p.get('source') == 'projectdog']
    planhub_projects = [p for p in projects if p.get('source') == 'planhub']

    # Separate by type
    dcam_projects = [p for p in projectdog_projects if p.get('is_dcam')]
    rfq_projects = [p for p in projectdog_projects if p.get('is_rfq')]
    regular_projects = [p for p in projectdog_projects if not p.get('is_dcam') and not p.get('is_rfq')]

    # Count archived for stats display
    archived_count = len(archived_ids)

    # Extract GC companies for filter dropdown (top 30 by project count)
    from collections import Counter
    gc_counter = Counter()
    for p in projects:
        gc = p.get('gc_company')
        if gc:
            gc_counter[gc] += 1
    gc_companies = gc_counter.most_common(30)

    return render_template(
        'dashboard.html',
        projects=projects,
        local_projects=local_projects,
        projectdog_projects=projectdog_projects,
        planhub_projects=planhub_projects,
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
    """Project detail view"""
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

    return render_template(
        'project_detail.html',
        project=project,
        project_id=project_id,
        status=status
    )


# =============================================================================
# VENDORS PAGE
# =============================================================================

@dashboard_bp.route('/vendors')
def vendors_page():
    """Vendor management page"""
    return render_template('vendors.html')
