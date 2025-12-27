"""
Vendors Routes Blueprint

Handles vendor management APIs including CRUD operations, search, and quote tracking.
"""

from flask import Blueprint, jsonify, request

from utils import get_vendor_manager

vendors_bp = Blueprint('vendors', __name__)


# =============================================================================
# VENDOR LIST ENDPOINTS
# =============================================================================

@vendors_bp.route('/api/vendors')
def api_get_vendors():
    """Get all vendors with summary statistics"""
    vendor_manager = get_vendor_manager()
    vendors = vendor_manager.get_all_vendors()
    stats = vendor_manager.get_summary_stats()
    return jsonify({
        "vendors": vendors,
        "stats": stats
    })


@vendors_bp.route('/api/vendors/search')
def api_search_vendors():
    """Search vendors by name, specialty, or contact information"""
    vendor_manager = get_vendor_manager()
    query = request.args.get('q', '')
    if not query:
        return jsonify({"vendors": []})

    vendors = vendor_manager.search_vendors(query)
    return jsonify({"vendors": vendors, "query": query})


# =============================================================================
# VENDOR CRUD ENDPOINTS
# =============================================================================

@vendors_bp.route('/api/vendors', methods=['POST'])
def api_create_vendor():
    """Create a new vendor"""
    vendor_manager = get_vendor_manager()
    data = request.json
    vendor = vendor_manager.add_vendor(
        name=data.get('name'),
        contact_name=data.get('contact_name'),
        email=data.get('email'),
        phone=data.get('phone'),
        specialty=data.get('specialty', []),
        notes=data.get('notes')
    )
    return jsonify(vendor), 201


@vendors_bp.route('/api/vendors/<vendor_id>')
def api_get_vendor(vendor_id):
    """Get a single vendor by ID"""
    vendor_manager = get_vendor_manager()
    vendor = vendor_manager.get_vendor(vendor_id)
    if not vendor:
        return jsonify({"error": "Vendor not found"}), 404
    return jsonify(vendor)


@vendors_bp.route('/api/vendors/<vendor_id>', methods=['PUT'])
def api_update_vendor(vendor_id):
    """Update an existing vendor"""
    vendor_manager = get_vendor_manager()
    data = request.json
    vendor = vendor_manager.update_vendor(vendor_id, data)
    if not vendor:
        return jsonify({"error": "Vendor not found"}), 404
    return jsonify(vendor)


@vendors_bp.route('/api/vendors/<vendor_id>', methods=['DELETE'])
def api_delete_vendor(vendor_id):
    """Delete a vendor"""
    vendor_manager = get_vendor_manager()
    success = vendor_manager.delete_vendor(vendor_id)
    if not success:
        return jsonify({"error": "Vendor not found"}), 404
    return jsonify({"status": "ok", "message": "Vendor deleted"})


# =============================================================================
# VENDOR QUOTE ENDPOINTS
# =============================================================================

@vendors_bp.route('/api/vendors/<vendor_id>/quotes', methods=['POST'])
def api_add_vendor_quote(vendor_id):
    """Add a quote to a vendor's history"""
    vendor_manager = get_vendor_manager()
    data = request.json
    quote = vendor_manager.add_quote_to_vendor(
        vendor_id=vendor_id,
        project_id=data.get('project_id'),
        project_name=data.get('project_name'),
        amount=data.get('amount'),
        quote_date=data.get('quote_date'),
        notes=data.get('notes'),
        source_file=data.get('source_file')
    )
    if not quote:
        return jsonify({"error": "Vendor not found"}), 404
    return jsonify(quote), 201
