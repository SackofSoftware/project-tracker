"""
PlanHub Scraper Module

Playwright-based scraper for extracting construction project leads from PlanHub.

Usage:
    from modules.planhub_scraper import PlanHubScraper, Database

    scraper = PlanHubScraper(log_callback=my_callback)
    scraper.run()
"""

from .scraper import PlanHubScraper
from .db import Database, Lead, ProjectFile, init_database, show_stats
from .config import (
    HEADLESS, SESSION_FILE, DB_PATH, BASE_DIR,
    ensure_dirs
)

__all__ = [
    'PlanHubScraper',
    'Database',
    'Lead',
    'ProjectFile',
    'init_database',
    'show_stats',
    'HEADLESS',
    'SESSION_FILE',
    'DB_PATH',
    'BASE_DIR',
    'ensure_dirs',
]
