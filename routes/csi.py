"""
CSI Masterformat Routes Blueprint

Handles CSI section lookups, manufacturer matching, and auto-tagging.
"""

import json
from urllib.parse import unquote
from flask import Blueprint, jsonify, request

from utils import (
    find_project_by_id,
    get_project_folder_path,
    get_status_tracker,
    DATA_DIR
)

csi_bp = Blueprint('csi', __name__)


# =============================================================================
# CSI DATA ENDPOINTS
# =============================================================================

@csi_bp.route('/api/csi/stats')
def api_csi_stats():
    """Get CSI Masterformat data statistics"""
    try:
        from modules.csi import CSIService
        service = CSIService()
        return jsonify({
            "status": "ok",
            "sections_loaded": service.section_count,
            "products_loaded": service.product_count,
            "division8_sections": service.division8_count
        })
    except ImportError:
        return jsonify({"error": "CSI module not available"}), 500


@csi_bp.route('/api/csi/section/<section_id>')
def api_csi_section(section_id):
    """Get info about a specific CSI section"""
    try:
        from modules.csi import get_section_info
        info = get_section_info(section_id)
        if info:
            return jsonify(info)
        return jsonify({"error": f"Section {section_id} not found"}), 404
    except ImportError:
        return jsonify({"error": "CSI module not available"}), 500


@csi_bp.route('/api/csi/sections/division8')
def api_csi_division8_sections():
    """Get all Division 8 CSI sections"""
    try:
        from modules.csi import CSIService
        service = CSIService()
        sections = service.get_division8_sections()
        return jsonify({
            "status": "ok",
            "sections": sections,
            "count": len(sections)
        })
    except ImportError:
        return jsonify({"error": "CSI module not available"}), 500


@csi_bp.route('/api/csi/enrich', methods=['POST'])
def api_csi_enrich():
    """Enrich text or scope items with CSI descriptions"""
    try:
        from modules.csi import enrich_scope_with_csi
        data = request.json or {}
        scope_items = data.get('items', [])
        enriched = enrich_scope_with_csi(scope_items)
        return jsonify({
            "status": "ok",
            "enriched": enriched,
            "count": len(enriched)
        })
    except ImportError:
        return jsonify({"error": "CSI module not available"}), 500


@csi_bp.route('/api/csi/manufacturers', methods=['POST'])
def api_csi_manufacturers():
    """Find manufacturer references in text"""
    try:
        from modules.csi import match_manufacturers
        data = request.json or {}
        text = data.get('text', '')
        matches = match_manufacturers(text)
        return jsonify({
            "status": "ok",
            "manufacturers": matches,
            "count": len(matches)
        })
    except ImportError:
        return jsonify({"error": "CSI module not available"}), 500


# =============================================================================
# CSI ANALYSIS ENDPOINT
# =============================================================================

