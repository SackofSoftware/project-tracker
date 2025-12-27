"""
GovWin Importer - Import government leads from GovWin database.

Reads from govwin.db and imports to GovLead table (separate from projects).
GovWin leads stay in forecasting/research until explicitly converted.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import re

from modules.database.db import get_session
from modules.database.models import GovLead

logger = logging.getLogger(__name__)


class GovWinImporter:
    """
    Imports leads from GovWin SQLite database.
    These go to a separate leads table, not main projects.
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)

    def import_all(self) -> Dict[str, Any]:
        """
        Import all GovWin leads.
        Returns summary statistics.
        """
        results = {
            'source': 'govwin',
            'database': str(self.db_path),
            'count': 0,
            'new': 0,
            'updated': 0,
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

            # Get all opportunities
            cursor.execute("""
                SELECT * FROM opportunities
                WHERE status = 'done'
                ORDER BY response_date DESC NULLS LAST
            """)

            with get_session() as session:
                for row in cursor.fetchall():
                    try:
                        opp = dict(row)
                        result = self._import_opportunity(session, opp)
                        results['count'] += 1
                        if result == 'new':
                            results['new'] += 1
                        elif result == 'updated':
                            results['updated'] += 1
                        elif result == 'skipped':
                            results['skipped'] += 1
                    except Exception as e:
                        logger.error(f"Error importing GovWin opp {row.get('opportunity_id')}: {e}")
                        results['errors'].append({
                            'id': row.get('opportunity_id'),
                            'error': str(e)
                        })

            conn.close()

        except Exception as e:
            results['error'] = str(e)
            logger.error(f'Error reading GovWin database: {e}')

        logger.info(f"Imported {results['count']} GovWin leads")
        return results

    def _import_opportunity(self, session, opp: Dict) -> str:
        """
        Import a single GovWin opportunity to GovLead table.
        Returns: 'new', 'updated', or 'skipped'
        """
        opportunity_id = opp.get('opportunity_id', '')

        # Check if already exists
        existing = session.query(GovLead).filter(
            GovLead.opportunity_id == opportunity_id
        ).first()

        lead_data = self._normalize_opportunity(opp)

        if existing:
            # Update existing lead
            for key, value in lead_data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.last_synced = datetime.now()
            return 'updated'
        else:
            # Create new lead
            lead = GovLead(
                opportunity_id=opportunity_id,
                last_synced=datetime.now(),
                **lead_data
            )
            session.add(lead)
            return 'new'

    def _normalize_opportunity(self, opp: Dict) -> Dict[str, Any]:
        """Normalize GovWin opportunity to GovLead format."""
        data = {}

        # Basic fields
        data['entity_type'] = opp.get('entity_type', 'LEAD')  # BID or LEAD
        data['title'] = opp.get('title', '')
        data['status'] = opp.get('status', '')
        data['state'] = opp.get('state', '')
        data['organization'] = opp.get('organization', '')
        data['description'] = opp.get('description', '')

        # Dates
        if opp.get('response_date'):
            data['response_date'] = opp['response_date']
        if opp.get('solicitation_date'):
            data['solicitation_date'] = opp['solicitation_date']

        # Value
        if opp.get('estimated_value'):
            try:
                # Parse value like "$1,000,000" or "1000000"
                value_str = str(opp['estimated_value'])
                value_str = re.sub(r'[$,]', '', value_str)
                data['estimated_value'] = float(value_str)
            except:
                pass

        # JSON data
        if opp.get('overview_json'):
            try:
                data['overview_data'] = json.loads(opp['overview_json']) if isinstance(opp['overview_json'], str) else opp['overview_json']
            except:
                pass

        if opp.get('contact_json'):
            try:
                data['contact_data'] = json.loads(opp['contact_json']) if isinstance(opp['contact_json'], str) else opp['contact_json']
            except:
                pass

        return data