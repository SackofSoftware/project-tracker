"""
PlanHub Database Reader
Reads project data directly from planhub.db SQLite database
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# Import unified schema
from modules.schema.unified_project import (
    UnifiedProject,
    Location,
    Document,
    Division8Scope,
    normalize_date,
    normalize_project_value
)


class PlanHubDatabaseReader:
    """Read and normalize PlanHub project data from SQLite database"""

    def __init__(self, db_path: str = None):
        """Initialize with database path from env or config"""
        if db_path:
            self.db_path = Path(db_path)
        else:
            # Get from environment variable with platform awareness
            is_mac = sys.platform == "darwin"
            if is_mac:
                db_path_env = os.getenv('PLANHUB_DB_PATH_MAC') or os.getenv('PLANHUB_DB_PATH', '')
            else:
                db_path_env = os.getenv('PLANHUB_DB_PATH', '')

            if not db_path_env:
                raise ValueError("PLANHUB_DB_PATH environment variable not set. Copy .env.example to .env and configure.")
            self.db_path = Path(db_path_env)

        if not self.db_path.exists():
            raise FileNotFoundError(f"PlanHub database not found: {self.db_path}")

    def get_all_leads(self, status_filter: List[str] = None) -> List[UnifiedProject]:
        """
        Query all leads from database.

        Args:
            status_filter: Optional list like ['done', 'queued'] to filter by status

        Returns:
            List of UnifiedProject instances
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # Build query with optional status filter
            query = """
                SELECT
                    leads.*,
                    COUNT(pf.id) as file_count
                FROM leads
                LEFT JOIN project_files pf ON leads.id = pf.lead_id
            """

            params = []
            if status_filter:
                placeholders = ','.join('?' * len(status_filter))
                query += f" WHERE leads.status IN ({placeholders})"
                params.extend(status_filter)

            query += " GROUP BY leads.id ORDER BY leads.last_seen_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            projects = []
            for row in rows:
                project = self.normalize_lead_to_project(dict(row))
                if project:
                    projects.append(project)

            return projects

        finally:
            conn.close()

    def get_lead_by_id(self, planhub_id: str) -> Optional[UnifiedProject]:
        """Get single lead by planhub_id"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    leads.*,
                    COUNT(pf.id) as file_count
                FROM leads
                LEFT JOIN project_files pf ON leads.id = pf.lead_id
                WHERE leads.planhub_id = ?
                GROUP BY leads.id
            """, (planhub_id,))

            row = cursor.fetchone()
            if row:
                return self.normalize_lead_to_project(dict(row))
            return None

        finally:
            conn.close()

    def get_scraper_stats(self) -> Dict:
        """
        Get scraper statistics for dashboard display.

        Returns:
            {
                'total_leads': int,
                'queued': int,
                'done': int,
                'skipped': int,
                'locked': int,
                'errors': int,
                'last_discovery': datetime,
                'discovery_complete': bool
            }
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # Get lead counts by status
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) as queued,
                    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done,
                    SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) as skipped,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                    SUM(CASE WHEN skip_reason = 'locked' THEN 1 ELSE 0 END) as locked,
                    MAX(last_seen_at) as last_seen
                FROM leads
            """)

            stats_row = cursor.fetchone()

            # Get pagination state
            cursor.execute("""
                SELECT
                    last_page,
                    total_leads_found,
                    discovery_complete,
                    last_updated
                FROM pagination_state
                WHERE id = 1
            """)

            pagination_row = cursor.fetchone()

            return {
                'total_leads': stats_row['total'] or 0,
                'queued': stats_row['queued'] or 0,
                'done': stats_row['done'] or 0,
                'skipped': stats_row['skipped'] or 0,
                'locked': stats_row['locked'] or 0,
                'errors': stats_row['errors'] or 0,
                'last_seen': stats_row['last_seen'],
                'last_discovery': pagination_row['last_updated'] if pagination_row else None,
                'discovery_complete': bool(pagination_row['discovery_complete']) if pagination_row else False,
                'last_page': pagination_row['last_page'] if pagination_row else 1,
            }

        finally:
            conn.close()

    def normalize_lead_to_project(self, lead_row: Dict) -> Optional[UnifiedProject]:
        """
        Convert database lead row to UnifiedProject.

        Maps:
        - lead.planhub_id -> project.source_id
        - lead.name -> project.title
        - Parse project_info_json for address, dates, etc.
        - Parse contractors_json for general_contractors list
        - Parse market_intel_json for matching_trades
        """
        try:
            planhub_id = lead_row.get('planhub_id')
            if not planhub_id:
                return None

            # Parse JSON fields safely
            project_info = self._parse_json_field(lead_row.get('project_info_json'), {})
            contractors = self._parse_json_field(lead_row.get('contractors_json'), [])
            market_intel = self._parse_json_field(lead_row.get('market_intel_json'), {})

            # Extract tags from project_info
            tags = project_info.get('tags', [])

            # Parse combined location string (e.g., "Davisville, RI 02852")
            loc_parsed = self._parse_location_string(project_info.get('location'))

            # Build Location object - prefer parsed values, fall back to explicit fields
            location = Location(
                address=project_info.get('address'),
                city=loc_parsed.get('city') or project_info.get('city'),
                state=loc_parsed.get('state') or project_info.get('state'),
                zip=loc_parsed.get('zip') or project_info.get('zip'),
                raw=project_info.get('location')  # Keep original string as fallback
            )

            # Parse project value
            project_value_float, project_value_str = normalize_project_value(
                project_info.get('project_value')
            )

            # Build Division8Scope object
            matching_trades = market_intel.get('matching_trades', [])
            division_8 = Division8Scope(
                matching_trades=matching_trades,
                spec_sections=[],  # Not available from PlanHub
                scope_summary=None
            )

            # Determine if Division 8
            is_division_8 = self._is_division_8(market_intel)

            # Get documents from project_files table
            documents = self._get_documents_for_lead(planhub_id)

            # Build UnifiedProject
            project = UnifiedProject(
                # Identity
                id=f"planhub-{planhub_id}",
                source="planhub",
                source_id=planhub_id,
                url=lead_row.get('url'),

                # Basic Info
                title=lead_row.get('name', ''),
                description=project_info.get('description'),

                # Location
                location=location,

                # Dates
                bid_date=normalize_date(lead_row.get('bid_due_date')),

                # Project Details
                owner=project_info.get('owner'),
                architect=project_info.get('architect'),
                general_contractors=contractors,
                project_value=project_value_float,
                project_value_str=project_value_str,
                project_size=project_info.get('project_size'),

                # Classification
                project_type=self._extract_project_type(tags),
                sector=self._extract_sector(tags),
                tags=tags,

                # Division 8
                is_division_8=is_division_8,
                division_8=division_8,

                # Documents
                documents=documents,

                # PlanHub-specific flags
                is_sub_bidding="Sub Bidding" in tags,
                is_gc_awarded="GC Awarded" in tags,

                # Metadata
                last_sync=lead_row.get('last_seen_at')
            )

            return project

        except Exception as e:
            print(f"Error normalizing lead {lead_row.get('planhub_id')}: {e}")
            return None

    def _parse_json_field(self, value: str, default=None):
        """Safely parse JSON field from database"""
        if not value:
            return default if default is not None else {}
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Warning: Failed to parse JSON: {e}")
            return default if default is not None else {}

    def _parse_location_string(self, loc_str: str) -> dict:
        """
        Parse combined location string into components.

        Examples:
            "Davisville, RI 02852" -> {'city': 'Davisville', 'state': 'RI', 'zip': '02852'}
            "Boston, MA" -> {'city': 'Boston', 'state': 'MA', 'zip': None}
            "Unknown Location" -> {'raw': 'Unknown Location'}
        """
        import re
        if not loc_str:
            return {}

        # Pattern: City, ST ZIP (ZIP is optional)
        match = re.match(r'^(.+?),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)?', loc_str.strip())
        if match:
            return {
                'city': match.group(1).strip(),
                'state': match.group(2),
                'zip': match.group(3)
            }

        # Fallback: return as raw
        return {'raw': loc_str}

    def _get_documents_for_lead(self, planhub_id: str) -> List[Document]:
        """Get list of documents for a specific lead, mapped to Document objects"""
        files = self.get_files_for_lead(planhub_id)
        documents = []

        for i, file_data in enumerate(files):
            doc = Document(
                id=f"{planhub_id}-{i}",
                title=file_data.get('file_name', ''),
                type=file_data.get('file_type', 'unknown'),
                url=file_data.get('download_url'),
                file_size=self._parse_file_size(file_data.get('file_size')),
                downloaded=False,  # PlanHub doesn't download files automatically
                upload_date=file_data.get('upload_date'),
                metadata={
                    'uploaded_by': file_data.get('uploaded_by')
                }
            )
            documents.append(doc)

        return documents

    def _parse_file_size(self, size_str: Optional[str]) -> Optional[int]:
        """Parse file size string (e.g., '2.5 MB') to bytes"""
        if not size_str:
            return None

        try:
            # Handle formats like "2.5 MB", "500 KB", "1.2 GB"
            parts = size_str.strip().split()
            if len(parts) != 2:
                return None

            value = float(parts[0])
            unit = parts[1].upper()

            multipliers = {
                'B': 1,
                'KB': 1024,
                'MB': 1024 * 1024,
                'GB': 1024 * 1024 * 1024
            }

            return int(value * multipliers.get(unit, 1))
        except (ValueError, IndexError):
            return None

    def _is_division_8(self, market_intel: Dict) -> bool:
        """Check if project has Division 8 related trades"""
        matching_trades = market_intel.get('matching_trades', [])
        if not matching_trades:
            return False

        div8_keywords = [
            'glazing', 'glass', 'window', 'door', 'storefront',
            'curtain wall', 'aluminum', 'entrance', 'div 8', 'division 8'
        ]

        for trade in matching_trades:
            trade_lower = str(trade).lower()
            if any(keyword in trade_lower for keyword in div8_keywords):
                return True

        return False

    def _extract_project_type(self, tags: List[str]) -> str:
        """
        Extract primary project type from tags.

        Args:
            tags: List of tag strings from project_info

        Returns:
            Project type string: "New Construction", "Renovation", "Tenant Build-Out", or "Unknown"
        """
        if not tags:
            return "Unknown"

        # Check in priority order
        if "New Construction" in tags:
            return "New Construction"
        elif "Renovation" in tags:
            return "Renovation"
        elif "Tenant Build-Out" in tags or "Tenant Improvement" in tags:
            return "Tenant Build-Out"
        elif "Addition" in tags:
            return "Addition"

        return "Unknown"

    def _extract_sector(self, tags: List[str]) -> str:
        """
        Extract project sector from tags.

        Args:
            tags: List of tag strings from project_info

        Returns:
            Sector string: "Retail", "Industrial", "Commercial", "Education", etc.
        """
        if not tags:
            return "Unknown"

        # Check for specific sectors
        if "Retail" in tags:
            return "Retail"
        elif "Industrial" in tags:
            return "Industrial"
        elif "Education" in tags or "School" in tags:
            return "Education"
        elif "Healthcare" in tags or "Medical" in tags:
            return "Healthcare"
        elif "Hospitality" in tags or "Hotel" in tags:
            return "Hospitality"
        elif "Commercial" in tags:
            return "Commercial"

        return "Unknown"

    def get_files_for_lead(self, planhub_id: str) -> List[Dict]:
        """Get list of files for a specific lead"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # Get lead internal ID first
            cursor.execute("SELECT id FROM leads WHERE planhub_id = ?", (planhub_id,))
            lead = cursor.fetchone()
            if not lead:
                return []

            lead_id = lead['id']

            # Get files
            cursor.execute("""
                SELECT
                    file_name,
                    file_type,
                    file_size,
                    upload_date,
                    uploaded_by,
                    download_url
                FROM project_files
                WHERE lead_id = ?
                ORDER BY upload_date DESC
            """, (lead_id,))

            files = []
            for row in cursor.fetchall():
                files.append({
                    'file_name': row['file_name'],
                    'file_type': row['file_type'],
                    'file_size': row['file_size'],
                    'upload_date': row['upload_date'],
                    'uploaded_by': row['uploaded_by'],
                    'download_url': row['download_url'],
                })

            return files

        finally:
            conn.close()
