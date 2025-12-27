"""
Files Routes Blueprint

Handles file/document serving, listing, organization, and quotes APIs.
"""

import os
import urllib.parse
from pathlib import Path
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file

from utils import (
    find_project_by_id,
    get_project_folder_path,
    BIDDING_FOLDER
)

from modules.files import FileOrganizer


files_bp = Blueprint('files', __name__)


# =============================================================================
# FILE SERVING
# =============================================================================

@files_bp.route('/api/project/<project_id>/file/<path:filename>')
def serve_project_file(project_id, filename):
    """Serve a file (PDF, etc.) from a project folder"""
    # Find project folder
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    # URL decode the filename
    filename = urllib.parse.unquote(filename)

    # Security check: block path traversal attempts before resolution
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        return jsonify({"error": "Invalid file path"}), 403

    file_path = project_path / filename

    # Security check: make sure file is inside project folder (catches symlink attacks)
    try:
        file_path.resolve().relative_to(project_path.resolve())
    except ValueError:
        return jsonify({"error": "Invalid file path"}), 403

    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404

    # Determine mimetype
    ext = file_path.suffix.lower()
    mimetypes = {
        '.pdf': 'application/pdf',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
    }
    mimetype = mimetypes.get(ext, 'application/octet-stream')

    return send_file(str(file_path), mimetype=mimetype)


# =============================================================================
# FILE LISTING
# =============================================================================

@files_bp.route('/api/project/<project_id>/files')
def list_project_files(project_id):
    """List all viewable documents in a project folder (drawings, specs, PDFs)

    This endpoint can operate in two modes:
    1. Simple mode (default): Categorizes PDFs as drawings, specs, or other
    2. AI mode (use_ai=true): Uses FileOrganizer to scan and categorize all files
    """
    # Check if AI mode is requested
    use_ai = request.args.get('use_ai', 'false').lower() == 'true'

    if use_ai:
        # Use FileOrganizer for comprehensive file scanning
        project_path, project = get_project_folder_path(project_id)

        if not project:
            return jsonify({"error": "Project not found"}), 404

        if not project_path or not project_path.exists():
            return jsonify({"error": f"Project folder not found: {project_path}"}), 404

        organizer = FileOrganizer(str(project_path), os.getenv("OPENROUTER_API_KEY"))
        result = organizer.scan_folder(use_ai=use_ai)

        return jsonify(result)

    # Simple mode: Just categorize PDFs
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    # Categorize files
    drawings = []
    specs = []
    other_pdfs = []

    def classify_pdf(file_path, rel_path):
        """Classify a PDF as drawing, spec, or other"""
        name_lower = file_path.name.lower()
        rel_lower = str(rel_path).lower()

        # Check for drawings
        if any(x in rel_lower for x in ['drawing', '/drawings/', 'dwg', '/a-', '/s-', '/m-', '/e-', '/p-']):
            return 'drawing'
        if any(x in name_lower for x in ['elevation', 'floor plan', 'section', 'detail']):
            return 'drawing'

        # Check for specs
        if any(x in rel_lower for x in ['spec', '/specs/', 'division', 'section 08']):
            return 'spec'
        if any(x in name_lower for x in ['specification', 'spec', 'project manual']):
            return 'spec'

        # Default to other
        return 'other'

    # Find all PDFs
    for pdf_file in project_path.rglob("*.pdf"):
        try:
            rel_path = pdf_file.relative_to(project_path)
            file_info = {
                "name": pdf_file.name,
                "path": str(rel_path),
                "url": f"/api/project/{project_id}/file/{urllib.parse.quote(str(rel_path))}",
                "size": pdf_file.stat().st_size,
                "modified": datetime.fromtimestamp(pdf_file.stat().st_mtime).strftime('%m/%d/%y')
            }

            category = classify_pdf(pdf_file, rel_path)
            if category == 'drawing':
                drawings.append(file_info)
            elif category == 'spec':
                specs.append(file_info)
            else:
                other_pdfs.append(file_info)
        except Exception as e:
            print(f"Error processing {pdf_file}: {e}")
            continue

    # Sort by name
    drawings.sort(key=lambda x: x['name'].lower())
    specs.sort(key=lambda x: x['name'].lower())
    other_pdfs.sort(key=lambda x: x['name'].lower())

    return jsonify({
        "drawings": drawings,
        "specs": specs,
        "other": other_pdfs,
        "total": len(drawings) + len(specs) + len(other_pdfs)
    })


# =============================================================================
# FILE ORGANIZATION
# =============================================================================

@files_bp.route('/api/project/<project_id>/files/quotes')
def api_project_file_quotes(project_id):
    """Get identified quote files from a project"""
    project_path, project = get_project_folder_path(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if not project_path or not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    organizer = FileOrganizer(str(project_path), os.getenv("OPENROUTER_API_KEY"))
    quotes = organizer.identify_quotes()

    return jsonify({
        "quotes": quotes,
        "project_id": project_id,
        "project_name": project.get('name', project_id)
    })


@files_bp.route('/api/project/<project_id>/files/organize', methods=['POST'])
def api_project_organize_files(project_id):
    """Organize files in a project folder into standard structure"""
    project_path, project = get_project_folder_path(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if not project_path or not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    data = request.get_json() or {}
    dry_run = data.get('dry_run', True)  # Default to dry run for safety

    organizer = FileOrganizer(str(project_path), os.getenv("OPENROUTER_API_KEY"))
    plan = organizer.get_organization_plan()

    if dry_run:
        return jsonify({
            "dry_run": True,
            "plan": plan,
            "message": "This is a preview. Set dry_run=false to execute."
        })

    # Execute the organization
    result = organizer.execute_organization(plan['moves'], dry_run=False)
    return jsonify(result)


@files_bp.route('/api/project/<project_id>/files/structure')
def api_project_file_structure(project_id):
    """Get the standard folder structure definition"""
    return jsonify({
        "folders": FileOrganizer.STANDARD_FOLDERS,
        "project_id": project_id
    })
