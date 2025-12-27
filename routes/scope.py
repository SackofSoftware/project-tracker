"""
Scope/Document Classification Routes Blueprint

Handles document classification and scope analysis APIs:
- Division 8 scope extraction from spec PDFs (sync/async)
- Drawing discipline identification (sync/async)
- Full scope analysis combining specs and drawings
"""

import os
import json
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

from utils import (
    find_project_by_id,
    get_project_folder_path,
    BIDDING_FOLDER
)

from modules.files import FileOrganizer

# Import document classification modules (optional)
try:
    from modules.doc_classification import (
        extract_divisions_from_pdf,
        identify_sheets_in_pdf,
        summarize_disciplines,
        DISCIPLINE_CODES
    )
    DOC_CLASSIFICATION_AVAILABLE = True
except ImportError as e:
    print(f"Doc classification module not available in scope blueprint: {e}")
    DOC_CLASSIFICATION_AVAILABLE = False


scope_bp = Blueprint('scope', __name__)


# =============================================================================
# MODULE STATE FOR ASYNC OPERATIONS
# =============================================================================

# Division 8 async analysis state tracking
_division8_status = {}  # project_id -> {status, progress, result, error}
_division8_lock = threading.Lock()

# Drawings async analysis state tracking
_drawings_status = {}  # project_id -> {status, progress, result, error}
_drawings_lock = threading.Lock()


# =============================================================================
# DIVISION 8 SCOPE EXTRACTION - SYNCHRONOUS
# =============================================================================

