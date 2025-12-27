"""
Duplicates API - Deduplication review queue.

Endpoints:
- GET /duplicates - All potential duplicates
- GET /duplicates/pending - Duplicates awaiting review
- GET /duplicates/count - Count of pending duplicates
- POST /duplicates/merge - Merge two projects
- POST /duplicates/reject - Mark as not duplicate
- POST /duplicates/scan - Trigger deduplication scan
"""

from flask import Blueprint, jsonify, request

from modules.database.dedup_service import get_dedup_service
from modules.database.db import get_session
from modules.database.models import PendingDuplicate, Project

duplicates_bp = Blueprint('duplicates', __name__, url_prefix='/duplicates')


@duplicates_bp.route('', methods=['GET'])
def list_duplicates():
    """
    List all potential duplicates.

    Query params:
    - status: Filter by status (pending, approved, rejected)
    - limit: Max results (default 50)
    """
    status = request.args.get('status', 'pending')
    limit = request.args.get('limit', 50, type=int)

    with get_session() as session:
        query = session.query(PendingDuplicate)

        if status:
            query = query.filter(PendingDuplicate.status == status)

        query = query.order_by(PendingDuplicate.match_confidence.desc())
        duplicates = query.limit(limit).all()

        result = []
        for dup in duplicates:
            # Get both project details
            project_a = session.query(Project).filter(
                Project.id == dup.project_a_id
            ).first()

            result.append({
                'id': dup.id,
                'project_a': _project_summary(project_a) if project_a else {'id': dup.project_a_id},
                'project_b_id': dup.project_b_id,
                'project_b_type': dup.project_b_type,
                'match_confidence': dup.match_confidence,
                'match_reasons': dup.match_reasons,
                'status': dup.status,
                'created_at': dup.created_at.isoformat() if dup.created_at else None
            })

        return jsonify({
            'count': len(result),
            'duplicates': result
        })


@duplicates_bp.route('/pending', methods=['GET'])
def list_pending():
    """Get duplicates awaiting review (confidence 70-89%)."""
    limit = request.args.get('limit', 50, type=int)

    service = get_dedup_service()
    pending = service.get_pending_duplicates(limit=limit)

    with get_session() as session:
        result = []
        for dup in pending:
            project_a = session.query(Project).filter(
                Project.id == dup.project_a_id
            ).first()

            # Try to get project_b if it's a project type
            project_b = None
            if dup.project_b_type == 'project':
                project_b = session.query(Project).filter(
                    Project.id == dup.project_b_id
                ).first()

            result.append({
                'id': dup.id,
                'project_a': _project_summary(project_a) if project_a else {'id': dup.project_a_id},
                'project_b': _project_summary(project_b) if project_b else {
                    'id': dup.project_b_id,
                    'type': dup.project_b_type
                },
                'match_confidence': dup.match_confidence,
                'match_reasons': dup.match_reasons,
                'created_at': dup.created_at.isoformat() if dup.created_at else None
            })

        return jsonify({
            'count': len(result),
            'pending': result
        })


@duplicates_bp.route('/count', methods=['GET'])
def count_pending():
    """Get count of pending duplicates."""
    service = get_dedup_service()
    count = service.get_pending_count()

    return jsonify({'count': count})


@duplicates_bp.route('/merge', methods=['POST'])
def merge_duplicates():
    """
    Merge a duplicate into the canonical project.

    Body:
    - canonical_id: ID of the project to keep (required)
    - source_type: Type of source being merged (required)
    - source_id: ID of source being merged (required)
    - source_data: Optional data from source
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required = ['canonical_id', 'source_type', 'source_id']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400

    try:
        service = get_dedup_service()
        project = service.merge_projects(
            canonical_id=data['canonical_id'],
            source_type=data['source_type'],
            source_id=data['source_id'],
            source_data=data.get('source_data', {}),
            merged_by=data.get('merged_by', 'user')
        )

        return jsonify({
            'status': 'merged',
            'project': _project_summary(project)
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@duplicates_bp.route('/reject', methods=['POST'])
def reject_duplicate():
    """
    Mark a pending duplicate as not a duplicate.

    Body:
    - pending_id: ID of the PendingDuplicate record (required)
    - notes: Optional notes about why not a duplicate
    """
    data = request.get_json()

    if not data or not data.get('pending_id'):
        return jsonify({'error': 'pending_id is required'}), 400

    try:
        service = get_dedup_service()
        service.reject_duplicate(
            pending_id=data['pending_id'],
            rejected_by=data.get('rejected_by', 'user'),
            notes=data.get('notes')
        )

        return jsonify({'status': 'rejected'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@duplicates_bp.route('/scan', methods=['POST'])
def trigger_scan():
    """
    Trigger a deduplication scan across all projects.
    This finds new potential duplicates and queues them for review.
    """
    try:
        service = get_dedup_service()
        new_duplicates = service.find_all_potential_duplicates()

        return jsonify({
            'status': 'completed',
            'new_duplicates_found': len(new_duplicates)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@duplicates_bp.route('/compare', methods=['POST'])
def compare_projects():
    """
    Compare two projects and return match score.
    Useful for manual comparison before merging.

    Body:
    - project_a: Project data dict
    - project_b: Project data dict
    """
    data = request.get_json()

    if not data or not data.get('project_a') or not data.get('project_b'):
        return jsonify({'error': 'Both project_a and project_b are required'}), 400

    try:
        service = get_dedup_service()
        score, reasons = service.calculate_match_score(
            data['project_a'],
            data['project_b']
        )

        return jsonify({
            'match_score': score,
            'breakdown': reasons,
            'recommendation': _get_recommendation(score)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _project_summary(project: Project) -> dict:
    """Get a summary dict for a project."""
    if not project:
        return None
    return {
        'id': project.id,
        'title': project.title,
        'address': project.address,
        'city': project.city,
        'state': project.state,
        'bid_date': project.bid_date.isoformat() if project.bid_date else None,
        'source': project.source,
        'workflow_status': project.workflow_status
    }


def _get_recommendation(score: float) -> str:
    """Get recommendation based on match score."""
    if score >= 0.90:
        return 'auto_merge'
    elif score >= 0.70:
        return 'review'
    elif score >= 0.50:
        return 'possible_match'
    else:
        return 'not_duplicate'
