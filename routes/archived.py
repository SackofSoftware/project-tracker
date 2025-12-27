"""
Archived Projects Routes

Handles the archived projects page showing past bids from PlanHub and other sources.
"""

from flask import Blueprint, render_template, jsonify, request
from datetime import datetime

from modules.database.db import get_session
from modules.database.models import Project

archived_bp = Blueprint('archived', __name__)


@archived_bp.route('/archived')
def archived_page():
    """Render the archived projects page."""
    return render_template('archived.html')


@archived_bp.route('/api/projects/archived')
def get_archived_projects():
    """
    Get all archived projects.

    Query params:
    - source: Filter by source (local, planhub, all)
    - reason: Filter by archived reason (past_bid_date, no_bid, etc.)
    - search: Search by project name
    - limit: Max results (default 100)
    - offset: Pagination offset
    """
    source_filter = request.args.get('source', 'all')
    reason_filter = request.args.get('reason')
    search_query = request.args.get('search', '').strip()
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))

    with get_session() as session:
        query = session.query(Project).filter(Project.archived == True)

        # Source filter
        if source_filter != 'all':
            query = query.filter(Project.source == source_filter)

        # Reason filter
        if reason_filter:
            query = query.filter(Project.archived_reason == reason_filter)

        # Search filter
        if search_query:
            query = query.filter(Project.title.ilike(f'%{search_query}%'))

        # Get total count
        total = query.count()

        # Order by bid date descending (most recent first)
        query = query.order_by(Project.bid_date.desc())

        # Pagination
        projects = query.offset(offset).limit(limit).all()

        # Convert to dict
        result = []
        for p in projects:
            result.append({
                'id': p.id,
                'title': p.title,
                'source': p.source,
                'city': p.city,
                'state': p.state,
                'address': p.address,
                'bid_date': p.bid_date.isoformat() if p.bid_date else None,
                'estimated_value': p.estimated_value,
                'square_footage': p.square_footage,
                'construction_type': p.construction_type,
                'project_type': p.project_type,
                'building_use': p.building_use,
                'trades': p.trades,
                'description': p.description[:200] + '...' if p.description and len(p.description) > 200 else p.description,
                'distance_miles': p.distance_miles,
                'archived': p.archived,
                'archived_date': p.archived_date.isoformat() if p.archived_date else None,
                'archived_reason': p.archived_reason,
                'folder_path': p.folder_path,
                'has_folder': bool(p.folder_path),
            })

        return jsonify({
            'total': total,
            'limit': limit,
            'offset': offset,
            'projects': result
        })


@archived_bp.route('/api/projects/archived/stats')
def get_archived_stats():
    """Get statistics for archived projects."""
    with get_session() as session:
        # Total archived
        total = session.query(Project).filter(Project.archived == True).count()

        # By source
        by_source = {}
        for row in session.query(
            Project.source,
            session.query(Project).filter(Project.archived == True, Project.source == Project.source).count()
        ).filter(Project.archived == True).group_by(Project.source).all():
            by_source[row[0]] = row[1] if len(row) > 1 else 0

        # More accurate count
        local_count = session.query(Project).filter(
            Project.archived == True,
            Project.source == 'local'
        ).count()
        planhub_count = session.query(Project).filter(
            Project.archived == True,
            Project.source == 'planhub'
        ).count()

        # By reason
        by_reason = {}
        for row in session.query(
            Project.archived_reason,
        ).filter(Project.archived == True).distinct().all():
            reason = row[0] or 'unknown'
            count = session.query(Project).filter(
                Project.archived == True,
                Project.archived_reason == row[0]
            ).count()
            by_reason[reason] = count

        # With folders
        with_folders = session.query(Project).filter(
            Project.archived == True,
            Project.folder_path.isnot(None)
        ).count()

        return jsonify({
            'total': total,
            'by_source': {
                'local': local_count,
                'planhub': planhub_count,
            },
            'by_reason': by_reason,
            'with_folders': with_folders,
            'without_folders': total - with_folders,
        })


@archived_bp.route('/api/project/<project_id>/archive', methods=['POST'])
def archive_project(project_id: str):
    """Archive a project manually."""
    data = request.json or {}
    reason = data.get('reason', 'manual')

    with get_session() as session:
        project = session.query(Project).filter(Project.id == project_id).first()

        if not project:
            return jsonify({'error': 'Project not found'}), 404

        project.archived = True
        project.archived_date = datetime.now()
        project.archived_reason = reason

        session.commit()

        return jsonify({
            'success': True,
            'project_id': project_id,
            'archived': True,
            'reason': reason
        })


@archived_bp.route('/api/project/<project_id>/unarchive', methods=['POST'])
def unarchive_project(project_id: str):
    """Unarchive a project."""
    with get_session() as session:
        project = session.query(Project).filter(Project.id == project_id).first()

        if not project:
            return jsonify({'error': 'Project not found'}), 404

        project.archived = False
        project.archived_date = None
        project.archived_reason = None

        session.commit()

        return jsonify({
            'success': True,
            'project_id': project_id,
            'archived': False
        })
