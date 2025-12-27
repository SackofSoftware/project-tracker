"""
Pipeline Routes Blueprint

Handles the Master Analysis Pipeline for construction projects.
Provides endpoints for running the full pipeline, individual stages,
and status polling for UI progress updates.
"""

import os
import threading
import asyncio
from pathlib import Path
from flask import Blueprint, jsonify, request, render_template

from utils import (
    find_project_by_id,
    get_status_tracker,
    debounced_refresh,
    BIDDING_FOLDER
)

# SSE integration for real-time updates
try:
    from routes.sse import publish_pipeline_stage, publish_activity, publish_card_update
    SSE_AVAILABLE = True
except ImportError:
    SSE_AVAILABLE = False
    def publish_pipeline_stage(*args, **kwargs): pass
    def publish_activity(*args, **kwargs): pass
    def publish_card_update(*args, **kwargs): pass

# =============================================================================
# PIPELINE MODULE IMPORTS
# =============================================================================

try:
    from modules.pipeline import MasterPipeline, AIProviderManager
    PIPELINE_AVAILABLE = True
except ImportError as e:
    print(f"Pipeline module not available: {e}")
    PIPELINE_AVAILABLE = False

# =============================================================================
# BLUEPRINT SETUP
# =============================================================================

pipeline_bp = Blueprint('pipeline', __name__)

# =============================================================================
# MODULE STATE (Thread-Safe Pipeline Tracking)
# =============================================================================

# Pipeline state tracking (thread-safe)
_pipeline_status = {}  # project_id -> {status, current_stage, progress, stages, error}
_pipeline_lock = threading.Lock()

# API Keys from environment
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')


# =============================================================================
# PIPELINE PAGE ROUTE
# =============================================================================

@pipeline_bp.route('/pipeline')
def pipeline_page():
    """Render the batch pipeline analysis page"""
    return render_template('pipeline.html')


# =============================================================================
# UNIFIED ANALYSIS ENDPOINT (RECOMMENDED)
# =============================================================================

