"""
RAG Analysis Routes

API endpoints for RAG (Retrieval Augmented Generation) analysis data.
"""

from flask import Blueprint, jsonify, request
from pathlib import Path
import json
import os
from datetime import datetime
import threading

from utils import BIDDING_FOLDER as _BIDDING_FOLDER

rag_bp = Blueprint('rag', __name__)

# Size thresholds for automatic processing
MAX_CHUNKS_AUTO = 500  # Auto-process if estimated chunks under this
LARGE_PROJECT_THRESHOLD = 1000  # Flag as "large" above this
CACHE_DAYS = 7  # Re-run analysis if older than this

BIDDING_FOLDER = Path(_BIDDING_FOLDER)


def find_project_folder(project_id: str) -> Path | None:
    """Find project folder by ID or folder name"""
    # Try direct folder name match
    for item in BIDDING_FOLDER.iterdir():
        if item.is_dir():
            # Match by folder name converted to ID format
            folder_id = item.name.lower().replace(' ', '-').replace(',', '')
            if folder_id == project_id or item.name == project_id:
                return item
    return None


@rag_bp.route('/api/project/<project_id>/rag-analysis')
def get_rag_analysis(project_id: str):
    """Get RAG analysis data for a project"""
    folder = find_project_folder(project_id)
    if not folder:
        return jsonify({'error': 'Project not found', 'project_id': project_id}), 404

    rag_file = folder / 'division8_rag_analysis.json'
    if not rag_file.exists():
        return jsonify({
            'has_analysis': False,
            'project_id': project_id,
            'folder': folder.name,
            'message': 'RAG analysis not yet run for this project'
        })

    try:
        with open(rag_file, 'r') as f:
            data = json.load(f)
        return jsonify({
            'has_analysis': True,
            'project_id': project_id,
            'folder': folder.name,
            'analysis': data
        })
    except Exception as e:
        return jsonify({'error': f'Failed to load RAG analysis: {e}'}), 500


@rag_bp.route('/api/rag/stats')
def get_rag_stats():
    """Get RAG analysis statistics across all projects"""
    total_folders = 0
    with_analysis = 0
    without_analysis = 0
    analyzed_projects = []

    for item in BIDDING_FOLDER.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            # Skip special folders
            if item.name in ('div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman',
                             'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025'):
                continue

            total_folders += 1
            rag_file = item / 'division8_rag_analysis.json'

            if rag_file.exists():
                with_analysis += 1
                try:
                    with open(rag_file, 'r') as f:
                        data = json.load(f)
                    analyzed_projects.append({
                        'folder': item.name,
                        'analyzed_at': data.get('analyzed_at', ''),
                        'scope_summary': data.get('scope_summary', '')[:200] + '...' if len(data.get('scope_summary', '')) > 200 else data.get('scope_summary', '')
                    })
                except:
                    pass
            else:
                without_analysis += 1

    return jsonify({
        'total_projects': total_folders,
        'with_rag_analysis': with_analysis,
        'without_rag_analysis': without_analysis,
        'completion_percent': round(with_analysis / total_folders * 100, 1) if total_folders > 0 else 0,
        'recently_analyzed': sorted(analyzed_projects, key=lambda x: x.get('analyzed_at', ''), reverse=True)[:10]
    })


@rag_bp.route('/api/rag/projects')
def get_rag_projects():
    """Get list of projects with RAG analysis"""
    projects = []

    for item in BIDDING_FOLDER.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            if item.name in ('div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman',
                             'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025'):
                continue

            rag_file = item / 'division8_rag_analysis.json'
            if rag_file.exists():
                try:
                    with open(rag_file, 'r') as f:
                        data = json.load(f)
                    projects.append({
                        'folder': item.name,
                        'id': item.name.lower().replace(' ', '-').replace(',', ''),
                        'analyzed_at': data.get('analyzed_at', ''),
                        'scope_summary': data.get('scope_summary', ''),
                        'windows': data.get('windows', {}),
                        'doors': data.get('doors', {}),
                        'storefront': data.get('storefront', {}),
                        'curtain_wall': data.get('curtain_wall', {})
                    })
                except Exception as e:
                    print(f"Error reading RAG for {item.name}: {e}")

    return jsonify({
        'count': len(projects),
        'projects': sorted(projects, key=lambda x: x.get('analyzed_at', ''), reverse=True)
    })


