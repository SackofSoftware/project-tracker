"""
PlanHub Routes Blueprint

Handles PlanHub integration routes including:
- Project matching and linking
- Match statistics and suggestions
- GC logo serving
- PlanHub scraper sync controls
"""

import os
import traceback
from pathlib import Path
from flask import Blueprint, jsonify, request, send_from_directory

from modules.planhub.planhub_reader import load_planhub_projects
from modules.planhub.planhub_db_reader import PlanHubDatabaseReader
from utils import (
    get_all_projects,
    get_bidding_reader,
    get_planhub_matcher,
    get_background_sync,
    debounced_refresh
)

planhub_bp = Blueprint('planhub', __name__)


# =============================================================================
# GC LOGO SERVING
# =============================================================================

@planhub_bp.route('/planhub/gc-logo/<filename>')
def serve_gc_logo(filename):
    """Serve GC logo images from planhub/gc_logos directory"""
    logo_dir = Path(__file__).parent.parent / "planhub" / "gc_logos"
    return send_from_directory(logo_dir, filename)


# =============================================================================
# PLANHUB MATCHER APIs
# =============================================================================

@planhub_bp.route('/api/planhub/matches')
def api_planhub_matches():
    """Get all matched PlanHub-to-local project pairs"""
    planhub_projects = load_planhub_projects()
    bidding_reader = get_bidding_reader()
    local_projects = bidding_reader.read_all_projects()

    planhub_matcher = get_planhub_matcher()
    matches = planhub_matcher.find_matches(planhub_projects, local_projects)
    return jsonify({
        "count": len(matches),
        "matches": matches
    })


@planhub_bp.route('/api/planhub/stats')
def api_planhub_stats():
    """Get matching statistics between PlanHub and local projects"""
    planhub_projects = load_planhub_projects()
    bidding_reader = get_bidding_reader()
    local_projects = bidding_reader.read_all_projects()

    planhub_matcher = get_planhub_matcher()
    stats = planhub_matcher.get_match_stats(planhub_projects, local_projects)
    return jsonify(stats)


@planhub_bp.route('/api/planhub/<planhub_id>/suggestions')
def api_planhub_suggestions(planhub_id):
    """Get match suggestions for a specific PlanHub project"""
    planhub_projects = load_planhub_projects()
    bidding_reader = get_bidding_reader()
    local_projects = bidding_reader.read_all_projects()

    # Find the PlanHub project
    planhub_project = None
    for p in planhub_projects:
        pid = p.get('project_id') or p.get('id', '').replace('planhub-', '')
        if pid == planhub_id or p.get('id') == planhub_id or p.get('id') == f'planhub-{planhub_id}':
            planhub_project = p
            break

    if not planhub_project:
        return jsonify({"error": "PlanHub project not found"}), 404

    planhub_matcher = get_planhub_matcher()
    suggestions = planhub_matcher.get_match_suggestions(planhub_project, local_projects, limit=5)
    current_link = planhub_matcher.get_link(planhub_id)

    return jsonify({
        "planhub_id": planhub_id,
        "current_link": current_link,
        "suggestions": suggestions
    })


@planhub_bp.route('/api/planhub/<planhub_id>/link', methods=['POST'])
def api_planhub_link(planhub_id):
    """Manually link a PlanHub project to a local project"""
    data = request.get_json() or {}
    local_id = data.get('local_id')

    if not local_id:
        return jsonify({"error": "local_id is required"}), 400

    planhub_matcher = get_planhub_matcher()
    success = planhub_matcher.link_projects(planhub_id, local_id)

    if success:
        return jsonify({
            "success": True,
            "planhub_id": planhub_id,
            "local_id": local_id,
            "message": f"Linked PlanHub {planhub_id} to local project {local_id}"
        })
    else:
        return jsonify({"error": "Failed to save link"}), 500


@planhub_bp.route('/api/planhub/<planhub_id>/link', methods=['DELETE'])
def api_planhub_unlink(planhub_id):
    """Remove manual link for a PlanHub project"""
    planhub_matcher = get_planhub_matcher()
    success = planhub_matcher.unlink_project(planhub_id)

    if success:
        return jsonify({
            "success": True,
            "planhub_id": planhub_id,
            "message": f"Unlinked PlanHub {planhub_id}"
        })
    else:
        return jsonify({"error": "Failed to remove link"}), 500


# =============================================================================
# LOCAL PROJECT -> PLANHUB MATCHING (Reverse Lookup)
# =============================================================================

