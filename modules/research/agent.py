"""
Research Agent - Orchestrates company research and stores structured artifacts.

Pipeline:
1. Vision scraper extracts data from website
2. GPT-OSS generates company summary
3. Creates Claims with Evidence
4. Stores everything in database
"""

import os
import uuid
import requests
import logging
from datetime import datetime
from typing import Dict, Optional, Any

from .vision_scraper import scrape_company_deep, google_search

logger = logging.getLogger(__name__)

# OpenRouter config
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
SUMMARY_MODEL = "openai/gpt-4.1-nano"  # Cheap model for summaries


def generate_company_summary(scraped_data: Dict) -> str:
    """
    Generate a 6-8 sentence company summary using LLM.

    Args:
        scraped_data: Aggregated data from vision scraper

    Returns:
        Company summary string
    """
    if not OPENROUTER_API_KEY:
        return "Summary generation requires OPENROUTER_API_KEY"

    agg = scraped_data.get('aggregated', {})

    # Build context from scraped data
    context_parts = []

    if agg.get('company_name'):
        context_parts.append(f"Company: {agg['company_name']}")
    if agg.get('founded'):
        context_parts.append(f"Founded: {agg['founded']}")
    if agg.get('headquarters'):
        context_parts.append(f"Location: {agg['headquarters']}")
    if agg.get('description'):
        context_parts.append(f"Description: {agg['description']}")
    if agg.get('certifications'):
        context_parts.append(f"Certifications: {', '.join(agg['certifications'])}")
    if agg.get('employee_count'):
        context_parts.append(f"Team size: {agg['employee_count']}")

    # Leadership
    if agg.get('leadership'):
        leaders = [f"{p.get('name')} ({p.get('title')})" for p in agg['leadership'][:5]]
        context_parts.append(f"Leadership: {', '.join(leaders)}")

    # Staff count
    staff_count = len(agg.get('staff', [])) + len(agg.get('leadership', []))
    if staff_count:
        context_parts.append(f"Known staff: {staff_count} people")

    # Services
    if agg.get('services'):
        context_parts.append(f"Services: {', '.join(agg['services'][:5])}")

    context = "\n".join(context_parts)

    prompt = f"""Based on the following company information, write a professional 6-8 sentence summary about this construction company. Focus on what makes them notable, their specialties, leadership, and any certifications.

COMPANY DATA:
{context}

Write a cohesive summary paragraph (6-8 sentences). Be factual and professional. Do not make up information not provided."""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://project-tracker.local",
            },
            json={
                "model": SUMMARY_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5,
                "max_tokens": 500
            },
            timeout=30
        )

        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].strip()
        else:
            logger.error(f"Summary generation failed: {response.status_code}")
            return ""
    except Exception as e:
        logger.error(f"Summary generation error: {e}")
        return ""


