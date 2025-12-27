"""
PlanHub Data Exporter

Exports scraped lead data to JSON format for integration with
project-tracker's matching and display systems.
"""
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from .db import Database, Lead
from .config import BASE_DIR


# Output path for planhub_projects.json (used by existing matcher)
OUTPUT_DIR = Path(__file__).parent.parent.parent / "planhub"
OUTPUT_FILE = OUTPUT_DIR / "planhub_projects.json"


def parse_location(location_str: str) -> Dict[str, str]:
    """
    Parse location string into city, state, address components.

    Example input: "123 Main St, Boston, MA 02101"
    """
    result = {
        'address': location_str or '',
        'city': '',
        'state': ''
    }

    if not location_str:
        return result

    # Try to extract state (2-letter code)
    state_match = re.search(r'\b([A-Z]{2})\s*\d{5}', location_str)
    if state_match:
        result['state'] = state_match.group(1)

    # Try to extract city (word before state)
    city_match = re.search(r'([A-Za-z\s]+),?\s*[A-Z]{2}\s*\d{5}', location_str)
    if city_match:
        city = city_match.group(1).strip().rstrip(',')
        # Take last word as city if it contains commas
        if ',' in city:
            city = city.split(',')[-1].strip()
        result['city'] = city

    return result


def parse_bid_date(date_str: str) -> str:
    """
    Parse bid date string to ISO format.

    Example input: "01/15/2025 2:00 PM"
    """
    if not date_str:
        return ''

    try:
        # Try parsing with time
        dt = datetime.strptime(date_str, "%m/%d/%Y %I:%M %p")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        try:
            # Try just date
            dt = datetime.strptime(date_str, "%m/%d/%Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return date_str


def lead_to_project(lead: Lead) -> Dict[str, Any]:
    """
    Convert a Lead database record to project format for matcher.
    """
    project_info = {}
    contractors = []
    market_intel = {}

    # Parse JSON fields
    if lead.project_info_json:
        try:
            project_info = json.loads(lead.project_info_json)
        except json.JSONDecodeError:
            pass

    if lead.contractors_json:
        try:
            contractors = json.loads(lead.contractors_json)
        except json.JSONDecodeError:
            pass

    if lead.market_intel_json:
        try:
            market_intel = json.loads(lead.market_intel_json)
        except json.JSONDecodeError:
            pass

    # Parse location
    location = parse_location(project_info.get('location', ''))

    # Build project dict
    project = {
        'project_id': lead.planhub_id,
        'project_name': project_info.get('project_name') or lead.name,
        'bid_due_date': parse_bid_date(lead.bid_due_date),
        'time_remaining': lead.time_remaining,
        'source': 'planhub',
        'url': lead.url,

        # Location
        'address': location['address'],
        'city': location['city'],
        'state': location['state'],

        # Project details
        'description': project_info.get('description', ''),
        'project_size': project_info.get('project_size', ''),
        'project_value': project_info.get('project_value', ''),
        'start_date': project_info.get('start_date', ''),
        'end_date': project_info.get('end_date', ''),
        'tags': project_info.get('tags', []),

        # General contractors
        'general_contractors': contractors,

        # Market intelligence
        'downloads_by_scope': market_intel.get('downloads_by_scope', []),

        # Metadata
        'scraped_at': datetime.now().isoformat(),
    }

    return project


def export_to_json(db: Database = None) -> Dict[str, Any]:
    """
    Export all completed leads to planhub_projects.json.

    Returns summary of export.
    """
    if db is None:
        db = Database()
        db.connect()
        close_db = True
    else:
        close_db = False

    try:
        leads = db.get_all_completed_leads()

        projects = {}
        for lead in leads:
            project = lead_to_project(lead)
            projects[lead.planhub_id] = project

        # Ensure output directory exists
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Write JSON
        output_data = {
            'projects': projects,
            'exported_at': datetime.now().isoformat(),
            'count': len(projects)
        }

        with open(OUTPUT_FILE, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"Exported {len(projects)} projects to {OUTPUT_FILE}")

        return {
            'file': str(OUTPUT_FILE),
            'count': len(projects),
            'exported_at': output_data['exported_at']
        }

    finally:
        if close_db:
            db.close()


def get_projects_for_matcher() -> List[Dict[str, Any]]:
    """
    Load exported projects for use by matcher.

    Returns list of project dicts, or empty list if file doesn't exist.
    """
    if not OUTPUT_FILE.exists():
        return []

    try:
        with open(OUTPUT_FILE) as f:
            data = json.load(f)
        return list(data.get('projects', {}).values())
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading planhub projects: {e}")
        return []


def export_from_standalone_db(db_path: str = None) -> Dict[str, Any]:
    """
    Export leads from the standalone PlanHub scraper database.

    This reads from the original scraper's DB (not the integrated one)
    and exports to planhub_projects.json for the project tracker.

    Args:
        db_path: Path to standalone scraper's planhub.db
                 Default: Uses PLANHUB_DB_PATH from environment

    Returns:
        Summary of export with count and file path
    """
    import sqlite3

    if db_path is None:
        db_path = os.getenv("PLANHUB_DB_PATH", "")
        if not db_path:
            raise ValueError("PLANHUB_DB_PATH environment variable not set")

    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Standalone DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all completed leads
    cursor.execute("""
        SELECT planhub_id, name, url, bid_due_date, time_remaining,
               project_info_json, contractors_json, market_intel_json
        FROM leads
        WHERE status = 'done' AND project_info_json IS NOT NULL
    """)

    projects = {}
    for row in cursor.fetchall():
        planhub_id = row['planhub_id']

        # Parse JSON fields
        project_info = {}
        contractors = []
        market_intel = {}

        if row['project_info_json']:
            try:
                project_info = json.loads(row['project_info_json'])
            except json.JSONDecodeError:
                pass

        if row['contractors_json']:
            try:
                contractors = json.loads(row['contractors_json'])
            except json.JSONDecodeError:
                pass

        if row['market_intel_json']:
            try:
                market_intel = json.loads(row['market_intel_json'])
            except json.JSONDecodeError:
                pass

        # Parse location from project_info
        location_str = project_info.get('location', '')
        location = parse_location(location_str)

        # Build project in expected format for planhub_reader.py
        project = {
            'project_name': project_info.get('name') or row['name'],
            'city': location['city'],
            'state': location['state'],
            'address': location['address'],
            'bid_due_date': project_info.get('bid_date', ''),
            'bid_due_time': '',
            'square_feet': project_info.get('project_size', '').replace(',', '').replace(' SF', ''),
            'project_type': ', '.join(project_info.get('tags', [])),
            'sector': 'Commercial',  # Default
            'building_type': '',
            'description': project_info.get('description', ''),
            'start_date': project_info.get('start_date', ''),
            'end_date': project_info.get('end_date', ''),
            'project_value': project_info.get('project_value', ''),
            'general_contractors': contractors,
            'documents': [],
            'urls': {
                'project_page': row['url']
            },
            'market_intelligence': {
                'matching_trades': market_intel.get('downloads_by_scope', [])
            }
        }

        projects[planhub_id] = project

    conn.close()

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write JSON
    output_data = {
        'projects': projects,
        'exported_at': datetime.now().isoformat(),
        'count': len(projects)
    }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"Exported {len(projects)} projects from standalone DB to {OUTPUT_FILE}")

    return {
        'file': str(OUTPUT_FILE),
        'count': len(projects),
        'exported_at': output_data['exported_at']
    }


if __name__ == '__main__':
    # Quick test - export from standalone DB
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--standalone':
        result = export_from_standalone_db()
    else:
        result = export_to_json()
    print(f"Export result: {result}")
