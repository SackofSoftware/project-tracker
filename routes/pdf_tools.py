"""
PDF Tools Routes Blueprint

API endpoints for PDF manipulation:
- OCR text extraction
- PDF merging and splitting
- Text search
- Page rendering
"""

import os
import tempfile
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file, Response

from utils import find_project_by_id, get_project_folder_path
from modules.files.pdf_tools import PDFTools, get_pdf_tools


pdf_tools_bp = Blueprint('pdf_tools', __name__)


# =============================================================================
# PDF Information
# =============================================================================

@pdf_tools_bp.route('/api/project/<project_id>/pdf/info/<path:pdf_path>', methods=['GET'])
def get_pdf_info(project_id, pdf_path):
    """
    Get information about a PDF file.

    Returns page count, file size, whether it has text or is scanned.
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    try:
        tools = get_pdf_tools()
        info = tools.get_info(full_path)

        return jsonify({
            "success": True,
            "info": {
                "path": pdf_path,
                "page_count": info.page_count,
                "title": info.title,
                "author": info.author,
                "file_size": info.file_size,
                "file_size_mb": round(info.file_size / (1024 * 1024), 2),
                "has_text": info.has_text,
                "is_scanned": info.is_scanned
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Text Extraction
# =============================================================================

@pdf_tools_bp.route('/api/project/<project_id>/pdf/extract-text/<path:pdf_path>', methods=['GET'])
def extract_text(project_id, pdf_path):
    """
    Extract text from PDF.

    Query params:
    - pages: Comma-separated page numbers (e.g., "1,2,3")
    - method: 'auto', 'pymupdf', 'pdftotext', or 'ocr'
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    # Parse query params
    pages_str = request.args.get('pages')
    pages = None
    if pages_str:
        try:
            pages = [int(p.strip()) for p in pages_str.split(',')]
        except ValueError:
            return jsonify({"error": "Invalid pages format"}), 400

    method = request.args.get('method', 'auto')

    try:
        tools = get_pdf_tools()
        text = tools.extract_text(full_path, pages=pages, method=method)

        return jsonify({
            "success": True,
            "text": text,
            "method": method,
            "pages": pages,
            "char_count": len(text)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pdf_tools_bp.route('/api/project/<project_id>/pdf/ocr/<path:pdf_path>/<int:page>', methods=['GET'])
def ocr_page(project_id, pdf_path, page):
    """
    Perform OCR on a single PDF page.

    Returns extracted text with confidence score.
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    lang = request.args.get('lang', 'eng')

    try:
        tools = get_pdf_tools()
        result = tools.ocr_page(full_path, page, lang=lang)

        return jsonify({
            "success": True,
            "text": result.text,
            "confidence": round(result.confidence, 3),
            "page": result.page_number,
            "processing_time": round(result.processing_time, 2),
            "method": result.method
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Text Search
# =============================================================================

@pdf_tools_bp.route('/api/project/<project_id>/pdf/search/<path:pdf_path>', methods=['GET'])
def search_pdf(project_id, pdf_path):
    """
    Search for text in PDF.

    Query params:
    - q: Search query (required)
    - case: 'sensitive' for case-sensitive search
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    query = request.args.get('q')
    if not query:
        return jsonify({"error": "Search query 'q' is required"}), 400

    case_sensitive = request.args.get('case') == 'sensitive'

    try:
        tools = get_pdf_tools()
        matches = tools.find_text_in_pdf(full_path, query, case_sensitive=case_sensitive)

        return jsonify({
            "success": True,
            "query": query,
            "matches": matches,
            "count": len(matches),
            "pages_with_matches": list(set(m['page'] for m in matches))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# PDF Manipulation
# =============================================================================

@pdf_tools_bp.route('/api/project/<project_id>/pdf/merge', methods=['POST'])
def merge_pdfs(project_id):
    """
    Merge multiple PDFs into one.

    Request body:
    {
        "pdfs": ["path/to/pdf1.pdf", "path/to/pdf2.pdf"],
        "output_name": "merged.pdf"
    }
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    pdf_paths = data.get('pdfs', [])
    if len(pdf_paths) < 2:
        return jsonify({"error": "At least 2 PDFs required for merge"}), 400

    output_name = data.get('output_name', 'merged.pdf')

    # Validate all PDFs exist
    full_paths = []
    for pdf_path in pdf_paths:
        full_path = project_path / pdf_path
        if not full_path.exists():
            return jsonify({"error": f"PDF not found: {pdf_path}"}), 404
        full_paths.append(full_path)

    # Create output path
    output_dir = project_path / "Generated"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / output_name

    try:
        tools = get_pdf_tools()
        result_path = tools.merge_pdfs(full_paths, output_path)

        return jsonify({
            "success": True,
            "output_path": str(result_path.relative_to(project_path)),
            "merged_count": len(pdf_paths)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pdf_tools_bp.route('/api/project/<project_id>/pdf/split/<path:pdf_path>', methods=['POST'])
def split_pdf(project_id, pdf_path):
    """
    Split PDF into multiple files.

    Request body:
    {
        "pages_per_file": 1,  // Optional, default 1
        "output_folder": "split_output"  // Optional
    }
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    data = request.get_json() or {}
    pages_per_file = data.get('pages_per_file', 1)
    output_folder = data.get('output_folder', 'Generated/Split')

    output_dir = project_path / output_folder
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        tools = get_pdf_tools()
        result_paths = tools.split_pdf(full_path, output_dir, pages_per_file=pages_per_file)

        return jsonify({
            "success": True,
            "output_files": [str(p.relative_to(project_path)) for p in result_paths],
            "file_count": len(result_paths)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pdf_tools_bp.route('/api/project/<project_id>/pdf/extract-pages/<path:pdf_path>', methods=['POST'])
def extract_pages(project_id, pdf_path):
    """
    Extract specific pages from PDF.

    Request body:
    {
        "pages": [1, 3, 5],
        "output_name": "extracted.pdf"
    }
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    pages = data.get('pages', [])
    if not pages:
        return jsonify({"error": "Pages list required"}), 400

    output_name = data.get('output_name', f'{full_path.stem}_extracted.pdf')

    output_dir = project_path / "Generated"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / output_name

    try:
        tools = get_pdf_tools()
        result_path = tools.extract_pages(full_path, pages, output_path)

        return jsonify({
            "success": True,
            "output_path": str(result_path.relative_to(project_path)),
            "pages_extracted": pages
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@pdf_tools_bp.route('/api/project/<project_id>/pdf/rotate/<path:pdf_path>', methods=['POST'])
def rotate_pages(project_id, pdf_path):
    """
    Rotate pages in PDF.

    Request body:
    {
        "rotation": 90,  // 90, 180, or 270
        "pages": [1, 2],  // Optional, null for all pages
        "output_name": "rotated.pdf"  // Optional
    }
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    rotation = data.get('rotation')
    if rotation not in [90, 180, 270]:
        return jsonify({"error": "Rotation must be 90, 180, or 270"}), 400

    pages = data.get('pages')  # None means all pages
    output_name = data.get('output_name', f'{full_path.stem}_rotated.pdf')

    output_dir = project_path / "Generated"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / output_name

    try:
        tools = get_pdf_tools()
        result_path = tools.rotate_pages(full_path, output_path, rotation, pages)

        return jsonify({
            "success": True,
            "output_path": str(result_path.relative_to(project_path)),
            "rotation": rotation,
            "pages_rotated": pages or "all"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# High-Quality Rendering
# =============================================================================

@pdf_tools_bp.route('/api/project/<project_id>/pdf/render/<path:pdf_path>/<int:page>', methods=['GET'])
def render_page(project_id, pdf_path, page):
    """
    Render PDF page as high-quality image.

    Query params:
    - dpi: Resolution (default 200)
    - format: 'png' or 'jpeg' (default 'png')
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    dpi = request.args.get('dpi', 200, type=int)
    dpi = min(max(dpi, 72), 600)  # Clamp between 72-600

    fmt = request.args.get('format', 'png').lower()
    if fmt not in ['png', 'jpeg', 'jpg']:
        fmt = 'png'

    try:
        tools = get_pdf_tools()
        image = tools.render_page(full_path, page, dpi=dpi)

        if image is None:
            return jsonify({"error": f"Failed to render page {page}"}), 500

        # Convert to bytes
        import io
        buffer = io.BytesIO()
        image.save(buffer, format=fmt.upper().replace('JPG', 'JPEG'))
        buffer.seek(0)

        mimetype = 'image/png' if fmt == 'png' else 'image/jpeg'
        return Response(buffer.getvalue(), mimetype=mimetype)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Construction Document Utilities
# =============================================================================

@pdf_tools_bp.route('/api/project/<project_id>/pdf/title-block/<path:pdf_path>', methods=['GET'])
def extract_title_block(project_id, pdf_path):
    """
    Extract title block information from a drawing.

    Query params:
    - page: Page number (default 1)
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    full_path = project_path / pdf_path
    if not full_path.exists():
        return jsonify({"error": "PDF not found"}), 404

    page = request.args.get('page', 1, type=int)

    try:
        tools = get_pdf_tools()
        result = tools.extract_drawing_title_block(full_path, page)

        return jsonify({
            "success": True,
            "page": page,
            "title_block": result
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Batch Operations
# =============================================================================

@pdf_tools_bp.route('/api/project/<project_id>/pdf/batch-info', methods=['POST'])
def batch_pdf_info(project_id):
    """
    Get info for multiple PDFs at once.

    Request body:
    {
        "pdfs": ["path/to/pdf1.pdf", "path/to/pdf2.pdf"]
    }
    """
    project_path, _ = get_project_folder_path(project_id)
    if not project_path:
        return jsonify({"error": "Project not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    pdf_paths = data.get('pdfs', [])

    tools = get_pdf_tools()
    results = []

    for pdf_path in pdf_paths:
        full_path = project_path / pdf_path
        try:
            if full_path.exists():
                info = tools.get_info(full_path)
                results.append({
                    "path": pdf_path,
                    "success": True,
                    "page_count": info.page_count,
                    "file_size_mb": round(info.file_size / (1024 * 1024), 2),
                    "has_text": info.has_text,
                    "is_scanned": info.is_scanned
                })
            else:
                results.append({
                    "path": pdf_path,
                    "success": False,
                    "error": "File not found"
                })
        except Exception as e:
            results.append({
                "path": pdf_path,
                "success": False,
                "error": str(e)
            })

    return jsonify({
        "success": True,
        "results": results,
        "total": len(results),
        "successful": sum(1 for r in results if r.get('success'))
    })
