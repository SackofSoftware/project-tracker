"""
Email Importer - Import bid invites from Email Monitor output.

Reads email metadata from Email Monitor's output folder and creates
bid opportunities for new invites.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import re

from modules.database.db import get_session
from modules.database.models import Project, ProjectSourceLink, ProjectEmail
from modules.database.project_repository import ProjectRepository
from modules.database.dedup_service import DeduplicationService

logger = logging.getLogger(__name__)


class EmailImporter:
    """
    Imports bid invites from Email Monitor output.
    """

    def __init__(self, output_path: str):
        self.output_path = Path(output_path)
        self.repo = ProjectRepository()
        self.dedup = DeduplicationService()

    def import_all(self) -> Dict[str, Any]:
        """
        Import all email metadata from Email Monitor output.
        Returns summary statistics.
        """
        results = {
            'source': 'email',
            'path': str(self.output_path),
            'count': 0,
            'new': 0,
            'updated': 0,
            'merged': 0,
            'skipped': 0,
            'errors': []
        }

        if not self.output_path.exists():
            results['error'] = f'Path not found: {self.output_path}'
            return results

        # Scan for project folders in output
        for project_folder in self.output_path.iterdir():
            if not project_folder.is_dir() or project_folder.name.startswith('.'):
                continue

            # Look for metadata files
            for metadata_file in project_folder.glob('*.json'):
                try:
                    result = self._import_email_metadata(metadata_file, project_folder.name)
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
                    logger.error(f'Error importing email {metadata_file}: {e}')
                    results['errors'].append({
                        'file': str(metadata_file),
                        'error': str(e)
                    })

        logger.info(f"Imported {results['count']} email records")
        return results

    def _import_email_metadata(self, metadata_path: Path, project_folder: str) -> str:
        """
        Import a single email metadata file.
        Returns: 'new', 'updated', 'merged', or 'skipped'
        """
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        email_id = metadata.get('message_id') or str(metadata_path)

        # Check if email already imported
        with get_session() as session:
            existing = session.query(ProjectEmail).filter(
                ProjectEmail.metadata_path == str(metadata_path)
            ).first()

            if existing:
                # Already processed
                return 'skipped'

            # Extract project info from email
            project_data = self._extract_project_data(metadata, project_folder)

            # Check if this is a bid invite (vs general email)
            email_type = self._classify_email(metadata)

            if email_type not in ['bid_invite', 'addendum', 'deadline_reminder']:
                # Not a relevant email type
                return 'skipped'

            # Try to find matching project
            canonical = self.dedup.auto_merge_if_confident(
                project_data,
                source_type='email',
                source_id=email_id
            )

            if canonical:
                # Link email to existing project
                email_record = ProjectEmail(
                    project_id=canonical.id,
                    subject=metadata.get('subject', ''),
                    sender=metadata.get('from', ''),
                    sender_name=metadata.get('from_name', ''),
                    received_time=self._parse_date(metadata.get('date')),
                    metadata_path=str(metadata_path),
                    email_type=email_type,
                    source_platform=self._detect_platform(metadata),
                    project_folder=project_folder,
                    extracted_project_name=project_data.get('title'),
                    extracted_bid_date=self._parse_date(project_data.get('bid_date')),
                    match_confidence=0.9,
                    match_type='auto',
                    matched_by='system',
                    matched_at=datetime.now(),
                    attachments=metadata.get('attachments', [])
                )
                session.add(email_record)
                return 'merged'
            else:
                # Create new project as bid_opportunity
                project_id = self._generate_project_id(project_data.get('title', project_folder))

                self.repo.create_project({
                    'id': project_id,
                    'source': 'email',
                    'workflow_status': 'bid_opportunity',
                    'last_synced_at': datetime.now(),
                    **project_data
                })

                # Add source link
                self.repo.add_source_link(
                    project_id=project_id,
                    source_type='email',
                    source_id=email_id,
                    source_data=metadata,
                    match_confidence=1.0,
                    match_type='primary'
                )

                # Create email record
                email_record = ProjectEmail(
                    project_id=project_id,
                    subject=metadata.get('subject', ''),
                    sender=metadata.get('from', ''),
                    sender_name=metadata.get('from_name', ''),
                    received_time=self._parse_date(metadata.get('date')),
                    metadata_path=str(metadata_path),
                    email_type=email_type,
                    source_platform=self._detect_platform(metadata),
                    project_folder=project_folder,
                    extracted_project_name=project_data.get('title'),
                    match_confidence=1.0,
                    match_type='primary',
                    matched_by='system',
                    matched_at=datetime.now(),
                    attachments=metadata.get('attachments', [])
                )
                session.add(email_record)

                return 'new'

    def _extract_project_data(self, metadata: Dict, folder_name: str) -> Dict[str, Any]:
        """Extract project information from email metadata."""
        data = {
            'title': folder_name,  # Default to folder name
        }

        subject = metadata.get('subject', '')

        # Try to extract project name from subject
        # Common patterns: "Bid Invitation: Project Name" or "Project Name - Bid Due 1/15/25"
        name_patterns = [
            r'Invitation[:\s]+(.+?)(?:\s*[-|]\s*|$)',
            r'Project[:\s]+(.+?)(?:\s*[-|]\s*|$)',
            r'^(.+?)\s*[-|]\s*Bid',
        ]

        for pattern in name_patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                data['title'] = match.group(1).strip()
                break

        # Try to extract bid date from subject or body
        date_patterns = [
            r'Due[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'Bid Date[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        ]

        for pattern in date_patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                data['bid_date'] = match.group(1)
                break

        # Check body if available
        body = metadata.get('body', '') or metadata.get('text', '')
        if body and 'bid_date' not in data:
            for pattern in date_patterns:
                match = re.search(pattern, body, re.IGNORECASE)
                if match:
                    data['bid_date'] = match.group(1)
                    break

        return data

    def _classify_email(self, metadata: Dict) -> str:
        """Classify email type based on content."""
        subject = (metadata.get('subject', '') or '').lower()
        sender = (metadata.get('from', '') or '').lower()

        # Check for bid invite indicators
        invite_keywords = ['invitation', 'invite', 'bid request', 'rfp', 'rfq']
        if any(kw in subject for kw in invite_keywords):
            return 'bid_invite'

        # Check for addendum
        if 'addendum' in subject or 'addenda' in subject:
            return 'addendum'

        # Check for deadline reminder
        if 'reminder' in subject or 'deadline' in subject:
            return 'deadline_reminder'

        # Check sender for known platforms
        platform_domains = ['planhub', 'buildingconnected', 'smartbidnet', 'blubook']
        if any(domain in sender for domain in platform_domains):
            return 'bid_invite'

        return 'other'

    def _detect_platform(self, metadata: Dict) -> str:
        """Detect source platform from email."""
        sender = (metadata.get('from', '') or '').lower()
        subject = (metadata.get('subject', '') or '').lower()

        platforms = {
            'planhub': ['planhub'],
            'buildingconnected': ['buildingconnected', 'autodesk'],
            'smartbidnet': ['smartbidnet'],
            'blubook': ['blubook', 'thebluebook'],
        }

        for platform, keywords in platforms.items():
            if any(kw in sender or kw in subject for kw in keywords):
                return platform

        return 'unknown'

    def _parse_date(self, date_str) -> datetime:
        """Parse date string to datetime."""
        if not date_str:
            return None
        if isinstance(date_str, datetime):
            return date_str

        # Try common formats
        formats = [
            '%Y-%m-%d',
            '%m/%d/%Y',
            '%m/%d/%y',
            '%m-%d-%Y',
            '%m-%d-%y',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(str(date_str), fmt)
            except:
                continue

        return None

    def _generate_project_id(self, title: str) -> str:
        """Generate URL-safe project ID."""
        slug = title.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')
        return slug[:60] or 'email-project'