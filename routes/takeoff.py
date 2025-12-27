from flask import Blueprint, jsonify, request, send_file
from pathlib import Path
import json
from utils import find_project_by_id

# Check for database availability
try:
    from modules.database import (
        get_latest_takeoff, save_takeoff_result, get_or_create_project,
        get_takeoff_history, save_correction, get_corrections,
        get_latest_corrections, save_note, get_notes, update_note, delete_note
    )
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

takeoff_bp = Blueprint('takeoff', __name__)


def _get_project_folder_path(project_id):
    """Get the folder path for a project. Returns (Path, folder_name) or (None, None)."""
    project = find_project_by_id(project_id)
    if not project:
        return None, None
    folder_path = project.get('folder_path')
    folder_name = project.get('folder')
    if folder_path:
        return Path(folder_path), folder_name
    return None, None


@takeoff_bp.route('/api/project/<project_id>/scope-takeoff', methods=['GET'])
def get_scope_takeoff(project_id):
    """Get saved scope takeoff results."""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    project_path, folder_name = _get_project_folder_path(project_id)

    # Try database first if available
    if DATABASE_AVAILABLE:
        try:
            db_project = get_or_create_project(project_id, project.get('folder'))
            takeoff_result = get_latest_takeoff(db_project.id)
            if takeoff_result:
                return jsonify(takeoff_result.result_data)
        except Exception as e:
            print(f"Database lookup failed: {e}")

    # Fallback to JSON file
    if project_path:
        json_file = project_path / 'Extracted-Data' / 'scope_takeoff_result.json'
        if json_file.exists():
            with open(json_file, 'r') as f:
                result = json.load(f)
                return jsonify(result)

    return jsonify({'error': 'No takeoff results found'}), 404


@takeoff_bp.route('/api/project/<project_id>/scope-takeoff', methods=['POST'])
def run_scope_takeoff_route(project_id):
    """Run scope takeoff pipeline."""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    try:
        from modules.scope_takeoff import run_scope_takeoff
        result = run_scope_takeoff(project_id)

        # Save to database if available
        if DATABASE_AVAILABLE:
            try:
                db_project = get_or_create_project(project_id, project.get('folder'))
                save_takeoff_result(db_project.id, result)
            except Exception as e:
                print(f"Failed to save to database: {e}")

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@takeoff_bp.route('/api/project/<project_id>/highlighted-pages', methods=['GET'])
def get_highlighted_pages(project_id):
    """List highlighted pages."""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    project_path, folder_name = _get_project_folder_path(project_id)
    if not project_path:
        return jsonify({'error': 'Project path not found'}), 404

    page_info_file = project_path / 'Extracted-Data' / 'page_info.json'
    if not page_info_file.exists():
        return jsonify({'error': 'Page info not found'}), 404

    try:
        with open(page_info_file, 'r') as f:
            page_info = json.load(f)

        # Add URLs for each page
        pages = []
        for page in page_info.get('pages', []):
            page_data = page.copy()
            if 'filename' in page:
                page_data['url'] = f"/api/project/{project_id}/highlighted-page/{page['filename']}"
            pages.append(page_data)

        return jsonify({'pages': pages})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@takeoff_bp.route('/api/project/<project_id>/highlighted-page/<filename>', methods=['GET'])
def get_highlighted_page(project_id, filename):
    """Serve specific highlighted page PDF."""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    project_path, folder_name = _get_project_folder_path(project_id)
    if not project_path:
        return jsonify({'error': 'Project path not found'}), 404

    pdf_path = project_path / 'Extracted-Data' / 'Highlighted-Pages' / filename
    if not pdf_path.exists() or not pdf_path.is_file():
        return jsonify({'error': 'Highlighted page not found'}), 404

    return send_file(pdf_path, mimetype='application/pdf')


@takeoff_bp.route('/api/project/<project_id>/highlighted-pdf', methods=['GET'])
def get_highlighted_pdf(project_id):
    """Serve first highlighted PDF."""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    project_path, folder_name = _get_project_folder_path(project_id)
    if not project_path:
        return jsonify({'error': 'Project path not found'}), 404

    # Check Highlighted-Pages directory first
    highlighted_pages_dir = project_path / 'Extracted-Data' / 'Highlighted-Pages'
    if highlighted_pages_dir.exists():
        pdf_files = sorted(highlighted_pages_dir.glob('*.pdf'))
        if pdf_files:
            return send_file(pdf_files[0], mimetype='application/pdf')

    # Fallback to legacy *_highlighted.pdf files
    extracted_data_dir = project_path / 'Extracted-Data'
    if extracted_data_dir.exists():
        legacy_pdfs = sorted(extracted_data_dir.glob('*_highlighted.pdf'))
        if legacy_pdfs:
            return send_file(legacy_pdfs[0], mimetype='application/pdf')

    return jsonify({'error': 'No highlighted PDF found'}), 404


