"""
Division 8 Analysis Routes Blueprint

Provides endpoints for:
- Viewing Division 8 analysis page with visual cards
- Running/refreshing analysis using OpenRouter RAG
- Exporting analysis as PDF report
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime

from flask import Blueprint, render_template, jsonify, request, Response, send_file

from utils import (
    find_project_by_id,
    get_project_folder_path,
    BIDDING_FOLDER
)

logger = logging.getLogger(__name__)

analysis_bp = Blueprint('analysis', __name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def resolve_project_folder(project_id: str, project: dict = None) -> Path:
    """
    Resolve the actual project folder path.

    Handles cases where:
    - folder_path is the base bidding folder (need to append source_id)
    - folder_path is the full project path
    - folder is a relative path
    """
    if project is None:
        project = find_project_by_id(project_id)

    if not project:
        return None

    # Check source_id first (for local bidding projects)
    source_id = project.get('source_id')
    folder_path = project.get('folder_path')

    # If we have a source_id and folder_path is the base bidding folder
    if source_id and folder_path:
        base_path = Path(folder_path)
        potential_path = base_path / source_id
        if potential_path.exists():
            return potential_path

    # Try get_project_folder_path result
    result_path, _ = get_project_folder_path(project_id)
    if result_path and result_path.exists():
        # Check if this is a valid project folder (has files, not just the base)
        try:
            if list(result_path.iterdir()):
                # Check if it looks like a project folder (has PDFs or extracted data)
                if any(result_path.glob('*.pdf')) or (result_path / 'extracted_project_data.json').exists():
                    return result_path
        except:
            pass

    # Try constructing from BIDDING_FOLDER and source_id
    if source_id:
        bidding_path = Path(BIDDING_FOLDER) / source_id
        if bidding_path.exists():
            return bidding_path

    # Try folder field
    folder = project.get('folder')
    if folder:
        folder_path = Path(folder)
        if folder_path.is_absolute() and folder_path.exists():
            return folder_path
        elif (Path(BIDDING_FOLDER) / folder).exists():
            return Path(BIDDING_FOLDER) / folder

    return result_path


def load_analysis(project_path: Path) -> dict:
    """
    Load existing analysis from project folder.

    Checks for both new format (division8_analysis.json) and
    legacy format (division8_rag_analysis.json).
    """
    # Try new format first
    analysis_file = project_path / "division8_analysis.json"
    if analysis_file.exists():
        try:
            with open(analysis_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading analysis file: {e}")

    # Fallback to legacy format
    legacy_file = project_path / "division8_rag_analysis.json"
    if legacy_file.exists():
        try:
            with open(legacy_file, 'r') as f:
                data = json.load(f)
                # Convert legacy format to new format
                return convert_legacy_analysis(data)
        except Exception as e:
            logger.error(f"Error loading legacy analysis file: {e}")

    return None


def convert_legacy_analysis(legacy: dict) -> dict:
    """Convert legacy analysis format to new format for display"""
    # Build new format from legacy data
    metadata = legacy.get('_rag_metadata', {})

    return {
        "metadata": {
            "project_id": metadata.get('project_id', ''),
            "project_name": "",
            "analyzed_at": metadata.get('generated_at') or metadata.get('analyzed_at', ''),
            "embedder": metadata.get('embedder', 'ollama-nomic-embed-text'),
            "generator": metadata.get('generator', 'unknown'),
            "chunks_analyzed": metadata.get('chunks_analyzed', 0),
            "confidence": legacy.get('confidence', 'medium')
        },
        "summary": {
            "scope_description": legacy.get('scope_summary', ''),
            "key_items": [],
            "total_doors": 0,
            "total_windows": 0,
            "has_storefront": bool(legacy.get('storefront', {}).get('sf_estimate', 0)),
            "has_curtain_wall": False,
            "has_hardware": bool(legacy.get('hardware', {}).get('groups'))
        },
        "doors": {
            "metal_doors_frames": {
                "specified": legacy.get('doors', {}).get('metal_count') != 'not specified',
                "count": legacy.get('doors', {}).get('metal_count', 'not specified'),
                "types": [],
                "manufacturers": [],
                "spec_sections": [],
                "notes": legacy.get('doors', {}).get('notes', [])
            },
            "wood_doors": {
                "excluded": legacy.get('doors', {}).get('wood_count_excluded', True),
                "exclusion_note": "Division 6 - by others"
            },
            "aluminum_doors": {
                "specified": False,
                "count": "not specified",
                "types": [],
                "manufacturers": [],
                "spec_sections": [],
                "notes": []
            },
            "access_doors": {
                "specified": False,
                "count": "not specified",
                "types": [],
                "spec_sections": [],
                "notes": []
            },
            "automatic_entrances": {
                "specified": False,
                "types": [],
                "manufacturers": [],
                "spec_sections": [],
                "notes": []
            }
        },
        "windows": {
            "aluminum_windows": {
                "specified": False,
                "count": "not specified",
                "types": legacy.get('windows', {}).get('types', []),
                "manufacturers": [legacy.get('windows', {}).get('manufacturers', '')] if legacy.get('windows', {}).get('manufacturers') else [],
                "performance": {},
                "spec_sections": [],
                "notes": legacy.get('windows', {}).get('notes', [])
            },
            "vinyl_windows": {
                "specified": 'vinyl' in str(legacy.get('windows', {}).get('types', [])).lower(),
                "count": legacy.get('windows', {}).get('count', 'not specified'),
                "types": [],
                "manufacturers": [],
                "performance": {},
                "spec_sections": [],
                "notes": []
            }
        },
        "storefronts": {
            "specified": bool(legacy.get('storefront', {}).get('sf_estimate', 0)),
            "sf_estimate": legacy.get('storefront', {}).get('sf_estimate', 0),
            "systems": [],
            "manufacturers": [],
            "finish": "",
            "spec_sections": [],
            "notes": []
        },
        "curtain_wall": {
            "specified": False,
            "sf_estimate": 0,
            "systems": [],
            "manufacturers": [],
            "spec_sections": [],
            "notes": []
        },
        "hardware": {
            "specified": bool(legacy.get('hardware', {}).get('groups')),
            "hardware_sets": legacy.get('hardware', {}).get('groups', []),
            "manufacturers": [legacy.get('hardware', {}).get('manufacturers', '')] if legacy.get('hardware', {}).get('manufacturers') else [],
            "lockset_types": [],
            "finish": "",
            "access_control": False,
            "spec_sections": [],
            "notes": legacy.get('hardware', {}).get('notes', [])
        },
        "glazing": {
            "specified": bool(legacy.get('glass', {}).get('specs')),
            "glass_types": legacy.get('glass', {}).get('specs', []),
            "performance": {},
            "spec_sections": [],
            "notes": legacy.get('glass', {}).get('notes', [])
        },
        "exclusions": legacy.get('exclusions', []),
        "alternates": [],
        "clarifications_needed": [],
        "source_documents": [],
        "_legacy_converted": True
    }


def format_date(date_str: str) -> str:
    """Format ISO date string for display"""
    if not date_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except:
        return date_str


# =============================================================================
# ANALYSIS PAGE ROUTE
# =============================================================================

@analysis_bp.route('/project/<project_id>/analysis')
def project_analysis_page(project_id):
    """
    Render the Division 8 analysis page with visual cards.

    This page displays:
    - Project metadata and analysis status
    - Tabbed navigation for different scope categories
    - Visual cards for doors, windows, storefronts, hardware, etc.
    - Actions to refresh analysis or export PDF
    """
    project = find_project_by_id(project_id)

    if not project:
        return render_template('error.html', message='Project not found'), 404

    project_path = resolve_project_folder(project_id, project)

    if not project_path or not project_path.exists():
        return render_template('error.html', message=f'Project folder not found'), 404

    # Load existing analysis
    analysis = load_analysis(project_path)

    # Get project name
    project_name = project.get('name') or project.get('title') or project.get('folder') or project_id

    return render_template(
        'analysis.html',
        project=project,
        project_id=project_id,
        project_name=project_name,
        analysis=analysis,
        format_date=format_date
    )


# =============================================================================
# ANALYSIS API ENDPOINTS
# =============================================================================

@analysis_bp.route('/api/project/<project_id>/analysis')
def get_analysis_data(project_id):
    """Get analysis data as JSON"""
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path = resolve_project_folder(project_id, project)

    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    analysis = load_analysis(project_path)

    if not analysis:
        return jsonify({
            "status": "not_analyzed",
            "message": "No analysis data found. Run analysis first."
        })

    return jsonify({
        "status": "ok",
        "project_id": project_id,
        "analysis": analysis
    })


@analysis_bp.route('/api/project/<project_id>/analysis/run', methods=['POST'])
def run_analysis(project_id):
    """
    Trigger new Division 8 analysis for a project.

    Uses OpenRouter RAG with local Ollama embeddings.
    """
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path = resolve_project_folder(project_id, project)

    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    try:
        # Import RAG module
        from modules.rag.division8_rag_openrouter import Division8RAGOpenRouter

        # Check for OpenRouter API key
        api_key = os.getenv('OPENROUTER_API_KEY')
        if not api_key:
            return jsonify({
                "error": "OpenRouter API key not configured",
                "message": "Set OPENROUTER_API_KEY environment variable"
            }), 500

        # Run analysis
        rag = Division8RAGOpenRouter(project_path)
        rag.project_name = project.get('name') or project.get('title') or project_id

        results = rag.analyze_project(selective=True)

        # Check for errors
        if 'error' in results:
            return jsonify({
                "status": "error",
                "error": results['error']
            }), 500

        # Save results
        output_path = rag.save_results(results)

        return jsonify({
            "status": "ok",
            "message": "Analysis complete",
            "output_file": str(output_path.name),
            "chunks_analyzed": results.get('metadata', {}).get('chunks_analyzed', 0),
            "confidence": results.get('metadata', {}).get('confidence', 'unknown')
        })

    except ImportError as e:
        logger.error(f"RAG module import error: {e}")
        return jsonify({
            "error": "RAG module not available",
            "details": str(e)
        }), 500
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500


@analysis_bp.route('/api/project/<project_id>/analysis/export/pdf')
def export_analysis_pdf(project_id):
    """
    Generate and download PDF report of Division 8 analysis.
    """
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path = resolve_project_folder(project_id, project)

    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    analysis = load_analysis(project_path)

    if not analysis:
        return jsonify({
            "error": "No analysis data found",
            "message": "Run analysis first before exporting PDF"
        }), 404

    try:
        from modules.analysis.pdf_generator import AnalysisPDFGenerator

        project_name = project.get('name') or project.get('title') or project_id

        generator = AnalysisPDFGenerator()
        pdf_bytes = generator.generate(project, analysis, project_name)

        # Create filename
        safe_name = "".join(c if c.isalnum() or c in ' -_' else '_' for c in project_name)
        filename = f"Division8_Analysis_{safe_name}.pdf"

        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )

    except ImportError as e:
        logger.error(f"PDF generator import error: {e}")
        return jsonify({
            "error": "PDF generator not available",
            "details": str(e),
            "hint": "Install weasyprint: pip3 install weasyprint"
        }), 500
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": str(e)
        }), 500


@analysis_bp.route('/api/project/<project_id>/analysis/status')
def get_analysis_status(project_id):
    """Check if analysis exists and its metadata"""
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path = resolve_project_folder(project_id, project)

    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    # Check for analysis files
    new_file = project_path / "division8_analysis.json"
    legacy_file = project_path / "division8_rag_analysis.json"

    if new_file.exists():
        try:
            with open(new_file, 'r') as f:
                data = json.load(f)
            metadata = data.get('metadata', {})
            return jsonify({
                "status": "analyzed",
                "format": "new",
                "analyzed_at": metadata.get('analyzed_at'),
                "confidence": metadata.get('confidence'),
                "generator": metadata.get('generator'),
                "chunks_analyzed": metadata.get('chunks_analyzed')
            })
        except:
            pass

    if legacy_file.exists():
        try:
            with open(legacy_file, 'r') as f:
                data = json.load(f)
            metadata = data.get('_rag_metadata', {})
            return jsonify({
                "status": "analyzed",
                "format": "legacy",
                "analyzed_at": metadata.get('generated_at') or metadata.get('analyzed_at'),
                "confidence": data.get('confidence'),
                "generator": metadata.get('generator'),
                "chunks_analyzed": metadata.get('chunks_analyzed')
            })
        except:
            pass

    return jsonify({
        "status": "not_analyzed",
        "message": "No analysis found for this project"
    })


@analysis_bp.route('/api/project/<project_id>/rag-scope')
def get_rag_scope(project_id):
    """
    Get RAG analysis data for unified scope component.

    Returns summary and categories for the RAG Results tab
    in UnifiedScopeManager.
    """
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    project_path = resolve_project_folder(project_id, project)

    if not project_path or not project_path.exists():
        return jsonify({"error": "Project folder not found"}), 404

    analysis = load_analysis(project_path)

    if not analysis:
        return jsonify({
            "summary": None,
            "categories": [],
            "status": "not_analyzed"
        })

    # Build response for UnifiedScopeManager
    categories = []

    # Summary section
    summary_data = analysis.get('summary', {})
    scope_description = summary_data.get('scope_description', '')

    # Doors category
    doors = analysis.get('doors', {})
    metal_doors = doors.get('metal_doors_frames', {})
    if metal_doors.get('specified'):
        categories.append({
            "icon": "🚪",
            "title": "Metal Doors & Frames",
            "confidence": 0.85 if metal_doors.get('count') else 0.6,
            "details": f"<p><strong>Count:</strong> {metal_doors.get('count', 'TBD')}</p>" +
                      (f"<p><strong>Types:</strong> {', '.join(metal_doors.get('types', []))}</p>" if metal_doors.get('types') else "") +
                      (f"<p><strong>Manufacturers:</strong> {', '.join(metal_doors.get('manufacturers', []))}</p>" if metal_doors.get('manufacturers') else "") +
                      (f"<p><strong>Notes:</strong> {'; '.join(metal_doors.get('notes', []))}</p>" if metal_doors.get('notes') else "")
        })

    # Windows category
    windows = analysis.get('windows', {})
    for window_type in ['aluminum_windows', 'vinyl_windows']:
        window_data = windows.get(window_type, {})
        if window_data.get('specified'):
            type_name = window_type.replace('_', ' ').title()
            categories.append({
                "icon": "🪟",
                "title": type_name,
                "confidence": 0.85 if window_data.get('count') else 0.6,
                "details": f"<p><strong>Count:</strong> {window_data.get('count', 'TBD')}</p>" +
                          (f"<p><strong>Types:</strong> {', '.join(window_data.get('types', []))}</p>" if window_data.get('types') else "") +
                          (f"<p><strong>Manufacturers:</strong> {', '.join(window_data.get('manufacturers', []))}</p>" if window_data.get('manufacturers') else "") +
                          (f"<p><strong>Notes:</strong> {'; '.join(window_data.get('notes', []))}</p>" if window_data.get('notes') else "")
            })

    # Storefront category
    storefronts = analysis.get('storefronts', {})
    if storefronts.get('specified'):
        categories.append({
            "icon": "🏢",
            "title": "Storefront",
            "confidence": 0.8 if storefronts.get('sf_estimate') else 0.5,
            "details": f"<p><strong>SF Estimate:</strong> {storefronts.get('sf_estimate', 'TBD')} SF</p>" +
                      (f"<p><strong>Systems:</strong> {', '.join(storefronts.get('systems', []))}</p>" if storefronts.get('systems') else "") +
                      (f"<p><strong>Manufacturers:</strong> {', '.join(storefronts.get('manufacturers', []))}</p>" if storefronts.get('manufacturers') else "") +
                      (f"<p><strong>Finish:</strong> {storefronts.get('finish', '')}</p>" if storefronts.get('finish') else "") +
                      (f"<p><strong>Notes:</strong> {'; '.join(storefronts.get('notes', []))}</p>" if storefronts.get('notes') else "")
        })

    # Curtain Wall category
    curtain_wall = analysis.get('curtain_wall', {})
    if curtain_wall.get('specified'):
        categories.append({
            "icon": "🏗️",
            "title": "Curtain Wall",
            "confidence": 0.8 if curtain_wall.get('sf_estimate') else 0.5,
            "details": f"<p><strong>SF Estimate:</strong> {curtain_wall.get('sf_estimate', 'TBD')} SF</p>" +
                      (f"<p><strong>Systems:</strong> {', '.join(curtain_wall.get('systems', []))}</p>" if curtain_wall.get('systems') else "") +
                      (f"<p><strong>Manufacturers:</strong> {', '.join(curtain_wall.get('manufacturers', []))}</p>" if curtain_wall.get('manufacturers') else "") +
                      (f"<p><strong>Notes:</strong> {'; '.join(curtain_wall.get('notes', []))}</p>" if curtain_wall.get('notes') else "")
        })

    # Hardware category
    hardware = analysis.get('hardware', {})
    if hardware.get('specified'):
        hardware_sets = hardware.get('hardware_sets', [])
        hardware_details = f"<p><strong>Hardware Sets:</strong> {len(hardware_sets)} groups</p>" if hardware_sets else ""
        categories.append({
            "icon": "🔑",
            "title": "Door Hardware",
            "confidence": 0.7 if hardware_sets else 0.5,
            "details": hardware_details +
                      (f"<p><strong>Manufacturers:</strong> {', '.join(hardware.get('manufacturers', []))}</p>" if hardware.get('manufacturers') else "") +
                      (f"<p><strong>Finish:</strong> {hardware.get('finish', '')}</p>" if hardware.get('finish') else "") +
                      (f"<p><strong>Access Control:</strong> {'Yes' if hardware.get('access_control') else 'No'}</p>") +
                      (f"<p><strong>Notes:</strong> {'; '.join(hardware.get('notes', []))}</p>" if hardware.get('notes') else "")
        })

    # Glazing category
    glazing = analysis.get('glazing', {})
    if glazing.get('specified'):
        categories.append({
            "icon": "🔲",
            "title": "Glass & Glazing",
            "confidence": 0.75 if glazing.get('glass_types') else 0.5,
            "details": (f"<p><strong>Glass Types:</strong> {', '.join(glazing.get('glass_types', []))}</p>" if glazing.get('glass_types') else "") +
                      (f"<p><strong>Notes:</strong> {'; '.join(glazing.get('notes', []))}</p>" if glazing.get('notes') else "")
        })

    # Build exclusions list
    exclusions = analysis.get('exclusions', [])
    if exclusions:
        exclusions_html = "<ul>" + "".join(f"<li>{ex}</li>" for ex in exclusions) + "</ul>"
        categories.append({
            "icon": "⛔",
            "title": "Exclusions",
            "confidence": 1.0,
            "details": exclusions_html
        })

    return jsonify({
        "summary": f"<p>{scope_description}</p>" if scope_description else "<p>AI analysis complete. See categories below.</p>",
        "categories": categories,
        "status": "analyzed",
        "metadata": analysis.get('metadata', {})
    })
