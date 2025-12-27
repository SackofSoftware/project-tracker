"""
Projects Routes Blueprint

Handles project listing, filtering, and detail APIs.
"""

from flask import Blueprint, jsonify, request

from utils import (
    get_all_projects,
    find_project_by_id,
    get_bidding_reader,
    get_status_tracker,
    _last_refresh
)

from modules.scope import ScopeCardAggregator

projects_bp = Blueprint('projects', __name__)


# =============================================================================
# PROJECT LIST ENDPOINTS
# =============================================================================

@projects_bp.route('/api/projects')
def api_projects():
    """
    API endpoint for all projects with optional filtering.

    Query Parameters:
    - refresh: 'true' to force refresh (default: 'false')
    - archived: 'true', 'false', or 'only' (default: 'false')
    - source: Comma-separated list of sources to filter by (e.g., 'planhub,govwin')
      Valid sources: local_bidding, local_extracted, planhub, govwin, projectdog, email_monitor
    - decision: Comma-separated list of bid decisions to filter by
    - division_8: 'true' to show only Division 8 projects (default: 'false')
    - entity_type: Filter by entity type (e.g., 'BID', 'LEAD')
    - state: Filter by state code (e.g., 'MA', 'NH')

    Returns:
        JSON with count, projects list, and last_refresh timestamp
    """
    from utils import _last_refresh

    force = request.args.get('refresh', 'false').lower() == 'true'
    projects = get_all_projects(force_refresh=force)

    # Filter by archived status
    show_archived = request.args.get('archived', 'false').lower()
    if show_archived == 'false':
        projects = [p for p in projects if not p.get('archived', False)]
    elif show_archived == 'only':
        projects = [p for p in projects if p.get('archived', False)]

    # Filter by source
    source_filter = request.args.get('source')
    if source_filter:
        sources = source_filter.split(',')
        projects = [p for p in projects if p.get('source') in sources]

    # Filter by bid decision
    decision_filter = request.args.get('decision')
    if decision_filter:
        decisions = decision_filter.split(',')
        projects = [p for p in projects if p.get('bid_decision') in decisions]

    # Filter by Division 8
    division_8_filter = request.args.get('division_8', 'false').lower()
    if division_8_filter == 'true':
        projects = [p for p in projects if p.get('is_division_8', False)]

    # Filter by entity_type (for GovWin BID/LEAD distinction)
    entity_type_filter = request.args.get('entity_type')
    if entity_type_filter:
        entity_types = entity_type_filter.split(',')
        projects = [p for p in projects if p.get('entity_type') in entity_types]

    # Filter by state
    state_filter = request.args.get('state')
    if state_filter:
        states = state_filter.split(',')
        filtered = []
        for p in projects:
            loc = p.get('location', {})
            if isinstance(loc, dict):
                state = loc.get('state')
                if state in states:
                    filtered.append(p)
        projects = filtered

    return jsonify({
        "count": len(projects),
        "projects": projects,
        "last_refresh": _last_refresh.isoformat() if _last_refresh else None
    })


@projects_bp.route('/api/projects/local')
def api_local_projects():
    """API endpoint for local bidding projects"""
    projects = [p for p in get_all_projects() if p.get('source') in ('local_bidding', 'local_extracted')]
    return jsonify({"count": len(projects), "projects": projects})


@projects_bp.route('/api/projects/projectdog')
def api_projectdog_projects():
    """API endpoint for ProjectDog projects"""
    projects = [p for p in get_all_projects() if p.get('source') == 'projectdog']
    return jsonify({"count": len(projects), "projects": projects})


@projects_bp.route('/api/projects/planhub')
def api_planhub_projects():
    """API endpoint for PlanHub projects"""
    projects = [p for p in get_all_projects() if p.get('source') == 'planhub']
    return jsonify({"count": len(projects), "projects": projects})


@projects_bp.route('/api/projects/govwin')
def api_govwin_projects():
    """API endpoint for GovWin projects"""
    projects = [p for p in get_all_projects() if p.get('source') == 'govwin']
    return jsonify({"count": len(projects), "projects": projects})


@projects_bp.route('/api/projects/dcam')
def api_dcam_projects():
    """API endpoint for DCAM projects"""
    projects = [p for p in get_all_projects() if p.get('is_dcam')]
    return jsonify({"count": len(projects), "projects": projects})


@projects_bp.route('/api/projects/rfq')
def api_rfq_projects():
    """API endpoint for RFQ projects"""
    projects = [p for p in get_all_projects() if p.get('is_rfq')]
    return jsonify({"count": len(projects), "projects": projects})


@projects_bp.route('/api/projects/upcoming')
def api_upcoming():
    """API endpoint for upcoming bids"""
    bidding_reader = get_bidding_reader()
    days = int(request.args.get('days', 30))
    upcoming = bidding_reader.get_upcoming_bids(days)
    return jsonify({"count": len(upcoming), "days": days, "projects": upcoming})


# =============================================================================
# PROJECT DETAIL ENDPOINT
# =============================================================================

