"""
Scope Cards API Blueprint

Provides structured Division 8 scope data formatted for the Command Center UI.
Returns 7 hardcoded scope cards with standardized fields.

Cards (in order):
1. Glass & Glazing
2. Storefront & Curtain Wall
3. Commercial Windows
4. Metal Doors & Frames
5. Wood Doors
6. Door Hardware
7. Specialties
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from flask import Blueprint, jsonify, request

from utils import (
    find_project_by_id,
    get_project_folder_path,
    get_status_tracker,
    BIDDING_FOLDER
)

scope_cards_bp = Blueprint('scope_cards', __name__)


# =============================================================================
# SCOPE CARD DATA STRUCTURES
# =============================================================================

@dataclass
class PerformanceSpecs:
    """Performance specifications for glazing"""
    u_factor: Optional[float] = None
    shgc: Optional[float] = None
    vlt: Optional[float] = None
    stc: Optional[int] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ScopeCard:
    """Standard scope card structure"""
    id: str
    title: str
    icon: str
    order: int
    status: str  # 'specified', 'not_specified', 'by_others', 'pending'
    data: dict
    spec_references: List[str]
    linked_drawings: List[str]
    notes: List[str]

    def to_dict(self) -> dict:
        return asdict(self)


# Card definitions with CSI section mappings
CARD_DEFINITIONS = [
    {
        'id': 'glass-glazing',
        'title': 'Glass & Glazing',
        'icon': 'glass',
        'order': 1,
        'csi_prefixes': ['08 80', '08 81', '08 83', '08 84', '08 85', '08 87', '08 88'],
        'data_keys': ['glazing', 'glass'],
    },
    {
        'id': 'storefront-curtainwall',
        'title': 'Storefront & Curtain Wall',
        'icon': 'storefront',
        'order': 2,
        'csi_prefixes': ['08 41', '08 42', '08 43', '08 44', '08 45'],
        'data_keys': ['storefront', 'curtain_wall', 'curtainwall', 'glazing_systems'],
    },
    {
        'id': 'commercial-windows',
        'title': 'Commercial Windows',
        'icon': 'window',
        'order': 3,
        'csi_prefixes': ['08 51', '08 52', '08 53', '08 54', '08 55', '08 56'],
        'data_keys': ['windows'],
    },
    {
        'id': 'metal-doors',
        'title': 'Metal Doors & Frames',
        'icon': 'door-metal',
        'order': 4,
        'csi_prefixes': ['08 11', '08 12', '08 13', '08 14', '08 31', '08 32', '08 33', '08 34'],
        'data_keys': ['metal_doors', 'doors'],
    },
    {
        'id': 'door-hardware',
        'title': 'Door Hardware',
        'icon': 'hardware',
        'order': 6,
        'csi_prefixes': ['08 71', '08 74', '08 75', '08 78', '08 79'],
        'data_keys': ['hardware'],
    },
    {
        'id': 'specialties',
        'title': 'Specialties',
        'icon': 'specialty',
        'order': 7,
        'csi_prefixes': ['08 91', '08 95'],  # Louvers, vents, etc.
        'data_keys': ['specialties', 'exclusions', 'alternates'],
    },
]


# =============================================================================
# DATA EXTRACTION HELPERS
# =============================================================================

def extract_basis_of_design(data: dict) -> Optional[str]:
    """Extract manufacturer/product as basis of design"""
    # Try various field names
    for key in ['basis_of_design', 'manufacturer', 'manufacturers', 'product', 'series']:
        if key in data:
            val = data[key]
            if isinstance(val, list) and val:
                return val[0] if isinstance(val[0], str) else str(val[0])
            elif isinstance(val, str) and val:
                return val
    return None


def extract_material(data: dict) -> Optional[str]:
    """Extract material specification"""
    for key in ['material', 'materials', 'type', 'frame_material']:
        if key in data:
            val = data[key]
            if isinstance(val, list) and val:
                return val[0] if isinstance(val[0], str) else str(val[0])
            elif isinstance(val, str) and val:
                return val
    return None


def extract_finish(data: dict) -> Optional[str]:
    """Extract finish specification"""
    for key in ['finish', 'finishes', 'frame_finish', 'color']:
        if key in data:
            val = data[key]
            if isinstance(val, list) and val:
                return val[0]
            elif isinstance(val, str) and val:
                return val
    return None


def extract_performance(data: dict) -> dict:
    """Extract performance specifications"""
    perf = {}

    # Direct performance keys
    if 'performance' in data and isinstance(data['performance'], dict):
        perf = data['performance'].copy()

    # Also check performance_specs
    if 'performance_specs' in data and isinstance(data['performance_specs'], dict):
        perf.update(data['performance_specs'])

    # Check individual fields
    for key in ['u_factor', 'u_value', 'shgc', 'vlt', 'stc']:
        if key in data and data[key] is not None:
            # Normalize key name
            norm_key = 'u_factor' if key == 'u_value' else key
            perf[norm_key] = data[key]

    return perf


def extract_count(data: dict) -> Optional[str]:
    """Extract quantity/count"""
    for key in ['count', 'count_estimate', 'quantity', 'qty', 'total']:
        if key in data:
            val = data[key]
            if val:
                return str(val)
    return None


def extract_notes(data: dict) -> List[str]:
    """Extract notes"""
    notes = []
    if 'notes' in data:
        if isinstance(data['notes'], list):
            notes.extend([str(n) for n in data['notes'] if n])
        elif isinstance(data['notes'], str) and data['notes']:
            notes.append(data['notes'])
    if 'note' in data and data['note']:
        notes.append(str(data['note']))
    return notes


def determine_status(data: dict, card_def: dict) -> str:
    """Determine card status based on data"""
    # Check for explicit status
    if 'specified' in data:
        if data['specified']:
            return 'specified'
        else:
            return 'not_specified'

    # Check for 'in_scope' flag
    if 'in_scope' in data:
        if data['in_scope']:
            return 'specified'
        else:
            return 'not_specified'

    # Check for 'by_others' indicators
    if 'present_in_project' in data and data['present_in_project']:
        return 'by_others'

    # Check default status for card type
    if card_def.get('default_status'):
        return card_def['default_status']

    # If we have any meaningful data, assume specified
    meaningful_keys = ['manufacturer', 'manufacturers', 'type', 'types', 'material', 'count']
    if any(data.get(k) for k in meaningful_keys):
        return 'specified'

    return 'not_specified'


# =============================================================================
# SCOPE CARD BUILDER
# =============================================================================

def build_scope_cards(project: dict, status: dict = None) -> List[dict]:
    """
    Build 7 scope cards from project data.

    Args:
        project: Project data dict
        status: Status tracker data

    Returns:
        List of scope card dicts
    """
    cards = []

    # Gather all possible data sources
    rag_analysis = project.get('rag_analysis', {})
    division_8_scope = project.get('division_8_scope', {})
    extracted_data = project.get('extracted_data', {}).get('division_8', {})
    internal_status = status or project.get('status', {})
    csi_analysis = internal_status.get('csi_analysis', {})

    # Combine data sources (priority: rag > extracted > status)
    combined_data = {}
    for source in [internal_status, extracted_data, division_8_scope, rag_analysis]:
        if isinstance(source, dict):
            combined_data.update(source)

    # Build each card
    for card_def in CARD_DEFINITIONS:
        card_data = {}

        # Find relevant data for this card
        for data_key in card_def['data_keys']:
            if data_key in combined_data and combined_data[data_key]:
                source_data = combined_data[data_key]
                if isinstance(source_data, dict):
                    card_data.update(source_data)

        # Extract standardized fields
        extracted = {
            'basis_of_design': extract_basis_of_design(card_data),
            'material': extract_material(card_data),
            'finish': extract_finish(card_data),
            'performance': extract_performance(card_data),
            'count': extract_count(card_data),
        }

        # Find spec references
        spec_refs = []
        for prefix in card_def['csi_prefixes']:
            # Check if any CSI sections match
            for section in csi_analysis.get('sections', []):
                if isinstance(section, str) and section.startswith(prefix):
                    spec_refs.append(section)
                elif isinstance(section, dict) and str(section.get('number', '')).startswith(prefix):
                    spec_refs.append(section.get('number', ''))

        # Build card
        card = ScopeCard(
            id=card_def['id'],
            title=card_def['title'],
            icon=card_def['icon'],
            order=card_def['order'],
            status=determine_status(card_data, card_def),
            data=extracted,
            spec_references=list(set(spec_refs)),
            linked_drawings=[],  # Populated by auto_linker
            notes=extract_notes(card_data)
        )

        cards.append(card.to_dict())

    return cards


def load_extracted_project_data(project_path: Path) -> dict:
    """Load extracted_project_data.json if available"""
    data_file = project_path / 'extracted_project_data.json'
    if data_file.exists():
        try:
            with open(data_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass

    # Try Extracted-Data subdirectory
    extracted_dir = project_path / 'Extracted-Data'
    for filename in ['extracted_project_data.json', 'parsed_schedules.json', 'rag_analysis.json']:
        data_file = extracted_dir / filename
        if data_file.exists():
            try:
                with open(data_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass

    return {}


# =============================================================================
# API ENDPOINTS
# =============================================================================

@scope_cards_bp.route('/api/project/<project_id>/scope-cards')
def get_scope_cards(project_id: str):
    """
    Get structured scope cards for a project.

    Returns 7 Division 8 scope cards with standardized fields:
    - Glass & Glazing
    - Storefront & Curtain Wall
    - Commercial Windows
    - Metal Doors & Frames
    - Wood Doors
    - Door Hardware
    - Specialties
    """
    # Find project
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'error': 'Project not found'}), 404

    # Get project folder path
    project_path, _ = get_project_folder_path(project_id)

    # Load additional extracted data
    if project_path and project_path.exists():
        extracted = load_extracted_project_data(project_path)
        project['extracted_data'] = extracted

    # Get status data
    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}

    # Build scope cards
    cards = build_scope_cards(project, status)

    # Add metadata
    response = {
        'project_id': project_id,
        'cards': cards,
        'metadata': {
            'analyzed_at': status.get('last_analysis') or project.get('last_updated'),
            'confidence': determine_overall_confidence(cards),
            'source': determine_data_source(project, status)
        }
    }

    return jsonify(response)


@scope_cards_bp.route('/api/project/<project_id>/scope-cards/<card_id>')
def get_scope_card(project_id: str, card_id: str):
    """Get a single scope card by ID"""
    # Get all cards
    response = get_scope_cards(project_id)
    if response.status_code != 200:
        return response

    data = response.get_json()
    for card in data.get('cards', []):
        if card['id'] == card_id:
            return jsonify(card)

    return jsonify({'error': f'Card {card_id} not found'}), 404


@scope_cards_bp.route('/api/project/<project_id>/scope-cards/<card_id>/move', methods=['POST'])
def move_scope_item(project_id: str, card_id: str):
    """
    Move an item from one scope card to another.

    Used when AI misclassifies an item (e.g., storefront marked as window).
    """
    data = request.json or {}
    target_card_id = data.get('target_card')
    item_id = data.get('item_id')

    if not target_card_id:
        return jsonify({'error': 'target_card required'}), 400

    # Validate target card exists
    valid_card_ids = [c['id'] for c in CARD_DEFINITIONS]
    if target_card_id not in valid_card_ids:
        return jsonify({'error': f'Invalid target_card: {target_card_id}'}), 400

    # Get status tracker to save override
    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}

    # Store card overrides
    overrides = status.get('scope_card_overrides', {})
    if card_id not in overrides:
        overrides[card_id] = {'moved_to': {}}
    overrides[card_id]['moved_to'][item_id or 'all'] = target_card_id

    # Save updated status
    status_tracker.update_status(project_id, {'scope_card_overrides': overrides})

    return jsonify({
        'status': 'ok',
        'message': f'Item moved from {card_id} to {target_card_id}'
    })


@scope_cards_bp.route('/api/scope-cards/definitions')
def get_card_definitions():
    """Get scope card definitions (titles, icons, CSI mappings)"""
    return jsonify({
        'cards': CARD_DEFINITIONS,
        'statuses': ['specified', 'not_specified', 'by_others', 'pending']
    })


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def determine_overall_confidence(cards: List[dict]) -> str:
    """Determine overall confidence level based on card data"""
    specified_count = sum(1 for c in cards if c['status'] == 'specified')
    total = len(cards)

    if specified_count >= 5:
        return 'high'
    elif specified_count >= 3:
        return 'medium'
    else:
        return 'low'


def determine_data_source(project: dict, status: dict) -> str:
    """Determine primary data source for cards"""
    if project.get('rag_analysis'):
        return 'rag_analysis'
    elif project.get('extracted_data'):
        return 'extracted_data'
    elif project.get('division_8_scope'):
        return 'spec_scan'
    else:
        return 'manual'
