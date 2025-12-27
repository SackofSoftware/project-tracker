"""
Intake Routes

API endpoints for smart project intake:
- Analyze new project folders
- Parse emails for metadata
- Classify files
- Confirm and process intake

Updated to use SQLite database with JSON fallback.
"""

from flask import Blueprint, jsonify, request, render_template
from pathlib import Path
import os
import sys
import json
import shutil
from datetime import datetime
import logging

from modules.intake.email_parser import EmailParser
from modules.intake.file_classifier import FileClassifier, FileType
from utils import BIDDING_FOLDER as _BIDDING_FOLDER

logger = logging.getLogger(__name__)

intake_bp = Blueprint('intake', __name__)

BIDDING_FOLDER = Path(_BIDDING_FOLDER)


def is_pending_intake(folder: Path) -> bool:
    """
    Check if a folder needs intake review.

    A folder needs review if:
    - It has a random/hash-like name (no spaces, short)
    - OR it doesn't have extracted_project_data.json
    - AND it has PDFs or emails
    """
    name = folder.name

    # Skip known system folders
    skip_folders = {'.claude', 'div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman',
                    'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025',
                    '.chroma', '.chroma_local'}
    if name in skip_folders or name.startswith('.'):
        return False

    # Has extracted data = already processed
    if (folder / 'extracted_project_data.json').exists():
        return False

    # Check if it has any content worth processing (search recursively)
    has_pdfs = any(folder.rglob('*.pdf'))
    has_emails = any(folder.rglob('*.eml'))

    if not has_pdfs and not has_emails:
        return False

    # Hash-like name (random characters, no spaces)
    if ' ' not in name and len(name) < 30 and not name.replace('_', '').replace('-', '').isalpha():
        return True

    # Very short cryptic name
    if len(name) < 15 and ' ' not in name:
        return True

    # No extracted data but has content
    return True


def suggest_project_name(email_data: dict, folder_name: str) -> str:
    """Generate suggested project name from email data or folder name."""
    if email_data and email_data.get('extracted'):
        extracted = email_data['extracted']
        project_name = extracted.get('project_name')
        location = extracted.get('location')

        if project_name:
            # Try to extract city/state from location
            if location:
                # Parse "Street, City, State ZIP" format
                parts = location.split(',')
                if len(parts) >= 2:
                    city = parts[-2].strip() if len(parts) >= 3 else parts[0].strip()
                    state = parts[-1].strip()[:2] if parts[-1].strip() else ''
                    if state and len(state) >= 2:
                        return f"{project_name} - {city} {state}"
            return project_name

    # Fall back to cleaning folder name
    return folder_name.replace('_', ' ').replace('-', ' ').title()


@intake_bp.route('/intake')
def intake_page():
    """Render the intake review page."""
    return render_template('intake.html')


@intake_bp.route('/api/intake/pending')
def get_pending_intake():
    """
    Get list of folders that need intake review.

    Returns list of folder names that appear to be new/unprocessed projects.
    """
    pending = []

    for item in BIDDING_FOLDER.iterdir():
        if item.is_dir() and is_pending_intake(item):
            # Quick summary (search recursively for files in subfolders)
            pdf_count = len(list(item.rglob('*.pdf')))
            eml_count = len(list(item.rglob('*.eml')))

            pending.append({
                'folder': item.name,
                'path': str(item),
                'pdf_count': pdf_count,
                'email_count': eml_count,
                'has_emails': eml_count > 0
            })

    # Sort by email presence (folders with emails first)
    pending.sort(key=lambda x: (-x['has_emails'], x['folder']))

    return jsonify({
        'count': len(pending),
        'folders': pending
    })