def create_claims_from_scraped_data(scraped_data: Dict, session_id: str, company_id: str) -> list:
    """
    Create structured claims from scraped data.

    Each claim is a discrete, verifiable fact with evidence.
    """
    claims = []
    agg = scraped_data.get('aggregated', {})
    website = scraped_data.get('website', '')

    def make_claim(text: str, claim_type: str, confidence: float, evidence_text: str = None):
        claim_id = str(uuid.uuid4())
        return {
            'id': claim_id,
            'session_id': session_id,
            'company_id': company_id,
            'claim_text': text,
            'claim_type': claim_type,
            'confidence': confidence,
            'support_type': 'direct',
            'evidence': [{
                'id': str(uuid.uuid4()),
                'claim_id': claim_id,
                'evidence_text': evidence_text or text,
                'source_url': website,
                'source_title': 'Company Website',
                'source_type': 'website',
                'accessed_at': datetime.now()
            }]
        }

    # Company basics
    if agg.get('company_name'):
        claims.append(make_claim(
            f"The company is named {agg['company_name']}",
            'contact', 0.95
        ))

    if agg.get('founded'):
        claims.append(make_claim(
            f"Company was founded in {agg['founded']}",
            'experience', 0.85
        ))

    if agg.get('headquarters'):
        claims.append(make_claim(
            f"Company headquarters is located at {agg['headquarters']}",
            'contact', 0.80
        ))

    if agg.get('phone'):
        claims.append(make_claim(
            f"Company phone number is {agg['phone']}",
            'contact', 0.90
        ))

    if agg.get('email'):
        claims.append(make_claim(
            f"Company email is {agg['email']}",
            'contact', 0.90
        ))

    # Certifications
    for cert in agg.get('certifications', []):
        claims.append(make_claim(
            f"Company holds {cert} certification",
            'certification', 0.85
        ))

    # Leadership
    for person in agg.get('leadership', []):
        name = person.get('name')
        title = person.get('title')
        if name and title:
            claims.append(make_claim(
                f"{name} serves as {title}",
                'leadership', 0.90,
                person.get('bio')
            ))

    # Staff with titles
    for person in agg.get('staff', []):
        name = person.get('name')
        title = person.get('title')
        if name and title:
            claims.append(make_claim(
                f"{name} works as {title}",
                'leadership', 0.85
            ))

    # Social presence
    social = agg.get('social_links', {})
    if social.get('linkedin'):
        claims.append(make_claim(
            f"Company has LinkedIn presence",
            'contact', 0.95,
            f"LinkedIn: {social['linkedin']}"
        ))

    return claims


async def research_company(
    company_name: str,
    location: str = None,
    website_url: str = None,
    max_staff_pages: int = 10,
    save_to_db: bool = True,
    progress_callback: callable = None,
    screenshot_dir: str = None
) -> Dict[str, Any]:
    """
    Full research pipeline for a company.

    Args:
        company_name: Company to research
        location: Optional location hint
        website_url: Optional known website
        max_staff_pages: Max staff pages to visit
        save_to_db: Whether to save to database
        progress_callback: Optional callback for streaming progress updates
        screenshot_dir: Optional directory to save screenshots

    Returns:
        Complete research result with profile, claims, and summary
    """
    result = {
        'company_name': company_name,
        'session_id': str(uuid.uuid4()),
        'company_id': str(uuid.uuid4()),
        'status': 'running',
        'started_at': datetime.now(),
        'scraped_data': {},
        'profile': {},
        'claims': [],
        'summary': '',
        'error': None
    }

    try:
        # Step 1: Vision scrape
        logger.info(f"Starting research for: {company_name}")
        scraped = await scrape_company_deep(
            company_name,
            location=location,
            website_url=website_url,
            max_staff_pages=max_staff_pages,
            progress_callback=progress_callback,
            screenshot_dir=screenshot_dir
        )
        result['scraped_data'] = scraped
        result['profile'] = scraped.get('aggregated', {})

        # Step 2: Generate summary
        logger.info("Generating company summary...")
        summary = generate_company_summary(scraped)
        result['summary'] = summary
        result['profile']['company_summary'] = summary

        # Step 3: Create claims
        logger.info("Creating structured claims...")
        claims = create_claims_from_scraped_data(
            scraped,
            result['session_id'],
            result['company_id']
        )
        result['claims'] = claims

        result['status'] = 'complete'
        result['completed_at'] = datetime.now()

        # Step 4: Save to database (if requested)
        if save_to_db:
            try:
                save_research_to_db(result)
                logger.info("Saved to database")
            except Exception as e:
                logger.error(f"Database save failed: {e}")
                result['db_error'] = str(e)

        logger.info(f"Research complete! {len(claims)} claims generated.")

    except Exception as e:
        logger.error(f"Research failed: {e}")
        result['status'] = 'failed'
        result['error'] = str(e)

    return result