def estimate_project_size(folder: Path) -> dict:
    """Estimate project size for RAG processing.

    Returns dict with pdf_count, est_pages, est_chunks, is_large
    """
    pdf_count = 0
    docx_count = 0
    est_pages = 0

    # Count PDFs and estimate pages (assume ~10 pages per PDF average)
    for pdf in folder.glob('**/*.pdf'):
        if not pdf.name.startswith('.'):
            pdf_count += 1
            # Rough estimate: small PDFs ~5 pages, large specs ~50 pages
            file_size_mb = pdf.stat().st_size / (1024 * 1024)
            if file_size_mb < 1:
                est_pages += 5
            elif file_size_mb < 5:
                est_pages += 20
            else:
                est_pages += 50

    # Count Word docs
    for docx in folder.glob('**/*.docx'):
        if not docx.name.startswith('.'):
            docx_count += 1
            est_pages += 10  # Assume ~10 pages per Word doc

    # Estimate chunks (roughly 2 chunks per page with 1000 char chunks)
    est_chunks = est_pages * 2

    return {
        'pdf_count': pdf_count,
        'docx_count': docx_count,
        'est_pages': est_pages,
        'est_chunks': est_chunks,
        'is_large': est_chunks > MAX_CHUNKS_AUTO,
        'is_very_large': est_chunks > LARGE_PROJECT_THRESHOLD
    }


def is_analysis_recent(folder: Path) -> tuple[bool, str | None]:
    """Check if RAG analysis exists and is recent.

    Returns (is_recent, analyzed_at_date)
    """
    rag_file = folder / 'division8_rag_analysis.json'
    if not rag_file.exists():
        return False, None

    try:
        with open(rag_file, 'r') as f:
            data = json.load(f)

        # Check _rag_metadata.generated_at or analyzed_at
        analyzed_at = data.get('_rag_metadata', {}).get('generated_at') or \
                      data.get('_rag_metadata', {}).get('analyzed_at') or \
                      data.get('analyzed_at')

        if not analyzed_at:
            return True, None  # File exists but no date, consider it valid

        # Parse date and check age
        if analyzed_at.endswith('Z'):
            analyzed_at = analyzed_at[:-1] + '+00:00'
        analyzed_date = datetime.fromisoformat(analyzed_at)

        # Make datetime aware if it isn't
        if analyzed_date.tzinfo is None:
            from datetime import timezone
            analyzed_date = analyzed_date.replace(tzinfo=timezone.utc)

        age_days = (datetime.now(analyzed_date.tzinfo) - analyzed_date).days
        return age_days < CACHE_DAYS, analyzed_at[:10]
    except Exception as e:
        print(f"Error checking RAG analysis age: {e}")
        return True, None  # If we can't parse, assume it's valid


@rag_bp.route('/api/project/<project_id>/rag-status')
def get_rag_status(project_id: str):
    """Check RAG analysis status for a project.

    Returns status info including whether analysis is needed and project size.
    """
    folder = find_project_folder(project_id)
    if not folder:
        return jsonify({'error': 'Project not found', 'project_id': project_id}), 404

    # Check if analysis exists and is recent
    is_recent, analyzed_at = is_analysis_recent(folder)
    has_analysis = (folder / 'division8_rag_analysis.json').exists()

    # Estimate project size
    size_info = estimate_project_size(folder)

    # Determine if we need analysis
    needs_analysis = not has_analysis or not is_recent

    return jsonify({
        'project_id': project_id,
        'folder': folder.name,
        'has_analysis': has_analysis,
        'is_recent': is_recent,
        'analyzed_at': analyzed_at,
        'needs_analysis': needs_analysis,
        'size': size_info,
        'auto_process': needs_analysis and not size_info['is_large'],
        'too_large': size_info['is_very_large']
    })


@rag_bp.route('/api/project/<project_id>/trigger-rag', methods=['POST'])
def trigger_rag_analysis(project_id: str):
    """Trigger RAG analysis for a project.

    Query params:
    - force: true to process even if large
    """
    folder = find_project_folder(project_id)
    if not folder:
        return jsonify({'error': 'Project not found', 'project_id': project_id}), 404

    force = request.args.get('force', 'false').lower() == 'true'

    # Check size
    size_info = estimate_project_size(folder)
    if size_info['is_very_large'] and not force:
        return jsonify({
            'status': 'too_large',
            'message': f'Project has ~{size_info["est_chunks"]} estimated chunks. Use force=true to process anyway.',
            'size': size_info
        }), 400

    # Try to import and run RAG analysis
    try:
        # Import the RAG module
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from modules.rag.division8_rag_local import Division8RAGLocal

        # Run analysis
        rag = Division8RAGLocal(folder)
        result = rag.analyze_project()

        # Save results
        output_file = folder / 'division8_rag_analysis.json'
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)

        return jsonify({
            'status': 'success',
            'project_id': project_id,
            'folder': folder.name,
            'chunks_analyzed': result.get('_rag_metadata', {}).get('chunks_analyzed', 0),
            'confidence': result.get('confidence', 'unknown')
        })

    except ImportError as e:
        return jsonify({
            'status': 'error',
            'message': f'RAG module not available: {e}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
