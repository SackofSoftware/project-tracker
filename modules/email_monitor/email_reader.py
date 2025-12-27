"""
Email Monitor Reader

Reads emails from the Email Monitor output directory structure:
/output/
  /Bid Invites/
    /{Project Name}/
      /{date}/
        email_XXXX_metadata.json
        attachments/
  /In Progress/
    /{Category}/
      /{Project Name}/
        ...
"""

import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class EmailRecord:
    """Parsed email record from Email Monitor"""
    id: str
    metadata_path: str
    project_folder: str
    category: str  # 'Bid Invites' or 'In Progress'
    subject: str
    sender: str
    sender_name: str
    received_time: datetime
    email_type: str  # bid_invite, deadline_reminder, addendum, rfi, project_update
    source_platform: str  # planhub, buildingconnected, blubook, smartbidnet
    project_name: str  # Extracted project name
    bid_date: Optional[datetime]
    attachments: List[Dict] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    confidence: float = 0.5
    summary: Optional[str] = None
    html_path: Optional[str] = None
    attachments_folder: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'metadata_path': self.metadata_path,
            'project_folder': self.project_folder,
            'category': self.category,
            'subject': self.subject,
            'sender': self.sender,
            'sender_name': self.sender_name,
            'received_time': self.received_time.isoformat() if self.received_time else None,
            'email_type': self.email_type,
            'source_platform': self.source_platform,
            'project_name': self.project_name,
            'bid_date': self.bid_date.isoformat() if self.bid_date else None,
            'attachments': self.attachments,
            'links': self.links,
            'confidence': self.confidence,
            'summary': self.summary,
            'html_path': self.html_path,
            'attachments_folder': self.attachments_folder
        }


