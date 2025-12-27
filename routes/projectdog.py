"""
ProjectDog Routes Blueprint

Handles ProjectDog-specific document operations:
- Document listing
- Document downloads (single and batch)
- ProjectDog statistics
- GC logo serving (PlanHub integration)
"""

import json
import time
import threading
from pathlib import Path
from datetime import datetime

from flask import Blueprint, jsonify, request, send_from_directory

from utils import (
    load_projectdog_cache,
    PROJECTDOG_EMAIL,
    PROJECTDOG_PASSWORD,
    BIDDING_FOLDER,
    DATA_DIR,
    debounced_refresh
)

projectdog_bp = Blueprint('projectdog', __name__)


# =============================================================================
# PROJECTDOG DOCUMENT APIs
# =============================================================================

@projectdog_bp.route('/api/projectdog/<project_code>/documents')
def api_projectdog_documents(project_code):
    """Get list of available documents for a ProjectDog project"""
    # Find the project in cache
    pd_projects = load_projectdog_cache()
    project = None
    for p in pd_projects:
        if p.get('project_code') == project_code:
            project = p
            break

    if not project:
        return jsonify({"error": "Project not found", "project_code": project_code}), 404

    return jsonify({
        "project_code": project_code,
        "title": project.get('title'),
        "has_documents": project.get('has_documents', False),
        "documents_acquired": project.get('documents_acquired', False),
        "documents_folder": project.get('documents_folder'),
        "documents": project.get('documents', []),
        "document_recipients": project.get('document_recipients', [])
    })


