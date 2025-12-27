"""
Notes Routes Blueprint

Handles smart notes processing and document upload APIs.
"""

from flask import Blueprint, jsonify, request
from pathlib import Path
import tempfile

from utils import (
    get_smart_notes,
    get_status_tracker,
    find_project_by_id,
    debounced_refresh,
    BIDDING_FOLDER
)

notes_bp = Blueprint('notes', __name__)


# =============================================================================
# SMART NOTES ENDPOINTS
# =============================================================================

@notes_bp.route('/api/notes/<project_id>/smart', methods=['POST'])
def api_smart_note(project_id):
    """Process a note with AI to extract structured data"""
    smart_notes = get_smart_notes()
    status_tracker = get_status_tracker()

    data = request.json
    note_text = data.get('note', '')

    if not note_text:
        return jsonify({"error": "No note text provided"}), 400

    # Parse note with AI
    parsed = smart_notes.parse_note_text(note_text)

    # Store the original note
    status_tracker.add_note(project_id, note_text, data.get('author'))

    # Apply extracted data if found
    extracted = parsed.get('extracted', {})
    actions_taken = []

    # Update estimate if quote amount found
    if extracted.get('quote_amount'):
        status_tracker.update_estimate(
            project_id,
            total=extracted['quote_amount'],
            notes=f"From vendor: {extracted.get('vendor_name', 'Unknown')}"
        )
        actions_taken.append('updated_estimate')

    # Add vendor as a tag
    if extracted.get('vendor_name'):
        vendor_tag = f"vendor:{extracted['vendor_name'].lower().replace(' ', '_')[:20]}"
        status_tracker.add_tag(project_id, vendor_tag)
        actions_taken.append('added_vendor_tag')

    # Update bid decision if found
    if extracted.get('bid_decision'):
        status_tracker.update_bid_decision(
            project_id,
            extracted['bid_decision'],
            extracted.get('decision_reason')
        )
        actions_taken.append('updated_bid_decision')

    # Add any extracted tags
    for tag in extracted.get('tags', []):
        status_tracker.add_tag(project_id, tag)
        actions_taken.append(f'added_tag:{tag}')

    debounced_refresh.trigger()

    return jsonify({
        "status": "ok",
        "parsed": parsed,
        "actions_taken": actions_taken
    })


@notes_bp.route('/api/notes/<project_id>/upload', methods=['POST'])
def api_upload_document(project_id):
    """Upload and process a document (PDF) with AI classification"""
    smart_notes = get_smart_notes()
    status_tracker = get_status_tracker()

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Find project folder
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        file.save(tmp.name)
        tmp_path = Path(tmp.name)

    try:
        # Classify document
        doc_type, confidence = smart_notes.classify_document(file.filename)

        # If it's a quote, process it
        if doc_type == 'quote':
            result = smart_notes.process_quote_pdf(tmp_path, project_path)

            if result.get('status') == 'success':
                # Move file to Quotes folder
                dest_path = smart_notes.file_document(tmp_path, project_path, 'quote')

                # Update project with quote info
                quote_data = result.get('quote_data', {})
                if quote_data.get('total_amount'):
                    status_tracker.update_estimate(
                        project_id,
                        total=quote_data['total_amount'],
                        notes=f"Quote from {quote_data.get('vendor_name', 'Unknown')}"
                    )

                # Add note about the upload
                note = f"Uploaded quote from {quote_data.get('vendor_name', 'Unknown')}: ${quote_data.get('total_amount', 'N/A')}"
                status_tracker.add_note(project_id, note)

                debounced_refresh.trigger()

                return jsonify({
                    "status": "success",
                    "document_type": doc_type,
                    "confidence": confidence,
                    "filed_to": str(dest_path),
                    "quote_data": quote_data
                })
        else:
            # Just file the document
            dest_path = smart_notes.file_document(tmp_path, project_path, doc_type)

            # Add note about the upload
            status_tracker.add_note(project_id, f"Uploaded {doc_type}: {file.filename}")

            return jsonify({
                "status": "success",
                "document_type": doc_type,
                "confidence": confidence,
                "filed_to": str(dest_path)
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temp file
        if tmp_path.exists():
            tmp_path.unlink()