@csi_bp.route('/api/project/<project_id>/csi-analysis')
def api_project_csi_analysis(project_id):
    """Run CSI Masterformat analysis on project documents"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path, _ = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        from modules.csi import CSIService, get_section_info
        service = CSIService()

        spec_text = ""
        spec_files = []

        for pdf_file in project_path.rglob('*.pdf'):
            name_lower = pdf_file.name.lower()
            if any(kw in name_lower for kw in ['spec', 'division', 'section', 'manual']):
                spec_files.append(pdf_file.name)
                try:
                    import pdfplumber
                    with pdfplumber.open(pdf_file) as pdf:
                        for page in pdf.pages[:50]:
                            page_text = page.extract_text() or ""
                            spec_text += page_text + "\n"
                except:
                    pass

        extracted_file = project_path / "extracted_project_data.json"
        if extracted_file.exists():
            try:
                with open(extracted_file, 'r') as f:
                    extracted = json.load(f)
                    if 'division_8' in extracted:
                        div8 = extracted['division_8']
                        spec_text += str(div8.get('scope_summary', '')) + "\n"
                        for section in div8.get('sections', []):
                            spec_text += str(section) + "\n"
            except:
                pass

        sections_found = service.extract_sections(spec_text)
        manufacturers_found = service.match_manufacturers(spec_text)

        enriched_sections = []
        for section_id in sections_found:
            info = get_section_info(section_id)
            info['category'] = service.categorize(section_id)
            enriched_sections.append(info)

        return jsonify({
            "status": "ok",
            "project_id": project_id,
            "sections": enriched_sections,
            "sections_count": len(enriched_sections),
            "manufacturers": manufacturers_found,
            "manufacturers_count": len(manufacturers_found),
            "files_analyzed": spec_files[:10],
            "text_analyzed_chars": len(spec_text)
        })

    except ImportError as e:
        return jsonify({"error": f"CSI module not available: {e}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =============================================================================
# CSI AUTO-TAGGING ENDPOINTS
# =============================================================================

@csi_bp.route('/api/project/<project_id>/auto-tag', methods=['POST'])
def api_project_auto_tag(project_id):
    """Automatically generate CSI tags for a project based on spec analysis"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path, _ = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        from modules.csi import extract_and_generate_tags, CSI_TAGGING_AVAILABLE

        if not CSI_TAGGING_AVAILABLE:
            return jsonify({"error": "CSI tagging module not available"}), 500

        spec_text = ""
        spec_files = []

        for pdf_file in project_path.rglob('*.pdf'):
            name_lower = pdf_file.name.lower()
            if any(kw in name_lower for kw in ['spec', 'division', 'section', 'manual', 'project_manual']):
                spec_files.append(pdf_file.name)
                try:
                    import pdfplumber
                    with pdfplumber.open(pdf_file) as pdf:
                        for page in pdf.pages[:100]:
                            page_text = page.extract_text() or ""
                            spec_text += page_text + "\n"
                except:
                    pass

        specs_dir = project_path / "Specs"
        if specs_dir.exists():
            for pdf_file in specs_dir.rglob('*.pdf'):
                if pdf_file.name not in spec_files:
                    spec_files.append(pdf_file.name)
                    try:
                        import pdfplumber
                        with pdfplumber.open(pdf_file) as pdf:
                            for page in pdf.pages[:100]:
                                page_text = page.extract_text() or ""
                                spec_text += page_text + "\n"
                    except:
                        pass

        extracted_file = project_path / "extracted_project_data.json"
        if extracted_file.exists():
            try:
                with open(extracted_file, 'r') as f:
                    extracted = json.load(f)
                    if 'division_8' in extracted:
                        div8 = extracted['division_8']
                        spec_text += str(div8.get('scope_summary', '')) + "\n"
                        for section in div8.get('spec_sections', []):
                            spec_text += f"{section.get('number', '')} {section.get('title', '')}\n"
            except:
                pass

        if not spec_text.strip():
            return jsonify({
                "status": "warning",
                "message": "No spec text found to analyze",
                "tags_generated": [],
                "files_searched": spec_files
            })

        result = extract_and_generate_tags(spec_text)

        replace_tags = request.args.get('replace', 'false').lower() == 'true'
        status_tracker = get_status_tracker()

        if replace_tags:
            status_tracker.set_csi_tags(project_id, result['simple_tags'])
        else:
            existing = status_tracker.get_csi_tags(project_id)
            merged = sorted(list(set(existing + result['simple_tags'])))
            status_tracker.set_csi_tags(project_id, merged)

        all_tags = status_tracker.get_all_tags(project_id)

        return jsonify({
            "status": "ok",
            "project_id": project_id,
            "project_name": project.get('title') or project.get('name') or project.get('folder'),
            "sections_found": result['sections_found'],
            "section_count": len(result['sections_found']),
            "tags_generated": result['simple_tags'],
            "tag_count": len(result['simple_tags']),
            "detailed_tags": result['detailed_tags'],
            "by_category": result['by_category'],
            "categories_found": result.get('categories_found', []),
            "all_project_tags": all_tags,
            "files_analyzed": spec_files[:15],
            "text_analyzed_chars": len(spec_text)
        })

    except ImportError as e:
        return jsonify({"error": f"CSI tagging module not available: {e}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@csi_bp.route('/api/project/<project_id>/csi-tags', methods=['GET'])
def api_project_csi_tags_get(project_id):
    """Get CSI tags for a project"""
    status_tracker = get_status_tracker()
    all_tags = status_tracker.get_all_tags(project_id)
    return jsonify({
        "status": "ok",
        "project_id": project_id,
        "csi_tags": all_tags.get("csi", []),
        "manual_tags": all_tags.get("manual", []),
        "all_tags": all_tags.get("all", [])
    })


@csi_bp.route('/api/project/<project_id>/csi-tags', methods=['POST'])
def api_project_csi_tags_set(project_id):
    """Set CSI tags for a project manually"""
    data = request.json or {}
    tags = data.get('tags', [])

    if not isinstance(tags, list):
        return jsonify({"error": "tags must be a list"}), 400

    status_tracker = get_status_tracker()
    status_tracker.set_csi_tags(project_id, tags)

    return jsonify({
        "status": "ok",
        "project_id": project_id,
        "csi_tags": tags
    })


@csi_bp.route('/api/csi/tags/options')
def api_csi_tag_options():
    """Get all possible CSI tag options for filter dropdowns"""
    try:
        from modules.csi import get_all_csi_tag_options, CSI_TAGGING_AVAILABLE

        if not CSI_TAGGING_AVAILABLE:
            return jsonify({"error": "CSI tagging module not available"}), 500

        options = get_all_csi_tag_options()
        return jsonify({
            "status": "ok",
            "options": options,
            "count": len(options)
        })
    except ImportError:
        return jsonify({"error": "CSI tagging module not available"}), 500


@csi_bp.route('/api/csi/tags/in-use')
def api_csi_tags_in_use():
    """Get CSI tags currently in use across all projects"""
    status_tracker = get_status_tracker()
    tag_counts = status_tracker.get_all_csi_tags_in_use()
    return jsonify({
        "status": "ok",
        "tags": tag_counts,
        "count": len(tag_counts)
    })


@csi_bp.route('/api/csi/tags/summary')
def api_csi_tags_summary():
    """Get summary statistics about CSI tag usage"""
    status_tracker = get_status_tracker()
    summary = status_tracker.get_csi_tag_summary()
    return jsonify({
        "status": "ok",
        **summary
    })


@csi_bp.route('/api/projects/by-csi-tag/<tag>')
def api_projects_by_csi_tag(tag):
    """Get all projects with a specific CSI tag"""
    tag = unquote(tag)
    status_tracker = get_status_tracker()
    projects = status_tracker.get_projects_by_csi_tag(tag)

    return jsonify({
        "status": "ok",
        "tag": tag,
        "projects": [
            {
                "project_id": p.get("project_id"),
                "project_title": p.get("project_title"),
                "bid_decision": p.get("bid_decision"),
                "csi_tags": p.get("csi_tags", [])
            }
            for p in projects
        ],
        "count": len(projects)
    })


# =============================================================================
# BATCH CSI SCANNING
# =============================================================================

import threading
import uuid
from pathlib import Path

# Global state for batch jobs
_batch_scan_jobs = {}
_batch_scan_lock = threading.Lock()


def _run_batch_csi_scan(job_id: str, force: bool = False):
    """Background worker for batch CSI scanning"""
    from utils import get_all_projects, get_project_folder_path, debounced_refresh

    try:
        from modules.csi import extract_and_generate_tags, CSI_TAGGING_AVAILABLE
        if not CSI_TAGGING_AVAILABLE:
            with _batch_scan_lock:
                _batch_scan_jobs[job_id]['status'] = 'error'
                _batch_scan_jobs[job_id]['error'] = 'CSI tagging module not available'
            return
    except ImportError as e:
        with _batch_scan_lock:
            _batch_scan_jobs[job_id]['status'] = 'error'
            _batch_scan_jobs[job_id]['error'] = str(e)
        return

    status_tracker = get_status_tracker()
    all_projects = get_all_projects()

    # Filter projects that need scanning
    projects_to_scan = []
    for p in all_projects:
        project_id = p.get('project_code') or p.get('id') or p.get('folder', '').lower().replace(' ', '-')
        if not project_id:
            continue

        # Skip archived projects
        if p.get('archived'):
            continue

        # Check if already has tags (unless force)
        if not force:
            existing_tags = status_tracker.get_csi_tags(project_id)
            if existing_tags:
                continue

        # Check if has a folder path
        folder_path = p.get('folder_path')
        if folder_path and Path(folder_path).exists():
            projects_to_scan.append({
                'id': project_id,
                'name': p.get('title') or p.get('name') or p.get('folder') or project_id,
                'path': Path(folder_path)
            })

    total = len(projects_to_scan)
    with _batch_scan_lock:
        _batch_scan_jobs[job_id]['total'] = total
        _batch_scan_jobs[job_id]['status'] = 'running'

    print(f"[CSI Batch] Starting scan of {total} projects")

    completed = []
    errors = []

    for i, proj in enumerate(projects_to_scan, 1):
        project_id = proj['id']
        project_name = proj['name']
        project_path = proj['path']

        with _batch_scan_lock:
            _batch_scan_jobs[job_id]['current'] = i
            _batch_scan_jobs[job_id]['current_project'] = project_name

        print(f"[CSI Batch] Scanning {i}/{total}: {project_name}")

        try:
            # Extract spec text from PDFs
            spec_text = ""
            spec_files = []

            for pdf_file in project_path.rglob('*.pdf'):
                name_lower = pdf_file.name.lower()
                if any(kw in name_lower for kw in ['spec', 'division', 'section', 'manual', 'project_manual']):
                    spec_files.append(pdf_file.name)
                    try:
                        import pdfplumber
                        with pdfplumber.open(pdf_file) as pdf:
                            for page in pdf.pages[:100]:
                                page_text = page.extract_text() or ""
                                spec_text += page_text + "\n"
                    except:
                        pass

            # Also check Specs subfolder
            specs_dir = project_path / "Specs"
            if specs_dir.exists():
                for pdf_file in specs_dir.rglob('*.pdf'):
                    if pdf_file.name not in spec_files:
                        spec_files.append(pdf_file.name)
                        try:
                            import pdfplumber
                            with pdfplumber.open(pdf_file) as pdf:
                                for page in pdf.pages[:100]:
                                    page_text = page.extract_text() or ""
                                    spec_text += page_text + "\n"
                        except:
                            pass

            # Check extracted data
            extracted_file = project_path / "extracted_project_data.json"
            if extracted_file.exists():
                try:
                    with open(extracted_file, 'r') as f:
                        extracted = json.load(f)
                        if 'division_8' in extracted:
                            div8 = extracted['division_8']
                            spec_text += str(div8.get('scope_summary', '')) + "\n"
                            for section in div8.get('spec_sections', []):
                                spec_text += f"{section.get('number', '')} {section.get('title', '')}\n"
                except:
                    pass

            if spec_text.strip():
                result = extract_and_generate_tags(spec_text)
                tags = result.get('simple_tags', [])

                if tags:
                    # Save tags
                    status_tracker.set_csi_tags(project_id, tags)
                    completed.append({
                        'project_id': project_id,
                        'project_name': project_name,
                        'tags': tags,
                        'tag_count': len(tags)
                    })
                    print(f"[CSI Batch]   -> Found {len(tags)} tags: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")
                else:
                    completed.append({
                        'project_id': project_id,
                        'project_name': project_name,
                        'tags': [],
                        'tag_count': 0,
                        'note': 'No Division 8 sections found'
                    })
            else:
                completed.append({
                    'project_id': project_id,
                    'project_name': project_name,
                    'tags': [],
                    'tag_count': 0,
                    'note': 'No spec files found'
                })

        except Exception as e:
            errors.append({
                'project_id': project_id,
                'project_name': project_name,
                'error': str(e)
            })
            print(f"[CSI Batch]   -> Error: {e}")

    # Trigger refresh to update project cache
    debounced_refresh.trigger()

    with _batch_scan_lock:
        _batch_scan_jobs[job_id]['status'] = 'completed'
        _batch_scan_jobs[job_id]['completed'] = completed
        _batch_scan_jobs[job_id]['errors'] = errors

    tags_found = sum(c.get('tag_count', 0) for c in completed)
    print(f"[CSI Batch] Complete! Scanned {total} projects, found {tags_found} total tags")


@csi_bp.route('/api/csi/batch-scan', methods=['POST'])
def api_csi_batch_scan():
    """Start a batch CSI scan job for all projects without tags"""
    force = request.args.get('force', 'false').lower() == 'true'

    job_id = str(uuid.uuid4())[:8]

    with _batch_scan_lock:
        _batch_scan_jobs[job_id] = {
            'status': 'starting',
            'current': 0,
            'total': 0,
            'current_project': '',
            'completed': [],
            'errors': [],
            'force': force
        }

    thread = threading.Thread(target=_run_batch_csi_scan, args=(job_id, force))
    thread.daemon = True
    thread.start()

    return jsonify({
        "status": "ok",
        "job_id": job_id,
        "message": f"Batch scan started {'(force mode)' if force else '(skipping projects with existing tags)'}",
        "status_url": f"/api/csi/batch-scan/status?job_id={job_id}"
    })


@csi_bp.route('/api/csi/batch-scan/status')
def api_csi_batch_scan_status():
    """Get status of a batch scan job"""
    job_id = request.args.get('job_id')

    if not job_id:
        # Return list of all jobs
        with _batch_scan_lock:
            return jsonify({
                "status": "ok",
                "jobs": {jid: {"status": j["status"], "current": j["current"], "total": j["total"]}
                         for jid, j in _batch_scan_jobs.items()}
            })

    with _batch_scan_lock:
        job = _batch_scan_jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    response = {
        "status": "ok",
        "job_id": job_id,
        "job_status": job['status'],
        "current": job['current'],
        "total": job['total'],
        "current_project": job['current_project']
    }

    if job['status'] == 'completed':
        response['completed'] = job['completed']
        response['errors'] = job['errors']
        response['summary'] = {
            'projects_scanned': len(job['completed']),
            'projects_with_tags': len([c for c in job['completed'] if c.get('tag_count', 0) > 0]),
            'total_tags_found': sum(c.get('tag_count', 0) for c in job['completed']),
            'errors': len(job['errors'])
        }
    elif job['status'] == 'error':
        response['error'] = job.get('error')

    return jsonify(response)
