"""
Local Bidding Folder Reader
Reads extracted project JSON files from the local Bidding directory
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

# Import unified schema
from modules.schema.unified_project import (
    UnifiedProject,
    Location,
    Document,
    Division8Scope,
    normalize_date
)

# Import centralized RAG database
try:
    from modules.rag.rag_database import get_rag_database
except ImportError:
    get_rag_database = None


class BiddingFolderReader:
    """Reader for local bidding folder project data"""

    def __init__(self, bidding_folder: str):
        self.bidding_folder = Path(bidding_folder)
        self.projects = []
        self._projects_json_cache = None

    def read_all_projects(self) -> List[UnifiedProject]:
        """Read all project data from the bidding folder"""
        projects = []
        seen_folders = set()

        # First, try to read the main projects.json file
        projects_json = self.bidding_folder / "projects.json"
        if projects_json.exists():
            json_projects = self._read_projects_json(projects_json)
            for p in json_projects:
                projects.append(p)
                folder = p.source_id if hasattr(p, 'source_id') else None
                if folder:
                    seen_folders.add(folder)

        # Then scan each project folder
        for item in self.bidding_folder.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                # Skip special folders
                if item.name in ('div8_analyzer', 'tmp_xlsx', 'tmp_bridgeman', 'tmp_bridgeman_glass', 'Files', 'BIDS FALL WINTER 2025'):
                    continue

                # Skip if already in projects.json
                if item.name in seen_folders:
                    continue

                extracted_file = item / "extracted_project_data.json"
                if extracted_file.exists():
                    project = self._read_extracted_project(extracted_file, item.name)
                    if project:
                        projects.append(project)
                        seen_folders.add(item.name)
                        continue

                # Create a basic entry from folder name if no extracted data
                project = self._create_folder_project(item.name)
                if project:
                    projects.append(project)
                    seen_folders.add(item.name)

        self.projects = projects
        return projects

    def _create_folder_project(self, folder_name: str) -> Optional[UnifiedProject]:
        """Create a basic project entry from folder name"""
        # Try to parse location from folder name (e.g., "Project Name - City MA")
        title = folder_name
        city = None
        state = None

        # Common patterns: "Name - City MA", "Name - City, MA"
        import re
        match = re.search(r'-\s*([^-]+?)\s*,?\s*([A-Z]{2})\s*$', folder_name)
        if match:
            city = match.group(1).strip()
            state = match.group(2)

        location = Location(city=city, state=state)

        project = UnifiedProject(
            # Identity
            id=f"local-{folder_name.lower().replace(' ', '-').replace(',', '')}",
            source="local_bidding",
            source_id=folder_name,

            # Basic Info
            title=title,

            # Location
            location=location,

            # Division 8
            division_8=Division8Scope(),

            # Metadata
            created_at=datetime.now().isoformat()
        )

        # Check for RAG analysis file even if no extracted data
        folder_path = self.bidding_folder / folder_name
        project = self._load_rag_analysis(project, folder_path)

        return project

    def _read_projects_json(self, filepath: Path) -> List[UnifiedProject]:
        """Read the main projects.json file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            projects = []
            raw_projects = data.get('projects', []) if isinstance(data, dict) else data

            for proj in raw_projects:
                project = self._normalize_project(proj, source="projects.json")
                if project:
                    # Load RAG analysis for this project
                    folder_name = project.source_id
                    if folder_name:
                        folder_path = self.bidding_folder / folder_name
                        project = self._load_rag_analysis(project, folder_path)
                    projects.append(project)

            self._projects_json_cache = projects
            return projects

        except Exception as e:
            print(f"Error reading projects.json: {e}")
            return []

    def _read_extracted_project(self, filepath: Path, folder_name: str) -> Optional[UnifiedProject]:
        """Read an extracted_project_data.json file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            project = self._normalize_extracted_project(data, folder_name)

            # Also check for RAG analysis file
            if project:
                project = self._load_rag_analysis(project, filepath.parent)

            return project

        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            return None

    def _load_rag_analysis(self, project: UnifiedProject, folder_path: Path) -> UnifiedProject:
        """Load RAG analysis data from centralized database or JSON file and merge into UnifiedProject"""
        rag_data = None
        folder_name = project.source_id or folder_path.name

        # First try centralized database (with fuzzy matching)
        if get_rag_database:
            try:
                db = get_rag_database()
                rag_data = db.get_analysis(folder_name)
                if rag_data:
                    rag_data['_source'] = 'database'
            except Exception as e:
                print(f"Error loading RAG from database for {folder_name}: {e}")

        # Fall back to JSON file if not in database
        if not rag_data:
            rag_file = folder_path / "division8_rag_analysis.json"
            if rag_file.exists():
                try:
                    with open(rag_file, 'r') as f:
                        rag_data = json.load(f)
                        rag_data['_source'] = 'json_file'
                except Exception as e:
                    print(f"Error loading RAG analysis from {rag_file}: {e}")

        # Apply RAG data to project if found
        if rag_data:
            # Merge RAG scope into division_8 if not already present
            if rag_data.get('scope_summary') and not project.division_8.scope_summary:
                project.division_8.scope_summary = rag_data.get('scope_summary', '')

            # Add RAG-extracted counts if available (store in metadata for now)
            # We could extend Division8Scope to have rag_* fields if needed
            if not project.division_8.windows.get('count') and rag_data.get('windows', {}).get('count'):
                project.division_8.windows = rag_data['windows']

            if not project.division_8.doors.get('count') and rag_data.get('doors', {}).get('count'):
                project.division_8.doors = rag_data['doors']

            if rag_data.get('storefront'):
                project.division_8.storefront = bool(rag_data.get('storefront', {}).get('count', 0) > 0)

        return project

    def _normalize_project(self, data: Dict, source: str) -> Optional[UnifiedProject]:
        """Normalize a project from projects.json to UnifiedProject"""
        try:
            # Extract key fields from the schema
            location_data = data.get('location', {})
            bid_info = data.get('bid', {})
            div8 = data.get('division_8', {})
            folder_name = data.get('current_folder', '')
            title = data.get('project_name', '')

            if not title:
                return None

            # Build Location
            location = Location(
                address=location_data.get('address'),
                city=location_data.get('city'),
                state=location_data.get('state')
            )

            # Build Division8Scope
            division_8 = Division8Scope(
                scope_summary=div8.get('scope_summary'),
                spec_sections=div8.get('spec_sections', []),
                windows=div8.get('windows', {}),
                doors=div8.get('doors', {}),
                hardware=div8.get('hardware', []),
                glazing=div8.get('glazing', []),
                storefront=bool(div8.get('storefront', {}).get('count', 0) > 0)
            )

            # Check if Division 8
            is_division_8 = bool(division_8.spec_sections or division_8.windows.get('count', 0) > 0 or
                               division_8.doors.get('count', 0) > 0)

            project = UnifiedProject(
                # Identity
                id=f"local-{data.get('project_key', folder_name.lower().replace(' ', '-'))}",
                source="local_bidding",
                source_id=folder_name,

                # Basic Info
                title=title,
                description='\n'.join(data.get('summary_paragraphs', [])) if data.get('summary_paragraphs') else None,

                # Location
                location=location,

                # Dates
                bid_date=normalize_date(bid_info.get('due_date')),

                # Division 8
                is_division_8=is_division_8,
                division_8=division_8,

                # Metadata
                created_at=datetime.now().isoformat()
            )

            # Store estimate info in internal_status
            if data.get('estimate', {}).get('has_estimate'):
                project.internal_status.has_internal_estimate = True

            return project

        except Exception as e:
            print(f"Error normalizing project: {e}")
            return None

    def _normalize_extracted_project(self, data: Dict, folder_name: str) -> Optional[UnifiedProject]:
        """Normalize an extracted_project_data.json to UnifiedProject"""
        try:
            meta = data.get('meta', {})
            project_data = data.get('project', {})
            schedule = data.get('schedule', {})
            div8 = data.get('division_8', {})
            estimate = data.get('estimate', {})
            openings = data.get('openings_schedule', {})
            location_data = project_data.get('location', {})

            # Check if there's any meaningful data
            has_project_data = bool(project_data)
            has_div8 = bool(div8) and any(div8.values())
            has_openings = bool(openings) and (openings.get('windows') or openings.get('doors') or openings.get('storefronts'))

            # Skip if no meaningful data at all
            if not has_project_data and not has_div8 and not has_openings:
                return None

            # Build Location
            location = Location(
                address=location_data.get('address'),
                city=location_data.get('city'),
                state=location_data.get('state')
            )

            # Build division_8 from both div8 section and openings_schedule
            windows_data = div8.get('windows', {}).copy() if div8.get('windows') else {}
            doors_data = div8.get('doors', {}).copy() if div8.get('doors') else {}
            storefront_data = div8.get('storefront', {}).copy() if div8.get('storefront') else {}

            # Helper to safely get qty as int
            def safe_qty(item):
                qty = item.get('qty', 1)
                if qty is None:
                    return 1
                try:
                    return int(qty)
                except (ValueError, TypeError):
                    return 1

            # Enrich with openings_schedule counts if available
            if openings.get('windows'):
                window_count = len(openings['windows'])
                total_qty = sum(safe_qty(w) for w in openings['windows'])
                if not windows_data:
                    windows_data = {}
                windows_data['count'] = total_qty
                windows_data['schedule_items'] = window_count

            if openings.get('doors'):
                door_count = len(openings['doors'])
                total_qty = sum(safe_qty(d) for d in openings['doors'])
                if not doors_data:
                    doors_data = {}
                doors_data['count'] = total_qty
                doors_data['schedule_items'] = door_count

            if openings.get('storefronts'):
                sf_count = len(openings['storefronts'])
                if not storefront_data:
                    storefront_data = {}
                storefront_data['count'] = sf_count

            # Build Division8Scope
            division_8 = Division8Scope(
                scope_summary=div8.get('scope_summary'),
                spec_sections=div8.get('spec_sections', []),
                windows=windows_data,
                doors=doors_data,
                hardware=div8.get('hardware', []),
                glazing=div8.get('glazing', []),
                storefront=bool(storefront_data.get('count', 0) > 0),
                curtain_wall=bool(div8.get('curtain_wall', {}).get('count', 0) > 0)
            )

            # Check if Division 8
            is_division_8 = bool(division_8.spec_sections or windows_data.get('count', 0) > 0 or
                               doors_data.get('count', 0) > 0)

            project = UnifiedProject(
                # Identity
                id=f"local-{folder_name.lower().replace(' ', '-').replace(',', '')}",
                source="local_bidding",
                source_id=folder_name,

                # Basic Info
                title=project_data.get('name', folder_name),

                # Location
                location=location,

                # Dates
                bid_date=normalize_date(schedule.get('bid_date')),

                # Project Details
                architect=project_data.get('architect'),
                owner=project_data.get('owner'),

                # Division 8
                is_division_8=is_division_8,
                division_8=division_8,

                # Metadata
                created_at=meta.get('extracted_at'),
                updated_at=datetime.now().isoformat()
            )

            # Store estimate info in internal_status
            if estimate.get('has_estimate'):
                project.internal_status.has_internal_estimate = True
                project.internal_status.internal_estimate_total = estimate.get('division_8_total')

            return project

        except Exception as e:
            print(f"Error normalizing extracted project: {e}")
            return None

    def get_project_by_folder(self, folder_name: str) -> Optional[UnifiedProject]:
        """Get a specific project by folder name"""
        for project in self.projects:
            if project.source_id == folder_name:
                return project
        return None

    def get_projects_with_estimates(self) -> List[UnifiedProject]:
        """Get only projects that have estimates"""
        return [p for p in self.projects if p.internal_status.has_internal_estimate]

    def get_upcoming_bids(self, days: int = 30) -> List[UnifiedProject]:
        """Get projects with bid dates in the next N days (Eastern timezone)"""
        from datetime import timedelta

        # Use Eastern timezone for date calculations
        eastern = ZoneInfo('America/New_York')
        today = datetime.now(eastern).date()
        cutoff = today + timedelta(days=days)

        upcoming = []
        for project in self.projects:
            if project.bid_date:
                try:
                    bid_dt = datetime.strptime(project.bid_date, '%Y-%m-%d').date()
                    if today <= bid_dt <= cutoff:
                        upcoming.append(project)
                except ValueError:
                    pass

        return sorted(upcoming, key=lambda x: (datetime.strptime(x.bid_date, '%Y-%m-%d').date() - today).days if x.bid_date else 999)

    def get_summary_stats(self) -> Dict:
        """Get summary statistics about loaded projects"""
        total = len(self.projects)
        with_estimates = len(self.get_projects_with_estimates())
        upcoming = len(self.get_upcoming_bids(30))

        # Count by state (skip projects without state)
        states = {}
        for p in self.projects:
            state = p.location.state
            if state:  # Only count if state is known
                states[state] = states.get(state, 0) + 1

        return {
            "total_projects": total,
            "with_estimates": with_estimates,
            "upcoming_30_days": upcoming,
            "by_state": states
        }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    bidding_folder = os.getenv("BIDDING_FOLDER", "")
    if not bidding_folder:
        print("Error: BIDDING_FOLDER environment variable not set.")
        print("Copy .env.example to .env and configure your paths.")
        import sys
        sys.exit(1)

    reader = BiddingFolderReader(bidding_folder)
    projects = reader.read_all_projects()

    print(f"\nLoaded {len(projects)} projects from bidding folder")
    print(f"\nStats: {reader.get_summary_stats()}")

    # Show upcoming bids
    upcoming = reader.get_upcoming_bids(60)
    if upcoming:
        print(f"\nUpcoming bids (next 60 days):")
        for p in upcoming[:5]:
            print(f"  - {p['title']} - {p['bid_date']} ({p['days_until_bid']} days)")