@intake_bp.route('/api/intake/analyze/<folder_name>')
def analyze_folder(folder_name: str):
    """
    Analyze a folder for intake.

    Returns:
    - File classifications
    - Email metadata (if .eml files present)
    - Suggested project name
    - Recommended actions
    """
    folder = BIDDING_FOLDER / folder_name

    if not folder.exists():
        return jsonify({'error': 'Folder not found'}), 404

    # Classify files (with project_id for database storage)
    classifier = FileClassifier(project_id=folder_name)
    file_summary = classifier.get_folder_summary(folder)

    # Parse emails if present
    email_data = None
    if file_summary['emails']:
        parser = EmailParser(llm_provider='auto')
        # Use the first email found
        eml_path = Path(file_summary['emails'][0]['path'])
        email_data = parser.parse_eml(eml_path)

    # Generate suggested name
    suggested_name = suggest_project_name(email_data, folder_name)

    # Build recommended actions
    actions = []

    # 1. Rename folder if it looks like a hash
    if ' ' not in folder_name or len(folder_name) < 20:
        actions.append({
            'action': 'rename_folder',
            'from': folder_name,
            'to': suggested_name,
            'description': f'Rename folder to "{suggested_name}"'
        })

    # 2. Split drawing sets
    for ds in file_summary['drawing_sets']:
        if ds['details']['pages'] > 5:
            actions.append({
                'action': 'split_drawing_set',
                'file': ds['name'],
                'pages': ds['details']['pages'],
                'description': f'Split {ds["name"]} into individual sheets'
            })

    # 3. Split spec books
    for sb in file_summary['spec_books']:
        if sb['details']['pages'] > 50:
            actions.append({
                'action': 'split_spec_book',
                'file': sb['name'],
                'pages': sb['details']['pages'],
                'description': f'Split {sb["name"]} by CSI division'
            })

    # 4. Organize addenda
    if file_summary['addenda']:
        actions.append({
            'action': 'organize_addenda',
            'files': [a['name'] for a in file_summary['addenda']],
            'description': f'Move {len(file_summary["addenda"])} addenda to Addenda folder'
        })

    # 5. Move emails to Correspondence
    if file_summary['emails']:
        actions.append({
            'action': 'organize_emails',
            'files': [e['name'] for e in file_summary['emails']],
            'description': f'Move {len(file_summary["emails"])} emails to Correspondence folder'
        })

    # Build metadata from email
    metadata = {}
    if email_data and email_data.get('extracted'):
        ext = email_data['extracted']
        metadata = {
            'project_name': ext.get('project_name'),
            'location': ext.get('location'),
            'bid_date': ext.get('bid_date'),
            'bid_time': ext.get('bid_time'),
            'gc_name': ext.get('gc_name'),
            'gc_contact': ext.get('gc_contact'),
            'gc_email': ext.get('gc_email'),
            'owner': ext.get('owner'),
            'architect': ext.get('architect'),
            'trade_scope': ext.get('trade_scope'),
            'project_type': ext.get('project_type'),
            'source': 'email'
        }

    return jsonify({
        'folder': folder_name,
        'suggested_name': suggested_name,
        'files': file_summary['all_files'],
        'summary': {
            'total_files': file_summary['file_count'],
            'drawing_sets': len(file_summary['drawing_sets']),
            'spec_books': len(file_summary['spec_books']),
            'emails': len(file_summary['emails']),
            'addenda': len(file_summary['addenda'])
        },
        'metadata': metadata,
        'email_raw': email_data.get('raw') if email_data else None,
        'recommended_actions': actions
    })


