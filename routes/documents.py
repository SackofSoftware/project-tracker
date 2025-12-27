"""
Documents API Blueprint

Provides document listing, categorization, and thumbnail serving
for the Command Center document viewer overlay.

Features:
- List all project documents (specs, drawings)
- Filter by category (specs, floor plans, elevations, schedules, details)
- Smart linking to scope cards
- Thumbnail generation and serving
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from flask import Blueprint, jsonify, request, send_file, abort

from utils import (
    find_project_by_id,
    get_project_folder_path,
    BIDDING_FOLDER
)

documents_bp = Blueprint('documents', __name__)


# =============================================================================
# DOCUMENT DATA STRUCTURES
# =============================================================================

@dataclass
class Document:
    """Document metadata"""
    id: str
    filename: str
    filepath: str
    category: str  # 'spec', 'floor_plan', 'elevation', 'schedule', 'detail', 'other'
    subcategory: Optional[str]  # e.g., 'door_schedule', 'window_schedule'
    sheet_number: Optional[str]  # e.g., 'A601'
    page_count: int
    file_size: int
    linked_cards: List[str]  # Scope card IDs this doc relates to

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# DOCUMENT CLASSIFICATION PATTERNS
# =============================================================================

# Drawing sheet number patterns
SHEET_PATTERNS = {
    'floor_plan': {
        'prefixes': ['A1', 'A2', 'A-1', 'A-2', 'AD1', 'AD2'],
        'keywords': ['floor plan', 'flr plan', 'plan', 'level'],
    },
    'elevation': {
        'prefixes': ['A3', 'A-3', 'A30', 'A31', 'A32', 'A33'],
        'keywords': ['elevation', 'elev', 'exterior'],
    },
    'section': {
        'prefixes': ['A4', 'A-4', 'A5', 'A-5'],
        'keywords': ['section', 'building section', 'wall section'],
    },
    'detail': {
        'prefixes': ['A5', 'A-5', 'A7', 'A-7', 'A8', 'A-8', 'A9', 'A-9'],
        'keywords': ['detail', 'dtl', 'typ detail', 'window detail', 'door detail'],
    },
    'schedule': {
        'prefixes': ['A6', 'A-6', 'A60', 'A61', 'A62'],
        'keywords': ['schedule', 'door schedule', 'window schedule', 'hardware', 'finish'],
    },
    'cover': {
        'prefixes': ['G0', 'G-0', 'T-', 'T0', 'T1'],
        'keywords': ['cover', 'index', 'sheet index', 'drawing index'],
    },
}

# Spec section patterns for Division 8
SPEC_PATTERNS = {
    'glass_glazing': {
        'sections': ['08 80', '08 81', '08 83', '08 84', '08 85', '08 87', '08 88'],
        'keywords': ['glazing', 'glass', 'insulated glass'],
    },
    'storefront': {
        'sections': ['08 41', '08 42', '08 43', '08 44', '08 45'],
        'keywords': ['storefront', 'curtain wall', 'aluminum entrance'],
    },
    'windows': {
        'sections': ['08 51', '08 52', '08 53', '08 54', '08 55', '08 56'],
        'keywords': ['window', 'aluminum window', 'vinyl window'],
    },
    'doors': {
        'sections': ['08 11', '08 12', '08 13', '08 14', '08 16', '08 31', '08 32', '08 33', '08 34'],
        'keywords': ['door', 'hollow metal', 'aluminum door', 'entrance'],
    },
    'hardware': {
        'sections': ['08 71', '08 74', '08 75', '08 78', '08 79'],
        'keywords': ['hardware', 'lockset', 'closer', 'hinge'],
    },
}

# Scope card linking
CARD_LINKING = {
    'glass_glazing': ['glass-glazing'],
    'storefront': ['storefront-curtainwall'],
    'windows': ['commercial-windows'],
    'doors': ['metal-doors', 'wood-doors'],
    'hardware': ['door-hardware'],
    'floor_plan': ['glass-glazing', 'storefront-curtainwall', 'commercial-windows', 'metal-doors'],
    'elevation': ['glass-glazing', 'storefront-curtainwall', 'commercial-windows'],
    'schedule': ['commercial-windows', 'metal-doors', 'door-hardware'],
    'detail': ['glass-glazing', 'storefront-curtainwall', 'commercial-windows'],
}


# =============================================================================
# DOCUMENT DISCOVERY
# =============================================================================

def discover_documents(project_path: Path) -> List[Document]:
    """
    Discover and classify all documents in a project folder.

    Args:
        project_path: Path to project folder

    Returns:
        List of Document objects
    """
    documents = []

    # Define subdirectories to search
    search_dirs = [
        ('Drawings', 'drawing'),
        ('Plans', 'drawing'),
        ('Specs', 'spec'),
        ('Specifications', 'spec'),
        ('', 'unknown'),  # Root folder
    ]

    for subdir, default_type in search_dirs:
        search_path = project_path / subdir if subdir else project_path
        if not search_path.exists():
            continue

        for pdf_file in search_path.glob('*.pdf'):
            doc = classify_document(pdf_file, default_type)
            documents.append(doc)

        # Also check one level deeper for split PDFs
        for pdf_file in search_path.glob('*/*.pdf'):
            doc = classify_document(pdf_file, default_type)
            documents.append(doc)

    return documents


def classify_document(filepath: Path, default_type: str = 'unknown') -> Document:
    """
    Classify a document by analyzing filename and content.

    Args:
        filepath: Path to document
        default_type: Default classification if can't determine

    Returns:
        Document object with classification
    """
    filename = filepath.name
    filename_lower = filename.lower()
    stem = filepath.stem.upper()

    # Generate document ID
    doc_id = hashlib.md5(str(filepath).encode()).hexdigest()[:12]

    # Get file info
    try:
        file_size = filepath.stat().st_size
    except:
        file_size = 0

    # Try to get page count
    page_count = get_pdf_page_count(filepath)

    # Classify based on filename patterns
    category = default_type
    subcategory = None
    sheet_number = None
    linked_cards = []

    # Check for spec patterns
    if default_type == 'spec' or 'spec' in filename_lower or 'section' in filename_lower:
        category = 'spec'
        for spec_type, patterns in SPEC_PATTERNS.items():
            # Check section numbers in filename
            for section in patterns['sections']:
                if section.replace(' ', '') in filename_lower or section in filename_lower:
                    subcategory = spec_type
                    linked_cards.extend(CARD_LINKING.get(spec_type, []))
                    break
            # Check keywords
            for keyword in patterns['keywords']:
                if keyword in filename_lower:
                    subcategory = spec_type
                    linked_cards.extend(CARD_LINKING.get(spec_type, []))
                    break

    # Check for drawing patterns
    elif default_type == 'drawing' or any(p in stem for p in ['A-', 'A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6']):
        category = 'drawing'

        # Extract sheet number
        import re
        sheet_match = re.match(r'^([A-Z]+-?\d+(?:\.\d+)?)', stem)
        if sheet_match:
            sheet_number = sheet_match.group(1)

        # Classify drawing type
        for draw_type, patterns in SHEET_PATTERNS.items():
            # Check prefixes
            for prefix in patterns['prefixes']:
                if stem.startswith(prefix):
                    category = draw_type
                    linked_cards.extend(CARD_LINKING.get(draw_type, []))
                    break
            # Check keywords
            for keyword in patterns['keywords']:
                if keyword in filename_lower:
                    category = draw_type
                    linked_cards.extend(CARD_LINKING.get(draw_type, []))
                    break

        # Sub-classify schedules
        if category == 'schedule':
            if 'door' in filename_lower:
                subcategory = 'door_schedule'
                linked_cards = ['metal-doors', 'wood-doors', 'door-hardware']
            elif 'window' in filename_lower:
                subcategory = 'window_schedule'
                linked_cards = ['commercial-windows', 'glass-glazing']
            elif 'hardware' in filename_lower:
                subcategory = 'hardware_schedule'
                linked_cards = ['door-hardware']
            elif 'finish' in filename_lower:
                subcategory = 'finish_schedule'

    return Document(
        id=doc_id,
        filename=filename,
        filepath=str(filepath),
        category=category,
        subcategory=subcategory,
        sheet_number=sheet_number,
        page_count=page_count,
        file_size=file_size,
        linked_cards=list(set(linked_cards))
    )


def get_pdf_page_count(filepath: Path) -> int:
    """Get page count from PDF"""
    try:
        import fitz  # PyMuPDF
        with fitz.open(filepath) as doc:
            return len(doc)
    except:
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                return len(pdf.pages)
        except:
            return 0


# =============================================================================
# THUMBNAIL GENERATION
# =============================================================================

def get_thumbnail_path(project_id: str, doc_id: str) -> Path:
    """Get path for document thumbnail"""
    thumb_dir = Path(__file__).parent.parent / 'static' / 'thumbnails' / project_id
    thumb_dir.mkdir(parents=True, exist_ok=True)
    return thumb_dir / f'{doc_id}.png'


def generate_thumbnail(filepath: Path, thumb_path: Path, size: Tuple[int, int] = (300, 300)) -> bool:
    """
    Generate thumbnail for first page of PDF.

    Args:
        filepath: Path to PDF
        thumb_path: Output thumbnail path
        size: Thumbnail dimensions

    Returns:
        True if successful
    """
    try:
        import fitz  # PyMuPDF
        with fitz.open(filepath) as doc:
            page = doc[0]
            # Render at higher resolution then scale
            zoom = 2.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL for resizing
            from PIL import Image
            import io
            img_data = pix.tobytes('png')
            img = Image.open(io.BytesIO(img_data))
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumb_path, 'PNG')
            return True
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
        return False


# =============================================================================
# API ENDPOINTS
# =============================================================================

@documents_bp.route('/api/project/<project_id>/documents')
def get_project_documents(project_id: str):
    """
    Get all documents for a project.

    Query params:
        category: Filter by category (spec, floor_plan, elevation, schedule, detail)
        card_id: Filter by linked scope card
    """
    # Find project
    project_path, project = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({'error': 'Project not found or has no folder'}), 404

    # Discover documents
    documents = discover_documents(project_path)

    # Apply filters
    category_filter = request.args.get('category')
    card_filter = request.args.get('card_id')

    if category_filter:
        documents = [d for d in documents if d.category == category_filter]

    if card_filter:
        documents = [d for d in documents if card_filter in d.linked_cards]

    # Group by category
    grouped = {}
    for doc in documents:
        cat = doc.category
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(doc.to_dict())

    return jsonify({
        'project_id': project_id,
        'documents': [d.to_dict() for d in documents],
        'by_category': grouped,
        'counts': {cat: len(docs) for cat, docs in grouped.items()},
        'total': len(documents)
    })


@documents_bp.route('/api/project/<project_id>/documents/by-category/<category>')
def get_documents_by_category(project_id: str, category: str):
    """Get documents filtered by category"""
    # Find project
    project_path, project = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({'error': 'Project not found'}), 404

    # Discover and filter
    documents = discover_documents(project_path)
    filtered = [d for d in documents if d.category == category]

    return jsonify({
        'project_id': project_id,
        'category': category,
        'documents': [d.to_dict() for d in filtered],
        'count': len(filtered)
    })


@documents_bp.route('/api/project/<project_id>/documents/for-card/<card_id>')
def get_documents_for_card(project_id: str, card_id: str):
    """Get documents linked to a specific scope card"""
    # Find project
    project_path, project = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({'error': 'Project not found'}), 404

    # Discover and filter
    documents = discover_documents(project_path)
    linked = [d for d in documents if card_id in d.linked_cards]

    # Separate specs from drawings
    specs = [d.to_dict() for d in linked if d.category == 'spec']
    drawings = [d.to_dict() for d in linked if d.category != 'spec']

    return jsonify({
        'project_id': project_id,
        'card_id': card_id,
        'specs': specs,
        'drawings': drawings,
        'total': len(linked)
    })


@documents_bp.route('/api/project/<project_id>/document/<doc_id>/thumbnail')
def get_document_thumbnail(project_id: str, doc_id: str):
    """Get or generate thumbnail for a document"""
    # Find project
    project_path, project = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({'error': 'Project not found'}), 404

    # Find document
    documents = discover_documents(project_path)
    doc = next((d for d in documents if d.id == doc_id), None)
    if not doc:
        return jsonify({'error': 'Document not found'}), 404

    # Check for existing thumbnail
    thumb_path = get_thumbnail_path(project_id, doc_id)
    if not thumb_path.exists():
        # Generate thumbnail
        success = generate_thumbnail(Path(doc.filepath), thumb_path)
        if not success:
            abort(500, 'Failed to generate thumbnail')

    return send_file(thumb_path, mimetype='image/png')


@documents_bp.route('/api/project/<project_id>/document/<doc_id>')
def get_document_info(project_id: str, doc_id: str):
    """Get document metadata"""
    # Find project
    project_path, project = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({'error': 'Project not found'}), 404

    # Find document
    documents = discover_documents(project_path)
    doc = next((d for d in documents if d.id == doc_id), None)
    if not doc:
        return jsonify({'error': 'Document not found'}), 404

    # Add thumbnail URL
    doc_dict = doc.to_dict()
    doc_dict['thumbnail_url'] = f'/api/project/{project_id}/document/{doc_id}/thumbnail'

    return jsonify(doc_dict)


@documents_bp.route('/api/project/<project_id>/document/<doc_id>/serve')
def serve_document(project_id: str, doc_id: str):
    """Serve the actual PDF file"""
    # Find project
    project_path, project = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({'error': 'Project not found'}), 404

    # Find document
    documents = discover_documents(project_path)
    doc = next((d for d in documents if d.id == doc_id), None)
    if not doc:
        return jsonify({'error': 'Document not found'}), 404

    filepath = Path(doc.filepath)
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404

    return send_file(
        filepath,
        mimetype='application/pdf',
        as_attachment=False,
        download_name=doc.filename
    )


@documents_bp.route('/api/project/<project_id>/documents/generate-thumbnails', methods=['POST'])
def generate_all_thumbnails(project_id: str):
    """Generate thumbnails for all project documents"""
    # Find project
    project_path, project = get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({'error': 'Project not found'}), 404

    # Discover documents
    documents = discover_documents(project_path)

    generated = 0
    failed = 0

    for doc in documents:
        if doc.category not in ['spec']:  # Skip spec PDFs, focus on drawings
            thumb_path = get_thumbnail_path(project_id, doc.id)
            if not thumb_path.exists():
                if generate_thumbnail(Path(doc.filepath), thumb_path):
                    generated += 1
                else:
                    failed += 1

    return jsonify({
        'status': 'ok',
        'generated': generated,
        'failed': failed,
        'total': len(documents)
    })


# =============================================================================
# DOCUMENT CATEGORIES
# =============================================================================

@documents_bp.route('/api/documents/categories')
def get_document_categories():
    """Get available document categories"""
    return jsonify({
        'drawing_categories': [
            {'id': 'floor_plan', 'label': 'Floor Plans', 'icon': 'floor-plan'},
            {'id': 'elevation', 'label': 'Exterior Elevations', 'icon': 'elevation'},
            {'id': 'section', 'label': 'Wall Sections', 'icon': 'section'},
            {'id': 'detail', 'label': 'Details', 'icon': 'detail'},
            {'id': 'schedule', 'label': 'Schedules', 'icon': 'schedule'},
            {'id': 'cover', 'label': 'Cover/Index', 'icon': 'cover'},
        ],
        'spec_categories': [
            {'id': 'glass_glazing', 'label': 'Glass & Glazing', 'sections': ['08 80', '08 81']},
            {'id': 'storefront', 'label': 'Storefront', 'sections': ['08 41', '08 42']},
            {'id': 'windows', 'label': 'Windows', 'sections': ['08 51', '08 52']},
            {'id': 'doors', 'label': 'Doors', 'sections': ['08 11', '08 14']},
            {'id': 'hardware', 'label': 'Hardware', 'sections': ['08 71']},
        ]
    })
