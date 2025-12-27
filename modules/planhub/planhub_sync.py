"""
PlanHub Background Sync Function
Runs the PlanHub scraper on a schedule
"""

import os
from pathlib import Path
from datetime import datetime


def sync_planhub():
    """
    Sync function for background scheduler.

    Runs the PlanHub scraper in the configured mode (fast/full/discover).
    Updates global sync progress for status endpoint.
    """

    # Get configuration
    scraper_mode = os.getenv('PLANHUB_SCRAPER_MODE', 'fast')
    db_path = os.getenv('PLANHUB_DB_PATH')

    if not db_path or not Path(db_path).exists():
        print("PlanHub database not configured or not found")
        print(f"PLANHUB_DB_PATH: {db_path}")
        return

    try:
        from modules.planhub_scraper import PlanHubScraper
        from modules.planhub_scraper.db import Database

        print("=" * 60)
        print("PLANHUB SYNC STARTED")
        print(f"Mode: {scraper_mode}")
        print(f"Time: {datetime.now().isoformat()}")
        print("=" * 60)

        # Choose scraper based on mode
        if scraper_mode == 'discover':
            # Just discovery phase - find new leads
            print("Running discovery mode - finding new leads...")
            scraper = PlanHubScraper()
            scraper.start(headless=True)
            try:
                scraper.ensure_logged_in()
                scraper.discover_leads()
            finally:
                scraper.stop()

        elif scraper_mode == 'fast':
            # Fast parallel scraper (4 workers, ~2.3s per lead)
            print("Running fast mode - parallel extraction...")
            from modules.planhub_scraper.fast_scraper import run_fast_scrape
            run_fast_scrape()

        elif scraper_mode == 'full':
            # Full 6-tab extractor
            print("Running full mode - comprehensive 6-tab extraction...")
            print("Note: Full mode not yet implemented, running fast mode instead")
            from modules.planhub_scraper.fast_scraper import run_fast_scrape
            run_fast_scrape()

        else:
            print(f"Unknown scraper mode: {scraper_mode}")
            print("Valid modes: discover, fast, full")
            return

        # Get final stats
        try:
            with Database(db_path) as db:
                stats = db.get_stats()
                print(f"\nSYNC COMPLETE: {stats['total']} total leads")
                print(f"  - Done: {stats['done']}")
                print(f"  - Queued: {stats['queued']}")
                print(f"  - Skipped: {stats['skipped']}")
                print(f"  - Errors: {stats['error']}")
        except Exception as e:
            print(f"Error getting final stats: {e}")

        print("=" * 60)

        # Trigger project refresh after sync
        try:
            from utils import debounced_refresh
            debounced_refresh.trigger(immediate=True)
            print("Triggered project refresh")
        except Exception as e:
            print(f"Error triggering refresh: {e}")

    except Exception as e:
        import traceback
        print(f"PLANHUB SYNC ERROR: {e}")
        traceback.print_exc()
        print("=" * 60)