class EmailMonitorReader:
    """Reads and parses Email Monitor output directory"""

    EMAIL_TYPES = ['bid_invite', 'deadline_reminder', 'addendum', 'rfi', 'project_update', 'other']
    PLATFORMS = ['planhub', 'building_connected', 'bluebook', 'smartbidnet', 'unknown']

    DEFAULT_PATH = os.getenv("EMAIL_MONITOR_PATH", "")

    # Known email category patterns
    EMAIL_CATEGORIES = {
        'addendum', 'reminder', 'site visit', 'pre-bid',
        'bid due', 'proposal deadline', 'delivery', 'invoice',
        'link to', 'window installation'
    }

    def __init__(self, monitor_path: str = None):
        """
        Initialize the email reader.

        Args:
            monitor_path: Path to Email Monitor output directory
        """
        self.monitor_path = Path(monitor_path or self.DEFAULT_PATH)
        self.bid_invites_path = self.monitor_path / "Bid Invites"
        self.in_progress_path = self.monitor_path / "In Progress"

    def _is_email_category(self, folder_name: str) -> bool:
        """
        Detect if folder is an email category vs. actual project.

        Returns:
            True if category, False if actual project
        """
        name_lower = folder_name.lower()

        # Pattern 1: Known category prefixes
        category_prefixes = [
            'addendum', 'reminder', 'site visit', 'pre-bid',
            'proposal deadline', 'bid due', 'delivery #',
            'invoice #', 'link to'
        ]
        for prefix in category_prefixes:
            if name_lower.startswith(prefix):
                return True

        # Pattern 2: Generic email types
        if any(cat in name_lower for cat in self.EMAIL_CATEGORIES):
            return True

        # Pattern 3: Has date prefix = actual project
        if re.match(r'^\d{4}-\d{2}-\d{2}_', folder_name):
            return False

        return False

    def _extract_project_name(self, folder: str, emails: List[EmailRecord]) -> str:
        """
        Extract clean project name from folder and emails.

        Handles:
        - Date prefixes: "2025-11-21_Project Name" → "Project Name"
        - Uses email classification for better names when available

        Args:
            folder: Folder name
            emails: List of emails from this folder

        Returns:
            Clean project name
        """
        # Remove date prefix if present
        clean_folder = re.sub(r'^\d{4}-\d{2}-\d{2}_', '', folder)

        # Try to get from email classification (most reliable)
        for email in sorted(emails, key=lambda e: e.confidence, reverse=True):
            if email.project_name and email.project_name != folder:
                return email.project_name

        return clean_folder

    def read_all_emails(self) -> List[EmailRecord]:
        """
        Read all email metadata from both Bid Invites and In Progress folders.

        Returns:
            List of EmailRecord objects
        """
        emails = []

        # Read Bid Invites
        if self.bid_invites_path.exists():
            for project_folder in self.bid_invites_path.iterdir():
                if not project_folder.is_dir() or project_folder.name.startswith('.'):
                    continue

                folder_emails = self._read_project_folder(project_folder, 'Bid Invites')
                emails.extend(folder_emails)

        # Read In Progress
        if self.in_progress_path.exists():
            for category_folder in self.in_progress_path.iterdir():
                if not category_folder.is_dir() or category_folder.name.startswith('.'):
                    continue

                # Check if this is a category folder or actual project
                if self._is_email_category(category_folder.name):
                    # THREE-LEVEL: Category/{Project}/{emails}
                    for project_folder in category_folder.iterdir():
                        if not project_folder.is_dir() or project_folder.name.startswith('.'):
                            continue

                        folder_emails = self._read_project_folder(
                            project_folder,
                            f'In Progress/{category_folder.name}'
                        )
                        emails.extend(folder_emails)
                else:
                    # TWO-LEVEL: {Project}/{emails} (no category)
                    folder_emails = self._read_project_folder(
                        category_folder,
                        'In Progress'
                    )
                    emails.extend(folder_emails)

        # Sort by received time (newest first)
        emails.sort(key=lambda e: e.received_time if e.received_time else datetime.min, reverse=True)

        return emails

    def _read_project_folder(self, project_folder: Path, category: str) -> List[EmailRecord]:
        """
        Read all emails from a single project folder.

        Args:
            project_folder: Path to project folder
            category: Category string (e.g., 'Bid Invites')

        Returns:
            List of EmailRecord objects from this folder
        """
        emails = []

        # Find all metadata JSON files recursively
        for metadata_file in project_folder.rglob('*_metadata.json'):
            email = self._parse_metadata(metadata_file, project_folder.name, category)
            if email:
                emails.append(email)

        return emails

    def _parse_metadata(self, metadata_path: Path, project_folder: str, category: str) -> Optional[EmailRecord]:
        """
        Parse a single email metadata JSON file.

        Args:
            metadata_path: Path to metadata JSON file
            project_folder: Name of the project folder
            category: Category string

        Returns:
            EmailRecord or None if parsing fails
        """
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            classification = data.get('classification', {})

            # Parse received time
            received_str = data.get('received_time', '')
            received_time = None
            if received_str:
                try:
                    received_time = datetime.fromisoformat(received_str.replace('Z', '+00:00'))
                except ValueError:
                    pass

            # Parse bid date
            bid_date_str = classification.get('bid_date')
            bid_date = None
            if bid_date_str:
                bid_date = self._parse_date(bid_date_str)

            # Generate unique ID from folder + filename (to avoid duplicates across projects)
            base_id = metadata_path.stem.replace('_metadata', '')
            # Create unique ID by hashing folder path + base ID
            folder_hash = hashlib.md5(project_folder.encode()).hexdigest()[:6]
            email_id = f"{base_id}_{folder_hash}"

            # Find HTML file and attachments folder
            email_dir = metadata_path.parent
            html_path = None
            attachments_folder = None

            # Look for HTML file (same name as metadata but .html) - use base_id not email_id
            html_file = email_dir / f"{base_id}.html"
            if html_file.exists():
                html_path = str(html_file)

            # Look for attachments folder
            att_folder = email_dir / "attachments"
            if att_folder.exists() and att_folder.is_dir():
                attachments_folder = str(att_folder)

            # Parse attachments - get filenames from the attachments array
            attachments = []
            raw_attachments = data.get('attachments', [])
            if isinstance(raw_attachments, list):
                for att in raw_attachments:
                    if isinstance(att, str):
                        attachments.append({'name': att})
                    elif isinstance(att, dict):
                        attachments.append(att)

            return EmailRecord(
                id=email_id,
                metadata_path=str(metadata_path),
                project_folder=project_folder,
                category=category,
                subject=data.get('subject', '(No Subject)'),
                sender=data.get('sender', ''),
                sender_name=data.get('sender_name', ''),
                received_time=received_time,
                email_type=classification.get('email_type', 'other'),
                source_platform=classification.get('source_platform', 'unknown'),
                project_name=classification.get('project_name', project_folder),
                bid_date=bid_date,
                attachments=attachments,
                links=classification.get('links', []),
                confidence=classification.get('confidence', 0.5),
                summary=classification.get('summary'),
                html_path=html_path,
                attachments_folder=attachments_folder
            )

        except Exception as e:
            print(f"Error parsing {metadata_path}: {e}")
            return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string in various formats.

        Args:
            date_str: Date string to parse

        Returns:
            datetime object or None if parsing fails
        """
        if not date_str:
            return None

        # Common formats to try
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%B %d, %Y",
            "%b %d, %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def get_emails_for_project_folder(self, folder_name: str) -> List[EmailRecord]:
        """
        Get all emails associated with a specific project folder.

        Args:
            folder_name: Project folder name to filter by

        Returns:
            List of EmailRecord objects matching the folder
        """
        all_emails = self.read_all_emails()
        return [e for e in all_emails if e.project_folder == folder_name]

    def get_recent_emails(self, days: int = 7) -> List[EmailRecord]:
        """
        Get emails from the last N days.

        Args:
            days: Number of days to look back

        Returns:
            List of EmailRecord objects from the specified period
        """
        cutoff = datetime.now() - timedelta(days=days)
        all_emails = self.read_all_emails()
        return [e for e in all_emails if e.received_time and e.received_time >= cutoff]

    def get_emails_by_type(self, email_type: str) -> List[EmailRecord]:
        """
        Get all emails of a specific type.

        Args:
            email_type: Type to filter by (bid_invite, addendum, etc.)

        Returns:
            List of matching EmailRecord objects
        """
        all_emails = self.read_all_emails()
        return [e for e in all_emails if e.email_type == email_type]

    def get_emails_by_platform(self, platform: str) -> List[EmailRecord]:
        """
        Get all emails from a specific platform.

        Args:
            platform: Platform to filter by (planhub, buildingconnected, etc.)

        Returns:
            List of matching EmailRecord objects
        """
        all_emails = self.read_all_emails()
        return [e for e in all_emails if e.source_platform == platform]

    def get_project_folders(self) -> List[str]:
        """
        Get list of all unique project folder names.

        Returns:
            List of project folder names
        """
        all_emails = self.read_all_emails()
        folders = set(e.project_folder for e in all_emails)
        return sorted(folders)

    def _normalize_project_name(self, title: str) -> str:
        """
        Normalize a project name for deduplication matching.

        Strips common prefixes like "Addendum", "Request for", etc.
        and normalizes whitespace/punctuation.
        """
        if not title:
            return ''
        # Remove common prefixes (repeat to catch multiple)
        for _ in range(3):  # Up to 3 prefixes
            title = re.sub(r'^(Addendum\s*\d*\s*[-:]?\s*|Request for\s*(budgeting|bid)[\s:]*|BLDG\s*\d*\s*[-:]?\s*|Sheet\s*[A-Z0-9.]+\s*[-:]?\s*|Reminder to Bid\s*[-:]?\s*)', '', title, flags=re.I)
        # Remove trailing project/invitation words
        title = re.sub(r'\s+(Project|Invitation to Bid|Request for Bid)$', '', title, flags=re.I)
        # Remove GC names in parentheses at end
        title = re.sub(r'\s*\([^)]*(?:Construction|Contracting|Builders|Inc|LLC|Corp|Partners)[^)]*\)\s*$', '', title, flags=re.I)
        # Remove store numbers like #4025
        title = re.sub(r'\s*#\d+\s*', ' ', title)
        # Normalize common abbreviations
        title = re.sub(r'\bPkwy\.?\b', 'Parkway', title, flags=re.I)
        title = re.sub(r'\bSt\.?\b', 'Street', title, flags=re.I)
        title = re.sub(r'\bAve\.?\b', 'Avenue', title, flags=re.I)
        title = re.sub(r'\bRd\.?\b', 'Road', title, flags=re.I)
        title = re.sub(r'\bDr\.?\b', 'Drive', title, flags=re.I)
        title = re.sub(r'\bBlvd\.?\b', 'Boulevard', title, flags=re.I)
        # Remove window delivery dates like "Window Delivery 11/11"
        title = re.sub(r'\s*[-:]?\s*Window Delivery\s*\d+/\d+', '', title, flags=re.I)
        # Normalize punctuation and whitespace
        title = re.sub(r'[^\w\s]', ' ', title)
        title = ' '.join(title.lower().split())
        return title[:80]  # First 80 chars for matching (increased to reduce false merges)

    def get_email_projects(self) -> List[Dict]:
        """
        Aggregate emails into project entries for dashboard display.

        Groups emails by project_folder, extracts project metadata,
        and normalizes to the standard project format used by the tracker.
        Also deduplicates similar projects.

        Returns:
            List of normalized project dicts with source='email_monitor'
        """
        all_emails = self.read_all_emails()

        # Group emails by project folder
        projects_by_folder = {}
        for email in all_emails:
            folder = email.project_folder
            if folder not in projects_by_folder:
                projects_by_folder[folder] = []
            projects_by_folder[folder].append(email)

        # Create initial projects
        initial_projects = []
        for folder, emails in projects_by_folder.items():
            project = self._aggregate_project_from_emails(folder, emails)
            if project:
                initial_projects.append(project)

        # Deduplicate by normalized project name
        projects_by_normalized = {}
        for project in initial_projects:
            title = project.get('title', '')
            normalized = self._normalize_project_name(title)

            if not normalized or len(normalized) < 5:
                # Skip very short/empty names, keep as is
                if project['id'] not in [p['id'] for p in projects_by_normalized.values()]:
                    projects_by_normalized[project['id']] = project
                continue

            if normalized in projects_by_normalized:
                # Merge with existing project
                existing = projects_by_normalized[normalized]
                # Keep the one with more emails, or the one with a bid date
                if (project.get('email_count', 0) > existing.get('email_count', 0) or
                    (project.get('bid_date') and not existing.get('bid_date'))):
                    # Use this project but merge email counts
                    project['email_count'] = project.get('email_count', 0) + existing.get('email_count', 0)
                    project['merged_folders'] = existing.get('merged_folders', [existing.get('folder')]) + [project.get('folder')]
                    projects_by_normalized[normalized] = project
                else:
                    # Keep existing but update counts
                    existing['email_count'] = existing.get('email_count', 0) + project.get('email_count', 0)
                    existing['merged_folders'] = existing.get('merged_folders', [existing.get('folder')]) + [project.get('folder')]
            else:
                projects_by_normalized[normalized] = project

        return list(projects_by_normalized.values())

    def _aggregate_project_from_emails(self, folder: str, emails: List[EmailRecord]) -> Optional[Dict]:
        """
        Create a normalized project dict from aggregated emails.

        Uses most recent email for latest bid date, extracts location,
        categorizes by email types present.

        Args:
            folder: Project folder name
            emails: List of EmailRecord objects for this folder

        Returns:
            Normalized project dict or None if no emails
        """
        if not emails:
            return None

        # Sort by received time (newest first)
        emails.sort(key=lambda e: e.received_time if e.received_time else datetime.min, reverse=True)
        newest = emails[0]

        # Extract best project name (from classification or folder)
        project_name = self._extract_project_name(folder, emails)

        # Extract location from folder or emails
        city, state = self._extract_location(folder, emails)

        # Get most recent bid date
        bid_date = None
        for e in emails:
            if e.bid_date:
                bid_date = e.bid_date.strftime('%Y-%m-%d')
                break

        # Collect email types and platforms
        email_types = list(set(e.email_type for e in emails))
        platforms = list(set(e.source_platform for e in emails if e.source_platform != 'unknown'))

        # Determine status based on email types present
        has_bid_invite = 'bid_invite' in email_types
        has_addendum = 'addendum' in email_types
        has_shipping = 'shipping_notification' in email_types
        has_invoice = 'invoice' in email_types
        has_award = 'award_notification' in email_types

        # Infer project status from email types
        if has_shipping or has_invoice or has_award:
            inferred_status = 'awarded'
        elif has_addendum or 'rfi' in email_types or 'site_visit' in email_types:
            inferred_status = 'in_progress'
        elif has_bid_invite:
            inferred_status = 'upcoming'
        else:
            inferred_status = 'unknown'

        # Determine category (Bid Invites vs In Progress)
        categories = set(e.category for e in emails)
        primary_category = 'In Progress' if any('In Progress' in c for c in categories) else 'Bid Invites'

        # Generate project ID
        project_id = f"email-{self._normalize_id(folder)}"

        # Count attachments
        total_attachments = sum(len(e.attachments) for e in emails)

        # Extract contractor/GC information
        gc_info = self._extract_contractor_info(emails)

        return {
            "source": "email_monitor",
            "id": project_id,
            "title": project_name,
            "folder": folder,
            "email_folder": folder,
            "location": {
                "city": city,
                "state": state
            },
            "bid_date": bid_date,
            "email_status": inferred_status,
            "email_category": primary_category,
            "email_count": len(emails),
            "email_types": email_types,
            "platforms": platforms if platforms else ['unknown'],
            "latest_email": newest.received_time.isoformat() if newest.received_time else None,
            "oldest_email": emails[-1].received_time.isoformat() if emails[-1].received_time else None,
            "has_bid_invite": has_bid_invite,
            "has_addendum": has_addendum,
            "attachments_count": total_attachments,
            "loaded_at": datetime.now().isoformat(),
            # Contractor/GC information
            "gc_company": gc_info['gc_company'],
            "gc_contacts": gc_info['gc_contacts'],
            "gc_email_count": gc_info['gc_email_count'],
            "is_direct_email": gc_info['is_direct_email'],
            "direct_email_count": gc_info['direct_email_count'],
            "gc_companies": gc_info['gc_companies']  # ALL contractors for this project
        }

    def _extract_location(self, folder: str, emails: List[EmailRecord]) -> Tuple[str, str]:
        """
        Extract city and state from folder name or email content.

        Common patterns:
        - "Project Name - City, State"
        - "Project Name City STATE"
        - "Project Name (City, STATE)"

        Args:
            folder: Project folder name
            emails: List of emails to search

        Returns:
            Tuple of (city, state) or ('', '') if not found
        """
        # Patterns to try
        patterns = [
            r'[-_]\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s*$',  # "- City, MA"
            r'([A-Za-z\s]+),\s*([A-Z]{2})(?:\s|$)',       # "City, MA"
            r'\(([A-Za-z\s]+),?\s*([A-Z]{2})\)',          # "(City, MA)"
        ]

        # Try folder name first
        for pattern in patterns:
            match = re.search(pattern, folder)
            if match:
                return match.group(1).strip(), match.group(2)

        # Try project names from emails
        for email in emails:
            if email.project_name:
                for pattern in patterns:
                    match = re.search(pattern, email.project_name)
                    if match:
                        return match.group(1).strip(), match.group(2)

        return '', ''

    def _normalize_id(self, name: str) -> str:
        """
        Normalize name to ID format (lowercase, hyphenated).

        Args:
            name: Name to normalize

        Returns:
            Normalized ID string
        """
        normalized = name.lower()
        normalized = re.sub(r'[^a-z0-9\s-]', '', normalized)
        normalized = re.sub(r'\s+', '-', normalized)
        normalized = re.sub(r'-+', '-', normalized)
        return normalized[:50].strip('-')

    # Platform domains for detecting direct vs platform emails
    PLATFORM_DOMAINS = [
        'buildingconnected.com',
        'planhub.com',
        'smartbidnet.com',
        'thebluebook.com',
        'bbbid.thebluebook.com',
        'procore.com'
    ]

    # Vendor domains to exclude from GC detection (these are suppliers, not contractors)
    VENDOR_DOMAINS = [
        'tmiwindows.com',
        # Add other vendor domains as needed
    ]

    def _extract_contractor_info(self, emails: List[EmailRecord]) -> Dict:
        """
        Extract contractor (GC) information from emails.

        Parses sender_name format "Name (Company Name)" and identifies
        direct emails vs platform-forwarded emails.

        Args:
            emails: List of EmailRecord objects for a project

        Returns:
            Dict with gc_company, gc_contacts, is_direct_email, gc_email_count
        """
        companies = {}
        contacts_by_company = {}
        direct_count = 0
        direct_companies = set()

        for email in emails:
            # Check if direct email (not from platform)
            is_direct = True
            sender_domain = email.sender.split('@')[-1] if '@' in email.sender else ''
            for platform in self.PLATFORM_DOMAINS:
                if platform in sender_domain:
                    is_direct = False
                    break

            # Skip vendor domains (these are suppliers, not contractors)
            is_vendor = any(vendor in sender_domain for vendor in self.VENDOR_DOMAINS)
            if is_vendor:
                continue

            # Extract company from sender_name "(Company Name)"
            company = None
            contact = None
            if email.sender_name and '(' in email.sender_name:
                match = re.search(r'\(([^)]+)\)', email.sender_name)
                if match:
                    company = match.group(1).strip()
                    contact = email.sender_name.split('(')[0].strip()

            # For direct emails, use the domain as company identifier
            if is_direct and not company:
                company = sender_domain
                contact = email.sender_name or email.sender

            if company:
                companies[company] = companies.get(company, 0) + 1
                if company not in contacts_by_company:
                    contacts_by_company[company] = set()
                if contact:
                    contacts_by_company[company].add(contact)

            if is_direct:
                direct_count += 1
                if company:
                    direct_companies.add(company)

        # Build list of ALL contractors sorted by email count
        gc_companies = []
        for company, count in sorted(companies.items(), key=lambda x: -x[1]):
            gc_companies.append({
                'company': company,
                'contacts': list(contacts_by_company.get(company, []))[:5],
                'email_count': count,
                'is_direct': company in direct_companies
            })

        # Also keep single gc_company for backwards compatibility
        gc_company = None
        gc_contacts = []
        gc_email_count = 0
        if companies:
            gc_company = max(companies, key=companies.get)
            gc_email_count = companies[gc_company]
            gc_contacts = list(contacts_by_company.get(gc_company, []))[:5]

        return {
            'gc_company': gc_company,
            'gc_contacts': gc_contacts,
            'gc_email_count': gc_email_count,
            'is_direct_email': direct_count > 0,
            'direct_email_count': direct_count,
            'direct_companies': list(direct_companies),
            'gc_companies': gc_companies  # ALL contractors for this project
        }

    def get_stats(self) -> Dict:
        """
        Get statistics about the email collection.

        Returns:
            Dict with counts by type, platform, etc.
        """
        all_emails = self.read_all_emails()

        # Count by type
        by_type = {}
        for email in all_emails:
            by_type[email.email_type] = by_type.get(email.email_type, 0) + 1

        # Count by platform
        by_platform = {}
        for email in all_emails:
            by_platform[email.source_platform] = by_platform.get(email.source_platform, 0) + 1

        # Count by category
        by_category = {}
        for email in all_emails:
            by_category[email.category] = by_category.get(email.category, 0) + 1

        # Count unique projects
        unique_projects = len(set(e.project_folder for e in all_emails))

        return {
            'total_emails': len(all_emails),
            'unique_projects': unique_projects,
            'by_type': by_type,
            'by_platform': by_platform,
            'by_category': by_category
        }


# Example usage
if __name__ == "__main__":
    reader = EmailMonitorReader()
    stats = reader.get_stats()
    print(f"Total emails: {stats['total_emails']}")
    print(f"Unique projects: {stats['unique_projects']}")
    print(f"\nBy type:")
    for t, count in stats['by_type'].items():
        print(f"  {t}: {count}")
    print(f"\nBy platform:")
    for p, count in stats['by_platform'].items():
        print(f"  {p}: {count}")
