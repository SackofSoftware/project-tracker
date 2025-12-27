"""
Server-Sent Events (SSE) Manager Blueprint

Provides real-time event streaming for the Command Center UI.
Replaces polling-based updates with push notifications.

Event Types:
- pipeline_stage: Pipeline progress updates
- card_update: Scope card data refresh
- chat_response: AI Superintendent responses
- activity: General activity log entries
- heartbeat: Keep-alive signal
"""

import json
import queue
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Generator
from dataclasses import dataclass, asdict

from flask import Blueprint, Response, request, jsonify

sse_bp = Blueprint('sse', __name__)


# =============================================================================
# SSE EVENT DATA CLASSES
# =============================================================================

@dataclass
class SSEEvent:
    """Base SSE event structure"""
    event_type: str
    data: dict
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_sse_format(self) -> str:
        """Format as SSE message"""
        payload = {
            **self.data,
            'timestamp': self.timestamp
        }
        return f"event: {self.event_type}\ndata: {json.dumps(payload)}\n\n"


@dataclass
class PipelineStageEvent(SSEEvent):
    """Pipeline stage progress event"""
    def __init__(self, stage: str, status: str, message: str = "", progress: float = None, data: dict = None):
        super().__init__(
            event_type='pipeline_stage',
            data={
                'stage': stage,
                'status': status,  # 'pending', 'running', 'complete', 'error'
                'message': message,
                'progress': progress,
                'stage_data': data or {}
            }
        )


@dataclass
class CardUpdateEvent(SSEEvent):
    """Scope card data update event"""
    def __init__(self, card_id: str, card_data: dict):
        super().__init__(
            event_type='card_update',
            data={
                'card_id': card_id,
                **card_data
            }
        )


@dataclass
class ActivityEvent(SSEEvent):
    """Activity log entry event"""
    def __init__(self, activity_type: str, message: str, detail: str = "",
                 icon: str = "info", progress: float = None):
        super().__init__(
            event_type='activity',
            data={
                'type': activity_type,  # 'file_scan', 'rag_query', 'card_update', 'stage_complete'
                'message': message,
                'detail': detail,
                'icon': icon,  # 'folder', 'search', 'card', 'check', 'error'
                'progress': progress
            }
        )


@dataclass
class ChatResponseEvent(SSEEvent):
    """AI Superintendent chat response event"""
    def __init__(self, response_type: str, content: str, tool_call: dict = None,
                 status: str = "complete"):
        super().__init__(
            event_type='chat_response',
            data={
                'type': response_type,  # 'text', 'tool_call', 'error'
                'content': content,
                'tool_call': tool_call,
                'status': status
            }
        )


# =============================================================================
# SSE MANAGER (THREAD-SAFE)
# =============================================================================

class SSEManager:
    """
    Thread-safe SSE event manager.

    Manages subscriber queues per project and broadcasts events
    to all connected clients.
    """

    def __init__(self, heartbeat_interval: int = 30):
        self._queues: Dict[str, List[queue.Queue]] = {}
        self._lock = threading.Lock()
        self.heartbeat_interval = heartbeat_interval

    def subscribe(self, project_id: str) -> queue.Queue:
        """
        Create new queue for a subscriber.

        Args:
            project_id: Project to subscribe to

        Returns:
            Queue that will receive events for this project
        """
        q = queue.Queue()
        with self._lock:
            if project_id not in self._queues:
                self._queues[project_id] = []
            self._queues[project_id].append(q)
        return q

    def unsubscribe(self, project_id: str, q: queue.Queue):
        """
        Remove subscriber queue.

        Args:
            project_id: Project subscribed to
            q: Queue to remove
        """
        with self._lock:
            if project_id in self._queues:
                try:
                    self._queues[project_id].remove(q)
                except ValueError:
                    pass  # Already removed
                # Clean up empty project entries
                if not self._queues[project_id]:
                    del self._queues[project_id]

    def publish(self, project_id: str, event: SSEEvent):
        """
        Publish event to all subscribers of a project.

        Args:
            project_id: Target project
            event: SSEEvent to publish
        """
        message = event.to_sse_format()
        with self._lock:
            for q in self._queues.get(project_id, []):
                try:
                    q.put_nowait(message)
                except queue.Full:
                    pass  # Drop event if queue is full

    def publish_raw(self, project_id: str, event_type: str, data: dict):
        """
        Publish raw event data (convenience method).

        Args:
            project_id: Target project
            event_type: Event type string
            data: Event data dict
        """
        event = SSEEvent(event_type=event_type, data=data)
        self.publish(project_id, event)

    def get_subscriber_count(self, project_id: str = None) -> int:
        """Get number of active subscribers"""
        with self._lock:
            if project_id:
                return len(self._queues.get(project_id, []))
            return sum(len(qs) for qs in self._queues.values())

    def get_active_projects(self) -> List[str]:
        """Get list of projects with active subscribers"""
        with self._lock:
            return list(self._queues.keys())


