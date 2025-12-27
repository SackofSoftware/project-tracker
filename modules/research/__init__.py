"""
Research Module - Company Research with Structured Artifacts

Uses Vision Models + LLM for cost-effective company research.
- Vision scraper: Screenshots + Gemma 3 (free) for extraction
- Summary generation: GPT-OSS or similar cheap model
- Structured artifacts: Claims, Evidence stored in database

Cost: ~$0.002-0.005 per company
"""

from .vision_scraper import (
    scrape_company_deep,
    scrape_company_sync,
    google_search,
    find_company_website
)

from .agent import (
    research_company,
    research_company_sync,
    generate_company_summary,
    save_research_to_db
)

__all__ = [
    # Vision scraper
    'scrape_company_deep',
    'scrape_company_sync',
    'google_search',
    'find_company_website',
    # Research agent
    'research_company',
    'research_company_sync',
    'generate_company_summary',
    'save_research_to_db',
]
