"""
CSI Auto-Tagging API Endpoints

Add these endpoints to app.py after the existing CSI analysis endpoint (around line 3308)
"""

# ==================== CSI AUTO-TAGGING ENDPOINTS ====================

@app.route('/api/project/<project_id>/auto-tag', methods=['POST'])
def api_project_auto_tag(project_id):
    """
    Automatically generate CSI tags for a project based on spec analysis.
    
    This endpoint:
    1. Scans spec PDFs for CSI section references
    2. Generates human-readable tags (e.g., "Metal Windows", "Door Hardware")
    3. Stores tags in project status
    
    Query parameters:
    - replace: true/false (default: false) - Replace existing CSI tags vs merge
    
    Returns the generated tags and updated project status.
    """
    # Find project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Get project folder
    project_path, _ = _get_project_folder_path(project_id)
    if not project_path or not project_path.exists():
        return jsonify({"error": f"Project folder not found"}), 404

    try:
        from modules.csi import extract_and_generate_tags, get_section_info, CSI_TAGGING_AVAILABLE
        
        if not CSI_TAGGING_AVAILABLE:
            return jsonify({"error": "CSI tagging module not available"}), 500
        
        # Gather text from specs
        spec_text = ""
        spec_files = []

        for pdf_file in project_path.rglob('*.pdf'):
            name_lower = pdf_file.name.lower()
            # Match spec files by name patterns
            if any(kw in name_lower for kw in ['spec', 'division', 'section', 'manual', 'project_manual']):
                spec_files.append(pdf_file.name)
                try:
                    import pdfplumber
                    with pdfplumber.open(pdf_file) as pdf:
                        for page in pdf.pages[:100]:  # More pages for better coverage
                            page_text = page.extract_text() or ""
                            spec_text += page_text + "\n"
                except Exception as e:
                    pass

        # Also scan any PDF in a "Specs" subdirectory
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

        # Also include existing extracted data
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

        # Generate tags
        result = extract_and_generate_tags(spec_text)
        
        # Get option to replace or merge
        replace_tags = request.args.get('replace', 'false').lower() == 'true'
        
        # Store CSI tags
        if replace_tags:
            status_tracker.set_csi_tags(project_id, result['simple_tags'])
        else:
            existing = status_tracker.get_csi_tags(project_id)
            merged = sorted(list(set(existing + result['simple_tags'])))
            status_tracker.set_csi_tags(project_id, merged)
        
        # Get updated tags
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


@app.route('/api/project/<project_id>/csi-tags', methods=['GET'])
def api_project_csi_tags_get(project_id):
    """Get CSI tags for a project."""
    all_tags = status_tracker.get_all_tags(project_id)
    return jsonify({
        "status": "ok",
        "project_id": project_id,
        "csi_tags": all_tags.get("csi", []),
        "manual_tags": all_tags.get("manual", []),
        "all_tags": all_tags.get("all", [])
    })


@app.route('/api/project/<project_id>/csi-tags', methods=['POST'])
def api_project_csi_tags_set(project_id):
    """Set CSI tags for a project manually."""
    data = request.json or {}
    tags = data.get('tags', [])
    
    if not isinstance(tags, list):
        return jsonify({"error": "tags must be a list"}), 400
    
    status_tracker.set_csi_tags(project_id, tags)
    
    return jsonify({
        "status": "ok",
        "project_id": project_id,
        "csi_tags": tags
    })


@app.route('/api/csi/tags/options')
def api_csi_tag_options():
    """Get all possible CSI tag options for filter dropdowns."""
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


@app.route('/api/csi/tags/in-use')
def api_csi_tags_in_use():
    """Get CSI tags currently in use across all projects."""
    tag_counts = status_tracker.get_all_csi_tags_in_use()
    return jsonify({
        "status": "ok",
        "tags": tag_counts,
        "count": len(tag_counts)
    })


@app.route('/api/csi/tags/summary')
def api_csi_tags_summary():
    """Get summary statistics about CSI tag usage."""
    summary = status_tracker.get_csi_tag_summary()
    return jsonify({
        "status": "ok",
        **summary
    })


@app.route('/api/projects/by-csi-tag/<tag>')
def api_projects_by_csi_tag(tag):
    """Get all projects with a specific CSI tag."""
    from urllib.parse import unquote
    tag = unquote(tag)
    
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


# ==================== MODIFY EXISTING CSI ANALYSIS ====================
# Update the return statement in api_project_csi_analysis to include suggested tags

"""
In the existing api_project_csi_analysis function, add after line 3283:

        # Generate suggested tags
        try:
            from modules.csi import generate_simple_tags, generate_csi_tags
            suggested_tags = generate_simple_tags(sections_found)
            detailed_tags = generate_csi_tags(sections_found)
        except ImportError:
            suggested_tags = []
            detailed_tags = []

And update the return jsonify to include:
            "suggested_tags": suggested_tags,
            "detailed_tags": detailed_tags,
"""
