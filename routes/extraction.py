"""
Extraction/AI Analysis Routes Blueprint

Handles Division 8 extraction and AI analysis for construction projects.
Uses RAG (Retrieval Augmented Generation) with multi-agent orchestration.
"""

import threading
import asyncio
from pathlib import Path
from flask import Blueprint, jsonify

from utils import (
    find_project_by_id,
    get_status_tracker,
    debounced_refresh,
    BIDDING_FOLDER
)

# =============================================================================
# EXTRACTION MODULE IMPORTS (Optional Dependencies)
# =============================================================================

try:
    from modules.extraction.extraction_agents import ExtractionOrchestrator
    from modules.extraction.rag_engine import RAGEngine
    from modules.extraction.config import PROJECTS_DIR as EXTRACTION_PROJECTS_DIR
    EXTRACTION_AVAILABLE = True
except ImportError as e:
    print(f"Extraction module not available: {e}")
    EXTRACTION_AVAILABLE = False

# =============================================================================
# BLUEPRINT SETUP
# =============================================================================

extraction_bp = Blueprint('extraction', __name__)

# =============================================================================
# MODULE STATE (Thread-Safe Extraction Tracking)
# =============================================================================

# Extraction state tracking (thread-safe)
_extraction_status = {}  # project_id -> {status, progress, result, error}
_extraction_lock = threading.Lock()
_rag_engine = None


def get_rag_engine():
    """Get or create RAG engine (lazy init)"""
    global _rag_engine
    if _rag_engine is None and EXTRACTION_AVAILABLE:
        _rag_engine = RAGEngine()
    return _rag_engine


# =============================================================================
# EXTRACTION ROUTES
# =============================================================================

@extraction_bp.route('/api/extract/<project_id>', methods=['POST'])
def api_extract_project(project_id):
    """Trigger Division 8 extraction for a project"""
    if not EXTRACTION_AVAILABLE:
        return jsonify({
            "error": "Extraction module not available. Install dependencies: chromadb, pypdf, pandas"
        }), 503

    # Find project
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Get project folder path
    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder path for extraction"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Check if already extracting (thread-safe)
    with _extraction_lock:
        if project_id in _extraction_status and _extraction_status[project_id].get('status') == 'running':
            return jsonify({
                "error": "Extraction already in progress",
                "status": _extraction_status[project_id]
            }), 409

    # Start extraction in background thread
    def run_extraction():
        with _extraction_lock:
            _extraction_status[project_id] = {'status': 'running', 'progress': 0, 'messages': []}

        def stream_callback(msg):
            with _extraction_lock:
                _extraction_status[project_id]['messages'].append({
                    'agent': msg.agent,
                    'message': msg.message,
                    'progress': msg.progress
                })
                _extraction_status[project_id]['progress'] = msg.progress

        try:
            rag = get_rag_engine()
            orchestrator = ExtractionOrchestrator(rag, stream_callback)

            # Run async extraction
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(orchestrator.extract_project(project_path))
            loop.close()

            # Store result (thread-safe)
            with _extraction_lock:
                _extraction_status[project_id] = {
                    'status': 'complete',
                    'progress': 1.0,
                    'result': result
                }

            # Save extracted data to project status
            status_tracker = get_status_tracker()
            status_tracker.set_extracted_data(project_id, result)
            debounced_refresh.trigger()

        except Exception as e:
            with _extraction_lock:
                _extraction_status[project_id] = {
                    'status': 'error',
                    'error': str(e)
                }

    thread = threading.Thread(target=run_extraction)
    thread.start()

    return jsonify({
        "status": "started",
        "project_id": project_id,
        "message": "Extraction started in background"
    })


@extraction_bp.route('/api/extract/<project_id>/status')
def api_extraction_status(project_id):
    """Get extraction status for a project (thread-safe)"""
    with _extraction_lock:
        if project_id not in _extraction_status:
            return jsonify({"status": "not_started", "project_id": project_id})
        return jsonify(dict(_extraction_status[project_id]))


@extraction_bp.route('/api/extract/<project_id>/result')
def api_extraction_result(project_id):
    """Get extraction result for a project (thread-safe)"""
    with _extraction_lock:
        if project_id not in _extraction_status:
            return jsonify({"error": "No extraction found"}), 404

        status = _extraction_status[project_id]
        if status.get('status') != 'complete':
            return jsonify({
                "error": "Extraction not complete",
                "status": status.get('status')
            }), 400

        return jsonify(status.get('result', {}))


@extraction_bp.route('/api/extraction/available')
def api_extraction_available():
    """Check if extraction module is available"""
    return jsonify({
        "available": EXTRACTION_AVAILABLE,
        "model": "amazon/nova-lite-v1" if EXTRACTION_AVAILABLE else None,
        "limits": {
            "requests_per_minute": 10,
            "requests_per_day": 1000
        } if EXTRACTION_AVAILABLE else None
    })