@pipeline_bp.route('/api/project/<project_id>/analyze', methods=['POST'])
def api_analyze_project(project_id):
    """
    Run the unified 4-stage analysis pipeline for a project.

    This is the RECOMMENDED single entry point for project analysis.
    Replaces multiple separate buttons with one unified pipeline.

    Stages:
    1. ID & Split - Identify and split spec book + drawing set
    2. Organize - Move files to proper folders
    3. RAG Build - Build vector index from Division 8 specs
    4. AI Query - DeepSeek V3.2 scope extraction

    Request body (optional):
    {
        "mode": "manual",       // 'manual' or 'auto'
        "stop_on_error": false  // Whether to stop on first error
    }

    Returns:
        JSON with status and progress info
    """
    if not PIPELINE_AVAILABLE:
        return jsonify({
            "error": "Pipeline module not available. Check module dependencies."
        }), 503

    # Find project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Get project folder path
    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder path"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Check if already running (thread-safe)
    with _pipeline_lock:
        if project_id in _pipeline_status and _pipeline_status[project_id].get('status') == 'running':
            return jsonify({
                "error": "Analysis already in progress",
                "status": _pipeline_status[project_id]
            }), 409

    # Get options from request
    data = request.get_json() or {}
    mode = data.get('mode', 'manual')
    stop_on_error = data.get('stop_on_error', False)

    # Unified stage info for progress tracking
    unified_stages = [
        ('id_split', 'ID & Split'),
        ('organize', 'Organize Files'),
        ('rag_build', 'Build RAG Index'),
        ('ai_query', 'AI Query (DeepSeek V3.2)')
    ]
    total_stages = len(unified_stages)

    # Start unified pipeline in background thread
    def run_unified_pipeline():
        with _pipeline_lock:
            _pipeline_status[project_id] = {
                'status': 'running',
                'pipeline_type': 'unified',
                'current_stage': None,
                'current_stage_index': 0,
                'total_stages': total_stages,
                'progress': 0,
                'stages': {},
                'messages': []
            }

        try:
            # Create pipeline instance
            pipeline = MasterPipeline(
                project_folder=project_path,
                openai_key=OPENAI_API_KEY,
                openrouter_key=OPENROUTER_API_KEY
            )

            # Progress callback with SSE integration
            def progress_callback(stage_name, stage_status, message=None):
                with _pipeline_lock:
                    _pipeline_status[project_id]['current_stage'] = stage_name
                    _pipeline_status[project_id]['stages'][stage_name] = stage_status

                    if message:
                        _pipeline_status[project_id]['messages'].append({
                            'stage': stage_name,
                            'message': message
                        })

                    # Calculate overall progress based on unified stages
                    completed = sum(1 for s in _pipeline_status[project_id]['stages'].values()
                                    if s.get('completed'))
                    progress = completed / total_stages
                    _pipeline_status[project_id]['progress'] = progress

                    # Update stage index
                    stage_idx = next((i for i, (name, _) in enumerate(unified_stages) if name == stage_name), 0)
                    _pipeline_status[project_id]['current_stage_index'] = stage_idx

                # Publish SSE event for real-time UI updates
                status = 'complete' if stage_status.get('completed') else 'running'
                if stage_status.get('error'):
                    status = 'error'

                # Get stage display name
                stage_display = next((name for sn, name in unified_stages if sn == stage_name), stage_name)

                publish_pipeline_stage(
                    project_id,
                    stage_name,
                    status,
                    message or f'Processing {stage_display}...',
                    progress,
                    stage_status.get('data')
                )

            pipeline.set_progress_callback(progress_callback)

            # Run unified pipeline
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                pipeline.run_unified_pipeline(mode=mode, stop_on_error=stop_on_error)
            )
            loop.close()

            # Store result (thread-safe)
            with _pipeline_lock:
                _pipeline_status[project_id] = {
                    'status': 'complete',
                    'pipeline_type': 'unified',
                    'progress': 1.0,
                    'total_stages': total_stages,
                    'stages': result.get('stages', {}),
                    'result': result
                }

            # Publish completion SSE event
            publish_activity(
                project_id,
                'stage_complete',
                'Analysis complete!',
                f'All {total_stages} stages finished successfully',
                'check',
                1.0
            )

            # Refresh project data
            debounced_refresh.trigger()

        except Exception as e:
            with _pipeline_lock:
                _pipeline_status[project_id] = {
                    'status': 'error',
                    'pipeline_type': 'unified',
                    'error': str(e),
                    'stages': _pipeline_status.get(project_id, {}).get('stages', {})
                }

            # Publish error SSE event
            publish_activity(
                project_id,
                'error',
                'Analysis failed',
                str(e),
                'error',
                None
            )

    thread = threading.Thread(target=run_unified_pipeline)
    thread.start()

    return jsonify({
        "status": "started",
        "pipeline_type": "unified",
        "project_id": project_id,
        "total_stages": total_stages,
        "stages": [{"name": name, "display": display} for name, display in unified_stages],
        "message": "Unified analysis pipeline started"
    })


@pipeline_bp.route('/api/project/<project_id>/analyze/status')
def api_analyze_status(project_id):
    """
    Get unified analysis status for a project.

    Returns current progress, stage status, and results if complete.
    """
    with _pipeline_lock:
        if project_id not in _pipeline_status:
            # Check if there's stored results
            project = find_project_by_id(project_id)
            if project:
                project_folder = project.get('folder_path') or project.get('folder')
                if project_folder:
                    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)
                    status_tracker = get_status_tracker()
                    pipeline_status = status_tracker.get_pipeline_status(str(project_path))
                    if pipeline_status:
                        return jsonify({
                            "status": "complete" if pipeline_status.get('overall_complete') else "incomplete",
                            "project_id": project_id,
                            "pipeline": pipeline_status
                        })

            return jsonify({
                "status": "not_started",
                "project_id": project_id,
                "message": "Analysis has not been run for this project"
            })

        status_data = dict(_pipeline_status[project_id])
        status_data['project_id'] = project_id

        return jsonify(status_data)


