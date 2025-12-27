"""
Bid Opportunities API - Assessment queue for PlanHub/Email leads.

Endpoints:
- GET /opportunities - All bid opportunities awaiting review
- GET /opportunities/:id - Single opportunity with full details
- POST /opportunities/:id/accept - Accept opportunity, move to bidding
- POST /opportunities/:id/decline - Decline opportunity, archive
- POST /opportunities/:id/defer - Defer decision
"""

from flask import Blueprint, jsonify, request
from datetime import datetime

from modules.database.project_repository import get_repository, ProjectRepository
from modules.database.models import Project

opportunities_bp = Blueprint('opportunities', __name__, url_prefix='/opportunities')


@opportunities_bp.route('', methods=['GET'])
def list_opportunities():
    """
    List all bid opportunities awaiting review.

    Query params:
    - source: Filter by source (planhub, email)
    - limit: Max results
    - offset: Pagination offset
    """
    repo = get_repository()

    source = request.args.get('source')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    # Get all bid_opportunity status projects
    projects = repo.get_all_projects(
        status=ProjectRepository.STATUS_BID_OPPORTUNITY,
        source=source,
        limit=limit,
        offset=offset
    )

    return jsonify({
        'count': len(projects),
        'opportunities': [_opportunity_to_dict(p) for p in projects]
    })


@opportunities_bp.route('/<project_id>', methods=['GET'])
def get_opportunity(project_id):
    """Get a single opportunity with full details."""
    repo = get_repository()
    project = repo.get_project(project_id)

    if not project:
        return jsonify({'error': 'Opportunity not found'}), 404

    if project.workflow_status != ProjectRepository.STATUS_BID_OPPORTUNITY:
        return jsonify({'error': 'Project is not a bid opportunity'}), 400

    return jsonify(_opportunity_to_dict(project, full=True))


@opportunities_bp.route('/<project_id>/accept', methods=['POST'])
def accept_opportunity(project_id):
    """
    Accept a bid opportunity - moves to bidding status.

    Body:
    - folder_name: Optional custom folder name
    - notes: Optional notes about why we're bidding
    """
    repo = get_repository()
    data = request.get_json() or {}

    try:
        project = repo.accept_opportunity(
            project_id,
            folder_name=data.get('folder_name'),
            notes=data.get('notes')
        )

        if not project:
            return jsonify({'error': 'Opportunity not found'}), 404

        return jsonify({
            'status': 'accepted',
            'project': _opportunity_to_dict(project)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@opportunities_bp.route('/<project_id>/decline', methods=['POST'])
def decline_opportunity(project_id):
    """
    Decline a bid opportunity - archives the project.

    Body:
    - reason: Required - out_of_area, too_small, wrong_scope, timeline, other
    - notes: Optional detailed notes
    """
    repo = get_repository()
    data = request.get_json()

    if not data or not data.get('reason'):
        return jsonify({'error': 'Reason is required'}), 400

    valid_reasons = ['out_of_area', 'too_small', 'wrong_scope', 'timeline', 'other']
    if data['reason'] not in valid_reasons:
        return jsonify({
            'error': f'Invalid reason. Must be one of: {", ".join(valid_reasons)}'
        }), 400

    try:
        project = repo.decline_opportunity(
            project_id,
            reason=data['reason'],
            notes=data.get('notes')
        )

        if not project:
            return jsonify({'error': 'Opportunity not found'}), 404

        return jsonify({
            'status': 'declined',
            'project': _opportunity_to_dict(project)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@opportunities_bp.route('/<project_id>/defer', methods=['POST'])
def defer_opportunity(project_id):
    """
    Defer decision on an opportunity - keeps in queue.

    Body:
    - notes: Optional notes about why we're deferring
    """
    repo = get_repository()
    data = request.get_json() or {}

    project = repo.get_project(project_id)

    if not project:
        return jsonify({'error': 'Opportunity not found'}), 404

    if project.workflow_status != ProjectRepository.STATUS_BID_OPPORTUNITY:
        return jsonify({'error': 'Project is not a bid opportunity'}), 400

    # Update notes if provided
    if data.get('notes'):
        repo.update_project(project_id, {
            'workflow_status_notes': data['notes']
        })

    return jsonify({
        'status': 'deferred',
        'project': _opportunity_to_dict(project)
    })


@opportunities_bp.route('/count', methods=['GET'])
def count_opportunities():
    """Get count of pending opportunities."""
    repo = get_repository()
    count = repo.get_project_count(status=ProjectRepository.STATUS_BID_OPPORTUNITY)

    return jsonify({
        'count': count
    })


def _opportunity_to_dict(project: Project, full: bool = False) -> dict:
    """Convert Project to opportunity response dict."""
    data = {
        'id': project.id,
        'title': project.title,
        'source': project.source,
        'address': project.address,
        'city': project.city,
        'state': project.state,
        'zip_code': project.zip_code,
        'bid_date': project.bid_date.isoformat() if project.bid_date else None,
        'owner_name': project.owner_name,
        'architect_name': project.architect_name,
        'estimated_value': project.estimated_value,
        'trades': project.trades,
        'created_at': project.created_at.isoformat() if project.created_at else None,
    }

    if full:
        data.update({
            'description': project.description,
            'sub_bid_date': project.sub_bid_date.isoformat() if project.sub_bid_date else None,
            'pre_bid_meeting_date': project.pre_bid_meeting_date.isoformat() if project.pre_bid_meeting_date else None,
            'pre_bid_meeting_location': project.pre_bid_meeting_location,
            'square_footage': project.square_footage,
            'project_type': project.project_type,
            'building_use': project.building_use,
            'dcam_required': project.dcam_required,
            'prevailing_wage': project.prevailing_wage,
            'workflow_status_notes': project.workflow_status_notes,
        })

    return data