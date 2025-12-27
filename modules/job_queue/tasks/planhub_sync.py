"""
PlanHub Sync Task Handler

Executes PlanHub scraper as a background job with progress reporting.
"""
from typing import Callable, Dict, Any

from modules.job_queue import Job


def handle_planhub_sync(job: Job, progress_callback: Callable) -> Dict[str, Any]:
    """
    Execute PlanHub scraper as a background job.

    Args:
        job: The job being executed
        progress_callback: Function to report progress
            - progress_callback(progress=0.5, message="...", phase="...", log=True, level="info")

    Returns:
        Result dict with summary statistics
    """
    from modules.planhub_scraper import PlanHubScraper, Database
    from modules.planhub_scraper.exporter import export_to_json

    progress_callback(progress=0.01, message="Initializing PlanHub sync...", phase="init")

    # Create log callback that routes to progress_callback
    def log_callback(message: str, level: str = 'info'):
        progress_callback(message=message, log=True, level=level)

    # Initialize scraper
    scraper = PlanHubScraper(log_callback=log_callback)
    scraper.db = Database()
    scraper.db.connect()
    scraper.db.create_tables()
    scraper.db.reset_in_progress()

    try:
        # Phase 1: Start browser and check auth
        progress_callback(progress=0.05, message="Starting browser...", phase="auth")
        scraper.start(headless=True)

        progress_callback(progress=0.08, message="Checking session...", phase="auth")
        if not scraper.is_logged_in():
            raise Exception("PlanHub session expired - manual login required. Run: python -m modules.planhub_scraper.scraper login")

        progress_callback(progress=0.10, message="Session valid", phase="auth", log=True, level="success")

        # Phase 2: Discovery (if needed)
        state = scraper.db.get_pagination_state()
        if not state or not state.get('discovery_complete'):
            progress_callback(progress=0.12, message="Discovering leads...", phase="discovery")

            # Run discovery with progress updates
            scraper.discover_all_leads()

            # Update progress after discovery
            stats = scraper.db.get_stats()
            progress_callback(
                progress=0.30,
                message=f"Discovery complete: {stats.get('total_leads', 0)} leads found",
                phase="discovery",
                log=True,
                level="success"
            )
        else:
            progress_callback(progress=0.30, message="Discovery already complete", phase="discovery")

        # Phase 3: Scrape individual leads
        progress_callback(progress=0.32, message="Scraping lead details...", phase="scraping")

        stats = scraper.db.get_stats()
        total_to_process = stats.get('queued', 0)
        processed = 0

        while scraper.running:
            # Check for cancellation
            lead = scraper.db.get_next_queued()
            if not lead:
                break

            scraper.db.mark_in_progress(lead.id)

            try:
                data = scraper.scrape_lead(lead)
                scraper.db.save_lead_data(lead.id, data)

                for file_data in data.get('project_files', []):
                    if isinstance(file_data, dict) and not file_data.get('_total_count'):
                        scraper.db.add_file(lead.id, file_data)

                scraper.db.mark_done(lead.id)
                processed += 1

                # Calculate progress (30% to 90% during scraping)
                if total_to_process > 0:
                    scrape_progress = 0.30 + (0.60 * processed / total_to_process)
                else:
                    scrape_progress = 0.90

                progress_callback(
                    progress=scrape_progress,
                    message=f"Scraped: {lead.name[:40]}... ({processed}/{total_to_process})",
                    phase="scraping"
                )

            except Exception as e:
                error_msg = str(e)
                scraper.log(f"Error scraping {lead.name}: {error_msg}", 'error')

                html_path = scraper.save_fallback_html(lead)
                if html_path:
                    scraper.db.save_raw_html(lead.id, html_path)

                scraper.db.mark_error(lead.id, error_msg)

                # Check for session expiry
                if "session expired" in error_msg.lower() or "re-login" in error_msg.lower():
                    raise Exception("PlanHub session expired during scraping")

            # Brief pause between leads
            import time
            time.sleep(2)

        # Phase 4: Export results
        progress_callback(progress=0.92, message="Exporting results...", phase="export")

        export_result = export_to_json(scraper.db)
        progress_callback(
            progress=0.95,
            message=f"Exported {export_result['count']} projects",
            phase="export",
            log=True,
            level="success"
        )

        # Phase 5: Refresh project data
        progress_callback(progress=0.97, message="Refreshing project data...", phase="refresh")

        try:
            # Trigger project data refresh
            from utils import debounced_refresh
            if hasattr(debounced_refresh, 'trigger'):
                debounced_refresh.trigger(immediate=True)
        except Exception as e:
            progress_callback(message=f"Refresh warning: {e}", log=True, level="warning")

        # Done
        final_stats = scraper.db.get_stats()
        progress_callback(
            progress=1.0,
            message=f"PlanHub sync complete: {processed} leads processed",
            phase="complete",
            log=True,
            level="success"
        )

        return {
            'leads_processed': processed,
            'total_leads': final_stats.get('total_leads', 0),
            'done': final_stats.get('done', 0),
            'errors': final_stats.get('error', 0),
            'locked': final_stats.get('locked', 0),
            'exported': export_result['count'],
        }

    finally:
        scraper.stop()
        scraper.db.close()


# Register with task handlers
TASK_TYPE = 'planhub_sync'
TASK_HANDLER = handle_planhub_sync
