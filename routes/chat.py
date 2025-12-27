"""
Chat API Blueprint

Provides AI Superintendent chat interface that bridges natural language
commands to MCP tools and project actions.

Features:
- Natural language command parsing
- Intent detection and routing
- MCP tool execution proxy
- Response streaming via SSE
"""

import os
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from flask import Blueprint, jsonify, request

from utils import (
    find_project_by_id,
    get_status_tracker,
    get_project_folder_path,
    debounced_refresh
)

from routes.sse import publish_chat_response, publish_activity

chat_bp = Blueprint('chat', __name__)


# =============================================================================
# INTENT PATTERNS
# =============================================================================

# Regex patterns for detecting user intent
INTENT_PATTERNS = [
    # Bid date changes
    (r'(?:change|set|update)\s+(?:the\s+)?bid\s+date\s+(?:to\s+)?(.+)',
     'update_bid_date', lambda m: {'date_str': m.group(1)}),

    (r'bid\s+date\s+(?:is\s+)?(?:now\s+)?(.+)',
     'update_bid_date', lambda m: {'date_str': m.group(1)}),

    # Status changes
    (r'(?:mark|set)\s+(?:as\s+)?(bid|no_bid|no-bid|no bid|lost|awarded|gc[_\s]?awarded)',
     'update_status', lambda m: {'decision': normalize_decision(m.group(1))}),

    (r'we(?:\'re|\s+are)\s+(bidding|not bidding|passing)',
     'update_status', lambda m: {'decision': decision_from_verb(m.group(1))}),

    # Pipeline/Analysis
    (r'(?:run|start|execute)\s+(?:the\s+)?(?:full\s+)?(?:pipeline|analysis|extraction)',
     'run_pipeline', lambda m: {}),

    (r'(?:analyze|scan|process)\s+(?:the\s+)?(?:project|documents?|specs?|drawings?)',
     'run_pipeline', lambda m: {}),

    # Notes
    (r'(?:add|save)\s+(?:a\s+)?note[:\s]+(.+)',
     'add_note', lambda m: {'text': m.group(1)}),

    # Estimate
    (r'(?:set|update)\s+(?:the\s+)?estimate\s+(?:to\s+)?\$?([\d,\.]+)',
     'update_estimate', lambda m: {'amount': parse_amount(m.group(1))}),

    # Archive
    (r'archive\s+(?:this\s+)?(?:project)?(?:\s+because\s+)?(.+)?',
     'archive_project', lambda m: {'reason': m.group(1) if m.group(1) else None}),

    # Questions about scope
    (r'(?:what|which)\s+(?:windows?|doors?|hardware|storefront|glazing)\s+(?:are|is)\s+specified',
     'query_scope', lambda m: {'scope_type': extract_scope_type(m.group(0))}),

    # Open folder
    (r'(?:open|show)\s+(?:the\s+)?(?:project\s+)?folder',
     'open_folder', lambda m: {}),

    # Help
    (r'(?:help|what can you do|commands)',
     'show_help', lambda m: {}),

    # Count updates
    (r'(?:there are|we have|count is|set count to)\s+(\d+)\s+(windows?|doors?|storefronts?|frames?)',
     'update_count', lambda m: {'count': int(m.group(1)), 'scope_type': normalize_scope_type(m.group(2))}),

    (r'(\d+)\s+(windows?|doors?|storefronts?|frames?)\s+(?:total|in total|on this project)',
     'update_count', lambda m: {'count': int(m.group(1)), 'scope_type': normalize_scope_type(m.group(2))}),

    # Quote updates
    (r'(?:got|received|have)\s+(?:a\s+)?quote\s+from\s+(.+?)\s+for\s+\$?([\d,]+)',
     'add_quote', lambda m: {'vendor': m.group(1).strip(), 'amount': parse_amount(m.group(2))}),

    (r'(.+?)\s+(?:quoted|bid)\s+\$?([\d,]+)',
     'add_quote', lambda m: {'vendor': m.group(1).strip(), 'amount': parse_amount(m.group(2))}),

    # Addendum notification
    (r'(?:new\s+)?addendum\s*#?(\d+)?\s*(?:received|added|says?\s+)?(.+)?',
     'process_addendum', lambda m: {'number': int(m.group(1)) if m.group(1) else None, 'content': m.group(2)}),

    # Timeline extensions (NEW)
    (r'(?:extend|push|move)\s+(?:the\s+)?(?:bid\s+)?(?:date|timeline)\s+(?:by\s+)?(\d+)\s+(day|days|week|weeks)',
     'extend_timeline', lambda m: {'amount': int(m.group(1)), 'unit': m.group(2)}),

    (r'(?:push|move|extend)\s+(?:bid\s+)?date\s+to\s+(.+)',
     'update_bid_date', lambda m: {'date_str': m.group(1)}),

    # Pricing notes (NEW)
    (r'(?:add|save)\s+pricing\s+note[:\s]+(.+)',
     'add_pricing_note', lambda m: {'text': m.group(1)}),

    (r'pricing[:\s]+(.+)',
     'add_pricing_note', lambda m: {'text': m.group(1)}),

    # Scope status updates (NEW)
    (r'(?:mark|set)\s+(windows?|doors?|hardware|storefront|glazing)\s+as\s+(specified|not[_\s]specified|by[_\s]others)',
     'update_scope_status', lambda m: {'scope_type': m.group(1).lower(), 'status': m.group(2).replace(' ', '_').replace('-', '_')}),

    # Tag management (NEW)
    (r'(?:add|tag)\s+(?:tag[:\s]+)?(.+)',
     'add_tag', lambda m: {'tag': m.group(1)}),

    (r'(?:remove|delete)\s+tag[:\s]+(.+)',
     'remove_tag', lambda m: {'tag': m.group(1)}),

    # Cross-referencing / Linking (NEW)
    (r'(?:link|connect|match)\s+(?:this\s+)?(?:to\s+)?(?:planhub|govwin|projectdog|local)?\s*(?:project\s+)?(.+)',
     'link_project', lambda m: {'target': m.group(1)}),

    (r'this\s+is\s+(?:the\s+)?same\s+as\s+(.+)',
     'link_project', lambda m: {'target': m.group(1)}),
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def normalize_decision(raw: str) -> str:
    """Normalize bid decision string"""
    raw = raw.lower().replace('-', '_').replace(' ', '_')
    mapping = {
        'bid': 'bid',
        'no_bid': 'no_bid',
        'nobid': 'no_bid',
        'no_bid': 'no_bid',
        'lost': 'lost',
        'awarded': 'awarded',
        'gc_awarded': 'gc_awarded',
        'gcawarded': 'gc_awarded',
    }
    return mapping.get(raw, 'bid')


def decision_from_verb(verb: str) -> str:
    """Convert verb to decision"""
    verb = verb.lower()
    if 'not' in verb or 'passing' in verb:
        return 'no_bid'
    return 'bid'


def parse_amount(amount_str: str) -> float:
    """Parse dollar amount string"""
    cleaned = amount_str.replace(',', '').replace('$', '')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def extract_scope_type(text: str) -> str:
    """Extract scope type from question"""
    text = text.lower()
    if 'window' in text:
        return 'windows'
    elif 'door' in text:
        return 'doors'
    elif 'hardware' in text:
        return 'hardware'
    elif 'storefront' in text:
        return 'storefront'
    elif 'glazing' in text or 'glass' in text:
        return 'glazing'
    return 'general'


def normalize_scope_type(raw: str) -> str:
    """Normalize scope type string"""
    raw = raw.lower().rstrip('s')  # Remove plural
    mapping = {
        'window': 'windows',
        'door': 'doors',
        'storefront': 'storefront',
        'frame': 'frames',
    }
    return mapping.get(raw, raw + 's')


def parse_date(date_str: str) -> Optional[str]:
    """Parse natural language date to ISO format"""
    date_str = date_str.lower().strip()

    # Handle relative dates
    today = datetime.now()

    if 'today' in date_str:
        return today.strftime('%Y-%m-%d')
    elif 'tomorrow' in date_str:
        return (today + timedelta(days=1)).strftime('%Y-%m-%d')
    elif 'next week' in date_str:
        return (today + timedelta(days=7)).strftime('%Y-%m-%d')
    elif 'next month' in date_str:
        return (today + timedelta(days=30)).strftime('%Y-%m-%d')

    # Handle weekday names
    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for i, day in enumerate(weekdays):
        if day in date_str:
            days_ahead = i - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            if 'next' in date_str:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

    # Try common date formats
    formats = [
        '%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y', '%m-%d-%y',
        '%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y',
        '%B %d', '%b %d', '%m/%d', '%m-%d',
        '%Y-%m-%d'
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            # If no year specified, assume current or next year
            if parsed.year == 1900:
                parsed = parsed.replace(year=today.year)
                if parsed < today:
                    parsed = parsed.replace(year=today.year + 1)
            return parsed.strftime('%Y-%m-%d')
        except ValueError:
            continue

    return None


def detect_intent(message: str) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Detect intent from natural language message.

    Returns:
        Tuple of (intent_name, params) or (None, None) if no match
    """
    message = message.strip()

    for pattern, intent, extractor in INTENT_PATTERNS:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            params = extractor(match) if extractor else {}
            return intent, params

    return None, None


# =============================================================================
# ACTION HANDLERS
# =============================================================================

def handle_update_bid_date(project_id: str, params: Dict) -> Dict:
    """Update project bid date"""
    date_str = params.get('date_str', '')
    parsed_date = parse_date(date_str)

    if not parsed_date:
        return {
            'type': 'error',
            'content': f"Couldn't parse date: '{date_str}'. Try formats like '12/25/2025' or 'next Friday'."
        }

    status_tracker = get_status_tracker()
    status_tracker.update_status(project_id, {'bid_date_override': parsed_date})
    debounced_refresh.trigger()

    return {
        'type': 'text',
        'content': f"Bid date updated to {parsed_date}",
        'tool_call': {
            'tool': 'project.update',
            'params': {'bid_date': parsed_date},
            'status': 'complete'
        }
    }


def handle_update_status(project_id: str, params: Dict) -> Dict:
    """Update bid decision status"""
    decision = params.get('decision', 'bid')

    status_tracker = get_status_tracker()
    status_tracker.update_status(project_id, {'bid_decision': decision})
    debounced_refresh.trigger()

    labels = {
        'bid': 'Bidding',
        'no_bid': 'No Bid',
        'lost': 'Lost',
        'awarded': 'Awarded',
        'gc_awarded': 'GC Awarded'
    }

    return {
        'type': 'text',
        'content': f"Project marked as: {labels.get(decision, decision)}",
        'tool_call': {
            'tool': 'project.transition',
            'params': {'decision': decision},
            'status': 'complete'
        }
    }


def handle_run_pipeline(project_id: str, params: Dict) -> Dict:
    """Trigger pipeline analysis"""
    # Publish activity to start pipeline
    publish_activity(
        project_id,
        'pipeline',
        'Starting analysis pipeline...',
        'Triggered by AI Superintendent',
        'folder'
    )

    # Note: Actual pipeline execution should be triggered via the pipeline endpoint
    return {
        'type': 'tool_call',
        'content': 'Starting analysis pipeline...',
        'tool_call': {
            'tool': 'pipeline.run',
            'params': {},
            'status': 'executing'
        },
        'action': 'trigger_pipeline'  # Frontend can use this to trigger actual call
    }


def handle_add_note(project_id: str, params: Dict) -> Dict:
    """Add a note to the project"""
    text = params.get('text', '')

    if not text:
        return {
            'type': 'error',
            'content': 'No note text provided'
        }

    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}
    notes = status.get('notes', [])
    notes.append({
        'text': text,
        'timestamp': datetime.now().isoformat(),
        'source': 'ai_superintendent'
    })
    status_tracker.update_status(project_id, {'notes': notes})

    return {
        'type': 'text',
        'content': f'Note saved: "{text[:50]}..."' if len(text) > 50 else f'Note saved: "{text}"',
        'tool_call': {
            'tool': 'note.add',
            'params': {'text': text},
            'status': 'complete'
        }
    }


def handle_update_estimate(project_id: str, params: Dict) -> Dict:
    """Update estimate amount"""
    amount = params.get('amount', 0)

    status_tracker = get_status_tracker()
    status_tracker.update_status(project_id, {
        'estimate': {
            'total': amount,
            'updated': datetime.now().isoformat()
        }
    })

    return {
        'type': 'text',
        'content': f'Estimate updated to ${amount:,.2f}',
        'tool_call': {
            'tool': 'project.update',
            'params': {'estimate_total': amount},
            'status': 'complete'
        }
    }


def handle_archive_project(project_id: str, params: Dict) -> Dict:
    """Archive the project"""
    reason = params.get('reason')

    status_tracker = get_status_tracker()
    status_tracker.update_status(project_id, {
        'archived': True,
        'archived_reason': reason,
        'archived_date': datetime.now().isoformat()
    })
    debounced_refresh.trigger()

    return {
        'type': 'text',
        'content': f'Project archived' + (f': {reason}' if reason else ''),
        'tool_call': {
            'tool': 'project.archive',
            'params': {'reason': reason},
            'status': 'complete'
        }
    }


def handle_query_scope(project_id: str, params: Dict) -> Dict:
    """Query scope information"""
    scope_type = params.get('scope_type', 'general')

    # Try to get scope data from project
    project = find_project_by_id(project_id)
    if not project:
        return {
            'type': 'error',
            'content': 'Project not found'
        }

    # Look for scope data
    rag_analysis = project.get('rag_analysis', {})
    division_8 = project.get('division_8_scope', {})

    scope_data = rag_analysis.get(scope_type) or division_8.get(scope_type)

    if scope_data:
        # Format response
        if isinstance(scope_data, dict):
            if scope_data.get('specified'):
                details = []
                if scope_data.get('manufacturers'):
                    details.append(f"Manufacturers: {', '.join(scope_data['manufacturers'])}")
                if scope_data.get('types'):
                    details.append(f"Types: {', '.join(scope_data['types'])}")
                if scope_data.get('count_estimate'):
                    details.append(f"Quantity: {scope_data['count_estimate']}")
                return {
                    'type': 'text',
                    'content': f"{scope_type.title()} is specified. " + '. '.join(details)
                }
            else:
                return {
                    'type': 'text',
                    'content': f"{scope_type.title()} is not specified in this project."
                }

    return {
        'type': 'text',
        'content': f"No {scope_type} information found. Try running the analysis pipeline."
    }


def handle_open_folder(project_id: str, params: Dict) -> Dict:
    """Open project folder in Finder"""
    project_path, _ = get_project_folder_path(project_id)

    if project_path and project_path.exists():
        return {
            'type': 'text',
            'content': f'Opening folder: {project_path}',
            'tool_call': {
                'tool': 'system.open_folder',
                'params': {'path': str(project_path)},
                'status': 'complete'
            },
            'action': 'open_folder',
            'path': str(project_path)
        }

    return {
        'type': 'error',
        'content': 'Project folder not found'
    }


def handle_show_help(project_id: str, params: Dict) -> Dict:
    """Show available commands"""
    help_text = """I can help you with:

**Bid Date:**
- "Change bid date to 12/25/2025"
- "Bid date is next Friday"
- "Extend bid date by 2 weeks" ✨NEW
- "Push timeline by 5 days" ✨NEW

**Status:**
- "Mark as bidding" / "Mark as no bid"
- "We're passing on this one"
- "Mark as awarded"

**Analysis:**
- "Run the analysis pipeline"
- "Analyze the project"

**Notes:**
- "Add note: Called architect today"
- "Add pricing note: Waiting on hardware quote" ✨NEW

**Estimate:**
- "Set estimate to $45,000"

**Actions:**
- "Archive this project"
- "Open folder"

**Counts:**
- "There are 32 windows"
- "Set count to 15 doors"

**Quotes:**
- "Got a quote from Allied for $45,000"
- "ABC Glass quoted $32,000"

**Addenda:**
- "Addendum #1 received"

**Scope Status:** ✨NEW
- "Mark windows as specified"
- "Set doors as by others"
- "Mark hardware as not specified"

**Tags:** ✨NEW
- "Add tag: storefront replacement"
- "Remove tag: retail"

**Linking:** ✨NEW
- "Link to Main Street Renovation"
- "This is the same as PlanHub project 12345"

**Questions:**
- "What windows are specified?"
"""

    return {
        'type': 'text',
        'content': help_text
    }


def handle_update_count(project_id: str, params: Dict) -> Dict:
    """Update scope count for a type"""
    count = params.get('count', 0)
    scope_type = params.get('scope_type', 'unknown')

    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}

    # Get current count for comparison
    old_count = None
    spreadsheet_data = status.get('spreadsheet_data', {})
    if scope_type in spreadsheet_data:
        old_count = spreadsheet_data[scope_type].get('count')

    # Update spreadsheet_data with new count
    if 'spreadsheet_data' not in status:
        status['spreadsheet_data'] = {}
    status['spreadsheet_data'][scope_type] = {
        'count': count,
        'updated': datetime.now().isoformat(),
        'source': 'chat'
    }
    status_tracker.set_status(project_id, status)

    # Log timeline event
    status_tracker.log_scope_change(
        project_id,
        scope_type,
        'count',
        old_count,
        count,
        source='chat'
    )

    debounced_refresh.trigger()

    return {
        'type': 'text',
        'content': f'{scope_type.title()} count updated to {count}',
        'tool_call': {
            'tool': 'scope.update_count',
            'params': {'scope_type': scope_type, 'count': count},
            'status': 'complete'
        }
    }


def handle_add_quote(project_id: str, params: Dict) -> Dict:
    """Add a vendor quote"""
    vendor = params.get('vendor', 'Unknown')
    amount = params.get('amount', 0)

    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}

    # Add to quotes list
    quotes = status.get('quotes', [])
    quotes.append({
        'vendor': vendor,
        'amount': amount,
        'date': datetime.now().isoformat(),
        'source': 'chat'
    })
    status['quotes'] = quotes
    status_tracker.set_status(project_id, status)

    # Log timeline event
    status_tracker.log_quote_received(project_id, vendor, amount)

    debounced_refresh.trigger()

    return {
        'type': 'text',
        'content': f'Quote from {vendor} for ${amount:,.2f} recorded',
        'tool_call': {
            'tool': 'quote.add',
            'params': {'vendor': vendor, 'amount': amount},
            'status': 'complete'
        }
    }


def handle_process_addendum(project_id: str, params: Dict) -> Dict:
    """Process addendum notification"""
    number = params.get('number')
    content = params.get('content')

    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}

    # Increment addenda count
    docs = status.get('documents', {})
    current_count = docs.get('addenda_count', 0)
    new_count = number if number else current_count + 1
    docs['addenda_count'] = max(new_count, current_count)
    status['documents'] = docs
    status_tracker.set_status(project_id, status)

    # Log timeline event
    status_tracker.log_addendum_processed(
        project_id,
        new_count,
        content or f"Addendum #{new_count} received"
    )

    debounced_refresh.trigger()

    return {
        'type': 'text',
        'content': f'Addendum #{new_count} recorded' + (f': {content}' if content else ''),
        'tool_call': {
            'tool': 'addendum.add',
            'params': {'number': new_count},
            'status': 'complete'
        }
    }


def handle_extend_timeline(project_id: str, params: Dict) -> Dict:
    """Extend bid date by specified amount"""
    amount = params.get('amount', 0)
    unit = params.get('unit', 'days').lower()

    # Get current bid date
    project = find_project_by_id(project_id)
    if not project:
        return {
            'type': 'error',
            'content': 'Project not found'
        }

    current_date = project.get('bid_date')
    if not current_date:
        return {
            'type': 'error',
            'content': 'No bid date set for this project'
        }

    # Parse current date
    try:
        current_dt = datetime.fromisoformat(current_date) if isinstance(current_date, str) else current_date
    except (ValueError, TypeError):
        return {
            'type': 'error',
            'content': f'Invalid current bid date: {current_date}'
        }

    # Calculate new date
    if 'week' in unit:
        days_to_add = amount * 7
    else:
        days_to_add = amount

    new_date = current_dt + timedelta(days=days_to_add)
    new_date_str = new_date.strftime('%Y-%m-%d')

    # Update bid date
    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}
    status['bid_date_override'] = new_date_str
    status['timeline_adjustments'] = {
        'extension_reason': f'Extended by {amount} {unit}',
        'extended_by_days': days_to_add,
        'previous_date': current_date,
        'new_date': new_date_str,
        'updated': datetime.now().isoformat()
    }
    status_tracker.set_status(project_id, status)
    debounced_refresh.trigger()

    return {
        'type': 'text',
        'content': f'✓ Bid date extended by {amount} {unit}: {current_date} → {new_date_str}',
        'tool_call': {
            'tool': 'project.extend_timeline',
            'params': {'amount': amount, 'unit': unit, 'new_date': new_date_str},
            'status': 'complete'
        }
    }


def handle_add_pricing_note(project_id: str, params: Dict) -> Dict:
    """Add a pricing-specific note"""
    text = params.get('text', '')

    if not text:
        return {
            'type': 'error',
            'content': 'No note text provided'
        }

    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}

    pricing_notes = status.get('pricing_notes', [])
    pricing_notes.append({
        'timestamp': datetime.now().isoformat(),
        'note': text,
        'source': 'ai_superintendent'
    })
    status['pricing_notes'] = pricing_notes
    status_tracker.set_status(project_id, status)

    return {
        'type': 'text',
        'content': f'💵 Pricing note saved: "{text[:50]}..."' if len(text) > 50 else f'💵 Pricing note saved: "{text}"',
        'tool_call': {
            'tool': 'pricing.add_note',
            'params': {'text': text},
            'status': 'complete'
        }
    }


def handle_update_scope_status(project_id: str, params: Dict) -> Dict:
    """Update scope status (specified/not_specified/by_others)"""
    scope_type = params.get('scope_type', '').lower().rstrip('s')  # Remove plural
    status_value = params.get('status', 'specified')

    # Normalize scope type
    scope_map = {
        'window': 'windows',
        'door': 'doors',
        'hardware': 'hardware',
        'storefront': 'storefront',
        'glazing': 'glazing'
    }
    scope_type = scope_map.get(scope_type, scope_type + 's')

    # Update status
    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}

    scope_status = status.get('scope_status', {})
    scope_status[scope_type] = status_value
    status['scope_status'] = scope_status
    status_tracker.set_status(project_id, status)
    debounced_refresh.trigger()

    status_labels = {
        'specified': '✓ Specified',
        'not_specified': '✗ Not Specified',
        'by_others': '⊗ By Others'
    }

    return {
        'type': 'text',
        'content': f'{scope_type.title()} marked as: {status_labels.get(status_value, status_value)}',
        'tool_call': {
            'tool': 'scope.update_status',
            'params': {'scope_type': scope_type, 'status': status_value},
            'status': 'complete'
        }
    }


def handle_add_tag(project_id: str, params: Dict) -> Dict:
    """Add a tag to the project"""
    tag = params.get('tag', '').strip()

    if not tag:
        return {
            'type': 'error',
            'content': 'No tag provided'
        }

    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}

    tags = status.get('tags', [])
    if tag not in tags:
        tags.append(tag)
        status['tags'] = tags
        status_tracker.set_status(project_id, status)
        debounced_refresh.trigger()

        return {
            'type': 'text',
            'content': f'🏷️ Tag added: "{tag}"',
            'tool_call': {
                'tool': 'tag.add',
                'params': {'tag': tag},
                'status': 'complete'
            }
        }
    else:
        return {
            'type': 'text',
            'content': f'Tag "{tag}" already exists'
        }


def handle_remove_tag(project_id: str, params: Dict) -> Dict:
    """Remove a tag from the project"""
    tag = params.get('tag', '').strip()

    status_tracker = get_status_tracker()
    status = status_tracker.get_status(project_id) or {}

    tags = status.get('tags', [])
    if tag in tags:
        tags.remove(tag)
        status['tags'] = tags
        status_tracker.set_status(project_id, status)
        debounced_refresh.trigger()

        return {
            'type': 'text',
            'content': f'Tag removed: "{tag}"',
            'tool_call': {
                'tool': 'tag.remove',
                'params': {'tag': tag},
                'status': 'complete'
            }
        }
    else:
        return {
            'type': 'text',
            'content': f'Tag "{tag}" not found'
        }


def handle_link_project(project_id: str, params: Dict) -> Dict:
    """Link this project to another project"""
    target = params.get('target', '').strip()

    if not target:
        return {
            'type': 'error',
            'content': 'No target project specified'
        }

    # This would need to be implemented with actual linking logic
    # For now, return a message indicating the feature
    return {
        'type': 'text',
        'content': f'🔗 Linking to "{target}" - Use the project linker dropdown for cross-referencing',
        'tool_call': {
            'tool': 'project.link',
            'params': {'target': target},
            'status': 'pending'
        },
        'suggestion': 'Use the "Linked Sources" dropdown in the sidebar to confirm the link'
    }


# Intent to handler mapping
INTENT_HANDLERS = {
    'update_bid_date': handle_update_bid_date,
    'update_status': handle_update_status,
    'run_pipeline': handle_run_pipeline,
    'add_note': handle_add_note,
    'update_estimate': handle_update_estimate,
    'archive_project': handle_archive_project,
    'query_scope': handle_query_scope,
    'open_folder': handle_open_folder,
    'show_help': handle_show_help,
    'update_count': handle_update_count,
    'add_quote': handle_add_quote,
    'process_addendum': handle_process_addendum,
    # NEW handlers
    'extend_timeline': handle_extend_timeline,
    'add_pricing_note': handle_add_pricing_note,
    'update_scope_status': handle_update_scope_status,
    'add_tag': handle_add_tag,
    'remove_tag': handle_remove_tag,
    'link_project': handle_link_project,
}


# =============================================================================
# API ENDPOINT
# =============================================================================

@chat_bp.route('/api/project/<project_id>/chat', methods=['POST'])
def chat(project_id: str):
    """
    Process chat message and execute appropriate action.

    Request body:
        {
            "message": "Change bid date to next Friday"
        }

    Response:
        {
            "type": "text" | "tool_call" | "error",
            "content": "Response message",
            "tool_call": { ... } (optional)
        }
    """
    # Validate project exists
    project = find_project_by_id(project_id)
    if not project:
        return jsonify({'type': 'error', 'content': 'Project not found'}), 404

    # Get message
    data = request.json or {}
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'type': 'error', 'content': 'No message provided'}), 400

    # Detect intent
    intent, params = detect_intent(message)

    if intent and intent in INTENT_HANDLERS:
        # Execute handler
        response = INTENT_HANDLERS[intent](project_id, params)

        # Publish to SSE for activity log
        publish_chat_response(
            project_id,
            response.get('type', 'text'),
            response.get('content', ''),
            response.get('tool_call'),
            'complete'
        )

        return jsonify(response)

    # No intent matched - provide helpful response
    return jsonify({
        'type': 'text',
        'content': f"I'm not sure how to help with that. Try saying 'help' to see what I can do."
    })
