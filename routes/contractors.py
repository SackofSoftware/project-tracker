"""
Contractors Routes Blueprint

Handles contractor profile pages with merged Company research data
and Vendor quote/project engagement history.
"""

from datetime import datetime
from flask import Blueprint, jsonify, request, render_template

from modules.database.db import get_session
from modules.database.models import Company, Vendor, VendorQuote, Project, ProjectStatus
from modules.database.queries import (
    link_company_to_vendor,
    get_vendor_project_history,
    get_contractor_statistics,
    get_planhub_gc_projects
)

contractors_bp = Blueprint('contractors', __name__)


# =============================================================================
# PAGE ROUTES
# =============================================================================

@contractors_bp.route('/contractors')
def contractors_page():
    """Render the Contractors listing page"""
    return render_template('contractors.html')


# =============================================================================
# CONTRACTOR LIST ENDPOINTS
# =============================================================================

@contractors_bp.route('/api/contractors')
def api_list_contractors():
    """
    Get all contractors (merged Company + Vendor data).

    Query Parameters:
        - type: Filter by company_type (contractor, subcontractor)
        - has_research: Filter to those with research data (true/false)
        - has_quotes: Filter to those with quote history (true/false)
        - sort: Sort by (name, projects_count, last_active)

    Returns:
        JSON with contractors list and count
    """
    contractor_type = request.args.get('type', None)
    has_research = request.args.get('has_research', None) == 'true'
    has_quotes = request.args.get('has_quotes', None) == 'true'
    sort_by = request.args.get('sort', 'name')

    with get_session() as db:
        contractors = []

        # Get all companies of contractor types
        company_query = db.query(Company)
        if contractor_type:
            company_query = company_query.filter_by(company_type=contractor_type)
        else:
            company_query = company_query.filter(
                Company.company_type.in_(['contractor', 'subcontractor'])
            )

        companies = company_query.all()

        # Get all vendors with quotes
        vendors_with_quotes = db.query(Vendor).join(VendorQuote).distinct().all()

        # Merge data - track which names we've seen
        seen_names = set()

        # Process companies first
        for company in companies:
            link_result = link_company_to_vendor(company.name, session=db)
            vendor = link_result['vendor']

            # Get project history if vendor exists
            project_history = []
            quote_count = 0
            if vendor:
                project_history = get_vendor_project_history(vendor.id, session=db)
                quote_count = sum(h['quote_count'] for h in project_history)

            # Get PlanHub GC projects
            planhub_gc_projects = get_planhub_gc_projects(company.name)
            gc_project_count = len(planhub_gc_projects)

            # Apply filters
            if has_research and not company.research_status == 'complete':
                continue
            if has_quotes and quote_count == 0:
                continue

            contractors.append({
                'id': f"company_{company.id}",
                'name': company.name,
                'type': company.company_type,
                'has_research': company.research_status == 'complete',
                'has_quotes': quote_count > 0,
                'research_status': company.research_status,
                'project_count': len(project_history),
                'quote_count': quote_count,
                'gc_project_count': gc_project_count,
                'company_id': company.id,
                'vendor_id': vendor.id if vendor else None,
                'match_confidence': link_result['match_confidence'],
                'certifications': company.certifications or [],
                'specialties': vendor.specialties if vendor else [],
                'last_active': max(
                    company.last_researched or datetime.min,
                    vendor.updated_at if vendor and vendor.updated_at else datetime.min
                ).isoformat()
            })
            seen_names.add(company.name.lower())

        # Process vendors without matching companies
        for vendor in vendors_with_quotes:
            if vendor.name.lower() in seen_names:
                continue

            quote_count = db.query(VendorQuote).filter_by(vendor_id=vendor.id).count()

            if has_research:  # Skip if research required but not present
                continue
            if has_quotes and quote_count == 0:
                continue

            project_history = get_vendor_project_history(vendor.id, session=db)

            # Get PlanHub GC projects
            planhub_gc_projects = get_planhub_gc_projects(vendor.name)
            gc_project_count = len(planhub_gc_projects)

            contractors.append({
                'id': f"vendor_{vendor.id}",
                'name': vendor.name,
                'type': vendor.company_type or 'subcontractor',
                'has_research': False,
                'has_quotes': True,
                'research_status': 'pending',
                'project_count': len(project_history),
                'quote_count': quote_count,
                'gc_project_count': gc_project_count,
                'company_id': None,
                'vendor_id': vendor.id,
                'match_confidence': 0.0,
                'certifications': [],
                'specialties': vendor.specialties or [],
                'last_active': vendor.updated_at.isoformat() if vendor.updated_at else datetime.min.isoformat()
            })

        # Sort
        if sort_by == 'name':
            contractors.sort(key=lambda c: c['name'].lower())
        elif sort_by == 'projects_count':
            contractors.sort(key=lambda c: c['project_count'], reverse=True)
        elif sort_by == 'last_active':
            contractors.sort(key=lambda c: c['last_active'], reverse=True)

        return jsonify({
            'contractors': contractors,
            'count': len(contractors),
            'filters_applied': {
                'type': contractor_type,
                'has_research': has_research,
                'has_quotes': has_quotes,
                'sort': sort_by
            }
        })


