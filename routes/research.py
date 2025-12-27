"""
Research Routes Blueprint

Handles company research APIs including:
- Company CRUD operations
- Research session management
- Claims/Evidence viewing
- Real-time research progress (SSE)
"""

import asyncio
import uuid
import json
import logging
from datetime import datetime
from threading import Thread
from flask import Blueprint, jsonify, request, Response, render_template

from modules.database.db import get_session
from modules.database.models import (
    Company, ResearchSession, ResearchClaim, ResearchEvidence
)
from modules.research import research_company, scrape_company_deep

logger = logging.getLogger(__name__)

research_bp = Blueprint('research', __name__)

# Track active research tasks
active_research = {}


# =============================================================================
# PAGE ROUTES
# =============================================================================

@research_bp.route('/research')
def research_page():
    """Render the Research page"""
    return render_template('research.html')


# =============================================================================
# COMPANY ENDPOINTS
# =============================================================================

@research_bp.route('/api/research/companies')
def api_list_companies():
    """List all companies with research status"""
    with get_session() as db:
        companies = db.query(Company).order_by(Company.name).all()
        return jsonify({
            "companies": [
                {
                    "id": c.id,
                    "name": c.name,
                    "company_type": c.company_type,
                    "website": c.website,
                    "phone": c.phone,
                    "email": c.email,
                    "headquarters": c.headquarters,
                    "founded": c.founded,
                    "research_status": c.research_status,
                    "last_researched": c.last_researched.isoformat() if c.last_researched else None,
                    "company_summary": c.company_summary,
                    "certifications": c.certifications,
                }
                for c in companies
            ],
            "count": len(companies)
        })


@research_bp.route('/api/research/companies', methods=['POST'])
def api_create_company():
    """Create a new company"""
    data = request.json

    if not data.get('name'):
        return jsonify({"error": "Company name required"}), 400

    with get_session() as db:
        # Check if exists
        existing = db.query(Company).filter_by(name=data['name']).first()
        if existing:
            return jsonify({"error": "Company already exists", "company_id": existing.id}), 409

        company = Company(
            id=str(uuid.uuid4()),
            name=data['name'],
            company_type=data.get('company_type', 'contractor'),
            website=data.get('website'),
            phone=data.get('phone'),
            email=data.get('email'),
            headquarters=data.get('headquarters'),
            research_status='pending'
        )
        db.add(company)
        db.commit()

        return jsonify({
            "id": company.id,
            "name": company.name,
            "status": "created"
        }), 201


