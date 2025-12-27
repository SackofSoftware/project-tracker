"""
Estimates and Quotes Routes Blueprint

Handles estimate spreadsheet reading, quote PDF parsing, and comparison APIs.
"""

from pathlib import Path
from flask import Blueprint, jsonify

from utils import (
    find_project_by_id,
    BIDDING_FOLDER
)

from modules.estimates import EstimateReader
from modules.quotes import QuoteReader

estimates_bp = Blueprint('estimates', __name__)


# =============================================================================
# ESTIMATE ENDPOINTS
# =============================================================================

@estimates_bp.route('/api/estimate/<project_id>/openings')
def api_estimate_openings(project_id):
    """Read estimate spreadsheets and return openings breakdown"""
    # Find project folder
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        reader = EstimateReader(str(project_path))
        result = reader.read_all()

        return jsonify({
            "status": "ok",
            "openings": result.get('openings', []),
            "by_type": result.get('by_type', {}),
            "totals": result.get('totals', {}),
            "files_read": result.get('files_read', []),
            "total_count": result.get('total_count', 0),
            "unique_marks": result.get('unique_marks', 0)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# QUOTE ENDPOINTS
# =============================================================================

@estimates_bp.route('/api/quotes/<project_id>')
def api_quotes(project_id):
    """Read quote PDFs and return vendor pricing data"""
    # Find project folder
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        reader = QuoteReader(str(project_path))
        result = reader.read_all_quotes()

        return jsonify({
            "status": "ok",
            "quotes": result.get('quotes', []),
            "files_read": result.get('files_read', []),
            "total_quotes": result.get('total_quotes', 0),
            "quotes_with_pricing": result.get('quotes_with_pricing', 0),
            "total_value": result.get('total_value', 0),
            "vendors": result.get('vendors', []),
            "vendor_count": result.get('vendor_count', 0),
            "errors": result.get('errors', [])
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@estimates_bp.route('/api/quotes/<project_id>/compare')
def api_quotes_compare(project_id):
    """Compare vendor quotes against estimate data to find discrepancies"""
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_folder = project.get('folder_path') or project.get('folder')
    if not project_folder:
        return jsonify({"error": "Project has no folder"}), 400

    project_path = Path(BIDDING_FOLDER) / project_folder if not Path(project_folder).is_absolute() else Path(project_folder)

    if not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        # Get quote data
        quote_reader = QuoteReader(str(project_path))
        quote_result = quote_reader.read_all_quotes()
        quotes = quote_result.get('quotes', [])

        # Get estimate data
        estimate_reader = EstimateReader(str(project_path))
        estimate_result = estimate_reader.read_all()
        estimate_openings = estimate_result.get('openings', [])

        # Build estimate lookup by mark (normalized to uppercase)
        estimate_by_mark = {}
        for opening in estimate_openings:
            mark = str(opening.get('mark', '')).strip().upper()
            if mark:
                estimate_by_mark[mark] = opening

        # Compare each quote against estimate
        comparisons = []
        for quote in quotes:
            vendor = quote.get('vendor_name', 'Unknown')
            quote_items = quote.get('line_items', []) or []

            matched = []
            mismatched = []
            quote_only = []

            for item in quote_items:
                mark = str(item.get('mark', '')).strip().upper()
                if not mark:
                    continue

                quote_qty = item.get('qty', 1) or 1
                quote_width = item.get('width')
                quote_height = item.get('height')

                if mark in estimate_by_mark:
                    est = estimate_by_mark[mark]
                    est_qty = est.get('qty', 1) or 1

                    # Parse estimate size (format: "39'-0\" x 104'-0\"" or similar)
                    est_size = est.get('size', '')
                    est_width, est_height = None, None
                    if est_size:
                        import re
                        size_match = re.search(r"(\d+)'?-?(\d*)[\"']?\s*[xX]\s*(\d+)'?-?(\d*)", est_size)
                        if size_match:
                            est_width = int(size_match.group(1))
                            est_height = int(size_match.group(3))

                    # Check for discrepancies
                    issues = []
                    if quote_qty != est_qty:
                        issues.append(f"Qty: quote={quote_qty}, estimate={est_qty}")

                    # Allow 2" tolerance for size differences
                    if quote_width and est_width and abs(quote_width - est_width) > 2:
                        issues.append(f"Width: quote={quote_width}\", estimate={est_width}\"")
                    if quote_height and est_height and abs(quote_height - est_height) > 2:
                        issues.append(f"Height: quote={quote_height}\", estimate={est_height}\"")

                    if issues:
                        mismatched.append({
                            "mark": mark,
                            "issues": issues,
                            "quote": {"qty": quote_qty, "width": quote_width, "height": quote_height},
                            "estimate": {"qty": est_qty, "width": est_width, "height": est_height}
                        })
                    else:
                        matched.append({
                            "mark": mark,
                            "qty": quote_qty,
                            "size": f"{quote_width}x{quote_height}" if quote_width and quote_height else None
                        })
                else:
                    quote_only.append({
                        "mark": mark,
                        "qty": quote_qty,
                        "size": f"{quote_width}x{quote_height}" if quote_width and quote_height else None
                    })

            # Find estimate items not in this quote
            quote_marks = set(str(item.get('mark', '')).strip().upper() for item in quote_items)
            estimate_only = []
            for mark, est in estimate_by_mark.items():
                if mark not in quote_marks and est.get('type') == 'window':
                    estimate_only.append({
                        "mark": mark,
                        "qty": est.get('qty', 1),
                        "size": est.get('size')
                    })

            comparisons.append({
                "vendor": vendor,
                "source_file": quote.get('source_file'),
                "matched": matched,
                "mismatched": mismatched,
                "quote_only": quote_only,
                "estimate_only": estimate_only,
                "summary": {
                    "matched_count": len(matched),
                    "mismatch_count": len(mismatched),
                    "quote_only_count": len(quote_only),
                    "estimate_only_count": len(estimate_only)
                }
            })

        return jsonify({
            "status": "ok",
            "project_id": project_id,
            "comparisons": comparisons,
            "estimate_total_marks": len(estimate_by_mark),
            "vendors_compared": len(quotes)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
