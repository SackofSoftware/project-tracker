"""
GovWin Leads API - Forecasting and research (separate from projects).

Endpoints:
- GET /leads - All GovWin leads
- GET /leads/:id - Single lead details
- POST /leads/:id/convert - Convert lead to bid opportunity
"""

from flask import Blueprint, jsonify, request
from datetime import datetime

from modules.database.db import get_session
from modules.database.models import GovLead
from modules.database.project_repository import get_repository

leads_bp = Blueprint('leads', __name__, url_prefix='/leads')


@leads_bp.route('', methods=['GET'])
def list_leads():
    """
    List all GovWin leads.

    Query params:
    - type: BID or LEAD
    - state: Filter by state
    - limit: Max results (default 100)
    """
    entity_type = request.args.get('type')
    state = request.args.get('state')
    limit = request.args.get('limit', 100, type=int)

    with get_session() as session:
        query = session.query(GovLead)

        if entity_type:
            query = query.filter(GovLead.entity_type == entity_type.upper())

        if state:
            query = query.filter(GovLead.state == state.upper())

        query = query.order_by(GovLead.response_date.desc().nulls_last())
        leads = query.limit(limit).all()

        return jsonify({
            'count': len(leads),
            'leads': [lead.to_dict() for lead in leads]
        })


@leads_bp.route('/<opportunity_id>', methods=['GET'])
def get_lead(opportunity_id):
    """Get a single GovWin lead."""
    with get_session() as session:
        lead = session.query(GovLead).filter(
            GovLead.opportunity_id == opportunity_id
        ).first()

        if not lead:
            return jsonify({'error': 'Lead not found'}), 404

        return jsonify(lead.to_dict())


@leads_bp.route('/<opportunity_id>/convert', methods=['POST'])
def convert_lead(opportunity_id):
    """
    Convert a GovWin lead to a bid opportunity project.
    Creates a new project with bid_opportunity status.
    """
    repo = get_repository()

    with get_session() as session:
        lead = session.query(GovLead).filter(
            GovLead.opportunity_id == opportunity_id
        ).first()

        if not lead:
            return jsonify({'error': 'Lead not found'}), 404

        if lead.converted_to_project:
            return jsonify({'error': 'Lead already converted'}), 400

        # Create project from lead data
        project = repo.create_project({
            'title': lead.title,
            'state': lead.state,
            'owner_name': lead.organization,
            'description': lead.description,
            'estimated_value': str(lead.estimated_value) if lead.estimated_value else None,
            'bid_date': lead.response_date,
            'source': 'govwin',
            'workflow_status': 'bid_opportunity'
        })

        # Link to source
        repo.add_source_link(
            project_id=project.id,
            source_type='govwin',
            source_id=opportunity_id,
            match_confidence=1.0,
            match_type='converted'
        )

        # Mark lead as converted
        lead.converted_to_project = True
        lead.converted_at = datetime.now()
        lead.project_id = project.id

        return jsonify({
            'status': 'converted',
            'project_id': project.id,
            'lead': lead.to_dict()
        })