@scope_bp.route('/api/project/<project_id>/scope/division8')
def api_project_division8_scope(project_id):
    """Extract Division 8 (Openings) scope from spec PDFs in a project (SYNCHRONOUS)

    NOTE: This endpoint processes PDFs synchronously and may timeout for large projects.
    For large projects, use the async endpoints instead:
    - POST /api/project/<project_id>/scope/division8/analyze (start async analysis)
    - GET /api/project/<project_id>/scope/division8/status (check status)
    - GET /api/project/<project_id>/scope/division8/result (get result)

    Finds spec PDFs and extracts Division 08 content including:
    - Door sections (081113, 081416, etc.)
    - Window sections (085113, etc.)
    - Hardware sections (087100, etc.)
    - Glazing sections (088000, etc.)
    """
    if not DOC_CLASSIFICATION_AVAILABLE:
        return jsonify({"error": "Document classification module not available. Install pdfplumber."}), 503

    project_path, project = get_project_folder_path(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if not project_path or not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Find spec PDFs in project folder
    spec_pdfs = []
    for pdf_file in project_path.rglob("*.pdf"):
        name_lower = pdf_file.name.lower()
        # Match common spec file patterns
        if any(pattern in name_lower for pattern in ['spec', 'division', 'section', 'manual', 'project_manual']):
            spec_pdfs.append(pdf_file)
        # Also check for 08xxxx patterns in filename
        elif any(f"08{i}" in name_lower for i in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']):
            spec_pdfs.append(pdf_file)

    if not spec_pdfs:
        return jsonify({
            "project_id": project_id,
            "division8": None,
            "message": "No spec PDFs found in project folder",
            "searched_folder": str(project_path)
        })

    # Extract Division 08 from each spec PDF
    results = []
    for pdf_path in spec_pdfs[:5]:  # Limit to 5 PDFs to avoid timeout
        try:
            divisions = extract_divisions_from_pdf(
                pdf_path,
                target_divisions=["08"],  # Only Division 8 - Openings
                max_pages=200  # Limit pages for performance
            )

            if "08" in divisions:
                div8 = divisions["08"]
                results.append({
                    "source_file": str(pdf_path.relative_to(project_path)),
                    "division": div8.division,
                    "title": div8.title,
                    "start_page": div8.start_page,
                    "end_page": div8.end_page,
                    "sections": [
                        {
                            "section_id": s.section_id,
                            "title": s.title,
                            "page": s.page,
                            "excerpt": s.excerpt[:500] if s.excerpt else None
                        }
                        for s in div8.sections
                    ]
                })
        except Exception as e:
            results.append({
                "source_file": str(pdf_path.relative_to(project_path)),
                "error": str(e)
            })

    return jsonify({
        "project_id": project_id,
        "project_name": project.get('name', project_id),
        "division8_scope": results,
        "spec_files_found": len(spec_pdfs),
        "spec_files_processed": len(results)
    })


# =============================================================================
# DIVISION 8 SCOPE EXTRACTION - ASYNC
# =============================================================================

@scope_bp.route('/api/project/<project_id>/scope/division8/analyze', methods=['POST'])
def api_project_division8_analyze_async(project_id):
    """Start async Division 8 scope analysis for a project

    This endpoint starts the Division 8 analysis in a background thread and returns immediately.
    Use the status and result endpoints to check progress and retrieve results.
    """
    if not DOC_CLASSIFICATION_AVAILABLE:
        return jsonify({"error": "Document classification module not available. Install pdfplumber."}), 503

    # Find project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path, _ = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Check if already analyzing (thread-safe)
    with _division8_lock:
        if project_id in _division8_status and _division8_status[project_id].get('status') == 'running':
            return jsonify({"error": "Division 8 analysis already in progress", "status": _division8_status[project_id]}), 409

    # Start analysis in background thread
    def run_division8_analysis():
        with _division8_lock:
            _division8_status[project_id] = {'status': 'running', 'progress': 0}

        try:
            # Find spec PDFs in project folder
            spec_pdfs = []
            for pdf_file in project_path.rglob("*.pdf"):
                name_lower = pdf_file.name.lower()
                # Match common spec file patterns
                if any(pattern in name_lower for pattern in ['spec', 'division', 'section', 'manual', 'project_manual']):
                    spec_pdfs.append(pdf_file)
                # Also check for 08xxxx patterns in filename
                elif any(f"08{i}" in name_lower for i in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']):
                    spec_pdfs.append(pdf_file)

            with _division8_lock:
                _division8_status[project_id]['progress'] = 0.1

            if not spec_pdfs:
                with _division8_lock:
                    _division8_status[project_id] = {
                        'status': 'complete',
                        'progress': 1.0,
                        'result': {
                            "project_id": project_id,
                            "division8": None,
                            "message": "No spec PDFs found in project folder",
                            "searched_folder": str(project_path)
                        }
                    }
                return

            # Extract Division 08 from each spec PDF
            results = []
            total_pdfs = min(len(spec_pdfs), 5)  # Limit to 5 PDFs to avoid timeout
            for idx, pdf_path in enumerate(spec_pdfs[:total_pdfs]):
                try:
                    divisions = extract_divisions_from_pdf(
                        pdf_path,
                        target_divisions=["08"],  # Only Division 8 - Openings
                        max_pages=200  # Limit pages for performance
                    )

                    if "08" in divisions:
                        div8 = divisions["08"]
                        results.append({
                            "source_file": str(pdf_path.relative_to(project_path)),
                            "division": div8.division,
                            "title": div8.title,
                            "start_page": div8.start_page,
                            "end_page": div8.end_page,
                            "sections": [
                                {
                                    "section_id": s.section_id,
                                    "title": s.title,
                                    "page": s.page,
                                    "excerpt": s.excerpt[:500] if s.excerpt else None
                                }
                                for s in div8.sections
                            ]
                        })
                except Exception as e:
                    results.append({
                        "source_file": str(pdf_path.relative_to(project_path)),
                        "error": str(e)
                    })

                # Update progress
                with _division8_lock:
                    _division8_status[project_id]['progress'] = 0.1 + (0.9 * (idx + 1) / total_pdfs)

            # Store result (thread-safe)
            with _division8_lock:
                _division8_status[project_id] = {
                    'status': 'complete',
                    'progress': 1.0,
                    'result': {
                        "project_id": project_id,
                        "project_name": project.get('name', project_id),
                        "division8_scope": results,
                        "spec_files_found": len(spec_pdfs),
                        "spec_files_processed": len(results)
                    }
                }

        except Exception as e:
            with _division8_lock:
                _division8_status[project_id] = {
                    'status': 'error',
                    'error': str(e)
                }

    thread = threading.Thread(target=run_division8_analysis)
    thread.start()

    return jsonify({
        "status": "started",
        "project_id": project_id,
        "message": "Division 8 analysis started in background"
    })


@scope_bp.route('/api/project/<project_id>/scope/division8/status')
def api_project_division8_status(project_id):
    """Get Division 8 analysis status for a project (thread-safe)"""
    with _division8_lock:
        if project_id not in _division8_status:
            return jsonify({"status": "not_started", "project_id": project_id})
        return jsonify(dict(_division8_status[project_id]))


@scope_bp.route('/api/project/<project_id>/scope/division8/result')
def api_project_division8_result(project_id):
    """Get Division 8 analysis result for a project (thread-safe)"""
    with _division8_lock:
        if project_id not in _division8_status:
            return jsonify({"error": "No Division 8 analysis found"}), 404

        status = _division8_status[project_id]
        if status.get('status') != 'complete':
            return jsonify({"error": "Division 8 analysis not complete", "status": status.get('status')}), 400

        return jsonify(status.get('result', {}))


# =============================================================================
# DRAWINGS DISCIPLINE ANALYSIS - SYNCHRONOUS
# =============================================================================

@scope_bp.route('/api/project/<project_id>/scope/drawings')
def api_project_drawing_disciplines(project_id):
    """Analyze drawing PDFs in a project to identify disciplines (SYNCHRONOUS)

    NOTE: This endpoint processes PDFs synchronously and may timeout for large projects.
    For large projects, use the async endpoints instead:
    - POST /api/project/<project_id>/scope/drawings/analyze (start async analysis)
    - GET /api/project/<project_id>/scope/drawings/status (check status)
    - GET /api/project/<project_id>/scope/drawings/result (get result)

    Identifies drawing sheets by discipline:
    - Architectural (A-)
    - Structural (S-)
    - Mechanical (M-)
    - Electrical (E-)
    - Plumbing (P-)
    - Fire Protection (FP-)
    And more per NCS standards
    """
    if not DOC_CLASSIFICATION_AVAILABLE:
        return jsonify({"error": "Document classification module not available. Install pdfplumber."}), 503

    project_path, project = get_project_folder_path(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if not project_path or not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Find drawing PDFs
    drawing_pdfs = []
    for pdf_file in project_path.rglob("*.pdf"):
        name_lower = pdf_file.name.lower()
        # Match common drawing file patterns
        if any(pattern in name_lower for pattern in ['drawing', 'sheet', 'plan', 'elevation', 'detail', 'arch', 'dwg']):
            drawing_pdfs.append(pdf_file)
        # Also match sheet number patterns like A-101, M-001
        elif any(f"{code}-" in name_lower or f"{code}." in name_lower
                for code in ['a', 's', 'm', 'e', 'p', 'fp', 'g', 'c', 'l']):
            drawing_pdfs.append(pdf_file)

    if not drawing_pdfs:
        return jsonify({
            "project_id": project_id,
            "disciplines": None,
            "message": "No drawing PDFs found in project folder",
            "searched_folder": str(project_path)
        })

    # Analyze drawings
    all_sheets = []
    for pdf_path in drawing_pdfs[:10]:  # Limit to 10 PDFs
        try:
            sheets = identify_sheets_in_pdf(str(pdf_path), use_vision=False)
            for sheet in sheets:
                all_sheets.append({
                    "source_file": str(pdf_path.relative_to(project_path)),
                    "sheet_id": sheet.sheet_id,
                    "discipline_code": sheet.discipline_code,
                    "discipline_name": sheet.discipline_name,
                    "sheet_type": sheet.sheet_type,
                    "sheet_title": sheet.sheet_title,
                    "confidence": sheet.confidence,
                    "method": sheet.method
                })
        except Exception as e:
            all_sheets.append({
                "source_file": str(pdf_path.relative_to(project_path)),
                "error": str(e)
            })

    # Summarize by discipline
    summary = summarize_disciplines([s for s in all_sheets if 'error' not in s])

    return jsonify({
        "project_id": project_id,
        "project_name": project.get('name', project_id),
        "summary": summary,
        "sheets": all_sheets,
        "drawing_files_found": len(drawing_pdfs),
        "available_disciplines": DISCIPLINE_CODES
    })


# =============================================================================
# DRAWINGS DISCIPLINE ANALYSIS - ASYNC
# =============================================================================

@scope_bp.route('/api/project/<project_id>/scope/drawings/analyze', methods=['POST'])
def api_project_drawings_analyze_async(project_id):
    """Start async drawings discipline analysis for a project

    This endpoint starts the drawings analysis in a background thread and returns immediately.
    Use the status and result endpoints to check progress and retrieve results.
    """
    if not DOC_CLASSIFICATION_AVAILABLE:
        return jsonify({"error": "Document classification module not available. Install pdfplumber."}), 503

    # Find project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path, _ = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Check if already analyzing (thread-safe)
    with _drawings_lock:
        if project_id in _drawings_status and _drawings_status[project_id].get('status') == 'running':
            return jsonify({"error": "Drawings analysis already in progress", "status": _drawings_status[project_id]}), 409

    # Start analysis in background thread
    def run_drawings_analysis():
        with _drawings_lock:
            _drawings_status[project_id] = {'status': 'running', 'progress': 0}

        try:
            # Find drawing PDFs
            drawing_pdfs = []
            for pdf_file in project_path.rglob("*.pdf"):
                name_lower = pdf_file.name.lower()
                # Match common drawing file patterns
                if any(pattern in name_lower for pattern in ['drawing', 'sheet', 'plan', 'elevation', 'detail', 'arch', 'dwg']):
                    drawing_pdfs.append(pdf_file)
                # Also match sheet number patterns like A-101, M-001
                elif any(f"{code}-" in name_lower or f"{code}." in name_lower
                        for code in ['a', 's', 'm', 'e', 'p', 'fp', 'g', 'c', 'l']):
                    drawing_pdfs.append(pdf_file)

            with _drawings_lock:
                _drawings_status[project_id]['progress'] = 0.1

            if not drawing_pdfs:
                with _drawings_lock:
                    _drawings_status[project_id] = {
                        'status': 'complete',
                        'progress': 1.0,
                        'result': {
                            "project_id": project_id,
                            "disciplines": None,
                            "message": "No drawing PDFs found in project folder",
                            "searched_folder": str(project_path)
                        }
                    }
                return

            # Analyze drawings
            all_sheets = []
            total_pdfs = min(len(drawing_pdfs), 10)  # Limit to 10 PDFs
            for idx, pdf_path in enumerate(drawing_pdfs[:total_pdfs]):
                try:
                    sheets = identify_sheets_in_pdf(str(pdf_path), use_vision=False)
                    for sheet in sheets:
                        all_sheets.append({
                            "source_file": str(pdf_path.relative_to(project_path)),
                            "sheet_id": sheet.sheet_id,
                            "discipline_code": sheet.discipline_code,
                            "discipline_name": sheet.discipline_name,
                            "sheet_type": sheet.sheet_type,
                            "sheet_title": sheet.sheet_title,
                            "confidence": sheet.confidence,
                            "method": sheet.method
                        })
                except Exception as e:
                    all_sheets.append({
                        "source_file": str(pdf_path.relative_to(project_path)),
                        "error": str(e)
                    })

                # Update progress
                with _drawings_lock:
                    _drawings_status[project_id]['progress'] = 0.1 + (0.9 * (idx + 1) / total_pdfs)

            # Summarize by discipline
            summary = summarize_disciplines([s for s in all_sheets if 'error' not in s])

            # Store result (thread-safe)
            with _drawings_lock:
                _drawings_status[project_id] = {
                    'status': 'complete',
                    'progress': 1.0,
                    'result': {
                        "project_id": project_id,
                        "project_name": project.get('name', project_id),
                        "summary": summary,
                        "sheets": all_sheets,
                        "drawing_files_found": len(drawing_pdfs),
                        "available_disciplines": DISCIPLINE_CODES
                    }
                }

        except Exception as e:
            with _drawings_lock:
                _drawings_status[project_id] = {
                    'status': 'error',
                    'error': str(e)
                }

    thread = threading.Thread(target=run_drawings_analysis)
    thread.start()

    return jsonify({
        "status": "started",
        "project_id": project_id,
        "message": "Drawings analysis started in background"
    })


@scope_bp.route('/api/project/<project_id>/scope/drawings/status')
def api_project_drawings_status(project_id):
    """Get drawings analysis status for a project (thread-safe)"""
    with _drawings_lock:
        if project_id not in _drawings_status:
            return jsonify({"status": "not_started", "project_id": project_id})
        return jsonify(dict(_drawings_status[project_id]))


@scope_bp.route('/api/project/<project_id>/scope/drawings/result')
def api_project_drawings_result(project_id):
    """Get drawings analysis result for a project (thread-safe)"""
    with _drawings_lock:
        if project_id not in _drawings_status:
            return jsonify({"error": "No drawings analysis found"}), 404

        status = _drawings_status[project_id]
        if status.get('status') != 'complete':
            return jsonify({"error": "Drawings analysis not complete", "status": status.get('status')}), 400

        return jsonify(status.get('result', {}))


# =============================================================================
# FULL SCOPE ANALYSIS
# =============================================================================

@scope_bp.route('/api/project/<project_id>/scope/full')
def api_project_full_scope(project_id):
    """Get comprehensive scope analysis combining specs and drawings

    Returns Division 8 scope from specs AND drawing disciplines,
    providing a complete picture of openings/glazing work.
    """
    if not DOC_CLASSIFICATION_AVAILABLE:
        return jsonify({"error": "Document classification module not available. Install pdfplumber."}), 503

    project_path, project = get_project_folder_path(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if not project_path or not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    # Get file organization summary
    organizer = FileOrganizer(str(project_path), os.getenv("OPENROUTER_API_KEY"))
    file_scan = organizer.scan_folder(use_ai=False)
    quotes = organizer.identify_quotes()

    # Compile scope summary
    return jsonify({
        "project_id": project_id,
        "project_name": project.get('name', project_id),
        "project_folder": str(project_path),
        "file_summary": file_scan.get('summary', {}),
        "quotes_found": len(quotes),
        "quotes": quotes,
        "endpoints": {
            "division8_scope": f"/api/project/{project_id}/scope/division8",
            "drawing_disciplines": f"/api/project/{project_id}/scope/drawings",
            "file_organization": f"/api/project/{project_id}/files"
        },
        "doc_classification_available": DOC_CLASSIFICATION_AVAILABLE
    })


# =============================================================================
# BATCH SCOPE ANALYSIS
# =============================================================================

import uuid

# Global state for batch jobs
_batch_scope_jobs = {}
_batch_scope_lock = threading.Lock()


def _run_batch_scope_analysis(job_id: str, force: bool = False):
    """Background worker for batch Division 8 scope analysis"""
    from utils import get_all_projects, get_status_tracker, debounced_refresh

    if not DOC_CLASSIFICATION_AVAILABLE:
        with _batch_scope_lock:
            _batch_scope_jobs[job_id]['status'] = 'error'
            _batch_scope_jobs[job_id]['error'] = 'Document classification module not available'
        return

    status_tracker = get_status_tracker()
    all_projects = get_all_projects()

    # Filter projects that need analysis
    projects_to_analyze = []
    for p in all_projects:
        project_id = p.get('project_code') or p.get('id') or p.get('folder', '').lower().replace(' ', '-')
        if not project_id:
            continue

        # Skip archived projects
        if p.get('archived'):
            continue

        # Check if already has scope data (unless force)
        if not force:
            status = status_tracker.get_status(project_id)
            if status and status.get('division_8_scope'):
                continue

        # Check if has a folder path
        folder_path = p.get('folder_path')
        if folder_path and Path(folder_path).exists():
            projects_to_analyze.append({
                'id': project_id,
                'name': p.get('title') or p.get('name') or p.get('folder') or project_id,
                'path': Path(folder_path)
            })

    total = len(projects_to_analyze)
    with _batch_scope_lock:
        _batch_scope_jobs[job_id]['total'] = total
        _batch_scope_jobs[job_id]['status'] = 'running'

    print(f"[Scope Batch] Starting analysis of {total} projects")

    completed = []
    errors = []

    for i, proj in enumerate(projects_to_analyze, 1):
        project_id = proj['id']
        project_name = proj['name']
        project_path = proj['path']

        with _batch_scope_lock:
            _batch_scope_jobs[job_id]['current'] = i
            _batch_scope_jobs[job_id]['current_project'] = project_name

        print(f"[Scope Batch] Analyzing {i}/{total}: {project_name}")

        try:
            # Find spec PDFs
            spec_pdfs = []
            for pdf_file in project_path.rglob("*.pdf"):
                name_lower = pdf_file.name.lower()
                if any(pattern in name_lower for pattern in ['spec', 'division', 'section', 'manual', 'project_manual']):
                    spec_pdfs.append(pdf_file)
                elif any(f"08{i}" in name_lower for i in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']):
                    spec_pdfs.append(pdf_file)

            if not spec_pdfs:
                completed.append({
                    'project_id': project_id,
                    'project_name': project_name,
                    'sections_found': 0,
                    'note': 'No spec PDFs found'
                })
                continue

            # Extract Division 8 from spec PDFs
            results = []
            for pdf_path in spec_pdfs[:5]:
                try:
                    divisions = extract_divisions_from_pdf(
                        pdf_path,
                        target_divisions=["08"],
                        max_pages=200
                    )

                    if "08" in divisions:
                        div8 = divisions["08"]
                        results.append({
                            "source_file": str(pdf_path.relative_to(project_path)),
                            "division": div8.division,
                            "title": div8.title,
                            "sections": [
                                {
                                    "section_id": s.section_id,
                                    "title": s.title,
                                    "page": s.page
                                }
                                for s in div8.sections
                            ]
                        })
                except Exception as e:
                    pass

            # Save scope data to status
            if results:
                status = status_tracker.get_status(project_id) or status_tracker.create_project_status(project_id)
                status['division_8_scope'] = results
                status_tracker.set_status(project_id, status)

                section_count = sum(len(r.get('sections', [])) for r in results)
                completed.append({
                    'project_id': project_id,
                    'project_name': project_name,
                    'sections_found': section_count,
                    'files_processed': len(results)
                })
                print(f"[Scope Batch]   -> Found {section_count} sections in {len(results)} files")
            else:
                completed.append({
                    'project_id': project_id,
                    'project_name': project_name,
                    'sections_found': 0,
                    'note': 'No Division 8 content found'
                })

        except Exception as e:
            errors.append({
                'project_id': project_id,
                'project_name': project_name,
                'error': str(e)
            })
            print(f"[Scope Batch]   -> Error: {e}")

    # Trigger refresh
    debounced_refresh.trigger()

    with _batch_scope_lock:
        _batch_scope_jobs[job_id]['status'] = 'completed'
        _batch_scope_jobs[job_id]['completed'] = completed
        _batch_scope_jobs[job_id]['errors'] = errors

    sections_found = sum(c.get('sections_found', 0) for c in completed)
    print(f"[Scope Batch] Complete! Analyzed {total} projects, found {sections_found} total sections")


@scope_bp.route('/api/scope/batch-analyze', methods=['POST'])
def api_scope_batch_analyze():
    """Start a batch Division 8 scope analysis job for all projects"""
    if not DOC_CLASSIFICATION_AVAILABLE:
        return jsonify({"error": "Document classification module not available. Install pdfplumber."}), 503

    force = request.args.get('force', 'false').lower() == 'true'

    job_id = str(uuid.uuid4())[:8]

    with _batch_scope_lock:
        _batch_scope_jobs[job_id] = {
            'status': 'starting',
            'current': 0,
            'total': 0,
            'current_project': '',
            'completed': [],
            'errors': [],
            'force': force
        }

    thread = threading.Thread(target=_run_batch_scope_analysis, args=(job_id, force))
    thread.daemon = True
    thread.start()

    return jsonify({
        "status": "ok",
        "job_id": job_id,
        "message": f"Batch scope analysis started {'(force mode)' if force else '(skipping projects with existing scope data)'}",
        "status_url": f"/api/scope/batch-analyze/status?job_id={job_id}"
    })


@scope_bp.route('/api/scope/batch-analyze/status')
def api_scope_batch_analyze_status():
    """Get status of a batch scope analysis job"""
    job_id = request.args.get('job_id')

    if not job_id:
        # Return list of all jobs
        with _batch_scope_lock:
            return jsonify({
                "status": "ok",
                "jobs": {jid: {"status": j["status"], "current": j["current"], "total": j["total"]}
                         for jid, j in _batch_scope_jobs.items()}
            })

    with _batch_scope_lock:
        job = _batch_scope_jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    response = {
        "status": "ok",
        "job_id": job_id,
        "job_status": job['status'],
        "current": job['current'],
        "total": job['total'],
        "current_project": job['current_project']
    }

    if job['status'] == 'completed':
        response['completed'] = job['completed']
        response['errors'] = job['errors']
        response['summary'] = {
            'projects_analyzed': len(job['completed']),
            'projects_with_scope': len([c for c in job['completed'] if c.get('sections_found', 0) > 0]),
            'total_sections_found': sum(c.get('sections_found', 0) for c in job['completed']),
            'errors': len(job['errors'])
        }
    elif job['status'] == 'error':
        response['error'] = job.get('error')

    return jsonify(response)
