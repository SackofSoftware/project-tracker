"""
Project Brief Generation Routes Blueprint

Handles AI-powered project brief generation for Division 8 scope:
- Gathers comprehensive project context
- Generates briefs using LM Studio or OpenRouter
- Returns briefs in JSON or plain text format
"""

import os
import json
import requests
from pathlib import Path

from flask import Blueprint, jsonify, request, Response

from utils import (
    find_project_by_id,
    get_project_folder_path,
    BIDDING_FOLDER
)

from modules.estimates import EstimateReader
from modules.quotes import QuoteReader

# Import CSI Masterformat prompt builder for enhanced briefs (optional)
try:
    from modules.brief.prompt_builder import (
        build_division8_brief,
        get_section_description,
        load_division_context,
        load_manufacturer_specs
    )
    PROMPT_BUILDER_AVAILABLE = True
except ImportError as e:
    print(f"Prompt builder module not available in brief blueprint: {e}")
    PROMPT_BUILDER_AVAILABLE = False

# Import document classification modules (optional)
try:
    from modules.doc_classification import (
        extract_divisions_from_pdf,
        identify_sheets_in_pdf,
        summarize_disciplines,
        DISCIPLINE_CODES
    )
    DOC_CLASSIFICATION_AVAILABLE = True
except ImportError as e:
    print(f"Doc classification module not available in brief blueprint: {e}")
    DOC_CLASSIFICATION_AVAILABLE = False


