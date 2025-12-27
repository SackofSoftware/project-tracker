"""
Project Linking Routes Blueprint

Handles project source linking API endpoints for creating, removing,
and querying links between external sources and canonical local projects.
"""

from flask import Blueprint, jsonify, request
import logging
import json
import os

from modules.linking.link_service import get_link_service, ProjectLinkService
from utils import get_all_projects

logger = logging.getLogger(__name__)

linking_bp = Blueprint('linking', __name__)


def _load_projectdog_from_cache() -> list:
    """Load ProjectDog projects from JSON cache file"""
    cache_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'static', 'data', 'projectdog_projects.json'
    )
    try:
        if os.path.exists(cache_path):
            with open(cache_path, 'r') as f:
                data = json.load(f)
                return data.get('projects', [])
    except Exception as e:
        logger.error(f"Error loading ProjectDog cache: {e}")
    return []


# =============================================================================
# PROJECT-SPECIFIC LINKING ENDPOINTS
# =============================================================================

@linking_bp.route('/api/project/<project_id>/links')
def get_project_links(project_id: str):
    """Get all external sources linked to a project"""
    service = get_link_service()
    links = service.get_linked_sources(project_id)

    return jsonify({
        'project_id': project_id,
        'links': links,
        'count': len(links)
    })


@linking_bp.route('/api/project/<project_id>/links/suggested')
def get_project_suggested_links(project_id: str):
    """Get suggested (potential) links for a project based on fuzzy matching"""
    from utils import get_all_projects

    # Find the project
    projects = get_all_projects()
    local_project = None
    for p in projects:
        if p.get('id') == project_id:
            local_project = p
            break

    if not local_project:
        return jsonify({'error': 'Project not found'}), 404

    suggestions = []

    # Check ProjectDog for potential matches
    try:
        from modules.linking.projectdog_matcher import ProjectDogMatcher

        pd_projects = _load_projectdog_from_cache()

        matcher = ProjectDogMatcher()
        service = get_link_service()
        existing_links = service.get_all_links_by_source_type('projectdog')

        for pd_proj in pd_projects:
            # Use project_code or interest_list_id as source_id
            source_id = pd_proj.get('project_code') or pd_proj.get('interest_list_id')
            if not source_id:
                continue  # Skip projects without an ID

            if source_id in existing_links:
                continue  # Already linked

            score = matcher.calculate_match_score(pd_proj, local_project)
            if score >= matcher.SUGGEST_THRESHOLD:
                suggestions.append({
                    'source_type': 'projectdog',
                    'source_id': source_id,
                    'title': pd_proj.get('title'),
                    'confidence': round(score, 3),
                    'data': pd_proj
                })

    except Exception as e:
        logger.error(f"Error checking ProjectDog suggestions: {e}")

    # Sort by confidence descending
    suggestions.sort(key=lambda x: x['confidence'], reverse=True)

    return jsonify({
        'project_id': project_id,
        'suggestions': suggestions[:10],  # Limit to top 10
        'count': len(suggestions)
    })


@linking_bp.route('/api/project/<project_id>/links', methods=['POST'])
def create_project_link(project_id: str):
    """
    Create a link between a project and an external source.

    Request body:
    {
        "source_type": "projectdog",
        "source_id": "123456",
        "source_data": {...}  // Optional
    }
    """
    data = request.get_json() or {}

    source_type = data.get('source_type')
    source_id = data.get('source_id')

    if not source_type or not source_id:
        return jsonify({'error': 'source_type and source_id are required'}), 400

    service = get_link_service()
    link = service.link_project(
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
        confidence=1.0,
        match_type='manual',
        matched_by='user',
        source_data=data.get('source_data')
    )

    if link:
        return jsonify({
            'success': True,
            'link': {
                'project_id': project_id,
                'source_type': source_type,
                'source_id': source_id,
                'confidence': link.match_confidence,
                'match_type': link.match_type
            }
        })

    return jsonify({'error': 'Failed to create link'}), 500