@projects_bp.route('/api/projects/<project_id>')
def api_project_detail(project_id):
    """Get detailed info for a single project"""
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    return jsonify(project)


# =============================================================================
# SCOPE CARD ENDPOINT
# =============================================================================

@projects_bp.route('/api/project/<project_id>/scope-card/<card_id>')
def api_scope_card(project_id, card_id):
    """Get detailed scope card data for a project"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id)

    aggregator = ScopeCardAggregator(project_id)
    card = aggregator.get_card(card_id, project, status)

    if not card:
        return jsonify({"error": f"Scope card '{card_id}' not found"}), 404

    return jsonify(card)


@projects_bp.route('/api/project/<project_id>/scope-cards')
def api_scope_cards(project_id):
    """Get all scope cards for a project"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id)

    aggregator = ScopeCardAggregator(project_id)
    cards = aggregator.get_all_cards(project, status)

    return jsonify({"cards": cards})


# =============================================================================
# KEY DRAWINGS ENDPOINT
# =============================================================================

@projects_bp.route('/api/project/<project_id>/key-drawings')
def api_key_drawings(project_id):
    """Get categorized key drawings for a project"""
    import os
    import re
    from pathlib import Path

    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    folder_path = project.get('folder_path')
    if not folder_path:
        return jsonify({"error": "No folder path for project"}), 404

    # Look for Drawings folder
    drawings_path = Path(folder_path) / "Drawings"
    if not drawings_path.exists():
        # Try root folder
        drawings_path = Path(folder_path)

    # Category patterns for architectural drawings
    category_patterns = {
        'elevations': [
            r'[Ee]levat',
            r'A-?3\d{2}',
            r'A3\d{2}',
            r'[Ee]xt[\.|\s]',
            r'[Nn]orth|[Ss]outh|[Ee]ast|[Ww]est.*[Ee]lev'
        ],
        'floor_plans': [
            r'[Ff]loor\s*[Pp]lan',
            r'A-?1\d{2}',
            r'A1\d{2}',
            r'A-?2\d{2}',
            r'A2\d{2}',
            r'[Ll]evel\s*\d',
            r'[Pp]lan.*[Ll]evel'
        ],
        'schedules': [
            r'[Ss]chedule',
            r'A-?6\d{2}',
            r'A6\d{2}',
            r'[Dd]oor\s*[Ss]ch',
            r'[Ww]indow\s*[Ss]ch',
            r'[Ff]inish\s*[Ss]ch'
        ],
        'sections': [
            r'[Ss]ection',
            r'A-?5\d{2}',
            r'A5\d{2}',
            r'[Dd]etail',
            r'[Ww]all\s*[Ss]ect'
        ]
    }

    categories = {
        'elevations': [],
        'floor_plans': [],
        'schedules': [],
        'sections': [],
        'other': []
    }

    # Scan for PDF files
    pdf_files = []
    for root, dirs, files in os.walk(drawings_path):
        for f in files:
            if f.lower().endswith('.pdf'):
                full_path = os.path.join(root, f)
                pdf_files.append({
                    'name': f,
                    'path': full_path,
                    'sheet': extract_sheet_number(f)
                })

    # Categorize each file
    for pdf in pdf_files:
        filename = pdf['name']
        categorized = False

        for cat_name, patterns in category_patterns.items():
            for pattern in patterns:
                if re.search(pattern, filename, re.IGNORECASE):
                    categories[cat_name].append(pdf)
                    categorized = True
                    break
            if categorized:
                break

        if not categorized:
            categories['other'].append(pdf)

    # Sort each category by sheet number or name
    for cat in categories:
        categories[cat].sort(key=lambda x: x['sheet'] or x['name'])

    return jsonify({
        "project_id": project_id,
        "drawings_path": str(drawings_path),
        "total_drawings": len(pdf_files),
        "categories": categories
    })


def extract_sheet_number(filename):
    """Extract sheet number from drawing filename"""
    import re

    # Common patterns: A101, A-101, A1.01, etc.
    patterns = [
        r'([ASMEPG]-?\d{3,4})',  # A101, A-101, M201
        r'([ASMEPG]\d\.\d{2})',  # A1.01
        r'(\d{3,4})',  # Just numbers
    ]

    for pattern in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


# =============================================================================
# STATS ENDPOINT
# =============================================================================