# =============================================================================
# LEGACY PIPELINE API ROUTES
# =============================================================================

@pipeline_bp.route('/api/project/<project_id>/pipeline/run', methods=['POST'])
def api_run_pipeline(project_id):
    """
    Start full analysis pipeline for a project.

    Runs all 8 stages:
    1. Rename - Extract project name from cover sheet
    2. Organize - Move files into structured folders
    3. Split Specs - Split spec book by CSI section
    4. Split Drawings - Split drawing set by page
    5. AI Analysis - Analyze schedules with GPT-5 nano + DeepSeek
    6. Schedule Parse - Parse AI results into structured JSON
    7. Highlight - Highlight floor plans + exterior elevations
    8. Quote Analysis - Identify and parse vendor quotes
    """
    if not PIPELINE_AVAILABLE:
        return jsonify({
            "error": "Pipeline module not available. Check module dependencies."
        }), 503

    # Find project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Get project folder path
    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder path"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Check if already running (thread-safe)
    with _pipeline_lock:
        if project_id in _pipeline_status and _pipeline_status[project_id].get('status') == 'running':
            return jsonify({
                "error": "Pipeline already in progress",
                "status": _pipeline_status[project_id]
            }), 409

    # Get run mode from request
    data = request.get_json() or {}
    mode = data.get('mode', 'manual')  # 'manual' or 'auto'

    # Start pipeline in background thread
    def run_pipeline():
        with _pipeline_lock:
            _pipeline_status[project_id] = {
                'status': 'running',
                'current_stage': None,
                'progress': 0,
                'stages': {},
                'messages': []
            }

        try:
            # Create pipeline instance
            pipeline = MasterPipeline(
                project_folder=project_path,
                openai_key=OPENAI_API_KEY,
                openrouter_key=OPENROUTER_API_KEY
            )

            # Progress callback with SSE integration
            def progress_callback(stage_name, stage_status, message=None):
                with _pipeline_lock:
                    _pipeline_status[project_id]['current_stage'] = stage_name
                    _pipeline_status[project_id]['stages'][stage_name] = stage_status
                    if message:
                        _pipeline_status[project_id]['messages'].append({
                            'stage': stage_name,
                            'message': message
                        })
                    # Calculate overall progress
                    completed = sum(1 for s in _pipeline_status[project_id]['stages'].values()
                                    if s.get('completed'))
                    progress = completed / 8
                    _pipeline_status[project_id]['progress'] = progress

                # Publish SSE event for real-time UI updates
                status = 'complete' if stage_status.get('completed') else 'running'
                if stage_status.get('error'):
                    status = 'error'
                publish_pipeline_stage(
                    project_id,
                    stage_name,
                    status,
                    message or f'Processing {stage_name}...',
                    progress,
                    stage_status.get('data')
                )

            pipeline.set_progress_callback(progress_callback)

            # Run async pipeline
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(pipeline.run_full_pipeline(mode=mode))
            loop.close()

            # Store result (thread-safe)
            with _pipeline_lock:
                _pipeline_status[project_id] = {
                    'status': 'complete',
                    'progress': 1.0,
                    'stages': result.get('stages', {}),
                    'result': result
                }

            # Publish completion SSE event
            publish_activity(
                project_id,
                'stage_complete',
                'Pipeline complete!',
                f'All 8 stages finished successfully',
                'check',
                1.0
            )

            # Refresh project data
            debounced_refresh.trigger()

        except Exception as e:
            with _pipeline_lock:
                _pipeline_status[project_id] = {
                    'status': 'error',
                    'error': str(e),
                    'stages': _pipeline_status.get(project_id, {}).get('stages', {})
                }

            # Publish error SSE event
            publish_activity(
                project_id,
                'error',
                'Pipeline failed',
                str(e),
                'error',
                None
            )

    thread = threading.Thread(target=run_pipeline)
    thread.start()

    return jsonify({
        "status": "started",
        "project_id": project_id,
        "message": "Pipeline started in background"
    })