# Global SSE manager instance
sse_manager = SSEManager()


def get_sse_manager() -> SSEManager:
    """Get the global SSE manager instance"""
    return sse_manager


# =============================================================================
# SSE STREAMING ENDPOINT
# =============================================================================

@sse_bp.route('/api/project/<project_id>/events')
def stream_events(project_id: str):
    """
    SSE endpoint for real-time project events.

    Clients connect to receive:
    - Pipeline progress updates
    - Scope card data changes
    - AI chat responses
    - Activity log entries

    Includes automatic heartbeat every 30 seconds to keep connection alive.
    """
    def generate() -> Generator[str, None, None]:
        # Subscribe to project events
        q = sse_manager.subscribe(project_id)

        try:
            # Send initial connection event
            yield SSEEvent(
                event_type='connected',
                data={'project_id': project_id, 'message': 'Connected to event stream'}
            ).to_sse_format()

            last_heartbeat = time.time()

            while True:
                try:
                    # Check for new events (non-blocking with timeout)
                    message = q.get(timeout=1.0)
                    yield message
                except queue.Empty:
                    # No events, check if heartbeat needed
                    now = time.time()
                    if now - last_heartbeat >= sse_manager.heartbeat_interval:
                        yield SSEEvent(
                            event_type='heartbeat',
                            data={'status': 'alive'}
                        ).to_sse_format()
                        last_heartbeat = now
        except GeneratorExit:
            # Client disconnected
            pass
        finally:
            # Clean up subscription
            sse_manager.unsubscribe(project_id, q)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',  # Disable nginx buffering
        }
    )


# =============================================================================
# HELPER ENDPOINTS
# =============================================================================

@sse_bp.route('/api/sse/status')
def sse_status():
    """Get SSE manager status"""
    return jsonify({
        'status': 'ok',
        'total_subscribers': sse_manager.get_subscriber_count(),
        'active_projects': sse_manager.get_active_projects()
    })


@sse_bp.route('/api/sse/test/<project_id>', methods=['POST'])
def test_event(project_id: str):
    """Send a test event (for debugging)"""
    data = request.json or {}
    event_type = data.get('event_type', 'activity')
    event_data = data.get('data', {'message': 'Test event'})

    sse_manager.publish_raw(project_id, event_type, event_data)

    return jsonify({
        'status': 'sent',
        'event_type': event_type,
        'subscribers': sse_manager.get_subscriber_count(project_id)
    })


# =============================================================================
# CONVENIENCE FUNCTIONS FOR OTHER MODULES
# =============================================================================

def publish_pipeline_stage(project_id: str, stage: str, status: str,
                           message: str = "", progress: float = None, data: dict = None):
    """
    Publish pipeline stage update.

    Usage:
        from routes.sse import publish_pipeline_stage
        publish_pipeline_stage('project-123', 'ai_analysis', 'running', 'Analyzing schedules...', 0.5)
    """
    event = PipelineStageEvent(stage, status, message, progress, data)
    sse_manager.publish(project_id, event)


def publish_card_update(project_id: str, card_id: str, card_data: dict):
    """
    Publish scope card data update.

    Usage:
        from routes.sse import publish_card_update
        publish_card_update('project-123', 'commercial-windows', {'status': 'specified', ...})
    """
    event = CardUpdateEvent(card_id, card_data)
    sse_manager.publish(project_id, event)


def publish_activity(project_id: str, activity_type: str, message: str,
                     detail: str = "", icon: str = "info", progress: float = None):
    """
    Publish activity log entry.

    Usage:
        from routes.sse import publish_activity
        publish_activity('project-123', 'file_scan', 'Scanning PDFs...', 'Found 42 files', 'folder', 0.1)
    """
    event = ActivityEvent(activity_type, message, detail, icon, progress)
    sse_manager.publish(project_id, event)


def publish_chat_response(project_id: str, response_type: str, content: str,
                          tool_call: dict = None, status: str = "complete"):
    """
    Publish AI chat response.

    Usage:
        from routes.sse import publish_chat_response
        publish_chat_response('project-123', 'text', 'Bid date updated to 12/25/2025')
    """
    event = ChatResponseEvent(response_type, content, tool_call, status)
    sse_manager.publish(project_id, event)
