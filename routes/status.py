"""
Status Tracking Routes Blueprint

Handles project status, bid decisions, proposals, estimates, tags, and archiving.
"""

from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request

from utils import (
    get_status_tracker,
    get_all_projects,
    debounced_refresh
)

status_bp = Blueprint('status', __name__)

# Validation sets
VALID_DECISIONS = {'bid', 'no_bid', 'pending', 'gc_awarded', 'awarded', 'lost', None, ''}
VALID_CONFIDENCE = {'low', 'medium', 'high', None, ''}


# =============================================================================
# STATUS CRUD ENDPOINTS
# =============================================================================

@status_bp.route('/api/status/<project_id>')
def api_get_status(project_id):
    """Get internal status for a project"""
    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id)
    if not status:
        return jsonify({"error": "No status found", "project_id": project_id}), 404
    return jsonify(status)


@status_bp.route('/api/status/<project_id>', methods=['POST'])
def api_update_status(project_id):
    """Update status for a project"""
    status_tracker = get_status_tracker()
    data = request.json

    status = status_tracker.get_status(project_id)
    if not status:
        status = status_tracker.create_project_status(project_id, data.get('project_title'))

    status_tracker.set_status(project_id, data)
    debounced_refresh.trigger()

    return jsonify({"status": "ok", "project_id": project_id})


# =============================================================================
# DECISION ENDPOINT
# =============================================================================

@status_bp.route('/api/status/<project_id>/decision', methods=['POST'])
def api_update_decision(project_id):
    """Update bid decision"""
    status_tracker = get_status_tracker()
    data = request.json or {}
    decision = data.get('decision')
    reason = data.get('reason')

    if decision not in VALID_DECISIONS:
        return jsonify({"error": "Invalid decision value. Must be one of: bid, no_bid, pending, gc_awarded, awarded, lost"}), 400

    status_tracker.update_bid_decision(project_id, decision, reason)
    debounced_refresh.trigger()

    return jsonify({"status": "ok", "decision": decision})


# =============================================================================
# PROPOSAL ENDPOINT
# =============================================================================

@status_bp.route('/api/status/<project_id>/proposal', methods=['POST'])
def api_update_proposal(project_id):
    """Update proposal status"""
    status_tracker = get_status_tracker()
    data = request.json
    status_tracker.update_proposal(
        project_id,
        generated=data.get('generated'),
        submitted=data.get('submitted'),
        notes=data.get('notes')
    )
    debounced_refresh.trigger()
    return jsonify({"status": "ok"})


# =============================================================================
# ESTIMATE ENDPOINT
# =============================================================================

@status_bp.route('/api/status/<project_id>/estimate', methods=['POST'])
def api_update_estimate(project_id):
    """Update estimate data"""
    status_tracker = get_status_tracker()
    data = request.json or {}

    confidence = data.get('confidence')
    if confidence not in VALID_CONFIDENCE:
        return jsonify({"error": "Invalid confidence value. Must be one of: low, medium, high"}), 400

    total = data.get('total')
    if total is not None:
        try:
            total = float(total)
            if total < 0:
                return jsonify({"error": "Estimate total must be a positive number"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Estimate total must be a valid number"}), 400

    status_tracker.update_estimate(
        project_id,
        total=total,
        breakdown=data.get('breakdown'),
        notes=data.get('notes'),
        confidence=confidence
    )
    debounced_refresh.trigger()
    return jsonify({"status": "ok"})


# =============================================================================
# NOTES ENDPOINT
# =============================================================================

@status_bp.route('/api/status/<project_id>/note', methods=['POST'])
def api_add_note(project_id):
    """Add a note to project"""
    status_tracker = get_status_tracker()
    data = request.json
    status_tracker.add_note(project_id, data.get('note'), data.get('author'))
    debounced_refresh.trigger()
    return jsonify({"status": "ok"})


# =============================================================================
# TAG ENDPOINTS
# =============================================================================

@status_bp.route('/api/status/<project_id>/tag', methods=['POST'])
def api_add_tag(project_id):
    """Add a tag to project"""
    status_tracker = get_status_tracker()
    data = request.json
    status_tracker.add_tag(project_id, data.get('tag'))
    debounced_refresh.trigger()
    return jsonify({"status": "ok"})


@status_bp.route('/api/status/<project_id>/tag', methods=['DELETE'])
def api_remove_tag(project_id):
    """Remove a tag from project"""
    status_tracker = get_status_tracker()
    data = request.json
    status_tracker.remove_tag(project_id, data.get('tag'))
    debounced_refresh.trigger()
    return jsonify({"status": "ok"})


# =============================================================================
# ARCHIVE ENDPOINTS
# =============================================================================

@status_bp.route('/api/status/<project_id>/archive', methods=['POST'])
def api_archive_project(project_id):
    """Archive a project"""
    status_tracker = get_status_tracker()
    data = request.json or {}
    reason = data.get('reason', 'manual')
    status_tracker.archive_project(project_id, reason)
    debounced_refresh.trigger()
    return jsonify({"status": "ok", "archived": True})


@status_bp.route('/api/status/<project_id>/unarchive', methods=['POST'])
def api_unarchive_project(project_id):
    """Unarchive a project"""
    status_tracker = get_status_tracker()
    status_tracker.unarchive_project(project_id)
    debounced_refresh.trigger()
    return jsonify({"status": "ok", "archived": False})


@status_bp.route('/api/archive/auto', methods=['POST'])
def api_auto_archive():
    """Auto-archive projects with past bid dates"""
    status_tracker = get_status_tracker()

    days_threshold = request.json.get('days', 30) if request.json else 30
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    archived_count = 0
    archived_projects = []

    all_projects = get_all_projects()

    for project in all_projects:
        project_id = project.get('project_code') or project.get('id')
        if not project_id:
            continue

        if status_tracker.is_archived(project_id):
            continue

        bid_date_str = project.get('bid_date') or project.get('bid', {}).get('due_date')
        if not bid_date_str:
            continue

        try:
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']:
                try:
                    bid_date = datetime.strptime(bid_date_str[:10], '%Y-%m-%d')
                    break
                except:
                    continue
            else:
                continue

            if bid_date < cutoff_date:
                status_tracker.archive_project(project_id, 'past_bid_date')
                archived_count += 1
                archived_projects.append({
                    'id': project_id,
                    'title': project.get('title', project_id),
                    'bid_date': bid_date_str
                })
        except Exception as e:
            print(f"Error processing {project_id}: {e}")
            continue

    debounced_refresh.trigger()
    return jsonify({
        "status": "ok",
        "archived_count": archived_count,
        "archived_projects": archived_projects[:20]
    })
