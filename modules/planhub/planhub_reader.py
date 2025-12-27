"""
PlanHub Integration Module

Reads PlanHub project leads from planhub_projects.json and normalizes them
to the standard project format used by the dashboard.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


def load_gc_logo_mapping() -> Dict[str, str]:
    """
    Load GC name to logo filename mapping.

    Returns:
        Dict mapping GC names to their logo filenames
    """
    mapping_path = Path(__file__).parent.parent.parent / "planhub" / "gc_logos" / "gc_logo_mapping.json"
    if mapping_path.exists():
        try:
            with open(mapping_path, 'r') as f:
                data = json.load(f)
                # The mapping structure has GC name as key with original_file and renamed_file
                result = {}
                for gc_name, files in data.items():
                    if isinstance(files, dict) and 'renamed_file' in files:
                        result[gc_name] = files['renamed_file']
                return result
        except Exception as e:
            print(f"Error loading GC logo mapping: {e}")
    return {}


def normalize_gc_name(name: str) -> str:
    """Normalize GC name for matching (lowercase, remove suffixes)."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [', inc.', ', inc', ' inc.', ' inc', ', llc', ' llc',
                   ', corp.', ', corp', ' corp.', ' corp', ' corporation',
                   ', co.', ', co', ' co.', ' company', ' contractors',
                   ' construction', ' builders', ' group', ' services']:
        name = name.replace(suffix, '')
    # Remove punctuation
    name = re.sub(r'[.,&]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def add_logo_urls_to_gcs(general_contractors: List[Dict], logo_mapping: Dict[str, str] = None) -> List[Dict]:
    """
    Add logo_url to each GC that has a matching logo.

    Args:
        general_contractors: List of GC dicts with 'name' field
        logo_mapping: Optional pre-loaded mapping, otherwise loads from file

    Returns:
        The same list with logo_url added where available
    """
    if logo_mapping is None:
        logo_mapping = load_gc_logo_mapping()

    # Create normalized lookup
    normalized_mapping = {}
    for gc_name, logo_file in logo_mapping.items():
        normalized_mapping[normalize_gc_name(gc_name)] = (gc_name, logo_file)

    for gc in general_contractors:
        gc_name = gc.get("name", "")
        if not gc_name:
            continue

        # Try exact match first
        if gc_name in logo_mapping:
            gc["logo_url"] = f"/planhub/gc-logo/{logo_mapping[gc_name]}"
            continue

        # Try normalized match
        normalized = normalize_gc_name(gc_name)
        if normalized in normalized_mapping:
            _, logo_file = normalized_mapping[normalized]
            gc["logo_url"] = f"/planhub/gc-logo/{logo_file}"

    return general_contractors


def parse_planhub_date(date_str: str) -> Optional[str]:
    """
    Parse PlanHub date format (MM/DD/YYYY) to ISO format (YYYY-MM-DD).

    Args:
        date_str: Date string like "01/08/2026"

    Returns:
        ISO format date string or None if parsing fails
    """
    if not date_str:
        return None
    try:
        # Handle MM/DD/YYYY format
        dt = datetime.strptime(date_str, "%m/%d/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return date_str  # Return as-is if parsing fails


def has_division_8_trades(project: Dict) -> bool:
    """
    Check if project has Division 8 related trades in matching_trades.

    Args:
        project: PlanHub project dict

    Returns:
        True if project has Division 8 related trades
    """
    div8_keywords = [
        'glazing', 'storefront', 'curtain wall', 'window', 'door',
        'glass', 'entrance', 'aluminum', 'hardware'
    ]

    matching_trades = project.get('market_intelligence', {}).get('matching_trades', [])
    for trade in matching_trades:
        trade_lower = trade.lower()
        if any(kw in trade_lower for kw in div8_keywords):
            return True
    return False


def load_planhub_projects() -> List[Dict]:
    """
    Load and normalize PlanHub projects to standard format.

    Returns:
        List of normalized project dicts compatible with dashboard
    """
    try:
        from modules.planhub.planhub_db_reader import PlanHubDatabaseReader

        reader = PlanHubDatabaseReader()
        # Return all leads with extracted data (status can be 'done' or 'queued' if data exists)
        projects = reader.get_all_leads(status_filter=['done', 'queued'])

        # Convert UnifiedProject instances to dicts
        projects_dicts = []
        for proj in projects:
            if hasattr(proj, 'to_dict'):
                project_dict = proj.to_dict()
            else:
                project_dict = proj
            projects_dicts.append(project_dict)

        # Load GC logo mapping for adding logo URLs
        logo_mapping = load_gc_logo_mapping()

        # Add logo URLs to GCs
        for project in projects_dicts:
            general_contractors = project.get('general_contractors', [])
            if general_contractors:
                add_logo_urls_to_gcs(general_contractors, logo_mapping)

        return projects_dicts

    except Exception as e:
        print(f"Error loading PlanHub projects from database: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_planhub_stats() -> Dict:
    """
    Get summary statistics for PlanHub projects.

    Returns:
        Dict with count and breakdown stats
    """
    projects = load_planhub_projects()

    div8_count = sum(1 for p in projects if p.get('is_division_8'))

    # Count by sector
    sectors = {}
    for p in projects:
        sector = p.get('sector', 'Unknown')
        sectors[sector] = sectors.get(sector, 0) + 1

    return {
        "total": len(projects),
        "division_8": div8_count,
        "sectors": sectors
    }
