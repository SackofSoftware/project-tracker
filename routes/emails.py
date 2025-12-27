"""
Email Routes Blueprint

API endpoints for Email Monitor integration.
"""

import os
import json
import threading
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file, Response

from modules.email_monitor import EmailMonitorReader, EmailProjectMatcher
from utils import get_all_projects, BIDDING_FOLDER, debounced_refresh, get_background_sync

emails_bp = Blueprint('emails', __name__)

# Default path from environment variable
EMAIL_MONITOR_PATH = os.getenv("EMAIL_MONITOR_PATH", "")


def get_reader():
    """Get an EmailMonitorReader instance."""
    return EmailMonitorReader(EMAIL_MONITOR_PATH)


def get_matcher():
    """Get an EmailProjectMatcher instance."""
    return EmailProjectMatcher()


@emails_bp.route('/api/emails')
def api_emails():
    """
    Get all emails with optional filtering.

    Query params:
    - status: 'matched', 'unmatched', 'all' (default: 'all')
    - platform: Filter by source platform
    - type: Filter by email type
    - days: Only emails from last N days
    - limit: Maximum number to return
    """
    reader = get_reader()
    matcher = get_matcher()

    # Get filter params
    status_filter = request.args.get('status', 'all')
    platform_filter = request.args.get('platform')
    type_filter = request.args.get('type')
    days = request.args.get('days', type=int)
    limit = request.args.get('limit', 100, type=int)

    # Get emails
    if days:
        emails = reader.get_recent_emails(days)
    else:
        emails = reader.read_all_emails()

    # Apply platform filter
    if platform_filter:
        emails = [e for e in emails if e.source_platform == platform_filter]

    # Apply type filter
    if type_filter:
        emails = [e for e in emails if e.email_type == type_filter]

    # Apply match status filter
    if status_filter in ('matched', 'unmatched'):
        projects = get_all_projects()
        matches = matcher.find_matches(emails, projects)
        matched_ids = {m['email_id'] for m in matches}

        if status_filter == 'matched':
            emails = [e for e in emails if e.id in matched_ids]
        else:  # unmatched
            emails = [e for e in emails if e.id not in matched_ids]

    # Apply limit
    emails = emails[:limit]

    # Get match info for each email
    projects = get_all_projects()
    result = []
    for email in emails:
        email_dict = email.to_dict()
        match = matcher.get_best_match(email, projects)
        if match:
            email_dict['match'] = match
        result.append(email_dict)

    return jsonify({
        "count": len(result),
        "emails": result
    })


@emails_bp.route('/api/emails/stats')
def api_emails_stats():
    """Get email statistics."""
    reader = get_reader()
    matcher = get_matcher()

    stats = reader.get_stats()

    # Add match stats
    emails = reader.read_all_emails()
    projects = get_all_projects()
    match_stats = matcher.get_match_stats(emails, projects)

    stats['matching'] = match_stats

    return jsonify(stats)


@emails_bp.route('/api/emails/unmatched')
def api_unmatched_emails():
    """
    Get emails not yet matched to projects.

    Query params:
    - limit: Maximum number to return
    - with_suggestions: Include match suggestions (default: false)
    """
    reader = get_reader()
    matcher = get_matcher()

    limit = request.args.get('limit', 50, type=int)
    with_suggestions = request.args.get('with_suggestions', 'false').lower() == 'true'

    emails = reader.read_all_emails()
    projects = get_all_projects()

    unmatched = matcher.get_unmatched_emails(emails, projects)[:limit]

    result = []
    for email in unmatched:
        email_dict = email.to_dict()

        if with_suggestions:
            suggestions = matcher.get_match_suggestions(email, projects, limit=3)
            email_dict['suggestions'] = suggestions

        result.append(email_dict)

    return jsonify({
        "count": len(result),
        "emails": result
    })