@pipeline_bp.route('/api/project/<project_id>/pipeline/status')
def api_pipeline_status(project_id):
    """Get pipeline status for a project (for UI polling)"""
    with _pipeline_lock:
        if project_id not in _pipeline_status:
            # Check if pipeline has been run before from project status
            project = find_project_by_id(project_id)
            if project:
                project_folder = project.get('folder_path') or project.get('folder')
                if project_folder:
                    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)
                    status_tracker = get_status_tracker()
                    pipeline_status = status_tracker.get_pipeline_status(str(project_path))
                    if pipeline_status:
                        return jsonify({
                            "status": "complete" if pipeline_status.get('overall_complete') else "incomplete",
                            "project_id": project_id,
                            "pipeline": pipeline_status
                        })

            return jsonify({"status": "not_started", "project_id": project_id})

        return jsonify(dict(_pipeline_status[project_id], project_id=project_id))


@pipeline_bp.route('/api/project/<project_id>/pipeline/stage/<stage_name>/rerun', methods=['POST'])
def api_rerun_stage(project_id, stage_name):
    """Re-run a single pipeline stage"""
    if not PIPELINE_AVAILABLE:
        return jsonify({"error": "Pipeline module not available"}), 503

    valid_stages = ['rename', 'organize', 'split_specs', 'split_drawings',
                    'rag_analysis', 'ai_analysis', 'schedule_parse', 'highlight', 'quotes']

    if stage_name not in valid_stages:
        return jsonify({
            "error": f"Invalid stage name. Valid stages: {valid_stages}"
        }), 400

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

    # Check if already running
    with _pipeline_lock:
        if project_id in _pipeline_status and _pipeline_status[project_id].get('status') == 'running':
            return jsonify({
                "error": "Pipeline already in progress",
                "status": _pipeline_status[project_id]
            }), 409

    # Run single stage in background
    def run_stage():
        with _pipeline_lock:
            _pipeline_status[project_id] = {
                'status': 'running',
                'current_stage': stage_name,
                'progress': 0,
                'stages': {},
                'messages': []
            }

        try:
            pipeline = MasterPipeline(
                project_folder=project_path,
                openai_key=OPENAI_API_KEY,
                openrouter_key=OPENROUTER_API_KEY
            )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(pipeline.run_stage(stage_name))
            loop.close()

            with _pipeline_lock:
                _pipeline_status[project_id] = {
                    'status': 'complete',
                    'progress': 1.0,
                    'stages': {stage_name: result},
                    'result': result
                }

            debounced_refresh.trigger()

        except Exception as e:
            with _pipeline_lock:
                _pipeline_status[project_id] = {
                    'status': 'error',
                    'error': str(e)
                }

    thread = threading.Thread(target=run_stage)
    thread.start()

    return jsonify({
        "status": "started",
        "project_id": project_id,
        "stage": stage_name,
        "message": f"Stage '{stage_name}' started"
    })


