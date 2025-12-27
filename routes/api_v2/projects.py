"""
Projects API - Full project lifecycle management.

Endpoints:
- GET /projects - List all projects (paginated)
- GET /projects/:id - Get single project with full details
- POST /projects - Create new project
- PUT /projects/:id - Update project
- PUT /projects/:id/status - Change workflow status
- GET /projects/:id/sources - All linked sources
- GET /projects/:id/contractors - Project contractors
"""

from flask import Blueprint, jsonify, request
from datetime import datetime

from modules.database.project_repository import get_repository
from modules.database.models import Project

projects_bp = Blueprint('projects', __name__, url_prefix='/projects')


@projects_bp.route('', methods=['GET'])
def list_projects():
    """
    List all projects with optional filtering.

    Query params:
    - status: Filter by workflow status
    - source: Filter by source
    - upcoming: Get projects with bid dates in next N days
    - limit: Max results (default 100)
    - offset: Pagination offset
    - include_archived: Include archived projects (default false)
    """
    repo = get_repository()

    status = request.args.get('status')
    source = request.args.get('source')
    upcoming_days = request.args.get('upcoming', type=int)
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    include_archived = request.args.get('include_archived', 'false').lower() == 'true'

    if upcoming_days:
        projects = repo.get_upcoming_bids(upcoming_days)
    else:
        projects = repo.get_all_projects(
            include_archived=include_archived,
            status=status,
            source=source,
            limit=limit,
            offset=offset
        )

    return jsonify({
        'count': len(projects),
        'projects': [_project_to_dict(p) for p in projects]
    })


@projects_bp.route('/<project_id>', methods=['GET'])
def get_project(project_id):
    """Get a single project with full details."""
    repo = get_repository()
    project = repo.get_project(project_id)

    if not project:
        return jsonify({'error': 'Project not found'}), 404

    return jsonify(_project_to_dict(project, full=True))


@projects_bp.route('', methods=['POST'])
def create_project():
    """Create a new project."""
    repo = get_repository()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if not data.get('title'):
        return jsonify({'error': 'Title is required'}), 400

    try:
        project = repo.create_project(data)
        return jsonify(_project_to_dict(project)), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@projects_bp.route('/<project_id>', methods=['PUT'])
def update_project(project_id):
    """Update a project's fields."""
    repo = get_repository()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    project = repo.update_project(project_id, data)

    if not project:
        return jsonify({'error': 'Project not found'}), 404

    return jsonify(_project_to_dict(project))


@projects_bp.route('/<project_id>/status', methods=['PUT'])
def change_status(project_id):
    """
    Change a project's workflow status.

    Body:
    - status: New status (required)
    - notes: Optional status change notes
    """
    repo = get_repository()
    data = request.get_json()

    if not data or not data.get('status'):
        return jsonify({'error': 'Status is required'}), 400

    try:
        project = repo.change_status(
            project_id,
            data['status'],
            notes=data.get('notes')
        )

        if not project:
            return jsonify({'error': 'Project not found'}), 404

        return jsonify(_project_to_dict(project))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@projects_bp.route('/<project_id>/archive', methods=['POST'])
def archive_project(project_id):
    """Archive a project."""
    repo = get_repository()
    data = request.get_json() or {}

    project = repo.archive_project(project_id, reason=data.get('reason', 'manual'))

    if not project:
        return jsonify({'error': 'Project not found'}), 404

    return jsonify(_project_to_dict(project))


@projects_bp.route('/<project_id>/sources', methods=['GET'])
def get_project_sources(project_id):
    """Get all source links for a project."""
    repo = get_repository()
    sources = repo.get_project_sources(project_id)

    return jsonify({
        'project_id': project_id,
        'sources': [
            {
                'id': s.id,
                'source_type': s.source_type,
                'source_id': s.source_id,
                'source_url': s.source_url,
                'match_confidence': s.match_confidence,
                'match_type': s.match_type,
                'matched_at': s.matched_at.isoformat() if s.matched_at else None
            }
            for s in sources
        ]
    })


@projects_bp.route('/<project_id>/contractors', methods=['GET'])
def get_project_contractors(project_id):
    """Get contractors for a project."""
    repo = get_repository()
    role = request.args.get('role')

    contractors = repo.get_project_contractors(project_id, role=role)

    return jsonify({
        'project_id': project_id,
        'contractors': [c.to_dict() for c in contractors]
    })


@projects_bp.route('/<project_id>/contractors', methods=['POST'])
def add_contractor(project_id):
    """Add a contractor to a project."""
    repo = get_repository()
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    if not data.get('company_name'):
        return jsonify({'error': 'company_name is required'}), 400

    if not data.get('role'):
        return jsonify({'error': 'role is required'}), 400

    try:
        contractor = repo.add_contractor(
            project_id=project_id,
            company_name=data['company_name'],
            role=data['role'],
            contact_name=data.get('contact_name'),
            contact_email=data.get('contact_email'),
            contact_phone=data.get('contact_phone'),
            trade=data.get('trade'),
            source=data.get('source', 'manual')
        )
        return jsonify(contractor.to_dict()), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@projects_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get dashboard statistics."""
    repo = get_repository()
    stats = repo.get_dashboard_stats()
    return jsonify(stats)


@projects_bp.route('/search', methods=['GET'])
def search_projects():
    """Search projects by title, address, or owner."""
    repo = get_repository()
    query = request.args.get('q', '')
    limit = request.args.get('limit', 20, type=int)

    if not query:
        return jsonify({'error': 'Query parameter q is required'}), 400

    projects = repo.search_projects(query, limit=limit)

    return jsonify({
        'query': query,
        'count': len(projects),
        'projects': [_project_to_dict(p) for p in projects]
    })


def _project_to_dict(project: Project, full: bool = False) -> dict:
    """Convert Project model to API response dict."""
    data = {
        'id': project.id,
        'title': project.title,
        'source': project.source,
        'workflow_status': project.workflow_status,
        'address': project.address,
        'city': project.city,
        'state': project.state,
        'zip_code': project.zip_code,
        'bid_date': project.bid_date.isoformat() if project.bid_date else None,
        'owner_name': project.owner_name,
        'architect_name': project.architect_name,
        'estimated_value': project.estimated_value,
        'archived': project.archived,
        'created_at': project.created_at.isoformat() if project.created_at else None,
        'updated_at': project.updated_at.isoformat() if project.updated_at else None,
    }

    if full:
        data.update({
            'description': project.description,
            'folder_path': project.folder_path,
            'sub_bid_date': project.sub_bid_date.isoformat() if project.sub_bid_date else None,
            'pre_bid_meeting_date': project.pre_bid_meeting_date.isoformat() if project.pre_bid_meeting_date else None,
            'pre_bid_meeting_location': project.pre_bid_meeting_location,
            'engineer_name': project.engineer_name,
            'square_footage': project.square_footage,
            'project_type': project.project_type,
            'building_use': project.building_use,
            'trades': project.trades,
            'dcam_required': project.dcam_required,
            'prevailing_wage': project.prevailing_wage,
            'workflow_status_notes': project.workflow_status_notes,
            'workflow_status_changed_at': project.workflow_status_changed_at.isoformat() if project.workflow_status_changed_at else None,
            'archived_reason': project.archived_reason,
        })

    return data