@research_bp.route('/api/research/companies/<company_id>')
def api_get_company(company_id):
    """Get full company profile with all details"""
    with get_session() as db:
        company = db.query(Company).filter_by(id=company_id).first()

        if not company:
            return jsonify({"error": "Company not found"}), 404

        # Get recent research sessions
        sessions = db.query(ResearchSession).filter_by(
            company_id=company_id
        ).order_by(ResearchSession.created_at.desc()).limit(5).all()

        # Get claims count
        claims_count = db.query(ResearchClaim).filter_by(
            company_id=company_id
        ).count()

        # Get sources from latest session
        sources = []
        if sessions:
            latest_session = sessions[0]
            if latest_session.sources_used:
                sources = latest_session.sources_used if isinstance(latest_session.sources_used, list) else []

        return jsonify({
            "id": company.id,
            "name": company.name,
            "company_type": company.company_type,
            "website": company.website,
            "phone": company.phone,
            "email": company.email,
            "headquarters": company.headquarters,
            "founded": company.founded,
            "employee_count": company.employee_count,
            "description": company.description,
            "company_summary": company.company_summary,
            "certifications": company.certifications,
            "leadership": company.leadership,
            "staff": company.staff,
            "portfolio": company.portfolio,
            "social_links": company.social_links,
            "research_status": company.research_status,
            "last_researched": company.last_researched.isoformat() if company.last_researched else None,
            "sources": sources,
            "sessions": [
                {
                    "id": s.id,
                    "status": s.status,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in sessions
            ],
            "claims_count": claims_count
        })


@research_bp.route('/api/research/companies/<company_id>', methods=['PUT'])
def api_update_company(company_id):
    """Update company profile"""
    data = request.json

    with get_session() as db:
        company = db.query(Company).filter_by(id=company_id).first()

        if not company:
            return jsonify({"error": "Company not found"}), 404

        # Update allowed fields
        for field in ['name', 'company_type', 'website', 'phone', 'email',
                      'headquarters', 'founded', 'employee_count', 'description',
                      'company_summary', 'certifications', 'leadership', 'staff',
                      'portfolio', 'social_links']:
            if field in data:
                setattr(company, field, data[field])

        db.commit()
        return jsonify({"status": "updated", "company_id": company.id})


@research_bp.route('/api/research/companies/<company_id>', methods=['DELETE'])
def api_delete_company(company_id):
    """Delete a company and all related data"""
    with get_session() as db:
        company = db.query(Company).filter_by(id=company_id).first()

        if not company:
            return jsonify({"error": "Company not found"}), 404

        # Delete claims and evidence first
        claims = db.query(ResearchClaim).filter_by(company_id=company_id).all()
        for claim in claims:
            db.query(ResearchEvidence).filter_by(claim_id=claim.id).delete()
        db.query(ResearchClaim).filter_by(company_id=company_id).delete()

        # Delete sessions
        db.query(ResearchSession).filter_by(company_id=company_id).delete()

        # Delete company
        db.delete(company)
        db.commit()

        return jsonify({"status": "deleted"})


# =============================================================================
# RESEARCH SESSION ENDPOINTS
# =============================================================================

@research_bp.route('/api/research/start', methods=['POST'])
def api_start_research():
    """Start a new research session for a company"""
    import os

    data = request.json
    company_name = data.get('company_name')
    company_id = data.get('company_id')
    website_url = data.get('website_url')
    location = data.get('location')

    if not company_name and not company_id:
        return jsonify({"error": "company_name or company_id required"}), 400

    # Create session ID
    session_id = str(uuid.uuid4())

    # Create screenshot directory for this session
    base_dir = os.path.dirname(os.path.dirname(__file__))
    screenshot_dir = os.path.join(base_dir, 'static', 'research_screenshots', session_id)
    os.makedirs(screenshot_dir, exist_ok=True)

    # Store in active research with events queue
    active_research[session_id] = {
        "status": "starting",
        "progress": 0,
        "stage": "initializing",
        "company_name": company_name,
        "started_at": datetime.now().isoformat(),
        "events": [],  # Queue of events for SSE
        "screenshot_dir": screenshot_dir
    }

    # Progress callback to store events
    def progress_callback(event):
        """Store event for SSE streaming."""
        active_research[session_id]["events"].append(event)
        # Also update stage based on event type
        if event.get('type') == 'agent.step':
            active_research[session_id]["stage"] = f"{event.get('step_name', 'unknown')}: {event.get('detail', '')}"

    # Run research in background thread
    def run_research():
        try:
            active_research[session_id]["status"] = "running"
            active_research[session_id]["stage"] = "researching"

            result = asyncio.run(research_company(
                company_name=company_name,
                location=location,
                website_url=website_url,
                max_staff_pages=10,
                save_to_db=True,
                progress_callback=progress_callback,
                screenshot_dir=screenshot_dir
            ))

            active_research[session_id]["status"] = "complete"
            active_research[session_id]["progress"] = 100
            active_research[session_id]["stage"] = "complete"
            active_research[session_id]["result"] = {
                "claims_count": len(result.get('claims', [])),
                "summary": result.get('summary', ''),
                "company_id": result.get('company_id')
            }

        except Exception as e:
            logger.error(f"Research failed: {e}")
            active_research[session_id]["status"] = "failed"
            active_research[session_id]["error"] = str(e)

    thread = Thread(target=run_research)
    thread.start()

    return jsonify({
        "session_id": session_id,
        "status": "started",
        "message": f"Research started for {company_name}"
    })


@research_bp.route('/api/research/session/<session_id>')
def api_get_session(session_id):
    """Get research session status and results"""
    # Check active research first
    if session_id in active_research:
        return jsonify(active_research[session_id])

    # Check database
    with get_session() as db:
        session = db.query(ResearchSession).filter_by(id=session_id).first()

        if not session:
            return jsonify({"error": "Session not found"}), 404

        claims = db.query(ResearchClaim).filter_by(session_id=session_id).all()

        return jsonify({
            "id": session.id,
            "company_id": session.company_id,
            "status": session.status,
            "current_stage": session.current_stage,
            "progress_pct": session.progress_pct,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            "claims_count": len(claims),
            "claims": [
                {
                    "id": c.id,
                    "claim_text": c.claim_text,
                    "claim_type": c.claim_type,
                    "confidence": c.confidence,
                    "support_type": c.support_type
                }
                for c in claims
            ]
        })


@research_bp.route('/api/research/session/<session_id>/stream')
def api_session_stream(session_id):
    """SSE stream for real-time research progress with viewer events"""
    def generate():
        event_index = 0  # Track which events we've sent

        while True:
            if session_id in active_research:
                data = active_research[session_id]
                events = data.get('events', [])

                # Send any new events
                while event_index < len(events):
                    event = events[event_index]
                    yield f"data: {json.dumps(event)}\n\n"
                    event_index += 1

                # Send status update
                status_update = {
                    'type': 'run.status',
                    'status': data.get('status'),
                    'stage': data.get('stage'),
                    'progress': data.get('progress', 0),
                    'result': data.get('result')
                }
                yield f"data: {json.dumps(status_update)}\n\n"

                if data.get('status') in ['complete', 'failed']:
                    break
            else:
                yield f"data: {json.dumps({'type': 'run.status', 'status': 'not_found'})}\n\n"
                break

            import time
            time.sleep(0.5)  # Check more frequently for smoother updates

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# =============================================================================
# CLAIMS ENDPOINTS
# =============================================================================

@research_bp.route('/api/research/companies/<company_id>/claims')
def api_get_company_claims(company_id):
    """Get all claims for a company"""
    with get_session() as db:
        claims = db.query(ResearchClaim).filter_by(
            company_id=company_id
        ).order_by(ResearchClaim.claim_type).all()

        result = []
        for claim in claims:
            evidence = db.query(ResearchEvidence).filter_by(
                claim_id=claim.id
            ).all()

            result.append({
                "id": claim.id,
                "claim_text": claim.claim_text,
                "claim_type": claim.claim_type,
                "confidence": claim.confidence,
                "support_type": claim.support_type,
                "created_at": claim.created_at.isoformat() if claim.created_at else None,
                "evidence": [
                    {
                        "id": e.id,
                        "evidence_text": e.evidence_text,
                        "source_url": e.source_url,
                        "source_title": e.source_title,
                        "source_type": e.source_type
                    }
                    for e in evidence
                ]
            })

        return jsonify({
            "company_id": company_id,
            "claims": result,
            "count": len(result)
        })


@research_bp.route('/api/research/claims/<claim_id>', methods=['PUT'])
def api_update_claim(claim_id):
    """Update a claim (e.g., user verification)"""
    data = request.json

    with get_session() as db:
        claim = db.query(ResearchClaim).filter_by(id=claim_id).first()

        if not claim:
            return jsonify({"error": "Claim not found"}), 404

        if 'confidence' in data:
            claim.confidence = data['confidence']
        if 'support_type' in data:
            claim.support_type = data['support_type']

        db.commit()
        return jsonify({"status": "updated"})


# =============================================================================
# QUICK RESEARCH (scrape only, no save)
# =============================================================================

@research_bp.route('/api/research/quick', methods=['POST'])
def api_quick_research():
    """Quick scrape a company without saving to database"""
    data = request.json
    company_name = data.get('company_name')
    website_url = data.get('website_url')
    location = data.get('location')

    if not company_name:
        return jsonify({"error": "company_name required"}), 400

    try:
        result = asyncio.run(scrape_company_deep(
            company_name=company_name,
            location=location,
            website_url=website_url,
            max_staff_pages=5,
            explore_portfolio=True
        ))

        return jsonify({
            "status": "complete",
            "website": result.get('website'),
            "pages_visited": len(result.get('pages_visited', [])),
            "profile": result.get('aggregated', {}),
            "portfolio": result.get('portfolio_data', {}),
            "nav_structure": {k: len(v) for k, v in result.get('nav_structure', {}).items() if v}
        })

    except Exception as e:
        logger.error(f"Quick research failed: {e}")
        return jsonify({"error": str(e)}), 500


# =============================================================================
# BULK IMPORT
# =============================================================================

@research_bp.route('/api/research/import-companies', methods=['POST'])
def api_import_companies():
    """Import companies from existing companies.json file"""
    import os

    companies_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'data', 'companies', 'companies.json'
    )

    if not os.path.exists(companies_path):
        return jsonify({"error": "companies.json not found"}), 404

    with open(companies_path) as f:
        data = json.load(f)

    imported = []
    with get_session() as db:
        for company_type, companies in data.items():
            for name, info in companies.items():
                # Check if exists
                existing = db.query(Company).filter_by(name=name).first()
                if existing:
                    continue

                company = Company(
                    id=str(uuid.uuid4()),
                    name=name,
                    company_type=company_type.rstrip('s'),  # contractors -> contractor
                    website=info.get('website'),
                    phone=info.get('phone'),
                    email=info.get('email'),
                    research_status='pending'
                )
                db.add(company)
                imported.append(name)

        db.commit()

    return jsonify({
        "status": "imported",
        "count": len(imported),
        "companies": imported
    })
