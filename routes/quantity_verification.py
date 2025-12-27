"""
Quantity Verification Routes Blueprint

Provides API endpoints for the quantity verification workflow:
1. Learn patterns from schedule PDFs
2. Confirm/edit detected patterns
3. Scan floor plans + elevations
4. Get results and highlighted PDFs

Workflow:
POST /api/project/<id>/qty/learn-patterns   - AI detects patterns from schedules
POST /api/project/<id>/qty/scan             - Scan with confirmed patterns
GET  /api/project/<id>/qty/results          - Get results + highlighted PDF paths
"""

import os
import threading
import asyncio
from pathlib import Path
from flask import Blueprint, jsonify, request, render_template

from utils import (
    find_project_by_id,
    BIDDING_FOLDER
)

# =============================================================================
# MODULE IMPORTS
# =============================================================================

try:
    from modules.quantity_verification import (
        PatternLearner,
        TagPattern,
        DrawingScanner,
        QuantityHighlighter
    )
    from modules.pipeline import AIProviderManager
    VERIFICATION_AVAILABLE = True
except ImportError as e:
    print(f"Quantity verification module not available: {e}")
    VERIFICATION_AVAILABLE = False

# =============================================================================
# BLUEPRINT SETUP
# =============================================================================

qty_verification_bp = Blueprint('quantity_verification', __name__)

# Module state
_verification_status = {}  # project_id -> status
_verification_lock = threading.Lock()

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')


# =============================================================================
# PAGE ROUTES
# =============================================================================

@qty_verification_bp.route('/project/<project_id>/quantity-verification')
def quantity_verification_page(project_id):
    """Render the quantity verification page"""
    project = find_project_by_id(project_id)
    if not project:
        return render_template('error.html', error="Project not found"), 404

    return render_template(
        'quantity_verification.html',
        project_id=project_id,
        project=project
    )


# =============================================================================
# API ROUTES
# =============================================================================

@qty_verification_bp.route('/api/project/<project_id>/qty/learn-patterns', methods=['POST'])
def api_learn_patterns(project_id):
    """
    Learn tag patterns from schedule documents.

    Uses AI to analyze door/window schedules and detect the tagging
    convention used in this project (A, W1, WIN-A, Type 1, etc.)

    Returns detected patterns for user confirmation before scanning.
    """
    if not VERIFICATION_AVAILABLE:
        return jsonify({
            "error": "Quantity verification module not available"
        }), 503

    # Find project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder path"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Run pattern learning
    def learn_patterns():
        with _verification_lock:
            _verification_status[project_id] = {
                'status': 'learning',
                'step': 'pattern_learning',
                'patterns': None
            }

        try:
            # Initialize AI provider
            ai = AIProviderManager()

            # Initialize pattern learner
            learner = PatternLearner(ai)

            # Run async learning
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(learner.learn_patterns(project_path))
            loop.close()

            if result.success:
                # Convert patterns to JSON-serializable format
                patterns_data = {
                    'door_patterns': [
                        {
                            'pattern_id': p.pattern_id,
                            'category': p.category,
                            'examples': p.examples,
                            'regex': p.regex,
                            'source_file': p.source_file,
                            'confidence': p.confidence,
                            'quantity': p.quantity
                        }
                        for p in result.door_patterns
                    ],
                    'window_patterns': [
                        {
                            'pattern_id': p.pattern_id,
                            'category': p.category,
                            'examples': p.examples,
                            'regex': p.regex,
                            'source_file': p.source_file,
                            'confidence': p.confidence,
                            'quantity': p.quantity
                        }
                        for p in result.window_patterns
                    ],
                    'hardware_patterns': [
                        {
                            'pattern_id': p.pattern_id,
                            'category': p.category,
                            'examples': p.examples,
                            'regex': p.regex,
                            'source_file': p.source_file,
                            'confidence': p.confidence,
                            'quantity': p.quantity
                        }
                        for p in result.hardware_patterns
                    ]
                }

                with _verification_lock:
                    _verification_status[project_id] = {
                        'status': 'patterns_detected',
                        'step': 'awaiting_confirmation',
                        'patterns': patterns_data
                    }
            else:
                with _verification_lock:
                    _verification_status[project_id] = {
                        'status': 'error',
                        'error': result.error or "Pattern learning failed"
                    }

        except Exception as e:
            with _verification_lock:
                _verification_status[project_id] = {
                    'status': 'error',
                    'error': str(e)
                }

    thread = threading.Thread(target=learn_patterns)
    thread.start()

    return jsonify({
        "status": "started",
        "project_id": project_id,
        "message": "Pattern learning started"
    })


@qty_verification_bp.route('/api/project/<project_id>/qty/patterns')
def api_get_patterns(project_id):
    """Get detected patterns for a project (for UI to display)"""
    with _verification_lock:
        if project_id not in _verification_status:
            return jsonify({
                "status": "not_started",
                "message": "Pattern learning has not been run"
            })

        status = _verification_status[project_id]
        return jsonify(status)