@emails_bp.route('/api/emails/<email_id>')
def api_email_detail(email_id):
    """Get details for a single email."""
    reader = get_reader()
    matcher = get_matcher()

    emails = reader.read_all_emails()
    email = next((e for e in emails if e.id == email_id), None)

    if not email:
        return jsonify({"error": "Email not found"}), 404

    projects = get_all_projects()
    email_dict = email.to_dict()

    # Add match info
    match = matcher.get_best_match(email, projects)
    if match:
        email_dict['match'] = match

    # Add suggestions
    suggestions = matcher.get_match_suggestions(email, projects, limit=5)
    email_dict['suggestions'] = suggestions

    return jsonify(email_dict)


@emails_bp.route('/api/emails/<email_id>/link', methods=['POST'])
def api_link_email(email_id):
    """
    Manually link an email to a project.

    Request body:
    - project_id: Project ID to link to
    """
    matcher = get_matcher()

    data = request.get_json() or {}
    project_id = data.get('project_id')

    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    # Verify project exists
    projects = get_all_projects()
    project = next((p for p in projects if p.get('id') == project_id), None)

    if not project:
        return jsonify({"error": f"Project not found: {project_id}"}), 404

    success = matcher.link_email(email_id, project_id)

    if success:
        return jsonify({
            "status": "ok",
            "email_id": email_id,
            "project_id": project_id
        })
    else:
        return jsonify({"error": "Failed to save link"}), 500


@emails_bp.route('/api/emails/<email_id>/unlink', methods=['POST'])
def api_unlink_email(email_id):
    """Remove a manual link for an email."""
    matcher = get_matcher()

    success = matcher.unlink_email(email_id)

    if success:
        return jsonify({"status": "ok", "email_id": email_id})
    else:
        return jsonify({"error": "Failed to remove link"}), 500


@emails_bp.route('/api/project/<project_id>/emails')
def api_project_emails(project_id):
    """
    Get all emails matched to a specific project.

    Returns both auto-matched and manually linked emails.
    """
    reader = get_reader()
    matcher = get_matcher()

    emails = reader.read_all_emails()
    projects = get_all_projects()

    # Find project
    project = next((p for p in projects if p.get('id') == project_id), None)
    if not project:
        return jsonify({"error": f"Project not found: {project_id}"}), 404

    # Find all emails that match this project
    project_emails = []
    for email in emails:
        match = matcher.get_best_match(email, [project])
        if match and match['project_id'] == project_id:
            email_dict = email.to_dict()
            email_dict['match'] = match
            project_emails.append(email_dict)

    # Sort by received time
    project_emails.sort(
        key=lambda e: e.get('received_time') or '',
        reverse=True
    )

    return jsonify({
        "project_id": project_id,
        "project_title": project.get('title'),
        "count": len(project_emails),
        "emails": project_emails
    })


@emails_bp.route('/api/emails/platforms')
def api_email_platforms():
    """Get list of all email source platforms with counts."""
    reader = get_reader()
    stats = reader.get_stats()

    return jsonify({
        "platforms": stats.get('by_platform', {})
    })


@emails_bp.route('/api/emails/types')
def api_email_types():
    """Get list of all email types with counts."""
    reader = get_reader()
    stats = reader.get_stats()

    return jsonify({
        "types": stats.get('by_type', {})
    })


@emails_bp.route('/api/emails/folders')
def api_email_folders():
    """Get list of all project folders from Email Monitor."""
    reader = get_reader()
    folders = reader.get_project_folders()

    return jsonify({
        "count": len(folders),
        "folders": folders
    })


