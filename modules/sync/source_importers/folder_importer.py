"""
Folder Importer - Import projects from local bidding folders.

Handles importing from:
- Bidding folder (active bids)
- Brad Projects folder (additional bids)
- Current Projects folder (projects in progress)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import re

from modules.database.db import get_session
from modules.database.models import Project, ProjectSourceLink
from modules.database.project_repository import ProjectRepository
from modules.database.dedup_service import DeduplicationService

logger = logging.getLogger(__name__)


class FolderImporter:
    """
    Imports projects from local folder structures into the database.
    """

    def __init__(self, source_name: str, folder_path: str):
        self.source_name = source_name
        self.folder_path = Path(folder_path)
        self.repo = ProjectRepository()
        self.dedup = DeduplicationService()

    def import_all(self) -> Dict[str, Any]:
        """
        Import all projects from the folder.
        Returns summary statistics.
        """
        results = {
            'source': self.source_name,
            'folder': str(self.folder_path),
            'count': 0,
            'new': 0,
            'updated': 0,
            'skipped': 0,
            'errors': []
        }

        if not self.folder_path.exists():
            results['error'] = f'Folder not found: {self.folder_path}'
            return results

        # Scan for project folders
        for item in self.folder_path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                try:
                    result = self._import_project_folder(item)
                    results['count'] += 1
                    if result == 'new':
                        results['new'] += 1
                    elif result == 'updated':
                        results['updated'] += 1
                    elif result == 'skipped':
                        results['skipped'] += 1
                except Exception as e:
                    logger.error(f'Error importing {item.name}: {e}')
                    results['errors'].append({'folder': item.name, 'error': str(e)})

        logger.info(f"Imported {results['count']} projects from {self.source_name}")
        return results

    def _import_project_folder(self, folder: Path) -> str:
        """
        Import a single project folder.
        Returns: 'new', 'updated', 'skipped', or 'merged'
        """
        # Generate project ID from folder name
        project_id = self._generate_project_id(folder.name)

        # Check if already exists
        existing = self.repo.get_project(project_id)

        # Extract project data from folder
        project_data = self._extract_project_data(folder)

        if existing:
            # Update existing project
            self.repo.update_project(project_id, {
                'folder_path': str(folder),
                'last_synced_at': datetime.now(),
                **project_data
            })
            return 'updated'
        else:
            # Try to find duplicate match
            canonical = self.dedup.auto_merge_if_confident(
                project_data,
                source_type=self.source_name,
                source_id=folder.name
            )

            if canonical:
                # Merged with existing
                return 'merged'
            else:
                # Create new project
                self.repo.create_project({
                    'id': project_id,
                    'source': self.source_name,
                    'folder_path': str(folder),
                    'workflow_status': self._determine_initial_status(),
                    'last_synced_at': datetime.now(),
                    **project_data
                })

                # Add source link
                self.repo.add_source_link(
                    project_id=project_id,
                    source_type=self.source_name,
                    source_id=folder.name,
                    match_confidence=1.0,
                    match_type='primary'
                )

                return 'new'

    def _extract_project_data(self, folder: Path) -> Dict[str, Any]:
        """Extract project metadata from folder contents."""
        data = {
            'title': self._clean_folder_name(folder.name),
        }

        # Try to read projects.json if it exists
        projects_json = folder / 'projects.json'
        if projects_json.exists():
            try:
                with open(projects_json, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    data.update(self._normalize_json_data(json_data))
            except Exception as e:
                logger.warning(f'Error reading projects.json in {folder.name}: {e}')

        # Try to read extracted_project_data.json
        extracted_json = folder / 'extracted_project_data.json'
        if extracted_json.exists():
            try:
                with open(extracted_json, 'r', encoding='utf-8') as f:
                    extracted = json.load(f)
                    data.update(self._normalize_extracted_data(extracted))
            except Exception as e:
                logger.warning(f'Error reading extracted_project_data.json in {folder.name}: {e}')

        # Parse folder name for additional info
        name_data = self._parse_folder_name(folder.name)
        for key, value in name_data.items():
            if key not in data or not data[key]:
                data[key] = value

        return data

    def _normalize_json_data(self, json_data: Dict) -> Dict[str, Any]:
        """Normalize data from projects.json format."""
        normalized = {}

        # Direct mappings
        mappings = {
            'title': 'title',
            'name': 'title',
            'project_name': 'title',
            'address': 'address',
            'city': 'city',
            'state': 'state',
            'zip': 'zip_code',
            'zip_code': 'zip_code',
            'owner': 'owner_name',
            'owner_name': 'owner_name',
            'architect': 'architect_name',
            'architect_name': 'architect_name',
            'bid_date': 'bid_date',
            'sub_bid_date': 'sub_bid_date',
            'estimated_value': 'estimated_value',
            'description': 'description',
        }

        for src, dst in mappings.items():
            if src in json_data and json_data[src]:
                normalized[dst] = json_data[src]

        return normalized

    def _normalize_extracted_data(self, extracted: Dict) -> Dict[str, Any]:
        """Normalize data from AI-extracted format."""
        normalized = {}

        # Handle nested structures
        if 'project_info' in extracted:
            info = extracted['project_info']
            if isinstance(info, dict):
                normalized.update(self._normalize_json_data(info))

        if 'bid_info' in extracted:
            bid = extracted['bid_info']
            if isinstance(bid, dict):
                if 'bid_date' in bid:
                    normalized['bid_date'] = bid['bid_date']
                if 'sub_bid_date' in bid:
                    normalized['sub_bid_date'] = bid['sub_bid_date']

        if 'stakeholders' in extracted:
            stake = extracted['stakeholders']
            if isinstance(stake, dict):
                if 'owner' in stake:
                    normalized['owner_name'] = stake['owner']
                if 'architect' in stake:
                    normalized['architect_name'] = stake['architect']

        return normalized

    def _parse_folder_name(self, name: str) -> Dict[str, Any]:
        """Parse project info from folder name conventions."""
        data = {}

        # Common patterns:
        # "Project Name - City, State"
        # "21-27 Project Name"
        # "Project Name - 12345 (Zip)"

        # Try to extract city/state from end
        city_state_pattern = r'[,-]\s*([A-Za-z\s]+),?\s*(MA|CT|RI|NH|VT|ME|NY|NJ|PA)?$'
        match = re.search(city_state_pattern, name)
        if match:
            if match.group(1):
                data['city'] = match.group(1).strip()
            if match.group(2):
                data['state'] = match.group(2).upper()

        return data

    def _clean_folder_name(self, name: str) -> str:
        """Clean folder name to use as title."""
        # Remove common prefixes like dates
        name = re.sub(r'^\d{2}-\d{2}\s*', '', name)
        # Remove trailing location info
        name = re.sub(r'\s*[,-]\s*[A-Za-z]+,?\s*(MA|CT|RI|NH|VT|ME|NY|NJ|PA)?\s*$', '', name)
        return name.strip()

    def _generate_project_id(self, folder_name: str) -> str:
        """Generate a URL-safe project ID from folder name."""
        # Convert to lowercase, replace spaces with dashes
        slug = folder_name.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug[:60]  # Truncate

    def _determine_initial_status(self) -> str:
        """Determine initial workflow status based on source."""
        if self.source_name == 'bidding':
            return 'bidding'  # Active bidding folders
        elif self.source_name == 'brad':
            return 'bidding'  # Also active bidding
        elif self.source_name == 'current':
            return 'under_contract'  # Current projects are awarded
        else:
            return 'bid_opportunity'