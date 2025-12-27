"""
Timeline API Blueprint

Provides endpoints for project timeline/changelog functionality.
Tracks all significant project events chronologically.
"""

from flask import Blueprint, jsonify, request
from utils import get_status_tracker, find_project_by_id

timeline_bp = Blueprint('timeline', __name__)


@timeline_bp.route('/api/project/<project_id>/timeline', methods=['GET'])
def get_timeline(project_id: str):
    """
    Get timeline events for a project with smart grouping.

    Query params:
        limit: Maximum events to return (default 50)
        event_type: Filter by event type (optional)
        start_date: Filter events after this date (ISO format)
        end_date: Filter events before this date (ISO format)
        grouped: Whether to group events by time period (default: false)
        prioritize: Whether to prioritize major events (default: false)
        collapse_minor: Whether to collapse sequential minor events (default: false)

    Returns:
        {
            "project_id": "...",
            "events": [...],
            "total": 42,
            "grouped": {...}  # If grouped=true
        }
    """
    from datetime import datetime, timedelta

    # Verify project exists
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    status_tracker = get_status_tracker()

    # Get query params
    limit = request.args.get('limit', 50, type=int)
    event_type = request.args.get('event_type')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    include_email_status = request.args.get('include_email_status', 'false').lower() == 'true'
    grouped = request.args.get('grouped', 'false').lower() == 'true'
    prioritize = request.args.get('prioritize', 'false').lower() == 'true'
    collapse_minor = request.args.get('collapse_minor', 'false').lower() == 'true'

    # Get timeline with filters
    if start_date or end_date:
        events = status_tracker.get_timeline_by_date_range(
            project_id,
            start_date=start_date,
            end_date=end_date
        )
        if event_type:
            events = [e for e in events if e.get('event_type') == event_type]
    else:
        events = status_tracker.get_timeline(project_id, limit=limit*2, event_type=event_type)  # Get more for processing

    # Filter out email_status_changed events unless explicitly requested
    if not include_email_status and not event_type:
        events = [e for e in events if e.get('event_type') != 'email_status_changed']

    # Prioritize major events if requested
    if prioritize:
        events = _prioritize_events(events)

    # Collapse sequential minor events if requested
    if collapse_minor:
        events = _collapse_minor_events(events)

    # Apply limit after processing
    events = events[:limit]

    # Group by time period if requested
    result = {
        'project_id': project_id,
        'events': events,
        'total': len(events)
    }

    if grouped:
        result['grouped'] = _group_events_by_time(events)

    return jsonify(result)


def _prioritize_events(events: list) -> list:
    """
    Prioritize major events over minor events.

    Major events: status changes, bid dates, pipeline completion, quotes
    Minor events: file scans, minor scope changes
    """
    major_event_types = {
        'status_changed', 'bid_date_changed', 'pipeline_complete',
        'quote_received', 'estimate_updated', 'addendum_received',
        'project_created', 'awarded', 'lost'
    }

    minor_event_types = {
        'file_added', 'file_scanned', 'document_classified',
        'thumbnail_generated', 'email_status_changed'
    }

    # Separate major and minor
    major_events = []
    minor_events = []

    for event in events:
        event_type = event.get('event_type', '')
        if event_type in major_event_types:
            major_events.append(event)
        elif event_type in minor_event_types:
            minor_events.append(event)
        else:
            # Unknown event types treated as medium priority
            major_events.append(event)

    # Return major events first, then minor
    return major_events + minor_events


def _collapse_minor_events(events: list) -> list:
    """
    Collapse sequential minor events of the same type into summary events.

    For example, "Scanned file1.pdf", "Scanned file2.pdf", ... becomes
    "Scanned 15 files"
    """
    collapsible_types = {'file_added', 'file_scanned', 'document_classified', 'thumbnail_generated'}

    collapsed = []
    i = 0

    while i < len(events):
        event = events[i]
        event_type = event.get('event_type', '')

        if event_type in collapsible_types:
            # Look ahead for more of the same type
            count = 1
            j = i + 1
            while j < len(events) and events[j].get('event_type') == event_type:
                count += 1
                j += 1

            if count > 1:
                # Create collapsed summary event
                collapsed_event = event.copy()
                collapsed_event['title'] = f"{event_type.replace('_', ' ').title()} (×{count})"
                collapsed_event['collapsed'] = True
                collapsed_event['collapsed_count'] = count
                collapsed_event['original_events'] = events[i:j]
                collapsed.append(collapsed_event)
                i = j
            else:
                collapsed.append(event)
                i += 1
        else:
            collapsed.append(event)
            i += 1

    return collapsed


