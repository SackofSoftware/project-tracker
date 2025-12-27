"""
Annotation Routes Blueprint

Handles PDF annotation CRUD operations for the glazing takeoff tool.
"""

import uuid
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template

from utils import find_project_by_id, get_project_folder_path
from modules.database.db import get_session
from modules.database.models import PDFAnnotation, DetailRegistry


annotation_bp = Blueprint('annotation', __name__)


# =============================================================================
# CLASSIFICATION COLORS
# =============================================================================

CLASSIFICATION_COLORS = {
    # Tag colors (solid fill)
    'window': {
        'stroke': '#FF5722',  # Deep Orange
        'fill': 'rgba(255,87,34,0.2)',
    },
    'door': {
        'stroke': '#9C27B0',  # Purple
        'fill': 'rgba(156,39,176,0.2)',
    },
    'storefront': {
        'stroke': '#4CAF50',  # Green
        'fill': 'rgba(76,175,80,0.2)',
    },
    'curtainwall': {
        'stroke': '#2196F3',  # Blue
        'fill': 'rgba(33,150,243,0.2)',
    },
    # Zone colors (lighter fill, will use dashed stroke)
    'elevation_zone': {
        'stroke': '#FFC107',  # Amber
        'fill': 'rgba(255,193,7,0.08)',
    },
    'floor_plan_zone': {
        'stroke': '#9C27B0',  # Purple
        'fill': 'rgba(156,39,176,0.08)',
    },
    'detail_zone': {
        'stroke': '#00BCD4',  # Cyan
        'fill': 'rgba(0,188,212,0.08)',
    },
    'schedule_zone': {
        'stroke': '#607D8B',  # Blue-grey
        'fill': 'rgba(96,125,139,0.12)',
    },
}

# Direction-specific colors for elevation/floor plan zones
DIRECTION_COLORS = {
    'north': '#4CAF50',  # Green
    'south': '#F44336',  # Red
    'east': '#FF9800',   # Orange
    'west': '#2196F3',   # Blue
    'northeast': '#8BC34A',
    'northwest': '#009688',
    'southeast': '#FF5722',
    'southwest': '#3F51B5',
}


# =============================================================================
# UI ROUTES
# =============================================================================

@annotation_bp.route('/project/<project_id>/annotate')
def annotation_tool(project_id):
    """Render the annotation tool page"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    return render_template('annotation_tool.html',
                         project=project,
                         project_id=project_id,
                         colors=CLASSIFICATION_COLORS,
                         direction_colors=DIRECTION_COLORS)


@annotation_bp.route('/project/<project_id>/annotate/<path:pdf_path>')
def annotation_tool_with_pdf(project_id, pdf_path):
    """Render the annotation tool with a specific PDF loaded"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    return render_template('annotation_tool.html',
                         project=project,
                         project_id=project_id,
                         initial_pdf=pdf_path,
                         colors=CLASSIFICATION_COLORS,
                         direction_colors=DIRECTION_COLORS)


# =============================================================================
# API ROUTES - CRUD
# =============================================================================

@annotation_bp.route('/api/project/<project_id>/annotations', methods=['GET'])
def get_annotations(project_id):
    """Get annotations for a project, optionally filtered by PDF and page"""
    pdf_path = request.args.get('pdf')
    page = request.args.get('page', type=int)

    with get_session() as session:
        query = session.query(PDFAnnotation).filter(
            PDFAnnotation.project_id == project_id
        )

        if pdf_path:
            query = query.filter(PDFAnnotation.pdf_path == pdf_path)

        if page is not None:
            query = query.filter(PDFAnnotation.page_number == page)

        annotations = query.order_by(PDFAnnotation.created_at).all()

        return jsonify({
            'annotations': [a.to_dict() for a in annotations],
            'count': len(annotations),
            'project_id': project_id,
            'pdf_path': pdf_path,
            'page': page
        })