@linking_bp.route('/api/project/<project_id>/links/<source_type>/<source_id>', methods=['DELETE'])
def delete_project_link(project_id: str, source_type: str, source_id: str):
    """Remove a link between a project and an external source"""
    service = get_link_service()
    success = service.unlink_project(project_id, source_type, source_id)

    if success:
        return jsonify({
            'success': True,
            'message': f'Removed link {source_type}:{source_id} from {project_id}'
        })

    return jsonify({'error': 'Link not found'}), 404


# =============================================================================
# GLOBAL LINKING ENDPOINTS
# =============================================================================

@linking_bp.route('/api/linking/stats')
def linking_stats():
    """Get link statistics by source type"""
    service = get_link_service()
    stats = service.get_stats()

    return jsonify({
        'stats': stats
    })


@linking_bp.route('/api/linking/unlinked')
def get_unlinked_sources():
    """Get all external source records that are not linked to any project"""
    source_type = request.args.get('source_type')
    unlinked = {}

    service = get_link_service()

    # Check ProjectDog
    if not source_type or source_type == 'projectdog':
        try:
            pd_projects = _load_projectdog_from_cache()
            pd_ids = [p.get('project_code') for p in pd_projects if p.get('project_code')]

            linked_ids = service.get_all_links_by_source_type('projectdog')
            unlinked_ids = [pid for pid in pd_ids if pid not in linked_ids]

            unlinked['projectdog'] = {
                'total': len(pd_ids),
                'linked': len(linked_ids),
                'unlinked': len(unlinked_ids),
                'unlinked_ids': unlinked_ids[:50]  # Limit for response size
            }
        except Exception as e:
            logger.error(f"Error checking ProjectDog unlinked: {e}")

    return jsonify(unlinked)


@linking_bp.route('/api/linking/run-matching', methods=['POST'])
def run_auto_matching():
    """
    Trigger automatic matching for a source type.

    Request body:
    {
        "source_type": "projectdog",  // Optional, runs all if not specified
        "create_links": true  // If true, creates auto-match links
    }
    """
    data = request.get_json() or {}
    source_type = data.get('source_type')
    create_links = data.get('create_links', False)

    results = {}

    # Get local projects for matching
    local_projects = [p for p in get_all_projects() if p.get('source') in ('local_folder', 'local_bidding', 'local_extracted')]

    service = get_link_service()

    # Run ProjectDog matching
    if not source_type or source_type == 'projectdog':
        try:
            from modules.linking.projectdog_matcher import ProjectDogMatcher

            pd_projects = _load_projectdog_from_cache()

            matcher = ProjectDogMatcher()
            existing_links = service.get_all_links_by_source_type('projectdog')

            matches = matcher.find_matches(pd_projects, local_projects, existing_links)

            results['projectdog'] = {
                'auto_matches': len(matches['auto']),
                'suggestions': len(matches['suggested']),
                'matches': matches
            }

            # Create links for auto-matches if requested
            if create_links and matches['auto']:
                links_to_create = [
                    {
                        'project_id': m['local_id'],
                        'source_type': 'projectdog',
                        'source_id': m['source_id'],
                        'confidence': m['confidence'],
                        'match_type': 'auto',
                        'source_data': m['source']
                    }
                    for m in matches['auto']
                ]
                stats = service.bulk_create_links(links_to_create, matched_by='system')
                results['projectdog']['links_created'] = stats

        except Exception as e:
            logger.error(f"Error running ProjectDog matching: {e}")
            results['projectdog'] = {'error': str(e)}

    return jsonify({
        'success': True,
        'results': results
    })


@linking_bp.route('/api/linking/source/<source_type>/<source_id>')
def get_link_for_source(source_type: str, source_id: str):
    """Check if a specific source ID is linked to any project"""
    service = get_link_service()
    link = service.get_link_by_source(source_type, source_id)

    if link:
        return jsonify({
            'linked': True,
            'link': link
        })

    return jsonify({
        'linked': False,
        'source_type': source_type,
        'source_id': source_id
    })
