"""
PlanHub Importer - Import projects from PlanHub database.

Reads from planhub.db and imports completed leads as bid opportunities.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import re

from modules.database.db import get_session
from modules.database.models import Project, ProjectSourceLink, ProjectContractor
from modules.database.project_repository import ProjectRepository
from modules.database.dedup_service import DeduplicationService

logger = logging.getLogger(__name__)


class PlanHubImporter:
    """
    Imports projects from PlanHub SQLite database.
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.repo = ProjectRepository()
        self.dedup = DeduplicationService()

    def import_all(self) -> Dict[str, Any]:
        """
        Import all completed PlanHub leads.
        Returns summary statistics.
        """
        results = {
            'source': 'planhub',
            'database': str(self.db_path),
            'count': 0,
            'new': 0,
            'updated': 0,
            'merged': 0,
            'skipped': 0,
            'errors': []
        }

        if not self.db_path.exists():
            results['error'] = f'Database not found: {self.db_path}'
            return results

        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get completed leads (status='done')
            cursor.execute("""
                SELECT * FROM leads
                WHERE status = 'done'
                ORDER BY created_at DESC
            """)

            for row in cursor.fetchall():
                try:
                    lead = dict(row)
                    result = self._import_lead(lead)
                    results['count'] += 1
                    if result == 'new':
                        results['new'] += 1
                    elif result == 'updated':
                        results['updated'] += 1
                    elif result == 'merged':
                        results['merged'] += 1
                    elif result == 'skipped':
                        results['skipped'] += 1
                except Exception as e:
                    logger.error(f"Error importing PlanHub lead {row['id']}: {e}")
                    results['errors'].append({'id': row['id'], 'error': str(e)})

            conn.close()

        except Exception as e:
            results['error'] = str(e)
            logger.error(f'Error reading PlanHub database: {e}')

        logger.info(f"Imported {results['count']} PlanHub leads")
        return results

    def _import_lead(self, lead: Dict) -> str:
        """
        Import a single PlanHub lead.
        Returns: 'new', 'updated', 'merged', or 'skipped'
        """
        planhub_id = str(lead.get('id', ''))

        # Check if already linked
        existing = self.repo.find_project_by_source('planhub', planhub_id)

        # Extract project data
        project_data = self._normalize_lead(lead)

        if existing:
            # Update existing linked project
            self.repo.update_project(existing.id, {
                'last_synced_at': datetime.now(),
                **project_data
            })
            return 'updated'
        else:
            # Try deduplication
            canonical = self.dedup.auto_merge_if_confident(
                project_data,
                source_type='planhub',
                source_id=planhub_id
            )

            if canonical:
                return 'merged'
            else:
                # Create new project as bid_opportunity
                project_id = self._generate_project_id(project_data.get('title', f'planhub-{planhub_id}'))

                self.repo.create_project({
                    'id': project_id,
                    'source': 'planhub',
                    'workflow_status': 'bid_opportunity',  # Goes to assessment queue
                    'last_synced_at': datetime.now(),
                    **project_data
                })

                # Add source link
                self.repo.add_source_link(
                    project_id=project_id,
                    source_type='planhub',
                    source_id=planhub_id,
                    source_data=lead,
                    match_confidence=1.0,
                    match_type='primary'
                )

                # Import GCs if available
                self._import_gcs(project_id, lead)

                return 'new'

    def _normalize_lead(self, lead: Dict) -> Dict[str, Any]:
        """Normalize PlanHub lead to project format."""
        data = {}

        # Basic fields
        data['title'] = lead.get('title', '')
        data['description'] = lead.get('description', '')

        # Location
        data['address'] = lead.get('address', '')
        data['city'] = lead.get('city', '')
        data['state'] = lead.get('state', '')
        data['zip_code'] = lead.get('zip_code', '')

        # Dates
        if lead.get('bid_date'):
            data['bid_date'] = lead['bid_date']
        if lead.get('sub_bid_date'):
            data['sub_bid_date'] = lead['sub_bid_date']

        # Value
        if lead.get('estimated_value'):
            data['estimated_value'] = lead['estimated_value']

        # Project details from JSON fields
        if lead.get('project_info_json'):
            try:
                info = json.loads(lead['project_info_json']) if isinstance(lead['project_info_json'], str) else lead['project_info_json']
                if isinstance(info, dict):
                    if info.get('owner'):
                        data['owner_name'] = info['owner']
                    if info.get('architect'):
                        data['architect_name'] = info['architect']
                    if info.get('square_footage'):
                        data['square_footage'] = info['square_footage']
                    if info.get('project_type'):
                        data['project_type'] = info['project_type']
                    if info.get('building_use'):
                        data['building_use'] = info['building_use']

                    # Tags for Division 8 detection
                    tags = info.get('tags', [])
                    trades = info.get('trades', [])
                    all_tags = tags + trades if isinstance(tags, list) and isinstance(trades, list) else []
                    data['trades'] = '; '.join(all_tags) if all_tags else ''
            except:
                pass

        return data

    def _import_gcs(self, project_id: str, lead: Dict):
        """Import GC information from PlanHub lead."""
        if not lead.get('gc_json'):
            return

        try:
            gcs = json.loads(lead['gc_json']) if isinstance(lead['gc_json'], str) else lead['gc_json']
            if not isinstance(gcs, list):
                return

            for gc in gcs:
                if not isinstance(gc, dict):
                    continue

                self.repo.add_contractor(
                    project_id=project_id,
                    company_name=gc.get('company', gc.get('name', 'Unknown')),
                    role='gc',
                    contact_name=gc.get('contact'),
                    contact_email=gc.get('email'),
                    contact_phone=gc.get('phone'),
                    source='planhub'
                )
        except Exception as e:
            logger.warning(f'Error importing GCs for {project_id}: {e}')

    def _generate_project_id(self, title: str) -> str:
        """Generate URL-safe project ID."""
        slug = title.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug[:60] or 'planhub-project'