"""
Sync API - Background synchronization control.

Endpoints:
- GET /sync/status - Current sync status
- POST /sync/trigger - Trigger immediate sync
- GET /sync/history - Sync history log
- POST /sync/source/:name - Sync specific source
"""

from flask import Blueprint, jsonify, request
from datetime import datetime
import threading

from modules.sync.sync_service import get_sync_service

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')

# Track sync history in memory (would be in DB for production)
_sync_history = []


@sync_bp.route('/status', methods=['GET'])
def get_status():
    """Get current sync status."""
    service = get_sync_service()
    status = service.get_status()

    return jsonify({
        'in_progress': status['in_progress'],
        'last_sync': status['last_sync'],
        'recent_errors': status['errors']
    })


@sync_bp.route('/trigger', methods=['POST'])
def trigger_sync():
    """
    Trigger immediate sync of all sources.

    Query params:
    - async: If true, run in background (default false)
    - source: Optional specific source to sync
    """
    async_mode = request.args.get('async', 'false').lower() == 'true'
    source = request.args.get('source')

    service = get_sync_service()

    if async_mode:
        # Run in background thread
        thread = threading.Thread(
            target=_run_sync_and_log,
            args=(service, source),
            daemon=True
        )
        thread.start()

        return jsonify({
            'status': 'started',
            'message': 'Sync started in background',
            'source': source or 'all'
        })
    else:
        # Run synchronously
        result = service.trigger_sync(source)
        _log_sync_result(result, source)

        return jsonify(result)


@sync_bp.route('/source/<source_name>', methods=['POST'])
def sync_source(source_name):
    """
    Sync a specific source.

    Valid sources: bidding, brad, current, planhub, govwin, email
    """
    valid_sources = ['bidding', 'brad', 'current', 'planhub', 'govwin', 'email']

    if source_name not in valid_sources:
        return jsonify({
            'error': f'Invalid source. Must be one of: {", ".join(valid_sources)}'
        }), 400

    service = get_sync_service()
    result = service.trigger_sync(source_name)
    _log_sync_result(result, source_name)

    return jsonify(result)


@sync_bp.route('/history', methods=['GET'])
def get_history():
    """
    Get sync history.

    Query params:
    - limit: Max results (default 20)
    """
    limit = request.args.get('limit', 20, type=int)

    # Return most recent first
    history = _sync_history[-limit:][::-1]

    return jsonify({
        'count': len(history),
        'history': history
    })


@sync_bp.route('/schedule', methods=['GET'])
def get_schedule():
    """Get current sync schedule configuration."""
    import os

    return jsonify({
        'sync_interval_hours': int(os.environ.get('SYNC_INTERVAL_HOURS', 24)),
        'planhub_interval_hours': int(os.environ.get('PLANHUB_SYNC_INTERVAL_HOURS', 24)),
        'auto_sync_enabled': os.environ.get('AUTO_SYNC_ENABLED', 'true').lower() == 'true'
    })


@sync_bp.route('/schedule', methods=['PUT'])
def update_schedule():
    """
    Update sync schedule (runtime only, not persisted).

    Body:
    - sync_interval_hours: Hours between full syncs
    - auto_sync_enabled: Enable/disable auto sync
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': 'No data provided'}), 400

    import os

    if 'sync_interval_hours' in data:
        os.environ['SYNC_INTERVAL_HOURS'] = str(data['sync_interval_hours'])

    if 'auto_sync_enabled' in data:
        os.environ['AUTO_SYNC_ENABLED'] = str(data['auto_sync_enabled']).lower()

    return jsonify({
        'status': 'updated',
        'schedule': {
            'sync_interval_hours': int(os.environ.get('SYNC_INTERVAL_HOURS', 24)),
            'auto_sync_enabled': os.environ.get('AUTO_SYNC_ENABLED', 'true').lower() == 'true'
        }
    })


def _run_sync_and_log(service, source=None):
    """Run sync and log results (for background thread)."""
    try:
        result = service.trigger_sync(source)
        _log_sync_result(result, source)
    except Exception as e:
        _log_sync_result({
            'status': 'error',
            'error': str(e),
            'completed_at': datetime.now().isoformat()
        }, source)


def _log_sync_result(result: dict, source: str = None):
    """Log a sync result to history."""
    global _sync_history

    entry = {
        'timestamp': datetime.now().isoformat(),
        'source': source or 'all',
        'status': result.get('status', 'unknown'),
        'total_projects': result.get('total_projects', 0),
        'new_projects': result.get('new_projects', 0),
        'updated_projects': result.get('updated_projects', 0),
        'errors': len(result.get('errors', []))
    }

    _sync_history.append(entry)

    # Keep only last 100 entries
    if len(_sync_history) > 100:
        _sync_history = _sync_history[-100:]