def save_research_to_db(result: Dict):
    """Save research results to database."""
    from modules.database.db import get_session
    from modules.database.models import (
        Company, ResearchSession, ResearchClaim, ResearchEvidence
    )

    profile = result.get('profile', {})
    original_name = result.get('company_name')  # Original search name
    scraped_name = profile.get('company_name')  # Name from website

    with get_session() as db:
        # Try to find existing company - first by original name, then by scraped name
        company = None
        if original_name:
            company = db.query(Company).filter_by(name=original_name).first()
        if not company and scraped_name and scraped_name != original_name:
            company = db.query(Company).filter_by(name=scraped_name).first()

        if not company:
            # Create new company - use original name if available
            company = Company(
                id=result['company_id'],
                name=original_name or scraped_name,
                company_type='contractor'
            )
            db.add(company)
        else:
            result['company_id'] = company.id

        # Helper to convert dict to string for non-JSON columns
        def to_string(val):
            if val is None:
                return None
            if isinstance(val, dict):
                # For headquarters, try to get a string representation
                if 'address' in val:
                    return val['address']
                elif 'full' in val:
                    return val['full']
                return json.dumps(val)
            return str(val) if val else None

        # Update company fields
        company.website = profile.get('website')
        company.founded = profile.get('founded')
        company.headquarters = to_string(profile.get('headquarters'))
        company.phone = to_string(profile.get('phone'))
        company.email = to_string(profile.get('email'))
        company.description = profile.get('description')
        company.company_summary = profile.get('company_summary')
        company.certifications = profile.get('certifications')
        company.leadership = profile.get('leadership')
        company.staff = {'staff': profile.get('staff', [])}
        company.social_links = profile.get('social_links')
        company.portfolio = result.get('scraped_data', {}).get('portfolio_data')
        company.research_status = 'complete'
        company.last_researched = datetime.now()

        db.flush()

        # Create research session
        session = ResearchSession(
            id=result['session_id'],
            company_id=company.id,
            query=f"Research {profile.get('company_name')}",
            status='complete',
            started_at=result.get('started_at'),
            completed_at=result.get('completed_at'),
            current_stage='complete',
            progress_pct=100,
            sources_used=result.get('scraped_data', {}).get('pages_visited', [])
        )
        db.add(session)
        db.flush()

        # Create claims with evidence
        for claim_data in result.get('claims', []):
            claim = ResearchClaim(
                id=claim_data['id'],
                session_id=session.id,
                company_id=company.id,
                claim_text=claim_data['claim_text'],
                claim_type=claim_data['claim_type'],
                confidence=claim_data['confidence'],
                support_type=claim_data['support_type']
            )
            db.add(claim)

            for ev_data in claim_data.get('evidence', []):
                evidence = ResearchEvidence(
                    id=ev_data['id'],
                    claim_id=claim.id,
                    evidence_text=ev_data['evidence_text'],
                    source_url=ev_data['source_url'],
                    source_title=ev_data['source_title'],
                    source_type=ev_data['source_type'],
                    accessed_at=ev_data['accessed_at']
                )
                db.add(evidence)


# Sync wrapper
def research_company_sync(
    company_name: str,
    location: str = None,
    website_url: str = None,
    max_staff_pages: int = 10,
    save_to_db: bool = True
) -> Dict:
    """Synchronous wrapper for research_company."""
    import asyncio
    return asyncio.run(research_company(
        company_name, location, website_url, max_staff_pages, save_to_db
    ))


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    result = research_company_sync(
        "Kaplan Construction",
        website_url="https://www.kaplanconstructs.com",
        max_staff_pages=3,
        save_to_db=False
    )

    print("\n" + "="*60)
    print("RESEARCH RESULT")
    print("="*60)
    print(f"Status: {result['status']}")
    print(f"Claims: {len(result['claims'])}")
    print(f"\nSUMMARY:\n{result['summary']}")
    print(f"\nPROFILE:")
    print(json.dumps(result['profile'], indent=2, default=str)[:2000])