@contractors_bp.route('/api/contractors/<contractor_id>')
def api_get_contractor(contractor_id):
    """
    Get full contractor profile (merged Company + Vendor data).

    contractor_id format: "company_{uuid}" or "vendor_{int}"

    Returns:
        JSON with full contractor profile including:
        - company_data: Research data
        - vendor_data: Contact/quote data
        - project_engagement: Project history and statistics
    """
    with get_session() as db:
        # Parse ID
        company = None
        vendor = None

        if contractor_id.startswith('company_'):
            company_id = contractor_id.replace('company_', '')
            company = db.query(Company).filter_by(id=company_id).first()

            if not company:
                return jsonify({'error': 'Company not found'}), 404

            # Try to link to vendor
            link_result = link_company_to_vendor(company.name, session=db)
            vendor = link_result['vendor']

        elif contractor_id.startswith('vendor_'):
            vendor_id = int(contractor_id.replace('vendor_', ''))
            vendor = db.query(Vendor).filter_by(id=vendor_id).first()

            if not vendor:
                return jsonify({'error': 'Vendor not found'}), 404

            # Try to link to company
            link_result = link_company_to_vendor(vendor.name, session=db)
            company = link_result['company']
        else:
            return jsonify({'error': 'Invalid contractor ID format'}), 400

        # Get project engagement history
        project_history = []
        if vendor:
            project_history = get_vendor_project_history(vendor.id, session=db)

        # Get PlanHub GC projects
        contractor_name = company.name if company else vendor.name
        planhub_gc_projects = get_planhub_gc_projects(contractor_name)

        # Build merged profile
        profile = {
            'id': contractor_id,
            'name': company.name if company else vendor.name,
            'company_type': company.company_type if company else (vendor.company_type or 'subcontractor'),

            # Company data (research)
            'company_data': {
                'id': company.id,
                'website': company.website,
                'headquarters': company.headquarters,
                'phone': company.phone,
                'email': company.email,
                'founded': company.founded,
                'employee_count': company.employee_count,
                'description': company.description,
                'company_summary': company.company_summary,
                'certifications': company.certifications or [],
                'leadership': company.leadership or [],
                'staff': company.staff or [],
                'services': company.services or [],
                'portfolio': company.portfolio or [],
                'awards': company.awards or [],
                'social_links': company.social_links or {},
                'research_status': company.research_status,
                'last_researched': company.last_researched.isoformat() if company.last_researched else None
            } if company else None,

            # Vendor data (quotes)
            'vendor_data': {
                'id': vendor.id,
                'contact_name': vendor.contact_name,
                'email': vendor.email,
                'phone': vendor.phone,
                'address': vendor.address,
                'city': vendor.city,
                'state': vendor.state,
                'zip_code': vendor.zip_code,
                'specialties': vendor.specialties or [],
                'certifications': vendor.certifications or [],
                'active': vendor.active,
                'notes': vendor.notes
            } if vendor else None,

            # Project engagement
            'project_engagement': {
                'total_projects': len(project_history),
                'projects_won': sum(1 for h in project_history if h['result'] == 'won'),
                'projects_lost': sum(1 for h in project_history if h['result'] == 'lost'),
                'projects_pending': sum(1 for h in project_history if h['result'] == 'pending'),
                'total_quoted_value': sum(h['total_quoted'] for h in project_history if h['total_quoted']),
                'recent_projects': [
                    {
                        'project_id': h['project'].id,
                        'project_name': h['project'].title,
                        'project_address': h['project'].address,
                        'project_city': h['project'].city,
                        'project_state': h['project'].state,
                        'bid_date': h['project'].bid_date.isoformat() if h['project'].bid_date else None,
                        'quote_count': h['quote_count'],
                        'total_quoted': h['total_quoted'],
                        'result': h['result'],
                        'quotes': [
                            {
                                'id': q.id,
                                'category': q.category,
                                'amount': q.amount,
                                'status': q.status,
                                'quote_date': q.quote_date.isoformat() if q.quote_date else None,
                                'quote_number': q.quote_number
                            }
                            for q in h['quotes']
                        ]
                    }
                    for h in project_history[:20]  # Limit to recent 20
                ]
            },

            # GC Portfolio (PlanHub projects where they're the general contractor)
            'gc_portfolio': {
                'total_projects': len(planhub_gc_projects),
                'projects': [
                    {
                        'project_id': match['project'].get('id'),
                        'project_name': match['project'].get('title'),
                        'project_city': match['project'].get('location', {}).get('city'),
                        'project_state': match['project'].get('location', {}).get('state'),
                        'bid_date': match['project'].get('bid_date'),
                        'project_value': match['project'].get('project_value'),
                        'project_value_str': match['project'].get('project_value_str'),
                        'is_division_8': match['project'].get('is_division_8', False),
                        'is_sub_bidding': match['project'].get('is_sub_bidding', False),
                        'is_gc_awarded': match['project'].get('is_gc_awarded', False),
                        'match_confidence': match['match_confidence'],
                        'gc_data': match['gc_data']
                    }
                    for match in planhub_gc_projects[:20]  # Limit to recent 20
                ]
            },

            # Linking metadata
            'match_confidence': link_result['match_confidence'] if 'link_result' in locals() else 0.0,
            'match_method': link_result['match_method'] if 'link_result' in locals() else 'none',
            'has_research_data': company is not None and company.research_status == 'complete',
            'has_quote_data': vendor is not None and len(project_history) > 0,
            'has_gc_data': len(planhub_gc_projects) > 0
        }

        return jsonify(profile)


# =============================================================================
# CONTRACTOR ACTIONS
# =============================================================================

@contractors_bp.route('/api/contractors/<contractor_id>/link', methods=['POST'])
def api_link_contractor(contractor_id):
    """
    Manually link a Company and Vendor record.

    Request Body:
        {
            "vendor_id": 123,  # Link company to this vendor
            "company_id": "uuid"  # Link vendor to this company
        }

    Note: Currently not implemented - uses fuzzy matching only.
    Future enhancement: Store manual links in ContractorLink table.
    """
    data = request.json

    # TODO: Store manual links in a new ContractorLink table
    # For now, just validate the link is possible

    return jsonify({
        'status': 'success',
        'message': 'Manual linking not yet implemented - uses fuzzy matching',
        'note': 'Future enhancement to add ContractorLink table for user-confirmed mappings'
    })