@projectdog_bp.route('/api/projectdog/<project_code>/download', methods=['POST'])
def api_projectdog_download(project_code):
    """Download documents for a ProjectDog project to bidding folder"""
    from modules.scraper.projectdog_scraper import ProjectDogScraper

    if not PROJECTDOG_EMAIL or not PROJECTDOG_PASSWORD:
        return jsonify({"error": "ProjectDog credentials not configured"}), 500

    if not BIDDING_FOLDER:
        return jsonify({"error": "Bidding folder not configured"}), 500

    # Find the project
    pd_projects = load_projectdog_cache()
    project = None
    for p in pd_projects:
        if p.get('project_code') == project_code:
            project = p
            break

    if not project:
        return jsonify({"error": "Project not found"}), 404

    if not project.get('has_documents'):
        return jsonify({"error": "This project has no documents available (GO project)"}), 400

    # Start download in background thread
    def do_download():
        scraper = None
        try:
            scraper = ProjectDogScraper(PROJECTDOG_EMAIL, PROJECTDOG_PASSWORD, headless=False)
            scraper._init_driver()

            if not scraper.login():
                print(f"Failed to login for download of {project_code}")
                return

            # Create project folder
            folder_name = scraper.make_project_folder_name(project)
            project_folder = Path(BIDDING_FOLDER) / folder_name
            project_folder.mkdir(parents=True, exist_ok=True)

            # Download documents
            result = scraper.download_project_documents(project_code, project_folder)

            # Update cache with download info
            project['documents'] = result.get('documents', [])
            project['documents_acquired'] = result.get('success', False)
            project['documents_folder'] = folder_name

            # Get document recipients
            recipients = scraper.get_document_recipients(project_code)
            project['document_recipients'] = recipients

            # Save updated cache
            cache_file = DATA_DIR / "projectdog_projects.json"
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)

            for i, p in enumerate(cache_data.get('projects', [])):
                if p.get('project_code') == project_code:
                    cache_data['projects'][i] = project
                    break

            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            # Save metadata to project folder
            metadata = {
                "source": "projectdog",
                "project_code": project_code,
                "title": project.get('title'),
                "scraped_at": datetime.now().isoformat(),
                "bid_date": project.get('bid_date'),
                "estimated_value": project.get('estimated_value'),
                "location": project.get('location'),
                "owner": project.get('owner'),
                "architect": project.get('architect'),
                "is_rfq": project.get('is_rfq'),
                "is_dcam": project.get('is_dcam'),
                "documents": project.get('documents', []),
                "document_recipients": recipients
            }
            metadata_path = project_folder / "projectdog_metadata.json"
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            print(f"Download complete for {project_code}: {folder_name}")

            # Refresh project list
            debounced_refresh.trigger(immediate=True)

        except Exception as e:
            print(f"Error downloading documents for {project_code}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if scraper:
                scraper._close_driver()

    thread = threading.Thread(target=do_download)
    thread.start()

    return jsonify({
        "status": "started",
        "project_code": project_code,
        "title": project.get('title'),
        "message": f"Download started for {project.get('title')}. Check project folder for documents."
    })


@projectdog_bp.route('/api/projectdog/download-all', methods=['POST'])
def api_projectdog_download_all():
    """Download documents for all ProjectDog projects with documents"""
    from modules.scraper.projectdog_scraper import ProjectDogScraper

    if not PROJECTDOG_EMAIL or not PROJECTDOG_PASSWORD:
        return jsonify({"error": "ProjectDog credentials not configured"}), 500

    if not BIDDING_FOLDER:
        return jsonify({"error": "Bidding folder not configured"}), 500

    data = request.get_json() or {}
    max_projects = data.get('max_projects', 10)

    # Get projects with documents that haven't been downloaded
    pd_projects = load_projectdog_cache()
    projects_to_download = [
        p for p in pd_projects
        if p.get('has_documents') and p.get('project_code') and not p.get('documents_acquired')
    ][:max_projects]

    if not projects_to_download:
        return jsonify({
            "status": "complete",
            "message": "No projects need downloading"
        })

    def do_batch_download():
        scraper = None
        try:
            scraper = ProjectDogScraper(PROJECTDOG_EMAIL, PROJECTDOG_PASSWORD, headless=False)
            scraper._init_driver()

            if not scraper.login():
                print("Failed to login for batch download")
                return

            for project in projects_to_download:
                project_code = project.get('project_code')
                print(f"Downloading: {project.get('title')}")

                folder_name = scraper.make_project_folder_name(project)
                project_folder = Path(BIDDING_FOLDER) / folder_name
                project_folder.mkdir(parents=True, exist_ok=True)

                result = scraper.download_project_documents(project_code, project_folder)
                project['documents'] = result.get('documents', [])
                project['documents_acquired'] = result.get('success', False)
                project['documents_folder'] = folder_name

                recipients = scraper.get_document_recipients(project_code)
                project['document_recipients'] = recipients

                # Save metadata
                metadata = {
                    "source": "projectdog",
                    "project_code": project_code,
                    "title": project.get('title'),
                    "scraped_at": datetime.now().isoformat(),
                    "documents": project.get('documents', []),
                    "document_recipients": recipients
                }
                with open(project_folder / "projectdog_metadata.json", 'w') as f:
                    json.dump(metadata, f, indent=2)

                time.sleep(2)  # Rate limiting

            # Update cache
            cache_file = DATA_DIR / "projectdog_projects.json"
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)

            # Update projects in cache
            project_codes = {p.get('project_code') for p in projects_to_download}
            for i, p in enumerate(cache_data.get('projects', [])):
                if p.get('project_code') in project_codes:
                    for updated in projects_to_download:
                        if updated.get('project_code') == p.get('project_code'):
                            cache_data['projects'][i] = updated
                            break

            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            debounced_refresh.trigger(immediate=True)
            print(f"Batch download complete: {len(projects_to_download)} projects")

        except Exception as e:
            print(f"Error in batch download: {e}")
        finally:
            if scraper:
                scraper._close_driver()

    thread = threading.Thread(target=do_batch_download)
    thread.start()

    return jsonify({
        "status": "started",
        "projects_count": len(projects_to_download),
        "projects": [{"code": p.get('project_code'), "title": p.get('title')} for p in projects_to_download],
        "message": f"Batch download started for {len(projects_to_download)} projects"
    })


@projectdog_bp.route('/api/projectdog/stats')
def api_projectdog_stats():
    """Get statistics about ProjectDog projects"""
    pd_projects = load_projectdog_cache()

    total = len(pd_projects)
    with_docs = sum(1 for p in pd_projects if p.get('has_documents'))
    go_projects = sum(1 for p in pd_projects if not p.get('has_documents'))
    rfq_count = sum(1 for p in pd_projects if p.get('is_rfq'))
    dcam_count = sum(1 for p in pd_projects if p.get('is_dcam'))
    downloaded = sum(1 for p in pd_projects if p.get('documents_acquired'))

    return jsonify({
        "total": total,
        "with_documents": with_docs,
        "go_projects": go_projects,
        "rfq_count": rfq_count,
        "dcam_count": dcam_count,
        "downloaded": downloaded,
        "pending_download": with_docs - downloaded
    })


# =============================================================================
# PLANHUB GC LOGO SERVING
# =============================================================================

@projectdog_bp.route('/planhub/gc-logo/<filename>')
def serve_gc_logo(filename):
    """Serve GC logo images from planhub/gc_logos directory"""
    logo_dir = Path(__file__).parent.parent / "planhub" / "gc_logos"
    return send_from_directory(logo_dir, filename)