@planhub_bp.route('/api/project/<project_id>/planhub/suggestions')
def api_local_planhub_suggestions(project_id):
    """
    Get PlanHub match suggestions for a local project (reverse lookup).
    This finds PlanHub projects that might match a local folder.
    """
    planhub_projects = load_planhub_projects()
    bidding_reader = get_bidding_reader()
    local_projects = bidding_reader.read_all_projects()
    planhub_matcher = get_planhub_matcher()

    # Find the local project
    local_project = None
    for p in local_projects:
        if p.get('id') == project_id:
            local_project = p
            break

    if not local_project:
        return jsonify({"error": "Local project not found"}), 404

    # Find best matching PlanHub projects
    suggestions = []
    for ph_proj in planhub_projects:
        score, details = planhub_matcher._calculate_match_score(ph_proj, local_project)

        if score >= 0.3:  # Lower threshold for suggestions
            ph_id = ph_proj.get('project_id') or ph_proj.get('id', '').replace('planhub-', '')
            suggestions.append({
                'planhub_id': ph_id,
                'planhub_name': ph_proj.get('project_name') or ph_proj.get('title', ''),
                'planhub_city': ph_proj.get('city', ''),
                'planhub_state': ph_proj.get('state', ''),
                'bid_date': ph_proj.get('bid_date', ''),
                'confidence': round(score, 3),
                'match_details': details,
                'planhub_urls': ph_proj.get('planhub_urls', {}),
                'general_contractors': ph_proj.get('general_contractors', [])
            })

    # Sort by confidence descending, then alphabetically by name
    suggestions.sort(key=lambda x: (-x['confidence'], x['planhub_name'].lower()))

    # Check if already linked
    current_link = None
    for ph_id, local_id in planhub_matcher.manual_links.items():
        if local_id == project_id:
            current_link = ph_id
            break

    # Also check for auto-match
    matches = planhub_matcher.find_matches(planhub_projects, local_projects)
    for match in matches:
        if match.get('local_id') == project_id:
            current_link = match.get('planhub_id')
            break

    return jsonify({
        "local_id": project_id,
        "local_name": local_project.get('title') or local_project.get('folder', ''),
        "current_link": current_link,
        "suggestions": suggestions[:5]  # Top 5
    })


@planhub_bp.route('/api/project/<project_id>/planhub/link', methods=['POST'])
def api_local_link_planhub(project_id):
    """Link a local project to a PlanHub project"""
    data = request.get_json() or {}
    planhub_id = data.get('planhub_id')

    if not planhub_id:
        return jsonify({"error": "planhub_id is required"}), 400

    planhub_matcher = get_planhub_matcher()
    success = planhub_matcher.link_projects(planhub_id, project_id)

    if success:
        # Trigger refresh to merge data
        debounced_refresh()

        return jsonify({
            "success": True,
            "local_id": project_id,
            "planhub_id": planhub_id,
            "message": f"Linked local project {project_id} to PlanHub {planhub_id}"
        })
    else:
        return jsonify({"error": "Failed to save link"}), 500


@planhub_bp.route('/api/project/<project_id>/planhub/link', methods=['DELETE'])
def api_local_unlink_planhub(project_id):
    """Remove PlanHub link from a local project"""
    planhub_matcher = get_planhub_matcher()

    # Find which PlanHub ID is linked to this local project
    planhub_id = None
    for ph_id, local_id in planhub_matcher.manual_links.items():
        if local_id == project_id:
            planhub_id = ph_id
            break

    if not planhub_id:
        return jsonify({"error": "No manual link found for this project"}), 404

    success = planhub_matcher.unlink_project(planhub_id)

    if success:
        # Trigger refresh to update data
        debounced_refresh()

        return jsonify({
            "success": True,
            "local_id": project_id,
            "planhub_id": planhub_id,
            "message": f"Unlinked local project {project_id} from PlanHub {planhub_id}"
        })
    else:
        return jsonify({"error": "Failed to remove link"}), 500


@planhub_bp.route('/api/planhub/projects')
def api_planhub_projects():
    """Get all PlanHub projects (for dropdown/selection UI)"""
    planhub_projects = load_planhub_projects()

    # Return simplified list for UI
    projects = []
    for p in planhub_projects:
        ph_id = p.get('project_id') or p.get('id', '').replace('planhub-', '')
        projects.append({
            'planhub_id': ph_id,
            'name': p.get('project_name') or p.get('title', ''),
            'city': p.get('city', ''),
            'state': p.get('state', ''),
            'bid_date': p.get('bid_date', ''),
            'bid_due_date': p.get('bid_due_date', ''),
            'gc_count': len(p.get('general_contractors', []))
        })

    # Sort alphabetically by name
    projects.sort(key=lambda x: x['name'].lower())

    return jsonify({
        "count": len(projects),
        "projects": projects
    })