brief_bp = Blueprint('brief', __name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def gather_project_context(project_path: Path, project: dict) -> dict:
    """
    Gather comprehensive project context for AI brief generation.

    Args:
        project_path: Path to the project folder
        project: Project dict with metadata

    Returns:
        Dict with all available project context
    """
    context = {
        'project_metadata': {},
        'division_8_scope': {},
        'drawings_summary': {},
        'openings_data': {},
        'estimate_status': {},
        'quotes_data': {},
        'available_documents': {},
        'errors': []
    }

    # 1. Basic project metadata
    context['project_metadata'] = {
        'name': project.get('name') or project.get('folder'),
        'address': project.get('address'),
        'owner': project.get('owner'),
        'architect': project.get('architect'),
        'bid_date': project.get('bid_date'),
        'source': project.get('source'),
        'project_code': project.get('project_code')
    }

    # 2. Load extracted project data if available
    extracted_data_path = project_path / 'extracted_project_data.json'
    if extracted_data_path.exists():
        try:
            with open(extracted_data_path, 'r') as f:
                extracted = json.load(f)

                # Get openings schedule
                openings = extracted.get('openings_schedule', {})
                context['openings_data'] = {
                    'windows': openings.get('windows', []),
                    'doors': openings.get('doors', []),
                    'storefronts': openings.get('storefronts', []),
                    'total_windows': len(openings.get('windows', [])),
                    'total_doors': len(openings.get('doors', [])),
                    'total_storefronts': len(openings.get('storefronts', []))
                }

                # Get Division 8 scope
                context['division_8_scope'] = extracted.get('division_8', {})

                # Get schedule
                schedule = extracted.get('schedule', {})
                if schedule:
                    context['project_metadata'].update({
                        'construction_start': schedule.get('construction_start'),
                        'construction_duration': schedule.get('duration'),
                        'substantial_completion': schedule.get('substantial_completion')
                    })

        except Exception as e:
            context['errors'].append(f"Error reading extracted_project_data.json: {str(e)}")

    # 3. Check for estimate spreadsheets
    try:
        estimate_reader = EstimateReader(str(project_path))
        estimate_result = estimate_reader.read_all()

        if estimate_result.get('openings'):
            context['estimate_status'] = {
                'has_estimate': True,
                'total_openings': estimate_result.get('total_count', 0),
                'unique_marks': estimate_result.get('unique_marks', 0),
                'by_type': estimate_result.get('by_type', {}),
                'files': estimate_result.get('files_read', [])
            }
        else:
            context['estimate_status'] = {'has_estimate': False}
    except Exception as e:
        context['estimate_status'] = {'has_estimate': False, 'error': str(e)}

    # 4. Check for quotes
    try:
        quote_reader = QuoteReader(str(project_path))
        quote_result = quote_reader.read_all_quotes()

        if quote_result.get('quotes'):
            context['quotes_data'] = {
                'has_quotes': True,
                'total_quotes': quote_result.get('total_quotes', 0),
                'quotes_with_pricing': quote_result.get('quotes_with_pricing', 0),
                'total_value': quote_result.get('total_value', 0),
                'vendors': quote_result.get('vendors', []),
                'quotes': quote_result.get('quotes', [])
            }
        else:
            context['quotes_data'] = {'has_quotes': False}
    except Exception as e:
        context['quotes_data'] = {'has_quotes': False, 'error': str(e)}

    # 5. Scan for available documents
    docs = {
        'specs': [],
        'drawings': [],
        'schedules': [],
        'addendums': [],
        'quotes': [],
        'other': []
    }

    try:
        for file_path in project_path.rglob('*.pdf'):
            name_lower = file_path.name.lower()
            relative_path = str(file_path.relative_to(project_path))

            if any(p in name_lower for p in ['spec', 'division', 'section', 'manual']):
                docs['specs'].append(relative_path)
            elif any(p in name_lower for p in ['drawing', 'sheet', 'plan', 'elevation', 'arch', 'dwg']):
                docs['drawings'].append(relative_path)
            elif any(p in name_lower for p in ['schedule', 'door schedule', 'window schedule', 'hardware']):
                docs['schedules'].append(relative_path)
            elif any(p in name_lower for p in ['addend', 'revision']):
                docs['addendums'].append(relative_path)
            elif any(p in name_lower for p in ['quote', 'proposal', 'bid', 'pricing']):
                docs['quotes'].append(relative_path)
            else:
                docs['other'].append(relative_path)

        # Also check for Excel files
        for file_path in project_path.rglob('*.xlsx'):
            name_lower = file_path.name.lower()
            if not name_lower.startswith('~$'):  # Skip temp files
                docs['schedules'].append(str(file_path.relative_to(project_path)))

    except Exception as e:
        context['errors'].append(f"Error scanning documents: {str(e)}")

    context['available_documents'] = docs

    # 6. Check for Division 8 spec sections
    if DOC_CLASSIFICATION_AVAILABLE:
        try:
            spec_pdfs = [f for f in docs['specs'] if f][:3]  # Limit to 3 specs
            division8_sections = []

            for spec_file in spec_pdfs:
                try:
                    divisions = extract_divisions_from_pdf(
                        project_path / spec_file,
                        target_divisions=["08"],
                        max_pages=100
                    )

                    if "08" in divisions:
                        div8 = divisions["08"]
                        for section in div8.sections:
                            division8_sections.append({
                                'section_id': section.section_id,
                                'title': section.title,
                                'source_file': spec_file
                            })
                except:
                    pass

            if division8_sections:
                context['division_8_scope']['sections'] = division8_sections

        except Exception as e:
            context['errors'].append(f"Error extracting Division 8 specs: {str(e)}")

    return context


def generate_project_brief(context: dict, use_lm_studio: bool = True) -> str:
    """
    Generate an AI project brief using LLM with CSI Masterformat enrichment.

    Args:
        context: Project context dict from gather_project_context()
        use_lm_studio: If True, try LM Studio first, fallback to OpenRouter

    Returns:
        Generated brief text
    """
    # Build CSI-enriched prompt if prompt_builder is available
    if PROMPT_BUILDER_AVAILABLE:
        # Create context dict for prompt_builder (maps our context to expected format)
        meta = context.get('project_metadata', {})
        div8 = context.get('division_8_scope', {})

        pb_context = {
            'title': meta.get('name', 'Unknown Project'),
            'location': meta.get('address', ''),
            'value': meta.get('value', ''),
            'bid_date': meta.get('bid_date', ''),
            'description': div8.get('scope_summary', ''),
            'scope': json.dumps(div8, indent=2),
            'specifications': ', '.join([
                s.get('section_id', '')
                for s in div8.get('sections', [])
            ])
        }

        # Build CSI-enriched base prompt with section descriptions and manufacturer data
        csi_prompt = build_division8_brief(pb_context)

        # Append additional project-specific data that prompt_builder doesn't cover
        prompt = f"""{csi_prompt}

ADDITIONAL PROJECT DATA:

OPENINGS DATA:
{json.dumps(context.get('openings_data', {}), indent=2)}

ESTIMATE STATUS:
{json.dumps(context.get('estimate_status', {}), indent=2)}

VENDOR QUOTES:
{json.dumps(context.get('quotes_data', {}), indent=2)}

AVAILABLE DOCUMENTS:
{json.dumps(context.get('available_documents', {}), indent=2)}

Based on all the above context (CSI section references, manufacturer products, and project data),
generate a comprehensive project brief that includes:
1. Project summary with Division 8 scope highlights
2. CSI specification sections identified (with descriptions)
3. Specified manufacturers and their products
4. Openings breakdown (windows, doors, storefronts)
5. Estimate and quote status
6. Key clarifications needed
7. Next steps for bid preparation"""
    else:
        # Fallback to original prompt if prompt_builder not available
        prompt = f"""You are a construction project analyst for a Division 8 (Openings) contractor specializing in doors, windows, storefronts, and glazing.

Generate a concise project brief based on the following information:

PROJECT METADATA:
{json.dumps(context['project_metadata'], indent=2)}

DIVISION 8 SCOPE:
{json.dumps(context['division_8_scope'], indent=2)}

OPENINGS DATA:
{json.dumps(context['openings_data'], indent=2)}

ESTIMATE STATUS:
{json.dumps(context['estimate_status'], indent=2)}

QUOTES:
{json.dumps(context['quotes_data'], indent=2)}

AVAILABLE DOCUMENTS:
{json.dumps(context['available_documents'], indent=2)}

Generate a brief following this structure:

PROJECT SUMMARY
[2-3 sentences summarizing the project scope, focusing on Division 8 work. Include key details about windows, doors, storefronts.]

SCHEDULE
Start: [date or TBD] | Duration: [days or TBD] | Bid Date: [date or TBD]

DIVISION 8 SCOPE
[List of spec sections if known, with brief descriptions]
[Window/door quantities and types]
[Key manufacturers or systems specified]

OPENINGS BREAKDOWN
Windows: [count and key types]
Doors: [count and key types]
Storefronts: [count if applicable]

DOCUMENTS AVAILABLE
✓ [List available document types]
✗ [List missing critical documents]

ESTIMATE STATUS
[Current status: Has takeoff? Has quotes? Quote value range?]

NEXT STEPS
[2-3 bullet points on what needs to be done]

Keep it concise, professional, and actionable. If information is missing, say "TBD" or "Not available"."""

    # Try LM Studio first
    if use_lm_studio:
        try:
            response = requests.post(
                "http://localhost:1234/v1/chat/completions",
                json={
                    "model": "local-model",
                    "messages": [
                        {"role": "system", "content": "You are a construction project analyst specializing in Division 8 (Openings) work."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2000
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
        except Exception as e:
            print(f"LM Studio call failed: {e}, falling back to OpenRouter")

    # Fallback to OpenRouter
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        # Return a simple text-based brief if no API available
        return generate_simple_brief(context)

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://project-tracker.local",
            },
            json={
                "model": "amazon/nova-lite-v1",
                "messages": [
                    {"role": "system", "content": "You are a construction project analyst specializing in Division 8 (Openings) work."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 2000
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            print(f"OpenRouter API error: {response.status_code} - {response.text}")
            return generate_simple_brief(context)

    except Exception as e:
        print(f"OpenRouter call failed: {e}")
        return generate_simple_brief(context)


def generate_simple_brief(context: dict) -> str:
    """Generate a simple text-based brief without AI when APIs are unavailable."""
    meta = context['project_metadata']
    openings = context['openings_data']
    estimate = context['estimate_status']
    quotes = context['quotes_data']
    docs = context['available_documents']
    div8 = context['division_8_scope']

    brief = f"""PROJECT SUMMARY
{meta.get('name', 'Unknown Project')}
{meta.get('address', 'Address not available')}

Owner: {meta.get('owner') or 'TBD'}
Architect: {meta.get('architect') or 'TBD'}

This project includes Division 8 work with {openings.get('total_windows', 0)} windows, {openings.get('total_doors', 0)} doors, and {openings.get('total_storefronts', 0)} storefronts.

SCHEDULE
Start: {meta.get('construction_start') or 'TBD'} | Duration: {meta.get('construction_duration') or 'TBD'} | Bid Date: {meta.get('bid_date') or 'TBD'}

DIVISION 8 SCOPE
"""

    # Add spec sections if available
    if div8.get('sections'):
        brief += "Specification Sections:\n"
        for section in div8['sections'][:10]:  # Limit to 10
            brief += f"  • {section.get('section_id')}: {section.get('title')}\n"

    # Add openings breakdown
    if openings.get('windows'):
        brief += f"\nWindows:\n"
        window_types = {}
        for w in openings['windows'][:10]:  # Limit display
            wtype = w.get('type', 'Unknown')
            qty = w.get('qty', 1)
            if wtype in window_types:
                window_types[wtype] += qty if qty else 0
            else:
                window_types[wtype] = qty if qty else 0
        for wtype, qty in list(window_types.items())[:5]:
            brief += f"  • {wtype}: {qty} units\n"

    if openings.get('doors'):
        brief += f"\nDoors:\n"
        door_types = {}
        for d in openings['doors'][:10]:
            dtype = d.get('material', 'Unknown')
            qty = d.get('qty', 1)
            if dtype in door_types:
                door_types[dtype] += qty if qty else 0
            else:
                door_types[dtype] = qty if qty else 0
        for dtype, qty in list(door_types.items())[:5]:
            brief += f"  • {dtype}: {qty} units\n"

    brief += f"""
DOCUMENTS AVAILABLE
✓ Specs: {len(docs.get('specs', []))} files
✓ Drawings: {len(docs.get('drawings', []))} files
✓ Schedules: {len(docs.get('schedules', []))} files
✓ Quotes: {len(docs.get('quotes', []))} files
"""

    # Check for missing documents
    missing = []
    if not docs.get('specs'):
        missing.append("Specifications")
    if not docs.get('drawings'):
        missing.append("Drawings")
    if not docs.get('schedules'):
        missing.append("Door/Window Schedules")

    if missing:
        brief += "✗ Missing: " + ", ".join(missing) + "\n"

    brief += f"""
ESTIMATE STATUS
"""

    if estimate.get('has_estimate'):
        brief += f"Takeoff Complete: {estimate.get('total_openings', 0)} openings in {len(estimate.get('files', []))} files\n"
    else:
        brief += "No takeoff spreadsheets found\n"

    if quotes.get('has_quotes'):
        brief += f"Quotes Received: {quotes.get('total_quotes', 0)} quotes from {len(quotes.get('vendors', []))} vendors\n"
        if quotes.get('total_value'):
            brief += f"Total Quote Value: ${quotes['total_value']:,.2f}\n"
    else:
        brief += "No vendor quotes found\n"

    brief += """
NEXT STEPS
• Review specifications and drawings
• Complete takeoff if not done
• Request quotes from qualified vendors
• Prepare bid package
"""

    return brief


# =============================================================================
# BRIEF GENERATION ENDPOINT
# =============================================================================

@brief_bp.route('/api/project/<project_id>/brief')
def api_project_brief(project_id):
    """
    Generate an AI-powered project brief for Division 8 scope.

    This endpoint gathers all available project data and uses an LLM
    to generate a comprehensive summary including:
    - Project metadata and key dates
    - Division 8 scope from specs
    - Window/door counts and types
    - Available documents
    - Estimate and quote status
    - Next steps

    Query parameters:
    - use_lm_studio: true/false (default: true) - Try LM Studio first
    - force_openrouter: true/false (default: false) - Force OpenRouter
    - format: json/text (default: json)
    """
    # Find project
    project = find_project_by_id(project_id)

    if not project:
        return jsonify({"error": "Project not found"}), 404

    # Get project folder
    project_path, _ = get_project_folder_path(project_id)

    if not project_path or not project_path.exists():
        return jsonify({"error": f"Project folder not found: {project_path}"}), 404

    try:
        # Gather context
        context = gather_project_context(project_path, project)

        # Generate brief
        use_lm_studio = request.args.get('use_lm_studio', 'true').lower() == 'true'
        force_openrouter = request.args.get('force_openrouter', 'false').lower() == 'true'

        if force_openrouter:
            use_lm_studio = False

        brief_text = generate_project_brief(context, use_lm_studio=use_lm_studio)

        # Return format
        response_format = request.args.get('format', 'json').lower()

        if response_format == 'text':
            return Response(brief_text, mimetype='text/plain')
        else:
            return jsonify({
                "status": "ok",
                "project_id": project_id,
                "project_name": context['project_metadata'].get('name'),
                "brief": brief_text,
                "context": context,
                "errors": context.get('errors', [])
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