@projects_bp.route('/api/stats')
def api_stats():
    """Get dashboard statistics"""
    projects = get_all_projects()

    # Count by source
    local_count = len([p for p in projects if p.get('source') in ('local_bidding', 'local_extracted')])
    projectdog_count = len([p for p in projects if p.get('source') == 'projectdog'])
    planhub_count = len([p for p in projects if p.get('source') == 'planhub'])
    govwin_count = len([p for p in projects if p.get('source') == 'govwin'])
    email_count = len([p for p in projects if p.get('source') == 'email_monitor'])

    # Count by type
    dcam_count = len([p for p in projects if p.get('is_dcam')])
    rfq_count = len([p for p in projects if p.get('is_rfq')])
    division_8_count = len([p for p in projects if p.get('is_division_8')])

    # Count GovWin entity types
    govwin_bids = len([p for p in projects if p.get('source') == 'govwin' and p.get('entity_type') == 'BID'])
    govwin_leads = len([p for p in projects if p.get('source') == 'govwin' and p.get('entity_type') == 'LEAD'])
    govwin_active = len([p for p in projects if p.get('source') == 'govwin' and p.get('is_active')])

    # Count by status
    with_estimate = len([p for p in projects if p.get('has_internal_estimate')])
    with_proposal = len([p for p in projects if p.get('has_proposal')])
    archived = len([p for p in projects if p.get('archived')])

    # Count by state
    by_state = {}
    for p in projects:
        loc = p.get('location', {})
        state = loc.get('state') if isinstance(loc, dict) else None
        if state:
            by_state[state] = by_state.get(state, 0) + 1

    # Count linked projects
    planhub_linked = len([p for p in projects if p.get('planhub_linked')])
    govwin_linked = len([p for p in projects if p.get('govwin_linked')])
    email_linked = len([p for p in projects if p.get('email_linked')])

    return jsonify({
        "total_projects": len(projects),
        "by_source": {
            "local": local_count,
            "projectdog": projectdog_count,
            "planhub": planhub_count,
            "govwin": govwin_count,
            "email_monitor": email_count
        },
        "by_type": {
            "dcam": dcam_count,
            "rfq": rfq_count,
            "division_8": division_8_count
        },
        "govwin": {
            "total": govwin_count,
            "bids": govwin_bids,
            "leads": govwin_leads,
            "active": govwin_active
        },
        "linked": {
            "planhub": planhub_linked,
            "govwin": govwin_linked,
            "email": email_linked
        },
        "internal_tracking": {
            "with_estimates": with_estimate,
            "with_proposals": with_proposal,
            "archived": archived
        },
        "by_state": by_state
    })


# =============================================================================
# FOLDER LINK ENDPOINTS
# =============================================================================

@projects_bp.route('/api/project/<project_id>/folder')
def api_get_folder(project_id):
    """Get the linked folder path for a project"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    folder_path = project.get('folder_path')

    return jsonify({
        "status": "ok",
        "project_id": project_id,
        "folder_path": folder_path,
        "has_folder": bool(folder_path)
    })


@projects_bp.route('/api/project/<project_id>/folder', methods=['PUT', 'POST'])
def api_set_folder(project_id):
    """Set/update the linked folder path for a project"""
    from modules.database.db import get_session
    from modules.database.models import Project as DBProject

    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    data = request.json or {}
    folder_path = data.get('folder_path', '').strip()

    if not folder_path:
        return jsonify({"error": "folder_path is required"}), 400

    # Validate the path exists
    from pathlib import Path
    if not Path(folder_path).exists():
        return jsonify({"error": f"Folder does not exist: {folder_path}"}), 400

    # Update in database
    with get_session() as session:
        db_project = session.query(DBProject).filter(DBProject.id == project_id).first()
        if db_project:
            db_project.folder_path = folder_path
            session.commit()
        else:
            # Create new record if doesn't exist
            db_project = DBProject(id=project_id, folder_path=folder_path)
            session.add(db_project)
            session.commit()

    # Also update status tracker for immediate visibility
    status_tracker = get_status_tracker()
    status_tracker.update_status(project_id, {'folder_path': folder_path})

    return jsonify({
        "status": "ok",
        "project_id": project_id,
        "folder_path": folder_path,
        "message": "Folder linked successfully"
    })


@projects_bp.route('/api/project/<project_id>/folder/open', methods=['POST'])
def api_open_folder(project_id):
    """Open the project folder in Finder/Explorer"""
    import subprocess
    import sys
    from pathlib import Path
    from utils import get_project_folder_path

    # Get folder path
    project_path, _ = get_project_folder_path(project_id)

    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        # Open in system file manager
        if sys.platform == 'darwin':
            subprocess.run(['open', str(project_path)], check=True)
        elif sys.platform == 'win32':
            subprocess.run(['explorer', str(project_path)], check=True)
        else:
            subprocess.run(['xdg-open', str(project_path)], check=True)

        return jsonify({
            "status": "ok",
            "folder_path": str(project_path),
            "message": "Folder opened"
        })
    except Exception as e:
        return jsonify({"error": f"Failed to open folder: {str(e)}"}), 500


@projects_bp.route('/api/project/<project_id>/folder/files')
def api_list_folder_files(project_id):
    """List files in the project folder"""
    from pathlib import Path
    from utils import get_project_folder_path

    # Get folder path
    project_path, _ = get_project_folder_path(project_id)

    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        files = []
        for item in sorted(project_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            # Skip hidden files
            if item.name.startswith('.'):
                continue
            file_info = {
                "name": item.name,
                "is_dir": item.is_dir()
            }
            if not item.is_dir():
                try:
                    file_info["size"] = item.stat().st_size
                except:
                    pass
            files.append(file_info)

        return jsonify({
            "status": "ok",
            "folder_path": str(project_path),
            "files": files,
            "count": len(files)
        })
    except Exception as e:
        return jsonify({"error": f"Failed to list files: {str(e)}"}), 500
