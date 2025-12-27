"""
Validation Routes Blueprint

Handles quantity validation tool for cross-referencing shape tags
between floor plans and elevations.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template, Response
import fitz  # PyMuPDF

from utils import find_project_by_id, get_project_folder_path, DATA_DIR


validation_bp = Blueprint('validation', __name__)


# =============================================================================
# CONFIG STORAGE
# =============================================================================

VALIDATION_CONFIG_DIR = DATA_DIR / "validation_configs"
VALIDATION_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_config_path(project_id: str) -> Path:
    """Get path to project's validation config file"""
    safe_id = project_id.replace('/', '_').replace('\\', '_')
    return VALIDATION_CONFIG_DIR / f"{safe_id}_validation.json"


# =============================================================================
# UI ROUTES
# =============================================================================

@validation_bp.route('/project/<project_id>/validate')
def validation_tool(project_id):
    """Render the quantity validation tool page"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Load saved config if exists
    config_path = get_config_path(project_id)
    saved_config = None
    if config_path.exists():
        try:
            with open(config_path) as f:
                saved_config = json.load(f)
        except Exception:
            pass

    return render_template('validation_tool.html',
                          project=project,
                          project_id=project_id,
                          saved_config=saved_config)


# =============================================================================
# API ROUTES - CONFIGURATION
# =============================================================================

@validation_bp.route('/api/project/<project_id>/validation/config', methods=['GET'])
def get_validation_config(project_id):
    """Get saved validation configuration for project"""
    config_path = get_config_path(project_id)

    if not config_path.exists():
        return jsonify({
            "config": None,
            "message": "No saved configuration"
        })

    try:
        with open(config_path) as f:
            config = json.load(f)
        return jsonify({
            "config": config,
            "message": "Configuration loaded"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@validation_bp.route('/api/project/<project_id>/validation/config', methods=['POST'])
def save_validation_config(project_id):
    """Save validation configuration for project"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Add metadata
    data['project_id'] = project_id
    data['updated_at'] = datetime.now().isoformat()

    config_path = get_config_path(project_id)

    try:
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
        return jsonify({
            "success": True,
            "message": "Configuration saved",
            "path": str(config_path)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@validation_bp.route('/api/project/<project_id>/validation/config', methods=['DELETE'])
def delete_validation_config(project_id):
    """Delete validation configuration for project"""
    config_path = get_config_path(project_id)

    if config_path.exists():
        config_path.unlink()

    return jsonify({
        "success": True,
        "message": "Configuration deleted"
    })


# =============================================================================
# API ROUTES - PDF MANAGEMENT
# =============================================================================

@validation_bp.route('/api/project/<project_id>/validation/pdfs', methods=['GET'])
def list_project_pdfs(project_id):
    """List all PDFs in project folder with page counts"""
    project_path, project = get_project_folder_path(project_id)

    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    pdfs = []

    # Find all PDFs recursively
    for pdf_file in project_path.rglob("*.pdf"):
        try:
            doc = fitz.open(str(pdf_file))
            page_count = len(doc)
            doc.close()

            # Get relative path from project folder
            rel_path = pdf_file.relative_to(project_path)

            pdfs.append({
                "path": str(rel_path),
                "name": pdf_file.name,
                "pages": page_count,
                "folder": str(rel_path.parent) if str(rel_path.parent) != "." else ""
            })
        except Exception as e:
            # Skip files that can't be opened
            continue

    # Sort by folder then name
    pdfs.sort(key=lambda x: (x['folder'], x['name']))

    return jsonify({
        "pdfs": pdfs,
        "count": len(pdfs),
        "project_path": str(project_path)
    })


@validation_bp.route('/api/project/<project_id>/validation/pdf-thumbnail/<path:pdf_path>/<int:page>', methods=['GET'])
def get_pdf_thumbnail(project_id, pdf_path, page):
    """Generate thumbnail for a specific PDF page"""
    project_path, _ = get_project_folder_path(project_id)

    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path

    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    try:
        doc = fitz.open(str(full_path))
        if page < 1 or page > len(doc):
            doc.close()
            return jsonify({"error": f"Page {page} out of range"}), 400

        pdf_page = doc[page - 1]

        # Render at low resolution for thumbnail
        zoom = 0.3  # ~72 DPI thumbnail
        mat = fitz.Matrix(zoom, zoom)
        pix = pdf_page.get_pixmap(matrix=mat)

        doc.close()

        # Return as PNG
        return Response(pix.tobytes("png"), mimetype='image/png')

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@validation_bp.route('/api/project/<project_id>/validation/pdf-page/<path:pdf_path>/<int:page>', methods=['GET'])
def get_pdf_page(project_id, pdf_path, page):
    """Get full-resolution PDF page image"""
    project_path, _ = get_project_folder_path(project_id)

    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path

    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    # Get DPI from query param (default 150 for viewing)
    dpi = request.args.get('dpi', 150, type=int)
    dpi = min(max(dpi, 72), 300)  # Clamp between 72-300

    try:
        doc = fitz.open(str(full_path))
        if page < 1 or page > len(doc):
            doc.close()
            return jsonify({"error": f"Page {page} out of range"}), 400

        pdf_page = doc[page - 1]

        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        pix = pdf_page.get_pixmap(matrix=mat)

        doc.close()

        return Response(pix.tobytes("png"), mimetype='image/png')

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# API ROUTES - DETECTION
# =============================================================================

@validation_bp.route('/api/project/<project_id>/validation/detect', methods=['POST'])
def run_detection(project_id):
    """Run shape detection on specified pages"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / 'shapedetector'))
    from detect_shapes import ShapeDetector

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    # Extract config from request
    floor_plan_pages = data.get('floor_plan_pages', [])
    elevation_pages = data.get('elevation_pages', [])
    shape_types = data.get('shape_types', ['hexagon'])
    tag_patterns = data.get('tag_patterns', {})
    use_vision_llm = data.get('use_vision_llm', False)
    dpi = data.get('dpi', 240)

    # Initialize detector
    detector = ShapeDetector(
        dpi=dpi,
        min_confidence=0.5,
        use_vision_llm=use_vision_llm,
        use_openrouter=use_vision_llm  # Use OpenRouter when vision LLM enabled
    )

    results = {
        'floor_plan_detections': {},
        'elevation_detections': {},
        'errors': []
    }

    # Process floor plans
    for page_spec in floor_plan_pages:
        pdf_path = project_path / page_spec['pdf']
        page_num = page_spec['page']

        try:
            detection = detector.detect_all(
                str(pdf_path),
                page=page_num,
                shape_types=shape_types
            )

            # Filter shapes by tag patterns if specified
            shapes = detection.get('shapes', [])
            if tag_patterns:
                shapes = filter_shapes_by_tags(shapes, tag_patterns)

            pdf_key = page_spec['pdf']
            if pdf_key not in results['floor_plan_detections']:
                results['floor_plan_detections'][pdf_key] = {}
            results['floor_plan_detections'][pdf_key][str(page_num)] = shapes

        except Exception as e:
            results['errors'].append({
                'pdf': page_spec['pdf'],
                'page': page_num,
                'error': str(e)
            })

    # Process elevations
    for page_spec in elevation_pages:
        pdf_path = project_path / page_spec['pdf']
        page_num = page_spec['page']

        try:
            detection = detector.detect_all(
                str(pdf_path),
                page=page_num,
                shape_types=shape_types
            )

            shapes = detection.get('shapes', [])
            if tag_patterns:
                shapes = filter_shapes_by_tags(shapes, tag_patterns)

            pdf_key = page_spec['pdf']
            if pdf_key not in results['elevation_detections']:
                results['elevation_detections'][pdf_key] = {}
            results['elevation_detections'][pdf_key][str(page_num)] = shapes

        except Exception as e:
            results['errors'].append({
                'pdf': page_spec['pdf'],
                'page': page_num,
                'error': str(e)
            })

    # Generate comparison summary
    results['summary'] = generate_comparison_summary(
        results['floor_plan_detections'],
        results['elevation_detections']
    )

    results['timestamp'] = datetime.now().isoformat()

    return jsonify(results)


def filter_shapes_by_tags(shapes: list, tag_patterns: dict) -> list:
    """Filter shapes to only include those matching configured tag patterns"""
    # Combine all tag patterns
    all_patterns = set()
    for category, patterns in tag_patterns.items():
        if isinstance(patterns, list):
            all_patterns.update(p.upper() for p in patterns)

    if not all_patterns:
        return shapes  # No filter if no patterns

    filtered = []
    for shape in shapes:
        text = shape.get('text', '').upper()
        if text in all_patterns:
            filtered.append(shape)

    return filtered


def generate_comparison_summary(floor_plan_detections: dict, elevation_detections: dict) -> dict:
    """Generate comparison between floor plan and elevation tag counts"""
    # Count tags in floor plans
    fp_counts = {}
    for pdf, pages in floor_plan_detections.items():
        for page, shapes in pages.items():
            for shape in shapes:
                tag = shape.get('text', '').upper()
                if tag:
                    fp_counts[tag] = fp_counts.get(tag, 0) + 1

    # Count tags in elevations
    el_counts = {}
    for pdf, pages in elevation_detections.items():
        for page, shapes in pages.items():
            for shape in shapes:
                tag = shape.get('text', '').upper()
                if tag:
                    el_counts[tag] = el_counts.get(tag, 0) + 1

    # Generate comparison
    all_tags = set(fp_counts.keys()) | set(el_counts.keys())
    by_tag = {}

    matches = 0
    mismatches = 0

    for tag in sorted(all_tags):
        fp_count = fp_counts.get(tag, 0)
        el_count = el_counts.get(tag, 0)
        is_match = fp_count == el_count

        by_tag[tag] = {
            'floor_plan': fp_count,
            'elevation': el_count,
            'status': 'match' if is_match else 'mismatch',
            'diff': el_count - fp_count
        }

        if is_match:
            matches += 1
        else:
            mismatches += 1

    return {
        'by_tag': by_tag,
        'totals': {
            'floor_plan_tags': sum(fp_counts.values()),
            'elevation_tags': sum(el_counts.values()),
            'unique_tags': len(all_tags),
            'matches': matches,
            'mismatches': mismatches
        }
    }


# =============================================================================
# API ROUTES - RESULTS & EXPORT
# =============================================================================

@validation_bp.route('/api/project/<project_id>/validation/export', methods=['GET'])
def export_results(project_id):
    """Export validation results as CSV"""
    # Get format from query params
    fmt = request.args.get('format', 'csv')

    # Get latest results from config
    config_path = get_config_path(project_id)
    if not config_path.exists():
        return jsonify({"error": "No validation results found"}), 404

    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    results = config.get('last_results', {})
    summary = results.get('summary', {})
    by_tag = summary.get('by_tag', {})

    if fmt == 'json':
        return jsonify(results)

    # Generate CSV
    lines = ['Tag,Floor Plan Count,Elevation Count,Status,Difference']
    for tag, data in sorted(by_tag.items()):
        lines.append(f"{tag},{data['floor_plan']},{data['elevation']},{data['status']},{data['diff']}")

    csv_content = '\n'.join(lines)

    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=validation_{project_id}.csv'}
    )
