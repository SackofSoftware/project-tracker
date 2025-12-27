"""
Sync Routes Blueprint

Handles ProjectDog sync and local data refresh operations.
"""

import time
from flask import Blueprint, jsonify

from utils import (
    get_background_sync,
    get_sync_progress,
    set_sync_progress,
    debounced_refresh,
    get_all_projects,
    PROJECTDOG_EMAIL,
    PROJECTDOG_PASSWORD,
    DATA_DIR
)
from modules.planhub.planhub_db_reader import PlanHubDatabaseReader

sync_bp = Blueprint('sync', __name__)


# =============================================================================
# SYNC API ENDPOINTS
# =============================================================================

@sync_bp.route('/api/sync/status')
def api_sync_status():
    """Get current sync status with progress details"""
    background_sync = get_background_sync()
    status = background_sync.get_status()
    status['progress'] = get_sync_progress()

    # Add PlanHub scraper stats
    try:
        reader = PlanHubDatabaseReader()
        status['planhub_stats'] = reader.get_scraper_stats()
    except Exception as e:
        status['planhub_stats'] = {"error": str(e)}

    return jsonify(status)


@sync_bp.route('/api/sync/progress')
def api_sync_progress():
    """Get detailed sync progress"""
    return jsonify(get_sync_progress())


@sync_bp.route('/api/sync/trigger', methods=['POST'])
def api_trigger_sync():
    """Trigger an immediate ProjectDog sync"""
    background_sync = get_background_sync()

    if background_sync.sync_in_progress:
        return jsonify({"status": "error", "message": "Sync already in progress"}), 409

    background_sync.run_now()
    return jsonify({"status": "ok", "message": "Sync started"})


@sync_bp.route('/api/refresh', methods=['POST'])
def api_refresh():
    """Refresh local project data"""
    from utils import _all_projects, _last_refresh

    debounced_refresh.trigger(immediate=True)

    # Get fresh data after refresh
    projects = get_all_projects()

    return jsonify({
        "status": "ok",
        "count": len(projects),
        "last_refresh": _last_refresh.isoformat() if _last_refresh else None
    })


# =============================================================================
# PROJECTDOG SYNC FUNCTION
# =============================================================================

def sync_projectdog():
    """Sync function for background scheduler with progress tracking"""
    if not PROJECTDOG_EMAIL or not PROJECTDOG_PASSWORD:
        print("ProjectDog credentials not configured, skipping sync")
        set_sync_progress({
            "stage": "error",
            "message": "Credentials not configured",
            "error": "Missing PROJECTDOG_EMAIL or PROJECTDOG_PASSWORD"
        })
        return

    try:
        from modules.scraper.projectdog_scraper import ProjectDogScraper

        set_sync_progress({
            "stage": "initializing",
            "message": "Starting browser...",
            "projects_found": 0,
            "projects_with_docs": 0,
            "current_project": 0,
            "total_projects": 0,
            "current_project_name": "",
            "error": None
        })

        print("=" * 60)
        print("PROJECTDOG SYNC STARTED")
        print("=" * 60)

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        scraper = ProjectDogScraper(PROJECTDOG_EMAIL, PROJECTDOG_PASSWORD, headless=False)
        scraper._init_driver()

        # Login
        set_sync_progress({
            **get_sync_progress(),
            "stage": "login",
            "message": "Logging in to ProjectDog..."
        })
        print("[1/5] Logging in to ProjectDog...")

        if not scraper.login():
            set_sync_progress({
                "stage": "error",
                "message": "Login failed",
                "error": "Could not log in to ProjectDog"
            })
            print("ERROR: Login failed!")
            scraper._close_driver()
            return

        print("      Login successful!")

        # Search
        progress = get_sync_progress()
        progress["stage"] = "searching"
        progress["message"] = "Searching Division 8 projects..."
        set_sync_progress(progress)
        print("[2/5] Searching Division 8 projects...")

        projects = scraper.search_division8()

        projects_with_docs = [p for p in projects if p.get('has_documents') and p.get('project_code')]
        go_projects = [p for p in projects if not p.get('has_documents')]

        progress = get_sync_progress()
        progress["projects_found"] = len(projects)
        progress["projects_with_docs"] = len(projects_with_docs)
        progress["message"] = f"Found {len(projects)} projects ({len(projects_with_docs)} with docs, {len(go_projects)} GO)"
        set_sync_progress(progress)

        print(f"      Found {len(projects)} total projects")
        print(f"      - {len(projects_with_docs)} with documents (code)")
        print(f"      - {len(go_projects)} without documents (GO)")

        # Fetch details
        progress = get_sync_progress()
        progress["stage"] = "fetching_details"
        progress["total_projects"] = len(projects_with_docs)
        set_sync_progress(progress)
        print(f"[3/5] Fetching details for {len(projects_with_docs)} projects with documents...")

        for i, project in enumerate(projects_with_docs):
            project_code = project.get('project_code')
            title = project.get('title', '')[:40]

            progress = get_sync_progress()
            progress["current_project"] = i + 1
            progress["current_project_name"] = title
            progress["message"] = f"({i+1}/{len(projects_with_docs)}) {title}"
            set_sync_progress(progress)

            print(f"      [{i+1}/{len(projects_with_docs)}] {project_code}: {title}")

            details = scraper.get_project_details(project_code)
            project.update(details)

            recipients = scraper.get_document_recipients(project_code)
            project['document_recipients'] = recipients
            print(f"               Found {len(recipients)} document recipients")

            documents = scraper.get_document_links(project_code)
            project['documents'] = documents
            print(f"               Found {len(documents)} downloadable documents")

            time.sleep(1)

        # Save
        progress = get_sync_progress()
        progress["stage"] = "saving"
        progress["message"] = "Saving results..."
        set_sync_progress(progress)
        print("[4/5] Saving results...")

        scraper.projects = projects
        scraper.save_results(str(DATA_DIR / "projectdog_projects.json"))

        scraper._close_driver()

        # Refresh
        progress = get_sync_progress()
        progress["stage"] = "refreshing"
        progress["message"] = "Refreshing dashboard..."
        set_sync_progress(progress)
        print("[5/5] Refreshing project list...")

        debounced_refresh.trigger(immediate=True)

        set_sync_progress({
            "stage": "complete",
            "message": f"Sync complete! {len(projects)} projects",
            "projects_found": len(projects),
            "projects_with_docs": len(projects_with_docs),
            "current_project": len(projects_with_docs),
            "total_projects": len(projects_with_docs),
            "current_project_name": "",
            "error": None
        })

        print("=" * 60)
        print(f"SYNC COMPLETE: {len(projects)} projects")
        print(f"  - {len(projects_with_docs)} with documents")
        print(f"  - {len(go_projects)} GO projects")
        print(f"  - {sum(1 for p in projects if p.get('is_rfq'))} RFQ projects")
        print("=" * 60)

    except Exception as e:
        import traceback
        set_sync_progress({
            "stage": "error",
            "message": str(e),
            "error": str(e)
        })
        print(f"SYNC ERROR: {e}")
        traceback.print_exc()