@planhub_bp.route('/api/planhub/filter', methods=['POST'])
def api_planhub_filter():
    """
    Filter PlanHub projects by tags and criteria.

    Request body (all fields optional):
    {
        "require_sub_bidding": true,      # Only "Sub Bidding" tagged projects
        "exclude_gc_awarded": true,       # Exclude "GC Awarded" projects
        "division_8_only": true,          # Only Division 8 projects
        "project_type": "Renovation",     # Filter by project type
        "sector": "Commercial",           # Filter by sector
        "state": "MA",                    # Filter by state
        "tags": ["Retail", "New Construction"]  # Must have all listed tags
    }

    Returns:
    {
        "total": 282,
        "filtered": 45,
        "projects": [...filtered projects...]
    }
    """
    try:
        filters = request.get_json() or {}

        # Get all PlanHub projects
        planhub_projects = load_planhub_projects()

        # Apply filters
        filtered = []
        for proj in planhub_projects:
            # Tag filters
            if filters.get('require_sub_bidding') and not proj.get('is_sub_bidding'):
                continue
            if filters.get('exclude_gc_awarded') and proj.get('is_gc_awarded'):
                continue

            # Division 8 filter
            if filters.get('division_8_only') and not proj.get('is_division_8'):
                continue

            # Project type filter
            if filters.get('project_type'):
                if proj.get('project_type') != filters['project_type']:
                    continue

            # Sector filter
            if filters.get('sector'):
                if proj.get('sector') != filters['sector']:
                    continue

            # State filter (handle both unified and legacy formats)
            if filters.get('state'):
                # Check if using unified schema location field
                loc = proj.get('location', {})
                if isinstance(loc, dict):
                    state = loc.get('state')
                else:
                    # Fallback to legacy state field
                    state = proj.get('state')

                if state != filters['state']:
                    continue

            # Multiple tags filter (must have ALL listed tags)
            if filters.get('tags'):
                proj_tags = proj.get('tags', [])
                if not all(tag in proj_tags for tag in filters['tags']):
                    continue

            filtered.append(proj)

        return jsonify({
            "total": len(planhub_projects),
            "filtered": len(filtered),
            "filters_applied": filters,
            "projects": filtered
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# =============================================================================
# PLANHUB SCRAPER SYNC CONTROLS
# =============================================================================

@planhub_bp.route('/api/planhub/sync/trigger', methods=['POST'])
def api_planhub_sync_trigger():
    """Trigger immediate PlanHub scraper run"""
    try:
        background_sync = get_background_sync()

        # Check if sync already in progress
        if background_sync.planhub_sync_in_progress:
            return jsonify({
                "error": "PlanHub sync already in progress"
            }), 409

        # Trigger sync
        background_sync.run_planhub_sync_now()

        return jsonify({
            "status": "ok",
            "message": "PlanHub sync started"
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@planhub_bp.route('/api/planhub/sync/status')
def api_planhub_sync_status():
    """Get PlanHub scraper stats and sync status"""
    try:
        # Get database stats
        db_reader = PlanHubDatabaseReader()
        scraper_stats = db_reader.get_scraper_stats()

        # Get background sync status
        background_sync = get_background_sync()
        sync_status = background_sync.get_status()

        return jsonify({
            "scraper_stats": scraper_stats,
            "sync_status": sync_status.get('planhub', {})
        })

    except FileNotFoundError as e:
        return jsonify({
            "error": f"PlanHub database not found: {str(e)}"
        }), 500

    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@planhub_bp.route('/api/planhub/scraper/reset', methods=['POST'])
def api_planhub_scraper_reset():
    """Reset PlanHub discovery state"""
    try:
        # Import Database from planhub_scraper
        import sys
        planhub_scraper_path = os.getenv('PLANHUB_SCRAPER_PATH')
        if not planhub_scraper_path:
            return jsonify({
                "error": "PLANHUB_SCRAPER_PATH environment variable not set"
            }), 500

        if planhub_scraper_path not in sys.path:
            sys.path.insert(0, planhub_scraper_path)

        from db import Database

        # Get database path
        db_path = os.getenv('PLANHUB_DB_PATH')
        if not db_path:
            return jsonify({
                "error": "PLANHUB_DB_PATH environment variable not set"
            }), 500

        # Reset discovery
        db = Database(Path(db_path))
        db.reset_discovery()

        return jsonify({
            "status": "ok",
            "message": "Discovery state reset"
        })

    except FileNotFoundError as e:
        return jsonify({
            "error": f"PlanHub database not found: {str(e)}"
        }), 500

    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
