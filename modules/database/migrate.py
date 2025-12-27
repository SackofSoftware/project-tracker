"""
Migration Script - Import JSON data to SQLite Database

Imports all existing JSON data into the new centralized database.
Handles both static data files and per-project JSON files.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import logging

from .db import get_session, init_db
from .models import (
    Project, ProjectStatus, ProjectFile, Division8Scope,
    Vendor, VendorQuote, ProjectDogProject, PlanHubLink,
    ProjectNote, ProjectTag, Competitor, ExtractedProjectData
)

logger = logging.getLogger(__name__)


class DatabaseMigration:
    """Handles migration of JSON data to SQLite database"""

    def __init__(self, bidding_folder: str = None):
        """
        Initialize migration

        Args:
            bidding_folder: Path to bidding folder (e.g., /Users/.../Bob Projects/Bidding)
        """
        self.project_root = Path(__file__).parent.parent.parent
        self.static_data = self.project_root / "static" / "data"
        self.bidding_folder = Path(bidding_folder) if bidding_folder else None

        # Statistics
        self.stats = {
            'projects_imported': 0,
            'projectdog_imported': 0,
            'vendors_imported': 0,
            'quotes_imported': 0,
            'files_imported': 0,
            'scope_imported': 0,
            'errors': []
        }

    def migrate_all(self, skip_projectdog: bool = False, skip_local: bool = False):
        """
        Run complete migration

        Args:
            skip_projectdog: Skip ProjectDog import (if file is too large)
            skip_local: Skip local bidding folder projects
        """
        logger.info("Starting database migration...")

        # Initialize database
        init_db()

        # Migrate static data
        if not skip_projectdog:
            self.migrate_projectdog_projects()
        self.migrate_planhub_links()
        self.migrate_project_status()
        self.migrate_vendors()

        # Migrate per-project data
        if not skip_local and self.bidding_folder:
            self.migrate_local_projects()

        self.print_summary()

    def migrate_projectdog_projects(self):
        """Import projectdog_projects.json"""
        json_path = self.static_data / "projectdog_projects.json"

        if not json_path.exists():
            logger.warning(f"ProjectDog JSON not found: {json_path}")
            return

        logger.info("Migrating ProjectDog projects...")

        try:
            # Read in chunks to handle large files
            with open(json_path, 'r') as f:
                data = json.load(f)

            projects = data.get('projects', [])
            scraped_at = data.get('scraped_at')

            with get_session() as session:
                for proj_data in projects:
                    try:
                        # Handle location object - extract raw to location_raw
                        if 'location' in proj_data:
                            loc = proj_data.pop('location')
                            if isinstance(loc, dict):
                                proj_data['location_raw'] = loc.get('raw')
                            else:
                                proj_data['location_raw'] = loc

                        # Remove fields not in model
                        proj_data.pop('source', None)  # 'source' is not a ProjectDog field

                        # Parse dates
                        if proj_data.get('bid_date'):
                            proj_data['bid_date'] = self._parse_date(proj_data['bid_date'])
                        if proj_data.get('sub_bid_date'):
                            proj_data['sub_bid_date'] = self._parse_date(proj_data['sub_bid_date'])
                        if scraped_at:
                            proj_data['scraped_at'] = self._parse_date(scraped_at)

                        # Check if exists
                        existing = session.query(ProjectDogProject).filter_by(
                            project_code=proj_data['project_code']
                        ).first()

                        if existing:
                            # Update
                            for key, value in proj_data.items():
                                if hasattr(existing, key):
                                    setattr(existing, key, value)
                        else:
                            # Create
                            project = ProjectDogProject(**proj_data)
                            session.add(project)

                        self.stats['projectdog_imported'] += 1

                    except Exception as e:
                        logger.error(f"Error importing ProjectDog project {proj_data.get('project_code')}: {e}")
                        self.stats['errors'].append(f"ProjectDog {proj_data.get('project_code')}: {e}")

            logger.info(f"Imported {self.stats['projectdog_imported']} ProjectDog projects")

        except Exception as e:
            logger.error(f"Failed to migrate ProjectDog projects: {e}")
            self.stats['errors'].append(f"ProjectDog migration: {e}")

    def migrate_planhub_links(self):
        """Import planhub_links.json"""
        json_path = self.static_data / "planhub_links.json"

        if not json_path.exists():
            logger.warning(f"PlanHub links JSON not found: {json_path}")
            return

        logger.info("Migrating PlanHub links...")

        try:
            with open(json_path, 'r') as f:
                links = json.load(f)

            with get_session() as session:
                for planhub_id, project_id in links.items():
                    existing = session.query(PlanHubLink).filter_by(planhub_id=planhub_id).first()

                    if existing:
                        existing.project_id = project_id
                    else:
                        link = PlanHubLink(planhub_id=planhub_id, project_id=project_id)
                        session.add(link)

            logger.info(f"Imported {len(links)} PlanHub links")

        except Exception as e:
            logger.error(f"Failed to migrate PlanHub links: {e}")
            self.stats['errors'].append(f"PlanHub links: {e}")

    def migrate_project_status(self):
        """Import project_status.json"""
        json_path = self.static_data / "project_status.json"

        if not json_path.exists():
            logger.warning(f"Project status JSON not found: {json_path}")
            return

        logger.info("Migrating project status...")

        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            projects = data.get('projects', {})

            with get_session() as session:
                for project_id, status_data in projects.items():
                    try:
                        # Ensure project exists
                        project = session.query(Project).filter_by(id=project_id).first()
                        if not project:
                            # Create minimal project record
                            project = Project(
                                id=project_id,
                                title=status_data.get('project_title'),
                                source='local',
                                created_at=self._parse_date(status_data.get('created_at'))
                            )
                            session.add(project)
                            session.flush()
                            self.stats['projects_imported'] += 1

                        # Create or update status
                        existing_status = session.query(ProjectStatus).filter_by(project_id=project_id).first()

                        status_dict = self._flatten_project_status(status_data)

                        if existing_status:
                            for key, value in status_dict.items():
                                if hasattr(existing_status, key):
                                    setattr(existing_status, key, value)
                        else:
                            status = ProjectStatus(project_id=project_id, **status_dict)
                            session.add(status)

                        # Import notes
                        for note in status_data.get('notes', []):
                            note_obj = ProjectNote(
                                project_id=project_id,
                                content=note.get('content', note) if isinstance(note, dict) else note,
                                note_type='general',
                                created_at=self._parse_date(note.get('created_at')) if isinstance(note, dict) else None
                            )
                            session.add(note_obj)

                        # Import tags
                        for tag in status_data.get('tags', []):
                            tag_obj = ProjectTag(project_id=project_id, tag=tag)
                            session.add(tag_obj)

                        # Import competitors
                        for comp in status_data.get('competitors', []):
                            if isinstance(comp, str):
                                comp_obj = Competitor(project_id=project_id, company_name=comp)
                            else:
                                comp_obj = Competitor(
                                    project_id=project_id,
                                    company_name=comp.get('company_name', comp.get('name', '')),
                                    contact_name=comp.get('contact_name'),
                                    notes=comp.get('notes')
                                )
                            session.add(comp_obj)

                    except Exception as e:
                        logger.error(f"Error importing status for {project_id}: {e}")
                        self.stats['errors'].append(f"Status {project_id}: {e}")

            logger.info(f"Imported status for {len(projects)} projects")

        except Exception as e:
            logger.error(f"Failed to migrate project status: {e}")
            self.stats['errors'].append(f"Project status migration: {e}")

    def migrate_vendors(self):
        """Import vendors.json"""
        json_path = self.static_data / "vendors.json"

        if not json_path.exists():
            logger.warning(f"Vendors JSON not found: {json_path}")
            return

        logger.info("Migrating vendors...")

        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            vendors = data.get('vendors', {})

            with get_session() as session:
                for vendor_name, vendor_data in vendors.items():
                    try:
                        existing = session.query(Vendor).filter_by(name=vendor_name).first()

                        vendor_dict = {
                            'name': vendor_name,
                            'contact_name': vendor_data.get('contact_name'),
                            'email': vendor_data.get('email'),
                            'phone': vendor_data.get('phone'),
                            'address': vendor_data.get('address'),
                            'city': vendor_data.get('city'),
                            'state': vendor_data.get('state'),
                            'specialties': vendor_data.get('specialties', []),
                            'notes': vendor_data.get('notes')
                        }

                        if existing:
                            for key, value in vendor_dict.items():
                                if value and hasattr(existing, key):
                                    setattr(existing, key, value)
                        else:
                            vendor = Vendor(**vendor_dict)
                            session.add(vendor)
                            self.stats['vendors_imported'] += 1

                    except Exception as e:
                        logger.error(f"Error importing vendor {vendor_name}: {e}")
                        self.stats['errors'].append(f"Vendor {vendor_name}: {e}")

            logger.info(f"Imported {self.stats['vendors_imported']} vendors")

        except Exception as e:
            logger.error(f"Failed to migrate vendors: {e}")
            self.stats['errors'].append(f"Vendors migration: {e}")

    def migrate_local_projects(self):
        """Import local bidding folder projects"""
        if not self.bidding_folder or not self.bidding_folder.exists():
            logger.warning(f"Bidding folder not found: {self.bidding_folder}")
            return

        logger.info(f"Migrating local projects from {self.bidding_folder}...")

        # Scan bidding folder
        for project_dir in self.bidding_folder.iterdir():
            if not project_dir.is_dir():
                continue

            try:
                self._import_project_folder(project_dir)
            except Exception as e:
                logger.error(f"Error importing project {project_dir.name}: {e}")
                self.stats['errors'].append(f"Project {project_dir.name}: {e}")

        logger.info(f"Imported {self.stats['projects_imported']} local projects")

    def _import_project_folder(self, project_dir: Path):
        """Import a single project folder"""
        project_id = self._slugify(project_dir.name)

        with get_session() as session:
            # Check if project exists
            project = session.query(Project).filter_by(id=project_id).first()

            if not project:
                project = Project(
                    id=project_id,
                    title=project_dir.name,
                    folder_path=str(project_dir),
                    source='local'
                )
                session.add(project)
                session.flush()
                self.stats['projects_imported'] += 1

            # Import extracted_project_data.json
            extracted_path = project_dir / "extracted_project_data.json"
            if extracted_path.exists():
                self._import_extracted_data(project_id, extracted_path, session)

            # Import division8_rag_analysis.json
            rag_path = project_dir / "division8_rag_analysis.json"
            if rag_path.exists():
                self._import_division8_scope(project_id, rag_path, session)

            # Import .file_classifications.json
            class_path = project_dir / ".file_classifications.json"
            if class_path.exists():
                self._import_file_classifications(project_id, class_path, session)

    def _import_extracted_data(self, project_id: str, file_path: Path, session):
        """Import extracted_project_data.json"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            # Save raw extracted data
            existing = session.query(ExtractedProjectData).filter_by(project_id=project_id).first()

            meta = data.get('meta', {})

            if existing:
                existing.data = data
                existing.schema_version = meta.get('schema_version')
                existing.extractor_model = meta.get('extractor_model')
                existing.source_folder = meta.get('source_folder')
                existing.extracted_at = self._parse_date(meta.get('extracted_at'))
            else:
                extracted = ExtractedProjectData(
                    project_id=project_id,
                    data=data,
                    schema_version=meta.get('schema_version'),
                    extractor_model=meta.get('extractor_model'),
                    source_folder=meta.get('source_folder'),
                    extracted_at=self._parse_date(meta.get('extracted_at'))
                )
                session.add(extracted)

            # Update project with extracted info
            project = session.query(Project).filter_by(id=project_id).first()
            if project and data.get('project'):
                proj_data = data['project']
                if proj_data.get('name'):
                    project.title = proj_data['name']
                if proj_data.get('address'):
                    project.address = proj_data['address']
                if proj_data.get('city'):
                    project.city = proj_data['city']
                if proj_data.get('state'):
                    project.state = proj_data['state']
                if proj_data.get('owner'):
                    project.owner_name = proj_data['owner']
                if proj_data.get('architect'):
                    project.architect_name = proj_data['architect']

            # Update schedule
            if data.get('schedule'):
                sched = data['schedule']
                if sched.get('bid_date'):
                    project.bid_date = self._parse_date(sched['bid_date'])
                if sched.get('pre_bid_meeting', {}).get('date'):
                    project.pre_bid_meeting_date = self._parse_date(sched['pre_bid_meeting']['date'])

        except Exception as e:
            logger.error(f"Error importing extracted data for {project_id}: {e}")
            self.stats['errors'].append(f"Extracted data {project_id}: {e}")

    def _import_division8_scope(self, project_id: str, file_path: Path, session):
        """Import division8_rag_analysis.json"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            existing = session.query(Division8Scope).filter_by(project_id=project_id).first()

            rag_meta = data.get('_rag_metadata', {})

            # Helper to convert lists to strings for Text fields
            def to_text(val):
                if val is None:
                    return None
                if isinstance(val, list):
                    return '\n'.join(str(v) for v in val)
                return str(val) if val else None

            # Helper to ensure value is string or None for String fields
            def to_string(val):
                if val is None:
                    return None
                if isinstance(val, list):
                    return ', '.join(str(v) for v in val)
                return str(val) if val else None

            scope_dict = {
                'project_id': project_id,
                'scope_summary': to_text(data.get('scope_summary')),
                'confidence': to_string(data.get('confidence')),
                'windows_count': to_string(data.get('windows', {}).get('count')),
                'windows_types': data.get('windows', {}).get('types'),  # JSON field
                'windows_notes': to_text(data.get('windows', {}).get('notes')),
                'metal_door_count': to_string(data.get('doors', {}).get('metal_count')),
                'wood_door_count': to_string(data.get('doors', {}).get('wood_count')),
                'doors_notes': to_text(data.get('doors', {}).get('notes')),
                'storefront_description': to_text(data.get('storefront', {}).get('description')),
                'storefront_sf_estimate': to_string(data.get('storefront', {}).get('sf_estimate')),
                'hardware_groups': data.get('hardware', {}).get('groups'),  # JSON field
                'hardware_manufacturers': data.get('hardware', {}).get('manufacturers'),  # JSON field
                'hardware_notes': to_text(data.get('hardware', {}).get('notes')),
                'glass_specs': data.get('glass', {}).get('specs'),  # JSON field
                'glass_notes': to_text(data.get('glass', {}).get('notes')),
                'exclusions': data.get('exclusions'),  # JSON field
                'embedder_model': rag_meta.get('embedder'),
                'generator_model': rag_meta.get('generator'),
                'chunks_analyzed': rag_meta.get('chunks_analyzed'),
                'total_chunks': rag_meta.get('total_chunks_in_db'),
                'tokens_used': rag_meta.get('tokens_used'),
                'generated_at': self._parse_date(rag_meta.get('generated_at'))
            }

            if existing:
                for key, value in scope_dict.items():
                    if key != 'project_id' and hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                scope = Division8Scope(**scope_dict)
                session.add(scope)

            self.stats['scope_imported'] += 1

        except Exception as e:
            logger.error(f"Error importing Division 8 scope for {project_id}: {e}")
            self.stats['errors'].append(f"Division 8 scope {project_id}: {e}")

    def _import_file_classifications(self, project_id: str, file_path: Path, session):
        """Import .file_classifications.json"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            files = data.get('files', [])

            for file_data in files:
                existing = session.query(ProjectFile).filter_by(
                    project_id=project_id,
                    path=file_data['path']
                ).first()

                details = file_data.get('details', {})

                file_dict = {
                    'project_id': project_id,
                    'name': file_data['name'],
                    'path': file_data['path'],
                    'file_type': file_data['type'],
                    'confidence': file_data.get('confidence'),
                    'pages': details.get('pages'),
                    'size_mb': details.get('size_mb'),
                    'width_pt': details.get('width_pt'),
                    'height_pt': details.get('height_pt'),
                    'dimensions': details.get('dimensions'),
                    'extension': details.get('extension'),
                    'classified_by': details.get('classified_by', 'heuristic')
                }

                if not existing:
                    file_obj = ProjectFile(**file_dict)
                    session.add(file_obj)
                    self.stats['files_imported'] += 1

        except Exception as e:
            logger.error(f"Error importing file classifications for {project_id}: {e}")
            self.stats['errors'].append(f"File classifications {project_id}: {e}")

    def _flatten_project_status(self, status_data: Dict) -> Dict:
        """Flatten nested project status structure"""
        flat = {}

        # Bid decision
        flat['bid_decision'] = status_data.get('bid_decision')
        flat['bid_decision_reason'] = status_data.get('bid_decision_reason')
        flat['bid_decision_date'] = self._parse_date(status_data.get('bid_decision_date'))

        # Proposal
        proposal = status_data.get('proposal', {})
        flat['proposal_generated'] = proposal.get('generated', False)
        flat['proposal_generated_date'] = self._parse_date(proposal.get('generated_date'))
        flat['proposal_submitted'] = proposal.get('submitted', False)
        flat['proposal_submitted_date'] = self._parse_date(proposal.get('submitted_date'))
        flat['proposal_notes'] = proposal.get('notes')

        # Estimate
        estimate = status_data.get('estimate', {})
        flat['estimate_created'] = estimate.get('created', False)
        flat['estimate_created_date'] = self._parse_date(estimate.get('created_date'))
        flat['estimate_total'] = estimate.get('total')
        flat['estimate_confidence'] = estimate.get('confidence')
        flat['estimate_notes'] = estimate.get('notes')

        # Estimate breakdown
        breakdown = estimate.get('breakdown', {})
        for category in ['windows', 'doors', 'hardware', 'storefront', 'curtain_wall', 'glazing', 'misc']:
            cat_data = breakdown.get(category, {})
            flat[f'{category}_material'] = cat_data.get('material')
            flat[f'{category}_labor'] = cat_data.get('labor')
            flat[f'{category}_total'] = cat_data.get('total')

        # Documents
        docs = status_data.get('documents', {})
        flat['documents_acquired'] = docs.get('acquired', False)
        flat['documents_acquired_date'] = self._parse_date(docs.get('acquired_date'))
        flat['has_specs'] = docs.get('specs', False)
        flat['has_drawings'] = docs.get('drawings', False)
        flat['addenda_count'] = docs.get('addenda_count', 0)

        # Timestamps
        flat['created_at'] = self._parse_date(status_data.get('created_at'))
        flat['updated_at'] = self._parse_date(status_data.get('last_updated'))

        return flat

    def _parse_date(self, date_str: Any) -> datetime:
        """Parse date string to datetime object"""
        if not date_str:
            return None

        if isinstance(date_str, datetime):
            return date_str

        try:
            # Try ISO format
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            try:
                # Try common formats
                for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S']:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except:
                        continue
            except:
                pass

        return None

    def _slugify(self, text: str) -> str:
        """Convert text to URL-friendly slug"""
        import re
        text = text.lower()
        text = re.sub(r'[^a-z0-9]+', '-', text)
        text = text.strip('-')
        return text

    def print_summary(self):
        """Print migration summary"""
        print("\n" + "=" * 60)
        print("MIGRATION SUMMARY")
        print("=" * 60)
        print(f"Projects imported:        {self.stats['projects_imported']}")
        print(f"ProjectDog projects:      {self.stats['projectdog_imported']}")
        print(f"Vendors imported:         {self.stats['vendors_imported']}")
        print(f"Quotes imported:          {self.stats['quotes_imported']}")
        print(f"Files classified:         {self.stats['files_imported']}")
        print(f"Division 8 scopes:        {self.stats['scope_imported']}")
        print(f"Errors:                   {len(self.stats['errors'])}")
        print("=" * 60)

        if self.stats['errors']:
            print("\nERRORS:")
            for error in self.stats['errors'][:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(self.stats['errors']) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more errors")


# ==================== CONVENIENCE FUNCTIONS ====================

def migrate_from_json(bidding_folder: str = None, skip_projectdog: bool = False, skip_local: bool = False):
    """
    Convenience function to run migration

    Args:
        bidding_folder: Path to local bidding folder
        skip_projectdog: Skip ProjectDog import (useful if file is too large)
        skip_local: Skip local project import
    """
    migrator = DatabaseMigration(bidding_folder=bidding_folder)
    migrator.migrate_all(skip_projectdog=skip_projectdog, skip_local=skip_local)
    return migrator.stats


if __name__ == '__main__':
    """Run migration from command line"""
    import sys
    import argparse

    parser = argparse.ArgumentParser(description='Migrate JSON data to SQLite database')
    parser.add_argument('--bidding-folder', help='Path to bidding folder')
    parser.add_argument('--skip-projectdog', action='store_true', help='Skip ProjectDog import')
    parser.add_argument('--skip-local', action='store_true', help='Skip local projects')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    migrate_from_json(
        bidding_folder=args.bidding_folder,
        skip_projectdog=args.skip_projectdog,
        skip_local=args.skip_local
    )