@pipeline_bp.route('/api/pipeline/batch', methods=['POST'])
def api_batch_pipeline():
    """
    Run pipeline on multiple projects.

    Request body:
    {
        "project_ids": ["proj1", "proj2", ...],
        "mode": "auto"
    }
    """
    if not PIPELINE_AVAILABLE:
        return jsonify({"error": "Pipeline module not available"}), 503

    data = request.get_json()
    if not data or 'project_ids' not in data:
        return jsonify({"error": "Missing project_ids in request body"}), 400

    project_ids = data.get('project_ids', [])
    mode = data.get('mode', 'auto')

    started = []
    skipped = []
    errors = []

    for project_id in project_ids:
        project = find_project_by_id(project_id)
        if not project:
            errors.append({"project_id": project_id, "error": "Not found"})
            continue

        project_folder = project.get('folder_path') or project.get('folder')
        if not project_folder:
            errors.append({"project_id": project_id, "error": "No folder path"})
            continue

        project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

        if not project_path.exists():
            errors.append({"project_id": project_id, "error": "Folder not found"})
            continue

        # Check if already running
        with _pipeline_lock:
            if project_id in _pipeline_status and _pipeline_status[project_id].get('status') == 'running':
                skipped.append(project_id)
                continue

        # Start pipeline (not in thread - batch runs sequentially to avoid overload)
        started.append(project_id)

    # Run batch in background thread
    if started:
        def run_batch():
            for project_id in started:
                project = find_project_by_id(project_id)
                project_folder = project.get('folder_path') or project.get('folder')
                project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

                with _pipeline_lock:
                    _pipeline_status[project_id] = {
                        'status': 'running',
                        'current_stage': None,
                        'progress': 0,
                        'stages': {},
                        'messages': []
                    }

                try:
                    pipeline = MasterPipeline(
                        project_folder=project_path,
                        openai_key=OPENAI_API_KEY,
                        openrouter_key=OPENROUTER_API_KEY
                    )

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(pipeline.run_full_pipeline(mode=mode))
                    loop.close()

                    with _pipeline_lock:
                        _pipeline_status[project_id] = {
                            'status': 'complete',
                            'progress': 1.0,
                            'stages': result.get('stages', {}),
                            'result': result
                        }

                except Exception as e:
                    with _pipeline_lock:
                        _pipeline_status[project_id] = {
                            'status': 'error',
                            'error': str(e)
                        }

            debounced_refresh.trigger()

        thread = threading.Thread(target=run_batch)
        thread.start()

    return jsonify({
        "status": "batch_started",
        "started": started,
        "skipped": skipped,
        "errors": errors
    })


@pipeline_bp.route('/api/pipeline/available')
def api_pipeline_available():
    """Check if pipeline module is available and configured"""
    return jsonify({
        "available": PIPELINE_AVAILABLE,
        "openai_configured": bool(OPENAI_API_KEY),
        "openrouter_configured": bool(OPENROUTER_API_KEY),
        "stages": [
            {"name": "rename", "description": "Extract project name from cover sheet"},
            {"name": "organize", "description": "Move files into structured folders"},
            {"name": "split_specs", "description": "Split spec book by CSI section"},
            {"name": "split_drawings", "description": "Split drawing set by page"},
            {"name": "ai_analysis", "description": "Analyze schedules with AI"},
            {"name": "schedule_parse", "description": "Parse schedules to JSON"},
            {"name": "highlight", "description": "Highlight floor plans and elevations"},
            {"name": "quotes", "description": "Identify vendor quotes"}
        ]
    })


@pipeline_bp.route('/api/projects/needing-pipeline')
def api_projects_needing_pipeline():
    """Get list of projects that haven't completed pipeline analysis"""
    status_tracker = get_status_tracker()
    needing = status_tracker.get_projects_needing_pipeline()

    return jsonify({
        "count": len(needing),
        "projects": needing
    })


@pipeline_bp.route('/api/projects/needing-update')
def api_projects_needing_update():
    """
    Get list of projects that need pipeline update (new files or changes).

    This includes:
    - Projects that have never run the pipeline
    - Projects that have run but have new/changed files since

    Query params:
    - include_complete: if 'true', include completed projects that have changes
    """
    status_tracker = get_status_tracker()
    bidding_path = Path(BIDDING_FOLDER)

    include_complete = request.args.get('include_complete', 'true').lower() == 'true'

    needing_update = status_tracker.get_projects_needing_update(bidding_path)

    # Separate by reason
    never_run = [p for p in needing_update if "not completed" in p["reason"].lower()]
    has_changes = [p for p in needing_update if "not completed" not in p["reason"].lower()]

    return jsonify({
        "total_needing_update": len(needing_update),
        "never_run_count": len(never_run),
        "has_changes_count": len(has_changes),
        "projects": needing_update if include_complete else never_run
    })