@qty_verification_bp.route('/api/project/<project_id>/qty/scan', methods=['POST'])
def api_scan_drawings(project_id):
    """
    Scan floor plans and elevations with confirmed patterns.

    Request body:
    {
        "patterns": {
            "door_patterns": [...],
            "window_patterns": [...]
        },
        "shape_type": "hexagon",  // or "circle", "square"
        "include_floor_plans": true,
        "include_elevations": true
    }
    """
    if not VERIFICATION_AVAILABLE:
        return jsonify({
            "error": "Quantity verification module not available"
        }), 503

    # Find project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder path"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Get confirmed patterns from request
    data = request.get_json() or {}
    patterns_data = data.get('patterns', {})
    shape_type = data.get('shape_type', 'hexagon')

    # If no patterns provided, try to get from previous learning
    if not patterns_data:
        with _verification_lock:
            if project_id in _verification_status:
                patterns_data = _verification_status[project_id].get('patterns', {})

    if not patterns_data:
        return jsonify({
            "error": "No patterns provided. Run pattern learning first or provide patterns."
        }), 400

    # Convert to TagPattern objects
    all_patterns = []
    for category in ['door_patterns', 'window_patterns', 'hardware_patterns']:
        for p in patterns_data.get(category, []):
            all_patterns.append(TagPattern(
                pattern_id=p.get('pattern_id', ''),
                category=p.get('category', ''),
                examples=p.get('examples', []),
                regex=p.get('regex', ''),
                source_file=p.get('source_file', ''),
                confidence=p.get('confidence', 0.5),
                quantity=p.get('quantity', 0)
            ))

    # Run scanning in background
    def run_scan():
        with _verification_lock:
            _verification_status[project_id] = {
                'status': 'scanning',
                'step': 'scanning_drawings',
                'patterns': patterns_data
            }

        try:
            # Initialize scanner
            scanner = DrawingScanner(patterns=all_patterns, shape_type=shape_type)

            # Scan project
            result = scanner.scan_project(project_path)

            if result.success:
                # Highlight results
                highlighter = QuantityHighlighter(
                    output_folder=project_path / 'Verification-Highlights',
                    style='circle',
                    show_summary=True
                )

                highlight_results = highlighter.highlight_scan_results(
                    result.by_sheet,
                    project_path
                )

                # Create comparison report
                report_path = highlighter.create_comparison_report(
                    result.comparison,
                    project_path
                )

                with _verification_lock:
                    _verification_status[project_id] = {
                        'status': 'complete',
                        'step': 'complete',
                        'patterns': patterns_data,
                        'results': {
                            'total_sheets_scanned': result.total_sheets_scanned,
                            'total_tags_found': result.total_tags_found,
                            'by_tag': result.by_tag,
                            'comparison': result.comparison,
                            'highlighted_files': [r.output_file for r in highlight_results if r.success],
                            'report_path': str(report_path)
                        }
                    }
            else:
                with _verification_lock:
                    _verification_status[project_id] = {
                        'status': 'error',
                        'error': result.error or "Scanning failed"
                    }

        except Exception as e:
            with _verification_lock:
                _verification_status[project_id] = {
                    'status': 'error',
                    'error': str(e)
                }

    thread = threading.Thread(target=run_scan)
    thread.start()

    return jsonify({
        "status": "started",
        "project_id": project_id,
        "message": "Drawing scan started"
    })


@qty_verification_bp.route('/api/project/<project_id>/qty/results')
def api_get_results(project_id):
    """
    Get verification results including comparison and highlighted PDF paths.
    """
    with _verification_lock:
        if project_id not in _verification_status:
            return jsonify({
                "status": "not_started",
                "message": "Verification has not been run for this project"
            })

        status = _verification_status[project_id]

        if status.get('status') != 'complete':
            return jsonify(status)

        return jsonify({
            "status": "complete",
            "project_id": project_id,
            "results": status.get('results', {})
        })


@qty_verification_bp.route('/api/project/<project_id>/qty/status')
def api_verification_status(project_id):
    """Get current verification status for a project"""
    with _verification_lock:
        if project_id not in _verification_status:
            return jsonify({
                "status": "not_started",
                "project_id": project_id
            })

        return jsonify(dict(_verification_status[project_id], project_id=project_id))


@qty_verification_bp.route('/api/qty/available')
def api_verification_available():
    """Check if quantity verification module is available"""
    return jsonify({
        "available": VERIFICATION_AVAILABLE,
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "features": {
            "pattern_learning": VERIFICATION_AVAILABLE,
            "drawing_scanning": VERIFICATION_AVAILABLE,
            "pdf_highlighting": VERIFICATION_AVAILABLE
        }
    })