@intake_bp.route('/api/intake/confirm', methods=['POST'])
def confirm_intake():
    """
    Confirm and execute intake actions.

    Request body:
    {
        "folder": "original_folder_name",
        "new_name": "New Project Name",
        "actions": ["rename_folder", "split_drawing_set", ...],
        "metadata": { ... }
    }
    """
    data = request.json
    folder_name = data.get('folder')
    new_name = data.get('new_name')
    actions = data.get('actions', [])
    metadata = data.get('metadata', {})

    folder = BIDDING_FOLDER / folder_name
    if not folder.exists():
        return jsonify({'error': 'Folder not found'}), 404

    results = []
    errors = []

    # Execute rename first if requested
    if 'rename_folder' in actions and new_name and new_name != folder_name:
        try:
            new_folder = BIDDING_FOLDER / new_name
            if new_folder.exists():
                errors.append(f'Folder "{new_name}" already exists')
            else:
                folder.rename(new_folder)
                folder = new_folder
                results.append(f'Renamed folder to "{new_name}"')
        except Exception as e:
            errors.append(f'Rename failed: {e}')

    # Create standard folders (only if they'll be used)
    folders_to_create = []
    if 'organize_addenda' in actions:
        folders_to_create.append('Addenda')
    if 'organize_emails' in actions:
        folders_to_create.append('Correspondence')

    for subfolder in folders_to_create:
        sub_path = folder / subfolder
        if not sub_path.exists():
            sub_path.mkdir(parents=True)
            results.append(f'Created {subfolder} folder')

    # Move addenda
    if 'organize_addenda' in actions:
        addenda_folder = folder / 'Addenda'
        for item in folder.glob('*.pdf'):
            name_lower = item.stem.lower()
            if any(p in name_lower for p in ['addendum', 'add_', 'add-']) and not any(p in name_lower for p in ['plan', 'drawing']):
                try:
                    shutil.move(str(item), str(addenda_folder / item.name))
                    results.append(f'Moved {item.name} to Addenda')
                except Exception as e:
                    errors.append(f'Failed to move {item.name}: {e}')

    # Move emails
    if 'organize_emails' in actions:
        corr_folder = folder / 'Correspondence'
        for item in folder.glob('*.eml'):
            try:
                shutil.move(str(item), str(corr_folder / item.name))
                results.append(f'Moved {item.name} to Correspondence')
            except Exception as e:
                errors.append(f'Failed to move {item.name}: {e}')

    # Save metadata to database and JSON
    if metadata:
        extracted_data = {
            'meta': {
                'source': 'intake',
                'processed_at': datetime.now().isoformat(),
                'version': '1.0'
            },
            'project': {
                'name': metadata.get('project_name') or new_name,
                'location': metadata.get('location'),
                'owner': metadata.get('owner'),
                'architect': metadata.get('architect'),
                'gc': metadata.get('gc_name'),
                'gc_contact': metadata.get('gc_contact'),
                'gc_email': metadata.get('gc_email')
            },
            'schedule': {
                'bid_date': metadata.get('bid_date'),
                'bid_time': metadata.get('bid_time')
            },
            'scope': {
                'trade': metadata.get('trade_scope'),
                'project_type': metadata.get('project_type')
            }
        }

        # Save to database
        try:
            from modules.database import queries

            # Parse bid_date if present
            bid_date = None
            if metadata.get('bid_date'):
                try:
                    from dateutil import parser
                    bid_date = parser.parse(metadata['bid_date'])
                except:
                    pass

            # Create or update project in database
            project_id = folder.name
            project_data = {
                'folder_path': str(folder),
                'title': metadata.get('project_name') or new_name,
                'source': 'local',
                'address': metadata.get('location'),
                'owner_name': metadata.get('owner'),
                'architect_name': metadata.get('architect'),
                'bid_date': bid_date
            }

            existing = queries.get_project(project_id)
            if existing:
                queries.update_project(project_id, project_data)
                logger.info(f"[Intake] Updated project {project_id} in database")
            else:
                queries.create_project(project_id, project_data)
                logger.info(f"[Intake] Created project {project_id} in database")

            # Save extracted data
            queries.save_extracted_data(
                project_id,
                extracted_data,
                metadata={
                    'schema_version': '1.0',
                    'extractor_model': 'email_parser',
                    'source_folder': str(folder),
                    'extracted_at': datetime.now()
                }
            )

            results.append('Saved project metadata to database')

        except ImportError:
            logger.warning("[Intake] Database module not available, only saving to JSON")
        except Exception as e:
            logger.error(f"[Intake] Failed to save to database: {e}")
            errors.append(f'Failed to save to database: {e}')

        # Also save to JSON for backward compatibility
        try:
            output_file = folder / 'extracted_project_data.json'
            with open(output_file, 'w') as f:
                json.dump(extracted_data, f, indent=2)
            results.append('Saved project metadata to JSON')
        except Exception as e:
            errors.append(f'Failed to save JSON metadata: {e}')

    return jsonify({
        'success': len(errors) == 0,
        'folder': str(folder),
        'new_name': folder.name,
        'results': results,
        'errors': errors,
        'next_steps': [
            'Run pipeline to split drawing sets and spec books',
            'Run RAG analysis for Division 8 scope'
        ]
    })


@intake_bp.route('/api/intake/run-pipeline/<folder_name>', methods=['POST'])
def trigger_pipeline(folder_name: str):
    """
    Trigger the processing pipeline for a folder.

    This runs the organize, split_specs, split_drawings stages.
    """
    folder = BIDDING_FOLDER / folder_name

    if not folder.exists():
        return jsonify({'error': 'Folder not found'}), 404

    # Import pipeline components
    try:
        from modules.pipeline import MasterPipeline
        import asyncio

        # Run pipeline stages
        pipeline = MasterPipeline(folder)
        # Run specific stages: organize, split_specs, split_drawings, rag_analysis
        # Use asyncio.run() since run_stages is async
        results = asyncio.run(pipeline.run_stages(['organize', 'split_specs', 'split_drawings', 'rag_analysis']))

        return jsonify({
            'success': True,
            'folder': folder_name,
            'pipeline_results': results
        })

    except ImportError as e:
        return jsonify({
            'error': f'Pipeline module not available: {e}',
            'folder': folder_name
        }), 500
    except Exception as e:
        return jsonify({
            'error': str(e),
            'folder': folder_name
        }), 500