@pipeline_bp.route('/api/pipeline/batch-smart', methods=['POST'])
def api_batch_pipeline_smart():
    """
    Smart batch pipeline - only processes projects that need updates.

    Automatically skips:
    - Projects that have completed pipeline with no file changes
    - Projects already running

    Request body (optional):
    {
        "force_all": false,     // Run on all projects regardless of status
        "limit": 10,            // Max projects to process in this batch
        "mode": "auto"          // Pipeline mode
    }
    """
    if not PIPELINE_AVAILABLE:
        return jsonify({"error": "Pipeline module not available"}), 503

    data = request.get_json() or {}
    force_all = data.get('force_all', False)
    limit = data.get('limit', 20)  # Default limit of 20 projects per batch
    mode = data.get('mode', 'auto')

    status_tracker = get_status_tracker()
    bidding_path = Path(BIDDING_FOLDER)

    # Get projects needing update
    if force_all:
        # Get all project folders
        all_folders = [
            f for f in bidding_path.iterdir()
            if f.is_dir() and not f.name.startswith('.') and list(f.rglob('*.pdf'))
        ]
        projects_to_run = [
            {"project_id": f.name, "folder_path": str(f), "reason": "Force run all"}
            for f in all_folders[:limit]
        ]
    else:
        needing_update = status_tracker.get_projects_needing_update(bidding_path)
        projects_to_run = needing_update[:limit]

    started = []
    skipped = []
    errors = []

    for proj_info in projects_to_run:
        project_id = proj_info["project_id"]
        project_path = Path(proj_info["folder_path"])

        # Check if already running
        with _pipeline_lock:
            if project_id in _pipeline_status and _pipeline_status[project_id].get('status') == 'running':
                skipped.append({
                    "project_id": project_id,
                    "reason": "Already running"
                })
                continue

        if not project_path.exists():
            errors.append({
                "project_id": project_id,
                "error": "Folder not found"
            })
            continue

        started.append({
            "project_id": project_id,
            "reason": proj_info.get("reason", "Needs update")
        })

    # Run batch in background
    if started:
        def run_smart_batch():
            for proj_info in started:
                project_id = proj_info["project_id"]
                project_path = bidding_path / project_id

                with _pipeline_lock:
                    _pipeline_status[project_id] = {
                        'status': 'running',
                        'current_stage': None,
                        'progress': 0,
                        'stages': {},
                        'messages': []
                    }

                try:
                    pipeline = MasterPipeline(
                        project_folder=project_path,
                        openai_key=OPENAI_API_KEY,
                        openrouter_key=OPENROUTER_API_KEY
                    )

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(pipeline.run_full_pipeline(mode=mode))
                    loop.close()

                    # Update fingerprint after successful run
                    status_tracker.update_pipeline_fingerprint(project_id, project_path)

                    with _pipeline_lock:
                        _pipeline_status[project_id] = {
                            'status': 'complete',
                            'progress': 1.0,
                            'stages': result.get('stages', {}),
                            'result': result
                        }

                except Exception as e:
                    with _pipeline_lock:
                        _pipeline_status[project_id] = {
                            'status': 'error',
                            'error': str(e)
                        }

            debounced_refresh.trigger()

        thread = threading.Thread(target=run_smart_batch)
        thread.start()

    return jsonify({
        "status": "batch_started",
        "started_count": len(started),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "started": started,
        "skipped": skipped,
        "errors": errors,
        "remaining": len(projects_to_run) - len(started) if not force_all else "unknown"
    })
