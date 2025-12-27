"""
PlanHub CSV Importer

Imports PlanHub projects from CSV, matches to existing local projects,
merges data to fill gaps, and archives expired projects.
"""

import csv
import re
import html
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple
import logging

from modules.database.db import get_session
from modules.database.models import Project, PlanHubLink

logger = logging.getLogger(__name__)


def normalize_project_id(name: str) -> str:
    """Create a slug-style ID from project name"""
    # Remove special chars, lowercase, replace spaces with dashes
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return f"planhub-{slug[:80]}"  # Limit length


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats to datetime"""
    if not date_str or date_str == '-':
        return None

    formats = [
        '%m/%d/%Y',  # 12/29/2025
        '%Y-%m-%d',  # 2025-12-29
        '%m/%d/%y',  # 12/29/25
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None


def parse_value(value_str: str) -> Optional[str]:
    """Clean project value string"""
    if not value_str or value_str == '-':
        return None
    # Keep as string since it may have special formatting
    return value_str.strip()


def parse_sqft(sqft_str: str) -> Optional[int]:
    """Parse square footage to integer"""
    if not sqft_str or sqft_str == '-':
        return None
    try:
        # Remove commas and parse as float, then int
        clean = sqft_str.replace(',', '').replace('.00', '')
        return int(float(clean))
    except ValueError:
        return None


def parse_distance(dist_str: str) -> Optional[float]:
    """Parse distance in miles"""
    if not dist_str or dist_str == '-':
        return None
    try:
        return float(dist_str)
    except ValueError:
        return None


def name_similarity(name1: str, name2: str) -> float:
    """Calculate name similarity ratio"""
    if not name1 or not name2:
        return 0.0
    return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()


def within_days(date1: Optional[datetime], date2: Optional[datetime], days: int = 7) -> bool:
    """Check if two dates are within N days of each other"""
    if not date1 or not date2:
        return False
    diff = abs((date1 - date2).days)
    return diff <= days


def extract_location_from_title(title: str) -> Tuple[str, str]:
    """Extract city and state from project title"""
    if not title:
        return ('', '')

    title_lower = title.lower()

    # Common state patterns
    state_patterns = {
        'massachusetts': 'ma', 'ma': 'ma',
        'rhode island': 'ri', 'ri': 'ri',
        'connecticut': 'ct', 'ct': 'ct',
        'new hampshire': 'nh', 'nh': 'nh',
        'maine': 'me', 'me': 'me',
        'vermont': 'vt', 'vt': 'vt',
        'new york': 'ny', 'ny': 'ny',
    }

    # Find state
    found_state = ''
    for pattern, abbrev in state_patterns.items():
        if pattern in title_lower:
            found_state = abbrev
            break

    # Try to find city from common patterns like "City, MA" or "- City MA"
    city = ''
    import re
    # Match patterns like "- Holyoke MA" or ", Falmouth, Massachusetts"
    city_match = re.search(r'[-,]\s*([A-Za-z\s]+?)(?:\s*,?\s*(?:MA|RI|CT|NH|ME|VT|NY|Massachusetts|Rhode Island|Connecticut))', title, re.I)
    if city_match:
        city = city_match.group(1).strip().lower()

    return (city, found_state)


def find_best_match(row: Dict, projects: List[Project]) -> Tuple[Optional[Project], float]:
    """
    Find best matching project for a PlanHub row.

    Project names are the key identifier - if names match well, it's the same project.
    Threshold: 0.55 similarity ratio (handles minor variations like "- Falmouth" vs "Falmouth -")

    Returns (project, score) if score >= threshold, else (None, 0)
    """
    best_score = 0.0
    best_match = None

    planhub_name = row.get('project_name', '').strip()
    if not planhub_name:
        return (None, 0.0)

    for project in projects:
        title = project.title or ''
        folder_name = (project.folder_path or '').split('/')[-1] if project.folder_path else ''

        # Calculate name similarity against both title and folder name
        title_ratio = name_similarity(planhub_name, title)
        folder_ratio = name_similarity(planhub_name, folder_name)

        # Use the best match
        score = max(title_ratio, folder_ratio)

        if score > best_score:
            best_score = score
            best_match = project

    # 0.55 threshold catches most variations while avoiding false positives
    threshold = 0.55
    if best_score >= threshold:
        return (best_match, best_score)
    return (None, 0.0)


def merge_planhub_data(project: Project, row: Dict) -> bool:
    """
    Merge PlanHub data into existing project, filling gaps only.
    Returns True if any data was updated.
    """
    updated = False

    # Fill in missing basic fields
    if not project.city and row.get('city'):
        project.city = row['city'].strip()
        updated = True

    if not project.state and row.get('state'):
        project.state = row['state'].strip()
        updated = True

    if not project.estimated_value and row.get('project_value'):
        project.estimated_value = parse_value(row['project_value'])
        updated = True

    if not project.bid_date and row.get('due_date'):
        project.bid_date = parse_date(row['due_date'])
        updated = True

    # PlanHub-specific fields (always update these for matched projects)
    sqft = parse_sqft(row.get('square_footage', ''))
    if sqft and not project.square_footage:
        project.square_footage = sqft
        updated = True

    if row.get('construction_type') and not project.construction_type:
        project.construction_type = row['construction_type'].strip()
        updated = True

    if row.get('project_type') and not project.project_type:
        project.project_type = row['project_type'].strip()
        updated = True

    if row.get('building_use') and not project.building_use:
        project.building_use = row['building_use'].strip()
        updated = True

    if row.get('description') and not project.description:
        project.description = row['description'].strip()
        updated = True

    if row.get('trades') and not project.trades:
        project.trades = row['trades'].strip()
        updated = True

    dist = parse_distance(row.get('distance_miles', ''))
    if dist and not project.distance_miles:
        project.distance_miles = dist
        updated = True

    # Metadata flags
    if row.get('viewed', '').lower() == 'yes':
        project.planhub_viewed = True
    if row.get('locked', '').lower() == 'yes':
        project.planhub_locked = True

    return updated


def create_planhub_project(row: Dict) -> Project:
    """Create a new Project from PlanHub CSV row"""
    project_id = normalize_project_id(row.get('project_name', 'unknown'))

    # Check if bid date is past
    bid_date = parse_date(row.get('due_date', ''))
    is_archived = False
    archived_reason = None
    archived_date = None

    if bid_date and bid_date < datetime.now():
        is_archived = True
        archived_reason = 'past_bid_date'
        archived_date = datetime.now()

    project = Project(
        id=project_id,
        title=html.unescape(row.get('project_name', '').strip()),
        source='planhub',
        folder_path=None,  # No local folder

        # Location
        city=row.get('city', '').strip() or None,
        state=row.get('state', '').strip() or None,
        address=row.get('location', '').strip() or None,

        # Dates
        bid_date=bid_date,

        # Project details
        estimated_value=parse_value(row.get('project_value', '')),
        square_footage=parse_sqft(row.get('square_footage', '')),
        construction_type=row.get('construction_type', '').strip() or None,
        project_type=row.get('project_type', '').strip() or None,
        building_use=row.get('building_use', '').strip() or None,
        description=row.get('description', '').strip() or None,
        trades=row.get('trades', '').strip() or None,
        distance_miles=parse_distance(row.get('distance_miles', '')),

        # Flags
        planhub_viewed=row.get('viewed', '').lower() == 'yes',
        planhub_locked=row.get('locked', '').lower() == 'yes',

        # Archive status
        archived=is_archived,
        archived_date=archived_date,
        archived_reason=archived_reason,
    )

    return project


def import_planhub_csv(csv_path: Path, dry_run: bool = False) -> Dict:
    """
    Import PlanHub CSV into database.

    Args:
        csv_path: Path to planhub_projects.csv
        dry_run: If True, don't actually save to database

    Returns:
        Statistics dictionary
    """
    stats = {
        'total_rows': 0,
        'matched': 0,
        'created': 0,
        'archived': 0,
        'updated': 0,
        'skipped': 0,
        'errors': [],
        'matches': [],  # List of (planhub_name, local_id, score)
    }

    if not csv_path.exists():
        stats['errors'].append(f"CSV file not found: {csv_path}")
        return stats

    # Read CSV
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    stats['total_rows'] = len(rows)
    logger.info(f"Loaded {len(rows)} rows from CSV")

    with get_session() as session:
        # Load all existing projects
        existing_projects = session.query(Project).filter(
            Project.source != 'planhub'  # Don't match against other PlanHub imports
        ).all()
        logger.info(f"Found {len(existing_projects)} existing projects to match against")

        # Track IDs to avoid duplicates
        seen_ids = set()
        for p in session.query(Project.id).all():
            seen_ids.add(p[0])

        for row in rows:
            try:
                project_name = row.get('project_name', '').strip()
                if not project_name:
                    stats['skipped'] += 1
                    continue

                # Try to match to existing project
                match, score = find_best_match(row, existing_projects)

                if match:
                    # Merge data into existing project
                    stats['matched'] += 1
                    stats['matches'].append((project_name, match.id, score))

                    if merge_planhub_data(match, row):
                        stats['updated'] += 1

                    # Create PlanHub link if not exists
                    planhub_id = normalize_project_id(project_name)
                    existing_link = session.query(PlanHubLink).filter(
                        PlanHubLink.planhub_id == planhub_id
                    ).first()

                    if not existing_link:
                        link = PlanHubLink(
                            planhub_id=planhub_id,
                            project_id=match.id
                        )
                        session.add(link)

                    logger.info(f"Matched '{project_name}' -> '{match.id}' (score: {score:.2f})")

                else:
                    # Create new project
                    new_project = create_planhub_project(row)

                    # Ensure unique ID
                    base_id = new_project.id
                    counter = 1
                    while new_project.id in seen_ids:
                        new_project.id = f"{base_id}-{counter}"
                        counter += 1

                    seen_ids.add(new_project.id)
                    session.add(new_project)
                    stats['created'] += 1

                    if new_project.archived:
                        stats['archived'] += 1

                    logger.debug(f"Created new project: {new_project.id}")

            except Exception as e:
                stats['errors'].append(f"Error processing '{row.get('project_name', 'unknown')}': {e}")
                logger.error(f"Error processing row: {e}")

        if not dry_run:
            session.commit()
            logger.info("Changes committed to database")
        else:
            session.rollback()
            logger.info("Dry run - changes not saved")

    return stats


def print_import_stats(stats: Dict):
    """Print import statistics"""
    print("\n" + "=" * 60)
    print("PlanHub CSV Import Summary")
    print("=" * 60)
    print(f"Total rows processed: {stats['total_rows']}")
    print(f"Matched to existing:  {stats['matched']}")
    print(f"  - Updated with data: {stats['updated']}")
    print(f"New projects created: {stats['created']}")
    print(f"  - Archived (past due): {stats['archived']}")
    print(f"Skipped (no name):    {stats['skipped']}")
    print(f"Errors:               {len(stats['errors'])}")

    if stats['matches']:
        print("\n" + "-" * 60)
        print("Top Matches:")
        for name, local_id, score in sorted(stats['matches'], key=lambda x: -x[2])[:20]:
            print(f"  {score:.2f}: '{name[:40]}' -> '{local_id}'")

    if stats['errors']:
        print("\n" + "-" * 60)
        print("Errors:")
        for err in stats['errors'][:10]:
            print(f"  - {err}")

    print("=" * 60)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python csv_importer.py <path_to_csv> [--dry-run]")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    dry_run = '--dry-run' in sys.argv

    logging.basicConfig(level=logging.INFO)

    stats = import_planhub_csv(csv_path, dry_run=dry_run)
    print_import_stats(stats)
