"""
Thumbnails Routes Blueprint

Handles project thumbnail generation and caching.
"""

from flask import Blueprint, send_file, jsonify
from utils import find_project_by_id, get_thumbnail_gen

thumbnails_bp = Blueprint('thumbnails', __name__, url_prefix='/api')


@thumbnails_bp.route('/thumbnail/<project_id>', methods=['GET'])
def get_thumbnail(project_id):
    """Get or generate thumbnail for a project"""
    # Get project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Get folder information
    folder_path = project.get('folder_path')
    folder_name = project.get('folder')

    if not folder_path or not folder_name:
        return jsonify({"error": "Project folder information missing"}), 404

    # Get thumbnail generator
    thumbnail_gen = get_thumbnail_gen()

    # Check for cached thumbnail
    thumb_path = thumbnail_gen.get_thumbnail_path(folder_name)
    if thumb_path:
        return send_file(str(thumb_path), mimetype='image/jpeg')

    # Generate thumbnail synchronously
    result = thumbnail_gen.generate_thumbnail(folder_name, folder_path)
    if result:
        return send_file(result, mimetype='image/jpeg')

    return jsonify({"error": "Thumbnail generation failed"}), 404


@thumbnails_bp.route('/thumbnail/<project_id>/generate', methods=['POST'])
def generate_thumbnail(project_id):
    """Trigger async thumbnail generation"""
    # Get project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Get folder information
    folder_path = project.get('folder_path')
    folder_name = project.get('folder')

    if not folder_path:
        return jsonify({"error": "Project folder path missing"}), 404

    # Get thumbnail generator
    thumbnail_gen = get_thumbnail_gen()

    # Trigger async generation
    thumbnail_gen.generate_thumbnail_async(folder_name, folder_path)

    return jsonify({"status": "generating", "project_id": project_id})


@thumbnails_bp.route('/thumbnails/status', methods=['GET'])
def get_thumbnails_status():
    """Get status of all cached thumbnails"""
    # Get thumbnail generator
    thumbnail_gen = get_thumbnail_gen()

    # Get all cached thumbnails
    cached = thumbnail_gen.get_all_cached()

    return jsonify({"cached_count": len(cached), "thumbnails": cached})
