"""
Sync Module - Background synchronization of project sources to database.

Handles importing projects from:
- Bidding folder (local files)
- Brad Projects folder (local files)
- Current Projects folder (local files)
- Email Monitor (email-based invites)
- PlanHub (planhub.db)
- GovWin (govwin.db)
"""

from .sync_service import SyncService, get_sync_service
from .background_sync import BackgroundSync
from .background_scheduler import (
    init_scheduler,
    stop_scheduler,
    get_scheduler,
    is_scheduler_running,
    trigger_immediate_sync,
    get_scheduler_status
)

__all__ = [
    'SyncService',
    'get_sync_service',
    'BackgroundSync',
    'init_scheduler',
    'stop_scheduler',
    'get_scheduler',
    'is_scheduler_running',
    'trigger_immediate_sync',
    'get_scheduler_status'
]

