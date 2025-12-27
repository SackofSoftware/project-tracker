"""
Gov Leads Reader

Reads from the GovWin SQLite database.
Configure database path via GOV_DB_PATH environment variable.

Schema:
- projects: id, opportunity_id, url, entity_type, title, status, state,
           organization, estimated_value, response_date, overview_json, contact_json
- documents: linked documents for each project
"""

import sqlite3
import json
import re
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

# Import unified schema
from modules.schema.unified_project import (
    UnifiedProject,
    Location,
    Document,
    Division8Scope,
    normalize_date,
    normalize_project_value
)


def parse_govwin_location(location_str: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse GovWin location string to extract city, state, and zip.

    Format examples:
    - "Boston, MA 02201; Suffolk County, MA"
    - "Melrose, MA 02176; Middlesex County, MA"
    - "Franklin County, MA; Greenfield, MA 01301; Leyden, MA"

    Returns:
        Tuple of (city, state_abbr, zip_code)
    """
    if not location_str:
        return None, None, None

    city = None
    state = None
    zip_code = None

    # Split by semicolon to get main location vs county
    parts = [p.strip() for p in location_str.split(';')]

    # First pass: find the part with a zip code (highest priority)
    city_with_zip = None
    for part in parts:
        zip_match = re.search(r'\b(\d{5})\b', part)
        if zip_match and ',' in part:
            zip_code = zip_match.group(1)
            # Extract city from this part
            city_with_zip = part.split(',')[0].strip()
            # Extract state from this part
            state_match = re.search(r'\b([A-Z]{2})\b', part)
            if state_match:
                state = state_match.group(1)
            break  # Use the first one with zip code

    # If we found a city with zip, use it
    if city_with_zip:
        city = city_with_zip
    else:
        # Second pass: find any city (not a county)
        for part in parts:
            if ',' in part:
                city_candidate = part.split(',')[0].strip()
                # Skip if it's a county name
                if not city_candidate.lower().endswith('county'):
                    city = city_candidate
                    # Try to get state from this part
                    state_match = re.search(r'\b([A-Z]{2})\b', part)
                    if state_match:
                        state = state_match.group(1)
                    break

    # Final fallback: try to get state from anywhere if still None
    if not state:
        for part in parts:
            state_match = re.search(r'\b([A-Z]{2})\b', part)
            if state_match:
                state = state_match.group(1)
                break

    return city, state, zip_code


@dataclass
class GovDocument:
    """Document attached to a gov lead"""
    id: int
    doc_id: str
    title: str
    doc_type: str
    file_size: str
    posting_date: str
    status: str
    local_path: Optional[str]

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'doc_id': self.doc_id,
            'title': self.title,
            'doc_type': self.doc_type,
            'file_size': self.file_size,
            'posting_date': self.posting_date,
            'status': self.status,
            'local_path': self.local_path
        }


@dataclass
class GovLeadRecord:
    """Parsed government lead/bid record"""
    id: int
    opportunity_id: str
    url: str
    entity_type: str  # 'BID' or 'LEAD'
    title: str
    status: str
    state: str
    organization: str
    estimated_value: Optional[float]
    estimated_value_str: str
    response_date: Optional[datetime]
    response_date_str: str
    solicitation_date: Optional[datetime]
    solicitation_date_str: str
    description: str

    # Parsed from JSON fields
    overview: Dict = field(default_factory=dict)
    contact: Dict = field(default_factory=dict)

    # Documents
    documents: List[GovDocument] = field(default_factory=list)

    # Computed
    is_active: bool = False
    days_until_response: Optional[int] = None

    # Additional parsed fields from overview
    place_of_performance: str = ""
    vertical: str = ""
    primary_requirement: str = ""
    fiscal_years: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'opportunity_id': self.opportunity_id,
            'url': self.url,
            'entity_type': self.entity_type,
            'title': self.title,
            'status': self.status,
            'state': self.state,
            'organization': self.organization,
            'estimated_value': self.estimated_value,
            'estimated_value_str': self.estimated_value_str,
            'response_date': self.response_date.isoformat() if self.response_date else None,
            'response_date_str': self.response_date_str,
            'solicitation_date': self.solicitation_date.isoformat() if self.solicitation_date else None,
            'solicitation_date_str': self.solicitation_date_str,
            'description': self.description,
            'overview': self.overview,
            'contact': self.contact,
            'documents': [d.to_dict() for d in self.documents],
            'is_active': self.is_active,
            'days_until_response': self.days_until_response,
            'place_of_performance': self.place_of_performance,
            'vertical': self.vertical,
            'primary_requirement': self.primary_requirement,
            'fiscal_years': self.fiscal_years,
            'has_documents': len(self.documents) > 0,
            'document_count': len(self.documents)
        }


class GovLeadsReader:
    """Reader for GovWin SQLite database"""

    @staticmethod
    def _get_default_db_path() -> str:
        """Get database path from environment"""
        is_mac = sys.platform == "darwin"

        if is_mac:
            path = os.getenv('GOV_DB_PATH_MAC') or os.getenv('GOV_DB_PATH', '')
        else:
            path = os.getenv('GOV_DB_PATH', '')

        if not path:
            raise ValueError("GOV_DB_PATH environment variable not set. Copy .env.example to .env and configure.")
        return path

    def __init__(self, db_path: str = None):
        """
        Initialize the reader.

        Args:
            db_path: Path to govwin.db (defaults to standard location)
        """
        self.db_path = db_path or self._get_default_db_path()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        return sqlite3.connect(self.db_path)

    def _parse_value(self, value_str: str) -> Optional[float]:
        """
        Parse estimated value from various string formats.

        Args:
            value_str: Value string (e.g., "$3,440", "3440000.0", "$19,025K")

        Returns:
            Float value in dollars or None
        """
        if not value_str:
            return None

        try:
            # Remove $ and commas
            clean = value_str.replace('$', '').replace(',', '').strip()

            # Handle K suffix (thousands)
            if clean.upper().endswith('K'):
                clean = clean[:-1]
                multiplier = 1000
            else:
                multiplier = 1

            return float(clean) * multiplier
        except (ValueError, TypeError):
            return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date from various formats.

        Args:
            date_str: Date string (e.g., "01/07/2026 02:00 PM (in 25 days)")

        Returns:
            datetime object or None
        """
        if not date_str:
            return None

        # Extract just the date part
        date_part = date_str.split('(')[0].strip()

        formats = [
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_part, fmt)
            except ValueError:
                continue

        # Try extracting month/year for estimates like "01/2026 (Deltek Estimate)"
        match = re.match(r'(\d{2})/(\d{4})', date_str)
        if match:
            try:
                return datetime(int(match.group(2)), int(match.group(1)), 1)
            except (ValueError, TypeError):
                pass

        return None

    def _parse_row(self, row: Dict) -> Optional[GovLeadRecord]:
        """
        Parse a database row into a GovLeadRecord.

        Args:
            row: Database row as dict

        Returns:
            GovLeadRecord or None if parsing fails
        """
        try:
            # Parse JSON fields
            overview = {}
            contact = {}

            try:
                overview_raw = row.get('overview_json') or '{}'
                overview = json.loads(overview_raw) if isinstance(overview_raw, str) else {}
            except json.JSONDecodeError:
                pass

            try:
                contact_raw = row.get('contact_json') or '{}'
                contact = json.loads(contact_raw) if isinstance(contact_raw, str) else {}
            except json.JSONDecodeError:
                pass

            # Parse estimated value (prefer overview_json, fallback to database field)
            value_str = overview.get('Value (USD-$K)', '') or row.get('estimated_value', '') or ''
            estimated_value = self._parse_value(value_str)

            # Parse response date (prefer overview_json, fallback to database field)
            response_str = overview.get('Response Date', '') or row.get('response_date', '') or ''
            response_date = self._parse_date(response_str)

            # Parse solicitation date (prefer overview_json, fallback to database field)
            solicitation_str = overview.get('Solicitation Date', '') or row.get('solicitation_date', '') or ''
            solicitation_date = self._parse_date(solicitation_str)

            # Calculate days until response
            days_until = None
            is_active = False
            if response_date:
                delta = (response_date.date() - datetime.now().date()).days
                if delta >= 0:
                    days_until = delta
                    is_active = True

            # Extract additional fields from overview
            place_of_performance = overview.get('Place of Performance', '')
            vertical = overview.get('Vertical', '')
            primary_requirement = overview.get('Primary Requirement', '')
            fiscal_years = overview.get('Lead Alert Year(s)', '')

            return GovLeadRecord(
                id=row['id'],
                opportunity_id=row.get('opportunity_id', ''),
                url=row.get('url', ''),
                entity_type=row.get('entity_type', 'LEAD'),
                title=row.get('title', ''),
                status=row.get('status', ''),
                state=row.get('state', ''),
                organization=row.get('organization', ''),
                estimated_value=estimated_value,
                estimated_value_str=value_str,
                response_date=response_date,
                response_date_str=response_str,
                solicitation_date=solicitation_date,
                solicitation_date_str=solicitation_str,
                description=row.get('description', ''),
                overview=overview,
                contact=contact,
                is_active=is_active,
                days_until_response=days_until,
                place_of_performance=place_of_performance,
                vertical=vertical,
                primary_requirement=primary_requirement,
                fiscal_years=fiscal_years
            )

        except Exception as e:
            print(f"Error parsing row {row.get('id')}: {e}")
            return None

    def _load_documents(self, conn: sqlite3.Connection, project_id: int, only_downloaded: bool = True) -> List[GovDocument]:
        """Load documents for a project.

        Args:
            conn: Database connection
            project_id: Project ID to load documents for
            only_downloaded: If True, only return documents that have files on disk
        """
        cursor = conn.execute("""
            SELECT id, doc_id, doc_title, doc_type, file_size, posting_date,
                   download_status, local_path
            FROM documents
            WHERE project_id = ?
        """, (project_id,))

        # Downloads folder path
        gov_downloads = os.getenv("GOV_DOWNLOADS_PATH", "")
        if not gov_downloads:
            return []  # No downloads path configured
        downloads_path = Path(gov_downloads)
        lead_folder = downloads_path / str(project_id)

        documents = []
        seen_doc_ids = set()  # Track seen doc_ids to avoid duplicates

        for row in cursor:
            doc_id = row[1] or ''

            # Skip duplicates
            if doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)

            # Check if file exists on disk
            has_file = False
            if lead_folder.exists() and doc_id:
                matches = list(lead_folder.glob(f"{doc_id}_*.pdf"))
                has_file = len(matches) > 0

            # Skip if we only want downloaded and file doesn't exist
            if only_downloaded and not has_file:
                continue

            documents.append(GovDocument(
                id=row[0],
                doc_id=doc_id,
                title=row[2] or '',
                doc_type=row[3] or '',
                file_size=row[4] or '',
                posting_date=row[5] or '',
                status='downloaded' if has_file else (row[6] or ''),
                local_path=row[7]
            ))
        return documents

    def read_all_leads(self, include_documents: bool = False) -> List[GovLeadRecord]:
        """
        Read all records from govwin.db.

        Args:
            include_documents: If True, load documents for each lead (slower)

        Returns:
            List of GovLeadRecord objects
        """
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT id, opportunity_id, url, entity_type, title, status, state,
                   organization, estimated_value, response_date, solicitation_date,
                   description, overview_json, contact_json
            FROM projects
            ORDER BY response_date ASC
        """)

        records = []
        for row in cursor:
            record = self._parse_row(dict(row))
            if record:
                if include_documents:
                    record.documents = self._load_documents(conn, record.id)
                records.append(record)

        conn.close()
        return records

    def get_active_bids(self) -> List[GovLeadRecord]:
        """
        Get BID records with future response dates.

        Returns:
            List of active BID records
        """
        all_leads = self.read_all_leads()
        return [
            r for r in all_leads
            if r.entity_type == 'BID' and r.is_active
        ]

    def get_leads_forecast(self) -> List[GovLeadRecord]:
        """
        Get LEAD records (forecasted CIP opportunities).

        Returns:
            List of LEAD records
        """
        return [r for r in self.read_all_leads() if r.entity_type == 'LEAD']

    def get_bids(self) -> List[GovLeadRecord]:
        """
        Get all BID records.

        Returns:
            List of BID records
        """
        return [r for r in self.read_all_leads() if r.entity_type == 'BID']

    def search(
        self,
        query: str,
        state: str = None,
        entity_type: str = None,
        limit: int = 100
    ) -> List[GovLeadRecord]:
        """
        Search leads by title, organization, or description.

        Args:
            query: Search query string
            state: Optional state filter
            entity_type: Optional entity type filter ('BID' or 'LEAD')
            limit: Maximum results to return

        Returns:
            List of matching GovLeadRecord objects
        """
        all_leads = self.read_all_leads()
        results = []
        query_lower = query.lower()

        for lead in all_leads:
            if state and lead.state != state:
                continue
            if entity_type and lead.entity_type != entity_type:
                continue

            # Search in title, organization, description
            if (query_lower in lead.title.lower() or
                query_lower in lead.organization.lower() or
                query_lower in (lead.description or '').lower()):
                results.append(lead)

            if len(results) >= limit:
                break

        return results

    def get_by_state(self, state: str) -> List[GovLeadRecord]:
        """
        Get all leads for a specific state.

        Args:
            state: State code (e.g., 'MA', 'NH')

        Returns:
            List of GovLeadRecord objects for that state
        """
        return [r for r in self.read_all_leads() if r.state == state]

    def get_by_id(self, lead_id: int) -> Optional[GovLeadRecord]:
        """
        Get a single lead by ID.

        Args:
            lead_id: Database ID

        Returns:
            GovLeadRecord or None
        """
        leads = [r for r in self.read_all_leads() if r.id == lead_id]
        return leads[0] if leads else None

    def get_by_opportunity_id(self, opportunity_id: str) -> Optional[GovLeadRecord]:
        """
        Get a single lead by opportunity ID.

        Args:
            opportunity_id: External opportunity ID

        Returns:
            GovLeadRecord or None
        """
        leads = [r for r in self.read_all_leads() if r.opportunity_id == opportunity_id]
        return leads[0] if leads else None

    def get_states(self) -> List[str]:
        """
        Get list of all states with leads.

        Returns:
            Sorted list of state codes
        """
        all_leads = self.read_all_leads()
        states = set(r.state for r in all_leads if r.state)
        return sorted(states)

    def get_organizations(self, limit: int = 50) -> List[Tuple[str, int]]:
        """
        Get top organizations by lead count.

        Args:
            limit: Maximum number to return

        Returns:
            List of (organization, count) tuples
        """
        all_leads = self.read_all_leads()
        org_counts = {}

        for lead in all_leads:
            org = lead.organization or 'Unknown'
            org_counts[org] = org_counts.get(org, 0) + 1

        # Sort by count descending
        sorted_orgs = sorted(org_counts.items(), key=lambda x: x[1], reverse=True)
        return sorted_orgs[:limit]

    def get_stats(self) -> Dict:
        """
        Get summary statistics.

        Returns:
            Dict with various counts and breakdowns
        """
        all_leads = self.read_all_leads()

        # Count by entity type
        bids = [r for r in all_leads if r.entity_type == 'BID']
        leads = [r for r in all_leads if r.entity_type == 'LEAD']

        # Count active bids
        active_bids = [r for r in bids if r.is_active]

        # Count by state
        by_state = {}
        for lead in all_leads:
            state = lead.state or 'Unknown'
            by_state[state] = by_state.get(state, 0) + 1

        # Sort by count
        by_state = dict(sorted(by_state.items(), key=lambda x: x[1], reverse=True))

        # Total estimated value
        total_value = sum(r.estimated_value or 0 for r in all_leads)
        bid_value = sum(r.estimated_value or 0 for r in bids)
        lead_value = sum(r.estimated_value or 0 for r in leads)

        return {
            'total_records': len(all_leads),
            'bids': len(bids),
            'leads': len(leads),
            'active_bids': len(active_bids),
            'by_state': by_state,
            'total_estimated_value': total_value,
            'bid_estimated_value': bid_value,
            'lead_estimated_value': lead_value,
            'states': self.get_states(),
            'top_organizations': self.get_organizations(10)
        }

    def normalize_to_unified_project(self, record: GovLeadRecord) -> UnifiedProject:
        """
        Normalize a GovLeadRecord to UnifiedProject.

        Args:
            record: GovLeadRecord to normalize

        Returns:
            UnifiedProject instance
        """
        # Parse location from place_of_performance string
        city, state_abbr, zip_code = parse_govwin_location(record.place_of_performance)
        location = Location(
            state=state_abbr or record.state or None,
            city=city,
            zip=zip_code,
            address=record.place_of_performance or None,
            raw=record.place_of_performance or None
        )

        # Parse dates (use .date().isoformat() to get YYYY-MM-DD format)
        response_date_iso = normalize_date(record.response_date.date().isoformat() if record.response_date else None)
        solicitation_date_iso = normalize_date(record.solicitation_date.date().isoformat() if record.solicitation_date else None)

        # Parse project value
        project_value_float, project_value_str = normalize_project_value(record.estimated_value_str)

        # Convert documents to unified format
        documents = []
        for doc in record.documents:
            documents.append(Document(
                id=doc.doc_id,
                title=doc.title,
                type=doc.doc_type.lower() if doc.doc_type else "unknown",
                url=None,
                local_path=doc.local_path,
                file_size=None,
                downloaded=doc.status == "downloaded",
                upload_date=doc.posting_date,
                metadata={"posting_date": doc.posting_date, "file_size_str": doc.file_size}
            ))

        # Determine if Division 8 based on description and primary requirement
        description_lower = (record.description or "").lower()
        primary_req_lower = record.primary_requirement.lower()
        is_division_8 = any(keyword in description_lower or keyword in primary_req_lower for keyword in [
            "door", "window", "glass", "glazing", "storefront", "entrance", "hardware",
            "curtain wall", "skylight", "openings"
        ])

        # Build tags
        tags = ["Government"]
        if record.entity_type == "BID":
            tags.append("BID")
        elif record.entity_type == "LEAD":
            tags.append("LEAD")
        if record.vertical:
            tags.append(record.vertical)
        if is_division_8:
            tags.append("Division 8")

        # Create unified project
        unified = UnifiedProject(
            # Identity
            id=f"govwin-{record.opportunity_id}",
            source="govwin",
            source_id=record.opportunity_id,
            url=record.url,

            # Basic Info
            title=record.title,
            description=record.description,

            # Location
            location=location,

            # Dates
            response_date=response_date_iso,
            solicitation_date=solicitation_date_iso,

            # Project Details
            owner=record.organization,
            project_value=project_value_float,
            project_value_str=project_value_str or record.estimated_value_str,

            # Classification
            sector=record.vertical or None,
            entity_type=record.entity_type,
            tags=tags,

            # Division 8
            is_division_8=is_division_8,
            division_8=Division8Scope(),

            # Documents
            documents=documents,

            # GovWin-specific flags
            is_active=record.is_active,

            # Metadata
            last_sync=datetime.now().isoformat()
        )

        return unified


# Example usage
if __name__ == "__main__":
    reader = GovLeadsReader()
    stats = reader.get_stats()

    print(f"Total records: {stats['total_records']}")
    print(f"BIDs: {stats['bids']}")
    print(f"LEADs: {stats['leads']}")
    print(f"Active BIDs: {stats['active_bids']}")
    print(f"\nBy state:")
    for state, count in list(stats['by_state'].items())[:5]:
        print(f"  {state}: {count}")