@takeoff_bp.route('/api/project/<project_id>/takeoff-legend', methods=['GET'])
def get_takeoff_legend(project_id):
    """Get color legend for highlighted PDF."""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    project_path, folder_name = _get_project_folder_path(project_id)
    if not project_path:
        return jsonify({'error': 'Project path not found'}), 404

    legend_file = project_path / 'Extracted-Data' / 'highlight_list.json'
    if not legend_file.exists():
        return jsonify({'error': 'Legend not found'}), 404

    try:
        with open(legend_file, 'r') as f:
            legend = json.load(f)
        return jsonify(legend)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@takeoff_bp.route('/api/project/<project_id>/corrections', methods=['GET', 'POST'])
def handle_corrections(project_id):
    """Get or save corrections."""
    if not DATABASE_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    try:
        db_project = get_or_create_project(project_id, project.get('folder'))

        if request.method == 'GET':
            corrections = get_corrections(db_project.id)
            latest_corrections = get_latest_corrections(db_project.id)
            return jsonify({
                'corrections': corrections,
                'latest_corrections': latest_corrections
            })

        elif request.method == 'POST':
            data = request.get_json()
            field_name = data.get('field_name')
            corrected_value = data.get('corrected_value')
            original_value = data.get('original_value')
            reason = data.get('reason')

            if not field_name or corrected_value is None:
                return jsonify({'error': 'Missing required fields'}), 400

            correction = save_correction(
                db_project.id,
                field_name,
                corrected_value,
                original_value,
                reason
            )

            return jsonify({
                'id': correction.id,
                'field_name': correction.field_name,
                'corrected_value': correction.corrected_value,
                'original_value': correction.original_value,
                'reason': correction.reason,
                'created_at': correction.created_at.isoformat()
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@takeoff_bp.route('/api/project/<project_id>/notes', methods=['GET', 'POST'])
def handle_notes(project_id):
    """Get or save notes."""
    if not DATABASE_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    try:
        db_project = get_or_create_project(project_id, project.get('folder'))

        if request.method == 'GET':
            note_type = request.args.get('type')
            notes = get_notes(db_project.id, note_type)
            return jsonify({'notes': notes})

        elif request.method == 'POST':
            data = request.get_json()
            content = data.get('content')
            note_type = data.get('note_type', 'general')

            if not content:
                return jsonify({'error': 'Content is required'}), 400

            note = save_note(db_project.id, content, note_type)

            return jsonify({
                'id': note.id,
                'content': note.content,
                'note_type': note.note_type,
                'created_at': note.created_at.isoformat(),
                'updated_at': note.updated_at.isoformat()
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@takeoff_bp.route('/api/project/<project_id>/notes/<int:note_id>', methods=['PUT', 'DELETE'])
def modify_note(project_id, note_id):
    """Update or delete note."""
    if not DATABASE_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    try:
        if request.method == 'PUT':
            data = request.get_json()
            content = data.get('content')
            note_type = data.get('note_type')

            note = update_note(note_id, content, note_type)
            if not note:
                return jsonify({'error': 'Note not found'}), 404

            return jsonify({
                'id': note.id,
                'content': note.content,
                'note_type': note.note_type,
                'created_at': note.created_at.isoformat(),
                'updated_at': note.updated_at.isoformat()
            })

        elif request.method == 'DELETE':
            success = delete_note(note_id)
            if not success:
                return jsonify({'error': 'Note not found'}), 404

            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@takeoff_bp.route('/api/project/<project_id>/takeoff-history', methods=['GET'])
def get_history(project_id):
    """Get version history."""
    if not DATABASE_AVAILABLE:
        return jsonify({'error': 'Database not available'}), 503

    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    try:
        db_project = get_or_create_project(project_id, project.get('folder'))
        history = get_takeoff_history(db_project.id)
        return jsonify({'history': history})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