def _group_events_by_time(events: list) -> dict:
    """
    Group events by time periods: Today, This Week, Earlier.

    Returns:
        {
            "today": [...],
            "this_week": [...],
            "earlier": [...]
        }
    """
    from datetime import datetime, timedelta

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())

    grouped = {
        'today': [],
        'this_week': [],
        'earlier': []
    }

    for event in events:
        timestamp = event.get('timestamp')
        if not timestamp:
            grouped['earlier'].append(event)
            continue

        try:
            event_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

            if event_time >= today_start:
                grouped['today'].append(event)
            elif event_time >= week_start:
                grouped['this_week'].append(event)
            else:
                grouped['earlier'].append(event)
        except (ValueError, AttributeError):
            grouped['earlier'].append(event)

    # Add counts
    grouped['today_count'] = len(grouped['today'])
    grouped['this_week_count'] = len(grouped['this_week'])
    grouped['earlier_count'] = len(grouped['earlier'])

    return grouped


@timeline_bp.route('/api/project/<project_id>/timeline/event', methods=['POST'])
def add_timeline_event(project_id: str):
    """
    Add a timeline event to a project.

    Request body:
        {
            "event_type": "note_added",
            "title": "Note added",
            "description": "Called architect about window sizes",
            "source": "user",
            "tags": ["note"]
        }

    Returns:
        The created event
    """
    # Verify project exists
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    data = request.json or {}

    # Validate required fields
    if not data.get('event_type'):
        return jsonify({'error': 'event_type is required'}), 400
    if not data.get('title'):
        return jsonify({'error': 'title is required'}), 400

    status_tracker = get_status_tracker()

    event = status_tracker.add_timeline_event(
        project_id=project_id,
        event_type=data.get('event_type'),
        title=data.get('title'),
        description=data.get('description'),
        actor=data.get('actor', 'user'),
        source=data.get('source'),
        changes=data.get('changes'),
        tags=data.get('tags'),
        related_file=data.get('related_file')
    )

    return jsonify(event), 201


@timeline_bp.route('/api/project/<project_id>/timeline/event-types', methods=['GET'])
def get_event_types(project_id: str):
    """
    Get all event types used in a project's timeline.

    Returns:
        {
            "event_types": ["project_created", "document_added", ...],
            "counts": {"project_created": 1, "document_added": 5, ...}
        }
    """
    status_tracker = get_status_tracker()
    timeline = status_tracker.get_timeline(project_id, limit=1000)

    event_types = {}
    for event in timeline:
        et = event.get('event_type', 'unknown')
        event_types[et] = event_types.get(et, 0) + 1

    return jsonify({
        'event_types': list(event_types.keys()),
        'counts': event_types
    })


# =============================================================================
# EVENT TYPE DEFINITIONS
# =============================================================================

EVENT_TYPE_METADATA = {
    'project_created': {
        'icon': '🆕',
        'color': 'green',
        'label': 'Project Created'
    },
    'document_added': {
        'icon': '📄',
        'color': 'blue',
        'label': 'Document Added'
    },
    'addendum_received': {
        'icon': '📋',
        'color': 'orange',
        'label': 'Addendum Received'
    },
    'scope_updated': {
        'icon': '🔧',
        'color': 'purple',
        'label': 'Scope Updated'
    },
    'count_added': {
        'icon': '🔢',
        'color': 'teal',
        'label': 'Count Added'
    },
    'bid_date_changed': {
        'icon': '📅',
        'color': 'yellow',
        'label': 'Bid Date Changed'
    },
    'quote_received': {
        'icon': '💰',
        'color': 'green',
        'label': 'Quote Received'
    },
    'status_changed': {
        'icon': '🔄',
        'color': 'blue',
        'label': 'Status Changed'
    },
    'note_added': {
        'icon': '📝',
        'color': 'gray',
        'label': 'Note Added'
    },
    'pipeline_complete': {
        'icon': '✅',
        'color': 'green',
        'label': 'Analysis Complete'
    },
    'estimate_updated': {
        'icon': '💵',
        'color': 'green',
        'label': 'Estimate Updated'
    }
}


@timeline_bp.route('/api/timeline/event-type-metadata', methods=['GET'])
def get_event_type_metadata():
    """Get metadata for all event types (icons, colors, labels)."""
    return jsonify(EVENT_TYPE_METADATA)