@emails_bp.route('/api/emails/projects')
def api_email_projects():
    """
    Get all projects discovered from emails.

    Returns projects aggregated from Email Monitor, including
    both matched and unmatched (new) projects.

    Query params:
    - status: Filter by email_status (upcoming, in_progress, awarded)
    - matched: true/false - Filter by match status
    """
    reader = get_reader()
    matcher = get_matcher()

    email_projects = reader.get_email_projects()

    # Filter by status
    status_filter = request.args.get('status')
    if status_filter:
        email_projects = [p for p in email_projects if p.get('email_status') == status_filter]

    # Filter by match status
    matched_filter = request.args.get('matched')
    if matched_filter:
        projects = get_all_projects()
        local_projects = [p for p in projects if p.get('source') in ('local_bidding', 'local_extracted')]
        emails = reader.read_all_emails()
        matches = matcher.find_matches(emails, local_projects)

        matched_folders = set()
        for match in matches:
            email_id = match['email_id']
            for email in emails:
                if email.id == email_id:
                    matched_folders.add(email.project_folder)
                    break

        if matched_filter.lower() == 'true':
            email_projects = [p for p in email_projects if p.get('email_folder') in matched_folders]
        else:
            email_projects = [p for p in email_projects if p.get('email_folder') not in matched_folders]

    return jsonify({
        "count": len(email_projects),
        "projects": email_projects
    })


