"""
Gov Leads Routes Blueprint

API endpoints and pages for government leads/forecasting.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template, send_file, abort

from modules.govleads import GovLeadsReader
from utils import get_platform_path

govleads_bp = Blueprint('govleads', __name__)

# Base path for downloaded documents
GOV_DOWNLOADS_PATH = get_platform_path("GOV_DOWNLOADS_PATH")

# Database path from environment
GOV_DB_PATH = get_platform_path("GOV_DB_PATH")


def get_reader():
    """Get a GovLeadsReader instance."""
    return GovLeadsReader(GOV_DB_PATH)


# ==================== PAGE ROUTES ====================

@govleads_bp.route('/forecasting')
def forecasting_page():
    """
    Forecasting page showing government leads.

    Displays a filterable list of BIDs and LEADs.
    """
    reader = get_reader()
    stats = reader.get_stats()
    states = reader.get_states()

    return render_template('forecasting.html',
        stats=stats,
        states=states
    )


# ==================== API ROUTES ====================

@govleads_bp.route('/api/govleads')
def api_govleads():
    """
    DEPRECATED: Use /api/projects?source=govwin instead.

    Get all gov leads with filtering.

    Query params:
    - type: 'BID', 'LEAD', or 'all' (default: 'all')
    - state: Filter by state code
    - active: 'true' to show only active BIDs with future dates
    - q: Search query string
    - limit: Maximum number to return (default: 100)
    """
    reader = get_reader()

    # Get filter params
    entity_type = request.args.get('type')
    state = request.args.get('state')
    active_only = request.args.get('active', '').lower() == 'true'
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 100, type=int)

    # Get leads
    if query:
        leads = reader.search(query, state=state, entity_type=entity_type, limit=limit)
    elif entity_type == 'BID':
        if active_only:
            leads = reader.get_active_bids()
        else:
            leads = reader.get_bids()
    elif entity_type == 'LEAD':
        leads = reader.get_leads_forecast()
    else:
        leads = reader.read_all_leads()

    # Apply state filter if not already applied in search
    if state and not query:
        leads = [r for r in leads if r.state == state]

    # Apply limit
    leads = leads[:limit]

    response = jsonify({
        "count": len(leads),
        "leads": [r.to_dict() for r in leads]
    })
    response.headers['X-Deprecated'] = 'Use /api/projects?source=govwin instead'
    return response


@govleads_bp.route('/api/govleads/stats')
def api_govleads_stats():
    """
    DEPRECATED: Use /api/stats instead (includes GovWin data in govwin section).

    Get gov leads statistics.
    """
    reader = get_reader()
    stats = reader.get_stats()

    response = jsonify(stats)
    response.headers['X-Deprecated'] = 'Use /api/stats instead'
    return response


@govleads_bp.route('/api/govleads/states')
def api_govleads_states():
    """
    DEPRECATED: Use /api/stats for by_state breakdown or /api/projects?source=govwin for filtering.

    Get list of states with leads.
    """
    reader = get_reader()
    states = reader.get_states()

    # Get counts per state
    all_leads = reader.read_all_leads()
    state_counts = {}
    for lead in all_leads:
        state = lead.state or 'Unknown'
        state_counts[state] = state_counts.get(state, 0) + 1

    response = jsonify({
        "states": [{"code": s, "count": state_counts.get(s, 0)} for s in states]
    })
    response.headers['X-Deprecated'] = 'Use /api/stats instead'
    return response


@govleads_bp.route('/api/govleads/organizations')
def api_govleads_organizations():
    """Get top organizations with lead counts."""
    reader = get_reader()
    limit = request.args.get('limit', 50, type=int)
    orgs = reader.get_organizations(limit)

    return jsonify({
        "organizations": [{"name": name, "count": count} for name, count in orgs]
    })


@govleads_bp.route('/api/govleads/<int:lead_id>')
def api_govlead_detail(lead_id):
    """Get single lead details with documents."""
    reader = get_reader()

    # Get lead with documents
    conn = reader._get_connection()
    conn.row_factory = __import__('sqlite3').Row

    cursor = conn.execute("""
        SELECT id, opportunity_id, url, entity_type, title, status, state,
               organization, estimated_value, response_date, solicitation_date,
               description, overview_json, contact_json
        FROM projects WHERE id = ?
    """, (lead_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Lead not found"}), 404

    lead = reader._parse_row(dict(row))
    lead.documents = reader._load_documents(conn, lead_id)
    conn.close()

    return jsonify(lead.to_dict())


@govleads_bp.route('/api/govleads/<int:lead_id>/documents')
def api_govlead_documents(lead_id):
    """Get documents for a specific lead."""
    reader = get_reader()
    conn = reader._get_connection()
    docs = reader._load_documents(conn, lead_id)
    conn.close()

    return jsonify({
        "lead_id": lead_id,
        "count": len(docs),
        "documents": [d.to_dict() for d in docs]
    })


@govleads_bp.route('/api/govleads/document/<int:lead_id>/<path:filename>')
def api_serve_document(lead_id, filename):
    """Serve a downloaded document PDF."""
    # Documents are stored in /downloads/{lead_id}/{filename}
    doc_path = Path(GOV_DOWNLOADS_PATH) / str(lead_id) / filename

    if not doc_path.exists():
        # Try finding by pattern
        lead_folder = Path(GOV_DOWNLOADS_PATH) / str(lead_id)
        if lead_folder.exists():
            matches = list(lead_folder.glob(f"*{filename}*"))
            if matches:
                doc_path = matches[0]

    if not doc_path.exists():
        abort(404, description="Document not found")

    return send_file(doc_path, as_attachment=False)


@govleads_bp.route('/api/govleads/document-by-id/<int:lead_id>/<doc_id>')
def api_serve_document_by_id(lead_id, doc_id):
    """Serve a downloaded document PDF by doc_id."""
    # Files are named: {doc_id}_{title}.pdf
    lead_folder = Path(GOV_DOWNLOADS_PATH) / str(lead_id)

    if not lead_folder.exists():
        abort(404, description="Lead folder not found")

    # Find file starting with doc_id
    matches = list(lead_folder.glob(f"{doc_id}_*.pdf"))
    if not matches:
        # Try without .pdf extension
        matches = list(lead_folder.glob(f"{doc_id}_*"))

    if not matches:
        abort(404, description=f"Document {doc_id} not found")

    return send_file(matches[0], as_attachment=False)


@govleads_bp.route('/api/govleads/<int:lead_id>/convert', methods=['POST'])
def api_convert_to_project(lead_id):
    """
    Convert a gov lead to a tracked project.

    Creates a new project entry from the lead data.
    """
    reader = get_reader()
    lead = reader.get_by_id(lead_id)

    if not lead:
        return jsonify({"error": "Lead not found"}), 404

    # Get request data for additional fields
    data = request.get_json() or {}
    prefix = data.get('prefix', 'L')  # Default to Lead

    # Import here to avoid circular imports
    from utils import get_all_projects
    from modules.database import get_session
    from modules.database.models import Project, GovLead as GovLeadModel
    from modules.numbering import ProjectNumberingService

    try:
        db = get_session()

        # Create slug from title
        slug = lead.title.lower()
        slug = ''.join(c if c.isalnum() or c == ' ' else '' for c in slug)
        slug = '-'.join(slug.split())[:50]

        # Check if project already exists
        existing = db.query(Project).filter_by(id=slug).first()
        if existing:
            return jsonify({
                "error": f"Project already exists with ID: {slug}",
                "project_id": slug
            }), 409

        # Create project
        project = Project(
            id=slug,
            title=lead.title,
            source='govlead',
            state=lead.state,
            owner_name=lead.organization,
            estimated_value=str(lead.estimated_value) if lead.estimated_value else None,
            bid_date=lead.response_date,
            description=lead.description,
            created_at=datetime.now()
        )
        db.add(project)

        # Update gov lead record
        gov_lead = db.query(GovLeadModel).filter_by(opportunity_id=lead.opportunity_id).first()
        if gov_lead:
            gov_lead.project_id = slug
            gov_lead.converted_to_project = True
            gov_lead.converted_at = datetime.now()

        db.commit()

        # Assign project number
        numbering = ProjectNumberingService(db)
        project_number = numbering.assign_number(slug, prefix)

        return jsonify({
            "status": "ok",
            "project_id": slug,
            "project_number": project_number,
            "message": f"Created project {project_number} from gov lead"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@govleads_bp.route('/api/govleads/active')
def api_active_bids():
    """
    DEPRECATED: Use /api/projects?source=govwin&entity_type=BID instead.

    Get all active BIDs with upcoming response dates.
    """
    reader = get_reader()
    active = reader.get_active_bids()

    # Sort by response date (soonest first)
    active.sort(key=lambda r: r.response_date or datetime.max)

    response = jsonify({
        "count": len(active),
        "leads": [r.to_dict() for r in active]
    })
    response.headers['X-Deprecated'] = 'Use /api/projects?source=govwin&entity_type=BID instead'
    return response


@govleads_bp.route('/api/govleads/forecast')
def api_forecast():
    """
    DEPRECATED: Use /api/projects?source=govwin&entity_type=LEAD instead.

    Get all LEAD records for forecasting.
    """
    reader = get_reader()
    state = request.args.get('state')
    limit = request.args.get('limit', 100, type=int)

    leads = reader.get_leads_forecast()

    if state:
        leads = [r for r in leads if r.state == state]

    leads = leads[:limit]

    response = jsonify({
        "count": len(leads),
        "leads": [r.to_dict() for r in leads]
    })
    response.headers['X-Deprecated'] = 'Use /api/projects?source=govwin&entity_type=LEAD instead'
    return response