@annotation_bp.route('/api/project/<project_id>/annotations', methods=['POST'])
def create_annotation(project_id):
    """Create a new annotation"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Validate required fields
    required = ['pdf_path', 'page_number', 'geometry']
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    # Get style based on classification category
    category = data.get('classification', {}).get('category', 'window')
    default_style = CLASSIFICATION_COLORS.get(category, CLASSIFICATION_COLORS['window'])

    annotation = PDFAnnotation(
        id=str(uuid.uuid4()),
        project_id=project_id,
        pdf_path=data['pdf_path'],
        page_number=data['page_number'],
        annotation_type=data.get('annotation_type', 'tag_marker'),
        geometry=data['geometry'],
        classification=data.get('classification'),
        style=data.get('style', {
            'strokeColor': default_style['stroke'],
            'fillColor': default_style['fill'],
            'strokeWidth': 2
        }),
        extracted_data=data.get('extracted_data'),
        source=data.get('source', 'manual')
    )

    with get_session() as session:
        session.add(annotation)
        session.commit()
        result = annotation.to_dict()

    return jsonify(result), 201


@annotation_bp.route('/api/project/<project_id>/annotations/<annotation_id>', methods=['GET'])
def get_annotation(project_id, annotation_id):
    """Get a single annotation by ID"""
    with get_session() as session:
        annotation = session.query(PDFAnnotation).filter(
            PDFAnnotation.id == annotation_id,
            PDFAnnotation.project_id == project_id
        ).first()

        if not annotation:
            return jsonify({"error": "Annotation not found"}), 404

        return jsonify(annotation.to_dict())


@annotation_bp.route('/api/project/<project_id>/annotations/<annotation_id>', methods=['PUT'])
def update_annotation(project_id, annotation_id):
    """Update an existing annotation"""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    with get_session() as session:
        annotation = session.query(PDFAnnotation).filter(
            PDFAnnotation.id == annotation_id,
            PDFAnnotation.project_id == project_id
        ).first()

        if not annotation:
            return jsonify({"error": "Annotation not found"}), 404

        # Update fields if provided
        if 'geometry' in data:
            annotation.geometry = data['geometry']
        if 'classification' in data:
            annotation.classification = data['classification']
            # Update style based on new category
            category = data['classification'].get('category', 'window')
            colors = CLASSIFICATION_COLORS.get(category, CLASSIFICATION_COLORS['window'])
            if not data.get('style'):
                annotation.style = {
                    'strokeColor': colors['stroke'],
                    'fillColor': colors['fill'],
                    'strokeWidth': annotation.style.get('strokeWidth', 2) if annotation.style else 2
                }
        if 'style' in data:
            annotation.style = data['style']
        if 'extracted_data' in data:
            annotation.extracted_data = data['extracted_data']
        if 'annotation_type' in data:
            annotation.annotation_type = data['annotation_type']

        annotation.updated_at = datetime.utcnow()
        session.commit()
        result = annotation.to_dict()

    return jsonify(result)


@annotation_bp.route('/api/project/<project_id>/annotations/<annotation_id>', methods=['DELETE'])
def delete_annotation(project_id, annotation_id):
    """Delete an annotation"""
    with get_session() as session:
        annotation = session.query(PDFAnnotation).filter(
            PDFAnnotation.id == annotation_id,
            PDFAnnotation.project_id == project_id
        ).first()

        if not annotation:
            return jsonify({"error": "Annotation not found"}), 404

        session.delete(annotation)
        session.commit()

    return jsonify({"success": True, "deleted_id": annotation_id})


# =============================================================================
# API ROUTES - SUMMARY & STATS
# =============================================================================

@annotation_bp.route('/api/project/<project_id>/annotations/summary', methods=['GET'])
def get_annotation_summary(project_id):
    """Get summary of annotations by category and type label"""
    with get_session() as session:
        annotations = session.query(PDFAnnotation).filter(
            PDFAnnotation.project_id == project_id,
            PDFAnnotation.annotation_type == 'tag_marker'
        ).all()

        # Build summary by category and type label
        summary = {
            'window': {},
            'door': {},
            'storefront': {},
            'curtainwall': {}
        }

        for ann in annotations:
            if ann.classification:
                category = ann.classification.get('category', 'window')
                type_label = ann.classification.get('typeLabel', '?')

                if category in summary:
                    if type_label not in summary[category]:
                        summary[category][type_label] = 0
                    summary[category][type_label] += 1

        # Calculate totals
        totals = {cat: sum(labels.values()) for cat, labels in summary.items()}

        return jsonify({
            'summary': summary,
            'totals': totals,
            'grand_total': sum(totals.values()),
            'project_id': project_id
        })


@annotation_bp.route('/api/annotation/colors', methods=['GET'])
def get_classification_colors():
    """Get the color scheme for classifications and zones"""
    return jsonify({
        'classifications': CLASSIFICATION_COLORS,
        'directions': DIRECTION_COLORS
    })


# =============================================================================
# API ROUTES - SHAPE DETECTION
# =============================================================================

@annotation_bp.route('/api/project/<project_id>/detect-shapes', methods=['POST'])
def detect_shapes(project_id):
    """
    Detect tag shapes on a PDF page.

    Request body:
    {
        "pdf_path": "Drawings/Architectural/A300.pdf",
        "page_number": 1,
        "shape_type": "hexagon",  // hexagon, circle, rectangle, diamond, triangle
        "min_confidence": 0.5
    }

    Returns list of detected tags with coordinates and labels.
    """
    from modules.files.shape_detector import detect_tags_on_page, ShapeType

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    pdf_path = data.get('pdf_path')
    page_number = data.get('page_number', 1)
    shape_type = data.get('shape_type', 'hexagon')
    min_confidence = data.get('min_confidence', 0.5)

    if not pdf_path:
        return jsonify({"error": "pdf_path is required"}), 400

    # Validate shape type
    valid_shapes = ['hexagon', 'circle', 'rectangle', 'diamond', 'triangle']
    if shape_type not in valid_shapes:
        return jsonify({
            "error": f"Invalid shape_type. Must be one of: {valid_shapes}"
        }), 400

    # Get full path to PDF
    project_folder = get_project_folder_path(project_id)
    if not project_folder:
        return jsonify({"error": "Project folder not found"}), 404

    full_pdf_path = project_folder / pdf_path
    if not full_pdf_path.exists():
        return jsonify({"error": f"PDF not found: {pdf_path}"}), 404

    try:
        # Detect shapes
        tags = detect_tags_on_page(
            str(full_pdf_path),
            page_number,
            shape_type,
            min_confidence
        )

        return jsonify({
            "success": True,
            "pdf_path": pdf_path,
            "page_number": page_number,
            "shape_type": shape_type,
            "tags": tags,
            "count": len(tags)
        })

    except Exception as e:
        return jsonify({
            "error": f"Detection failed: {str(e)}"
        }), 500


@annotation_bp.route('/api/project/<project_id>/annotations/bulk', methods=['POST'])
def create_bulk_annotations(project_id):
    """
    Create multiple annotations at once (for auto-detected tags).

    Request body:
    {
        "pdf_path": "Drawings/Architectural/A300.pdf",
        "page_number": 1,
        "tags": [
            {"label": "K", "pdf_x": 100, "pdf_y": 200, "width": 20, "height": 20, "category": "window"},
            ...
        ]
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    pdf_path = data.get('pdf_path')
    page_number = data.get('page_number', 1)
    tags = data.get('tags', [])

    if not pdf_path:
        return jsonify({"error": "pdf_path is required"}), 400

    if not tags:
        return jsonify({"error": "No tags provided"}), 400

    created = []

    with get_session() as session:
        for tag in tags:
            # Create polygon geometry from bounding box
            x = tag.get('pdf_x', 0)
            y = tag.get('pdf_y', 0)
            w = tag.get('width', 20)
            h = tag.get('height', 20)

            # Convert bbox to polygon points (PDF coordinates)
            points = [
                [x, y],
                [x + w, y],
                [x + w, y + h],
                [x, y + h]
            ]

            category = tag.get('category', 'window')
            label = tag.get('label', '')

            # Get style
            colors = CLASSIFICATION_COLORS.get(category, CLASSIFICATION_COLORS['window'])

            annotation = PDFAnnotation(
                id=str(uuid.uuid4()),
                project_id=project_id,
                pdf_path=pdf_path,
                page_number=page_number,
                annotation_type='tag_marker',
                geometry={
                    'type': 'polygon',
                    'points': points
                },
                classification={
                    'category': category,
                    'typeLabel': label
                },
                style={
                    'strokeColor': colors['stroke'],
                    'fillColor': colors['fill'],
                    'strokeWidth': 2
                },
                source='auto_detected'
            )

            session.add(annotation)
            created.append(annotation.to_dict())

        session.commit()

    return jsonify({
        "success": True,
        "created": len(created),
        "annotations": created
    }), 201


@annotation_bp.route('/api/shape-types', methods=['GET'])
def get_shape_types():
    """Get available shape types for detection"""
    return jsonify({
        "shapes": [
            {
                "id": "hexagon",
                "name": "Hexagon",
                "description": "6-sided tag shape (common for window/door tags)",
                "icon": "⬡"
            },
            {
                "id": "circle",
                "name": "Circle",
                "description": "Circular tag shape",
                "icon": "●"
            },
            {
                "id": "rectangle",
                "name": "Rectangle",
                "description": "Rectangular tag shape",
                "icon": "▭"
            },
            {
                "id": "diamond",
                "name": "Diamond",
                "description": "Diamond/rotated square shape",
                "icon": "◇"
            },
            {
                "id": "triangle",
                "name": "Triangle",
                "description": "Triangular tag shape (revision markers)",
                "icon": "△"
            }
        ]
    })


# =============================================================================
# API ROUTES - TAG CROSS-REFERENCE
# =============================================================================

@annotation_bp.route('/api/project/<project_id>/crossref', methods=['GET'])
def get_crossref_status(project_id):
    """Get current cross-reference status for a project"""
    from modules.files.tag_crossref import TagCrossReference, SheetType
    from pathlib import Path

    project_folder = get_project_folder_path(project_id)
    if not project_folder:
        return jsonify({"error": "Project folder not found"}), 404

    crossref = TagCrossReference(project_folder)
    sheets = crossref.find_architectural_sheets()

    return jsonify({
        "project_id": project_id,
        "sheets": {
            "floor_plans": [p.name for p in sheets[SheetType.FLOOR_PLAN]],
            "exterior_elevations": [p.name for p in sheets[SheetType.EXTERIOR_ELEVATION]],
            "interior_elevations": [p.name for p in sheets[SheetType.INTERIOR_ELEVATION]],
            "other": [p.name for p in sheets[SheetType.OTHER]]
        },
        "counts": {
            "floor_plans": len(sheets[SheetType.FLOOR_PLAN]),
            "exterior_elevations": len(sheets[SheetType.EXTERIOR_ELEVATION]),
            "interior_elevations": len(sheets[SheetType.INTERIOR_ELEVATION]),
            "other": len(sheets[SheetType.OTHER])
        }
    })


@annotation_bp.route('/api/project/<project_id>/crossref/scan', methods=['POST'])
def run_crossref_scan(project_id):
    """
    Run cross-reference scan on project sheets.

    Request body:
    {
        "sheet_types": ["floor_plan", "exterior_elevation", "interior_elevation"],
        "shape_type": "hexagon"
    }
    """
    from modules.files.tag_crossref import TagCrossReference, SheetType
    from modules.files.shape_detector import ShapeType as DetectShapeType
    from pathlib import Path

    project_folder = get_project_folder_path(project_id)
    if not project_folder:
        return jsonify({"error": "Project folder not found"}), 404

    data = request.get_json() or {}

    # Parse sheet types
    sheet_type_strs = data.get('sheet_types', ['floor_plan', 'exterior_elevation'])
    sheet_types = []
    for st in sheet_type_strs:
        try:
            sheet_types.append(SheetType(st))
        except ValueError:
            pass

    if not sheet_types:
        sheet_types = [SheetType.FLOOR_PLAN, SheetType.EXTERIOR_ELEVATION]

    shape_type_str = data.get('shape_type', 'hexagon')
    try:
        shape_type = DetectShapeType(shape_type_str)
    except ValueError:
        shape_type = DetectShapeType.HEXAGON

    # Run the scan
    crossref = TagCrossReference(project_folder)

    try:
        crossref.batch_scan(sheet_types=sheet_types, shape_type=shape_type)
        results = crossref.to_dict()

        return jsonify({
            "success": True,
            "project_id": project_id,
            **results
        })

    except Exception as e:
        return jsonify({
            "error": f"Scan failed: {str(e)}"
        }), 500


@annotation_bp.route('/api/project/<project_id>/crossref/reclassify', methods=['POST'])
def reclassify_sheet(project_id):
    """
    Manually reclassify a sheet's type.

    Request body:
    {
        "sheet_name": "A301 - INTERIOR ELEVATIONS.pdf",
        "sheet_type": "interior_elevation"
    }
    """
    # This would update a stored classification override
    # For now, return success - full implementation would persist this
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    return jsonify({
        "success": True,
        "sheet_name": data.get('sheet_name'),
        "new_type": data.get('sheet_type')
    })


@annotation_bp.route('/project/<project_id>/crossref')
def crossref_view(project_id):
    """Render the cross-reference view page"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    return render_template('crossref_tool.html',
                         project=project,
                         project_id=project_id)


# =============================================================================
# API ROUTES - ZONES
# =============================================================================

@annotation_bp.route('/api/project/<project_id>/zones', methods=['GET'])
def get_project_zones(project_id):
    """Get all zone annotations for a project"""
    with get_session() as session:
        zones = session.query(PDFAnnotation).filter(
            PDFAnnotation.project_id == project_id,
            PDFAnnotation.annotation_type.like('%_zone')
        ).all()

        return jsonify({
            'zones': [z.to_dict() for z in zones],
            'count': len(zones)
        })


@annotation_bp.route('/api/project/<project_id>/zones/<zone_id>/tags', methods=['GET'])
def get_tags_in_zone(project_id, zone_id):
    """Get all tags that fall within a specific zone"""
    from modules.files.tag_crossref import ZoneAwareCrossReference

    with get_session() as session:
        # Get all annotations for this project
        annotations = session.query(PDFAnnotation).filter(
            PDFAnnotation.project_id == project_id
        ).all()

        ann_dicts = [a.to_dict() for a in annotations]

        # Use zone-aware cross reference to find tags in zone
        crossref = ZoneAwareCrossReference(ann_dicts)
        matching_tags = crossref.get_tags_in_zone(zone_id)

        return jsonify({
            'zone_id': zone_id,
            'tags': matching_tags,
            'count': len(matching_tags)
        })


@annotation_bp.route('/api/project/<project_id>/crossref/zone-aware', methods=['GET'])
def get_zone_aware_crossref(project_id):
    """
    Get zone-aware cross-reference summary.

    Returns tag counts grouped by zone direction (e.g., "5 Type A on North Elevation").
    """
    from modules.files.tag_crossref import ZoneAwareCrossReference

    with get_session() as session:
        # Get all annotations for this project
        annotations = session.query(PDFAnnotation).filter(
            PDFAnnotation.project_id == project_id
        ).all()

        ann_dicts = [a.to_dict() for a in annotations]

        # Generate zone-aware cross-reference
        crossref = ZoneAwareCrossReference(ann_dicts)
        results = crossref.to_dict()

        return jsonify({
            'project_id': project_id,
            **results
        })


# =============================================================================
# API ROUTES - DETAIL REGISTRY
# =============================================================================

@annotation_bp.route('/api/project/<project_id>/details', methods=['GET'])
def get_project_details(project_id):
    """Get all detail registry entries for a project"""
    with get_session() as session:
        details = session.query(DetailRegistry).filter(
            DetailRegistry.project_id == project_id
        ).all()

        return jsonify({
            'details': [d.to_dict() for d in details],
            'count': len(details)
        })


@annotation_bp.route('/api/project/<project_id>/details', methods=['POST'])
def create_detail(project_id):
    """
    Create a new detail registry entry.

    Request body:
    {
        "detail_id": "A501-B",
        "detail_title": "Jamb Detail",
        "detail_type": "jamb",
        "source_sheet": "A501.pdf",
        "source_page": 1,
        "applies_to_types": ["A", "B", "C"],
        "applies_to_categories": ["window"],
        "annotation_id": "uuid-of-zone-annotation",
        "notes": "Optional notes"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    detail_id = data.get('detail_id')
    if not detail_id:
        return jsonify({"error": "detail_id is required"}), 400

    with get_session() as session:
        # Check for duplicate
        existing = session.query(DetailRegistry).filter(
            DetailRegistry.project_id == project_id,
            DetailRegistry.detail_id == detail_id
        ).first()

        if existing:
            return jsonify({"error": f"Detail {detail_id} already exists"}), 409

        detail = DetailRegistry(
            project_id=project_id,
            detail_id=detail_id,
            detail_title=data.get('detail_title'),
            detail_type=data.get('detail_type'),
            source_sheet=data.get('source_sheet'),
            source_page=data.get('source_page'),
            applies_to_types=data.get('applies_to_types', []),
            applies_to_categories=data.get('applies_to_categories', []),
            annotation_id=data.get('annotation_id'),
            notes=data.get('notes')
        )

        session.add(detail)
        session.commit()
        session.refresh(detail)

        return jsonify(detail.to_dict()), 201


@annotation_bp.route('/api/project/<project_id>/details/<int:detail_pk>', methods=['PUT'])
def update_detail(project_id, detail_pk):
    """Update an existing detail registry entry"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    with get_session() as session:
        detail = session.query(DetailRegistry).filter(
            DetailRegistry.id == detail_pk,
            DetailRegistry.project_id == project_id
        ).first()

        if not detail:
            return jsonify({"error": "Detail not found"}), 404

        # Update allowed fields
        if 'detail_title' in data:
            detail.detail_title = data['detail_title']
        if 'detail_type' in data:
            detail.detail_type = data['detail_type']
        if 'source_sheet' in data:
            detail.source_sheet = data['source_sheet']
        if 'source_page' in data:
            detail.source_page = data['source_page']
        if 'applies_to_types' in data:
            detail.applies_to_types = data['applies_to_types']
        if 'applies_to_categories' in data:
            detail.applies_to_categories = data['applies_to_categories']
        if 'annotation_id' in data:
            detail.annotation_id = data['annotation_id']
        if 'notes' in data:
            detail.notes = data['notes']

        session.commit()
        session.refresh(detail)

        return jsonify(detail.to_dict())


@annotation_bp.route('/api/project/<project_id>/details/<int:detail_pk>', methods=['DELETE'])
def delete_detail(project_id, detail_pk):
    """Delete a detail registry entry"""
    with get_session() as session:
        detail = session.query(DetailRegistry).filter(
            DetailRegistry.id == detail_pk,
            DetailRegistry.project_id == project_id
        ).first()

        if not detail:
            return jsonify({"error": "Detail not found"}), 404

        session.delete(detail)
        session.commit()

    return jsonify({"success": True, "deleted_id": detail_pk})


@annotation_bp.route('/api/project/<project_id>/type/<type_label>/details', methods=['GET'])
def get_details_for_type(project_id, type_label):
    """Get all details that apply to a specific window/door type label"""
    with get_session() as session:
        # Query details where applies_to_types contains this label
        # Note: This is a simple implementation - for large datasets,
        # consider using PostgreSQL JSON operators or dedicated junction table
        all_details = session.query(DetailRegistry).filter(
            DetailRegistry.project_id == project_id
        ).all()

        # Filter to those that include this type
        matching = []
        for detail in all_details:
            if detail.applies_to_types and type_label.upper() in [t.upper() for t in detail.applies_to_types]:
                matching.append(detail.to_dict())

        return jsonify({
            'type_label': type_label,
            'details': matching,
            'count': len(matching)
        })


@annotation_bp.route('/api/project/<project_id>/details/<detail_id_str>/types', methods=['GET'])
def get_types_for_detail(project_id, detail_id_str):
    """Get all window/door types that a detail applies to"""
    with get_session() as session:
        detail = session.query(DetailRegistry).filter(
            DetailRegistry.project_id == project_id,
            DetailRegistry.detail_id == detail_id_str
        ).first()

        if not detail:
            return jsonify({"error": "Detail not found"}), 404

        return jsonify({
            'detail_id': detail_id_str,
            'detail_title': detail.detail_title,
            'applies_to_types': detail.applies_to_types or [],
            'applies_to_categories': detail.applies_to_categories or []
        })