@emails_bp.route('/api/emails/sync', methods=['POST'])
def api_trigger_email_sync():
    """
    Trigger an immediate email sync.

    This runs the email sync process in the background and returns immediately.
    """
    try:
        background_sync = get_background_sync()
        thread = background_sync.run_email_sync_now()

        return jsonify({
            "status": "ok",
            "message": "Email sync triggered"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route('/api/emails/sync/status')
def api_email_sync_status():
    """Get email sync status."""
    try:
        background_sync = get_background_sync()
        status = background_sync.get_status()

        return jsonify({
            "email_monitor": status.get('email_monitor', {}),
            "running": status.get('running', False)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route('/api/emails/create-project', methods=['POST'])
def api_create_project_from_email():
    """
    Create a local project folder from an unmatched email project.

    Request body:
    - email_folder: Email Monitor folder name (required)
    - project_name: Desired project name (optional, uses email folder if not provided)

    Creates a new folder in the Bidding directory with extracted_project_data.json
    and links all emails from that folder to the new project.
    """
    reader = get_reader()
    matcher = get_matcher()

    data = request.get_json() or {}
    email_folder = data.get('email_folder')
    project_name = data.get('project_name') or email_folder

    if not email_folder:
        return jsonify({"error": "email_folder is required"}), 400

    # Verify email folder exists
    email_projects = reader.get_email_projects()
    email_proj = next((p for p in email_projects if p.get('email_folder') == email_folder), None)

    if not email_proj:
        return jsonify({"error": f"Email folder not found: {email_folder}"}), 404

    # Create project folder in Bidding directory
    new_folder = Path(BIDDING_FOLDER) / project_name

    if new_folder.exists():
        return jsonify({"error": f"Project folder already exists: {project_name}"}), 409

    try:
        new_folder.mkdir(parents=True)

        # Create initial project data file from email metadata
        project_data = {
            "meta": {
                "created_from": "email_monitor",
                "email_folder": email_folder,
                "created_at": datetime.now().isoformat()
            },
            "project": {
                "name": email_proj.get('title'),
                "address": "",
                "location": email_proj.get('location', {})
            },
            "schedule": {
                "bid_date": email_proj.get('bid_date')
            },
            "stakeholders": {},
            "division_8": {
                "scope_summary": f"Project discovered via email from {', '.join(email_proj.get('platforms', ['unknown']))}",
                "email_types": email_proj.get('email_types', [])
            }
        }

        with open(new_folder / "extracted_project_data.json", 'w') as f:
            json.dump(project_data, f, indent=2)

        # Generate project ID
        project_id = project_name.lower().replace(' ', '-').replace(',', '')

        # Link all emails from this folder to new project
        emails = reader.get_emails_for_project_folder(email_folder)
        for email in emails:
            matcher.link_email(email.id, project_id)

        # Refresh projects
        debounced_refresh.trigger(immediate=True)

        return jsonify({
            "status": "ok",
            "project_id": project_id,
            "project_folder": str(new_folder),
            "emails_linked": len(emails),
            "email_types": email_proj.get('email_types', []),
            "platforms": email_proj.get('platforms', [])
        })

    except Exception as e:
        # Clean up on failure
        if new_folder.exists():
            import shutil
            shutil.rmtree(new_folder)
        return jsonify({"error": str(e)}), 500


@emails_bp.route('/api/emails/bulk-link', methods=['POST'])
def api_bulk_link_emails():
    """
    Bulk link all emails from an email folder to a project.

    Request body:
    - email_folder: Email Monitor folder name
    - project_id: Project ID to link to
    """
    reader = get_reader()
    matcher = get_matcher()

    data = request.get_json() or {}
    email_folder = data.get('email_folder')
    project_id = data.get('project_id')

    if not email_folder or not project_id:
        return jsonify({"error": "email_folder and project_id are required"}), 400

    # Verify project exists
    projects = get_all_projects()
    project = next((p for p in projects if p.get('id') == project_id), None)

    if not project:
        return jsonify({"error": f"Project not found: {project_id}"}), 404

    # Get emails from folder
    emails = reader.get_emails_for_project_folder(email_folder)

    if not emails:
        return jsonify({"error": f"No emails found in folder: {email_folder}"}), 404

    # Link all emails
    linked = 0
    for email in emails:
        if matcher.link_email(email.id, project_id):
            linked += 1

    # Refresh to update project data
    debounced_refresh.trigger(immediate=True)

    return jsonify({
        "status": "ok",
        "email_folder": email_folder,
        "project_id": project_id,
        "emails_linked": linked,
        "total_emails": len(emails)
    })


@emails_bp.route('/api/emails/<email_id>/html')
def api_email_html(email_id):
    """
    Get the HTML content of an email.

    Returns the email HTML for display in an iframe or modal.
    """
    reader = get_reader()
    emails = reader.read_all_emails()

    email = next((e for e in emails if e.id == email_id), None)
    if not email:
        return jsonify({"error": "Email not found"}), 404

    if not email.html_path or not os.path.exists(email.html_path):
        return jsonify({"error": "Email HTML not available"}), 404

    try:
        with open(email.html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        return Response(html_content, mimetype='text/html')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route('/api/emails/<email_id>/attachment/<filename>')
def api_email_attachment(email_id, filename):
    """
    Download an email attachment.

    Returns the attachment file for download.
    """
    reader = get_reader()
    emails = reader.read_all_emails()

    email = next((e for e in emails if e.id == email_id), None)
    if not email:
        return jsonify({"error": "Email not found"}), 404

    if not email.attachments_folder:
        return jsonify({"error": "No attachments folder"}), 404

    # Security: ensure filename doesn't contain path traversal
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(email.attachments_folder, safe_filename)

    if not os.path.exists(file_path):
        return jsonify({"error": "Attachment not found"}), 404

    try:
        return send_file(file_path, as_attachment=True, download_name=safe_filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route('/api/emails/<email_id>/open-folder')
def api_open_email_folder(email_id):
    """
    Open the email folder in Finder (macOS).

    Useful for accessing all email files directly.
    """
    reader = get_reader()
    emails = reader.read_all_emails()

    email = next((e for e in emails if e.id == email_id), None)
    if not email:
        return jsonify({"error": "Email not found"}), 404

    # Get the folder containing the email
    email_folder = os.path.dirname(email.metadata_path)

    try:
        import subprocess
        subprocess.run(['open', email_folder], check=True)
        return jsonify({"status": "ok", "folder": email_folder})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@emails_bp.route('/api/emails/by-folder/<path:folder_name>')
def api_emails_by_folder(folder_name):
    """
    Get all emails for a specific email folder.

    Returns full email details including HTML paths and attachments.
    """
    reader = get_reader()
    emails = reader.get_emails_for_project_folder(folder_name)

    if not emails:
        return jsonify({"error": f"No emails found for folder: {folder_name}"}), 404

    return jsonify({
        "folder": folder_name,
        "count": len(emails),
        "emails": [e.to_dict() for e in emails]
    })
