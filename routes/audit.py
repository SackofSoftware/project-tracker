"""
Audit Routes

API endpoints for project folder auditing.
"""

from flask import Blueprint, jsonify, request
from pathlib import Path
import os
import json

from modules.audit.folder_auditor import (
    audit_project_folder,
    scan_folder,
    analyze_organization,
    scan_all_projects_for_duplicates,
    check_rag_analysis_status
)
from utils import BIDDING_FOLDER as _BIDDING_FOLDER

audit_bp = Blueprint('audit', __name__)

BIDDING_FOLDER = Path(_BIDDING_FOLDER)


def find_project_folder(project_id: str) -> Path | None:
    """Find project folder by ID or folder name"""
    for item in BIDDING_FOLDER.iterdir():
        if item.is_dir():
            folder_id = item.name.lower().replace(' ', '-').replace(',', '')
            if folder_id == project_id or item.name == project_id:
                return item
    return None


@audit_bp.route('/api/project/<project_id>/audit')
def get_project_audit(project_id: str):
    """Run audit on a single project folder.

    Query params:
    - use_ai: true/false (default true) - whether to include AI recommendations
    - refresh: true/false (default false) - force re-audit even if cached
    """
    folder = find_project_folder(project_id)
    if not folder:
        return jsonify({'error': 'Project not found', 'project_id': project_id}), 404

    use_ai = request.args.get('use_ai', 'true').lower() == 'true'
    refresh = request.args.get('refresh', 'false').lower() == 'true'

    # Check for cached audit
    audit_file = folder / 'folder_audit.json'
    if audit_file.exists() and not refresh:
        try:
            with open(audit_file, 'r') as f:
                cached = json.load(f)
            # Return cached if less than 24 hours old
            from datetime import datetime
            scanned_at = cached.get('scanned_at', '')
            if scanned_at:
                scanned_date = datetime.fromisoformat(scanned_at)
                age_hours = (datetime.now() - scanned_date).total_seconds() / 3600
                if age_hours < 24:
                    cached['from_cache'] = True
                    return jsonify(cached)
        except:
            pass

    # Run fresh audit
    try:
        result = audit_project_folder(folder, use_ai=use_ai)

        # Cache results
        with open(audit_file, 'w') as f:
            json.dump(result, f, indent=2)

        result['from_cache'] = False
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@audit_bp.route('/api/project/<project_id>/audit/quick')
def get_quick_audit(project_id: str):
    """Run quick audit without AI (just scan and analyze)."""
    folder = find_project_folder(project_id)
    if not folder:
        return jsonify({'error': 'Project not found', 'project_id': project_id}), 404

    try:
        scan_data = scan_folder(folder)
        analysis = analyze_organization(scan_data)

        return jsonify({
            'folder': str(folder),
            'folder_name': folder.name,
            'summary': {
                'total_files': scan_data['total_files'],
                'total_subfolders': scan_data['total_subfolders'],
                'organization_score': analysis['organization_score']
            },
            'issues': analysis['issues'],
            'duplicates': analysis['duplicates'][:10],  # Limit for quick response
            'file_types': {k: len(v) for k, v in analysis['file_classification'].items()}
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@audit_bp.route('/api/audit/batch')
def get_batch_audit_status():
    """Get audit status for all projects (quick scan, no AI)."""
    skip_folders = {'.claude', 'div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman',
                    'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025'}

    results = []
    for item in BIDDING_FOLDER.iterdir():
        if item.is_dir() and not item.name.startswith('.') and item.name not in skip_folders:
            try:
                scan_data = scan_folder(item)
                analysis = analyze_organization(scan_data)

                results.append({
                    'folder': item.name,
                    'id': item.name.lower().replace(' ', '-').replace(',', ''),
                    'total_files': scan_data['total_files'],
                    'total_subfolders': scan_data['total_subfolders'],
                    'organization_score': analysis['organization_score'],
                    'issue_count': len(analysis['issues']),
                    'duplicate_count': len(analysis['duplicates']),
                    'has_cached_audit': (item / 'folder_audit.json').exists()
                })
            except Exception as e:
                results.append({
                    'folder': item.name,
                    'error': str(e)
                })

    # Sort by organization score (worst first)
    results.sort(key=lambda x: x.get('organization_score', 100))

    return jsonify({
        'total_projects': len(results),
        'projects': results,
        'summary': {
            'avg_score': round(sum(r.get('organization_score', 0) for r in results if 'organization_score' in r) / len(results), 1) if results else 0,
            'needs_attention': len([r for r in results if r.get('organization_score', 100) < 70]),
            'well_organized': len([r for r in results if r.get('organization_score', 100) >= 90])
        }
    })


@audit_bp.route('/api/audit/cross-project-duplicates')
def get_cross_project_duplicates():
    """Find duplicate files across all project folders.

    This is a slow operation - scans and hashes all files.
    Results are cached for 24 hours.
    """
    cache_file = BIDDING_FOLDER / '.cross_project_duplicates.json'

    # Check cache
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cached = json.load(f)
            from datetime import datetime
            scanned_at = cached.get('scanned_at', '')
            if scanned_at:
                scanned_date = datetime.fromisoformat(scanned_at)
                age_hours = (datetime.now() - scanned_date).total_seconds() / 3600
                if age_hours < 24:
                    cached['from_cache'] = True
                    return jsonify(cached)
        except:
            pass

    # Run fresh scan
    try:
        result = scan_all_projects_for_duplicates(BIDDING_FOLDER)

        # Cache results
        with open(cache_file, 'w') as f:
            json.dump(result, f, indent=2)

        result['from_cache'] = False
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@audit_bp.route('/api/audit/rag-status')
def get_rag_analysis_status():
    """Check RAG analysis status across all projects.

    Identifies projects that need re-analysis due to:
    - Missing analysis
    - Parse errors
    - Low confidence
    - Stale data (>30 days old)
    - Significant file changes
    """
    try:
        result = check_rag_analysis_status(BIDDING_FOLDER)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@audit_bp.route('/api/audit/rag-reindex', methods=['POST'])
def trigger_rag_reindex():
    """Trigger RAG re-analysis for projects that need it.

    Query params:
    - category: 'all', 'no_analysis', 'parse_errors', 'low_confidence', 'needs_reindex'
    - limit: max number of projects to process (default 5)
    """
    category = request.args.get('category', 'parse_errors')
    limit = int(request.args.get('limit', '5'))

    # Get status first
    status = check_rag_analysis_status(BIDDING_FOLDER)

    # Determine which projects to process
    if category == 'all':
        projects = (
            status['details']['no_analysis'] +
            status['details']['parse_errors'] +
            status['details']['low_confidence'] +
            status['details']['needs_reindex']
        )
    elif category in status['details']:
        projects = status['details'][category]
    else:
        return jsonify({'error': f'Invalid category: {category}'}), 400

    projects = projects[:limit]

    if not projects:
        return jsonify({
            'status': 'no_projects',
            'message': f'No projects found in category: {category}'
        })

    # Queue for processing (don't block - return immediately)
    project_names = [p['project'] for p in projects]

    return jsonify({
        'status': 'queued',
        'category': category,
        'projects_to_process': project_names,
        'count': len(project_names),
        'message': f'Use POST /api/project/<id>/trigger-rag to process each project'
    })
