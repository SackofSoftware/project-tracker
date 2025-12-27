"""
Sync Service - Background synchronization coordinator.

Orchestrates importing projects from all sources into the unified database.
"""

import threading
import logging
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path
import os

logger = logging.getLogger(__name__)


class SyncService:
    """
    Coordinates background synchronization of all project sources.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._last_sync = {}
        self._sync_in_progress = False
        self._sync_errors = []

    def sync_all_sources(self) -> Dict[str, Any]:
        """
        Sync all configured project sources to database.
        Returns summary of sync results.
        """
        if self._sync_in_progress:
            return {'status': 'already_running', 'message': 'Sync already in progress'}

        with self._lock:
            self._sync_in_progress = True
            self._sync_errors = []
            results = {
                'started_at': datetime.now().isoformat(),
                'sources': {},
                'total_projects': 0,
                'new_projects': 0,
                'updated_projects': 0,
                'errors': []
            }

            try:
                # Sync local folders
                for source_name, folder_path in self._get_folder_sources():
                    try:
                        source_result = self._sync_folder_source(source_name, folder_path)
                        results['sources'][source_name] = source_result
                        results['total_projects'] += source_result.get('count', 0)
                        results['new_projects'] += source_result.get('new', 0)
                        results['updated_projects'] += source_result.get('updated', 0)
                    except Exception as e:
                        logger.error(f'Error syncing {source_name}: {e}')
                        results['errors'].append({'source': source_name, 'error': str(e)})

                # Sync PlanHub
                try:
                    planhub_result = self._sync_planhub()
                    results['sources']['planhub'] = planhub_result
                    results['total_projects'] += planhub_result.get('count', 0)
                except Exception as e:
                    logger.error(f'Error syncing PlanHub: {e}')
                    results['errors'].append({'source': 'planhub', 'error': str(e)})

                # Sync GovWin (separate - goes to leads)
                try:
                    govwin_result = self._sync_govwin()
                    results['sources']['govwin'] = govwin_result
                except Exception as e:
                    logger.error(f'Error syncing GovWin: {e}')
                    results['errors'].append({'source': 'govwin', 'error': str(e)})

                # Sync Email Monitor
                try:
                    email_result = self._sync_email_monitor()
                    results['sources']['email'] = email_result
                except Exception as e:
                    logger.error(f'Error syncing Email Monitor: {e}')
                    results['errors'].append({'source': 'email', 'error': str(e)})

                results['completed_at'] = datetime.now().isoformat()
                results['status'] = 'success' if not results['errors'] else 'partial'

            finally:
                self._sync_in_progress = False
                self._last_sync['all'] = datetime.now()

            return results

    def _get_folder_sources(self) -> List[tuple]:
        """Get configured folder sources from environment."""
        sources = []

        bidding = os.environ.get('BIDDING_FOLDER')
        if bidding and Path(bidding).exists():
            sources.append(('bidding', bidding))

        brad = os.environ.get('BRAD_PROJECTS_FOLDER')
        if brad and Path(brad).exists():
            sources.append(('brad', brad))

        current = os.environ.get('CURRENT_PROJECTS_FOLDER')
        if current and Path(current).exists():
            sources.append(('current', current))

        return sources

    def _sync_folder_source(self, source_name: str, folder_path: str) -> Dict[str, Any]:
        """Sync a local folder source to database."""
        from .source_importers.folder_importer import FolderImporter

        importer = FolderImporter(source_name, folder_path)
        result = importer.import_all()

        self._last_sync[source_name] = datetime.now()
        return result

    def _sync_planhub(self) -> Dict[str, Any]:
        """Sync PlanHub database to projects."""
        from .source_importers.planhub_importer import PlanHubImporter

        db_path = os.environ.get('PLANHUB_DB_PATH')
        if not db_path or not Path(db_path).exists():
            return {'status': 'skipped', 'reason': 'Database not configured'}

        importer = PlanHubImporter(db_path)
        result = importer.import_all()

        self._last_sync['planhub'] = datetime.now()
        return result

    def _sync_govwin(self) -> Dict[str, Any]:
        """Sync GovWin database to leads (separate from projects)."""
        from .source_importers.govwin_importer import GovWinImporter

        db_path = os.environ.get('GOV_DB_PATH')
        if not db_path or not Path(db_path).exists():
            return {'status': 'skipped', 'reason': 'Database not configured'}

        importer = GovWinImporter(db_path)
        result = importer.import_all()

        self._last_sync['govwin'] = datetime.now()
        return result

    def _sync_email_monitor(self) -> Dict[str, Any]:
        """Sync Email Monitor output to bid opportunities."""
        from .source_importers.email_importer import EmailImporter

        output_path = os.environ.get('EMAIL_MONITOR_PATH')
        if not output_path or not Path(output_path).exists():
            return {'status': 'skipped', 'reason': 'Path not configured'}

        importer = EmailImporter(output_path)
        result = importer.import_all()

        self._last_sync['email'] = datetime.now()
        return result

    def get_status(self) -> Dict[str, Any]:
        """Get current sync status."""
        return {
            'in_progress': self._sync_in_progress,
            'last_sync': {k: v.isoformat() for k, v in self._last_sync.items()},
            'errors': self._sync_errors[-10:] if self._sync_errors else []
        }

    def trigger_sync(self, source: str = None) -> Dict[str, Any]:
        """Trigger a sync operation (all sources or specific)."""
        if source:
            folder_sources = dict(self._get_folder_sources())
            if source in folder_sources:
                return self._sync_folder_source(source, folder_sources[source])
            elif source == 'planhub':
                return self._sync_planhub()
            elif source == 'govwin':
                return self._sync_govwin()
            elif source == 'email':
                return self._sync_email_monitor()
            else:
                return {'status': 'error', 'message': f'Unknown source: {source}'}
        else:
            return self.sync_all_sources()


_service = None


def get_sync_service() -> SyncService:
    """Get the singleton sync service."""
    global _service
    if _service is None:
        _service = SyncService()
    return _service