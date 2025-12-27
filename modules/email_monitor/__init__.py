"""
Email Monitor Integration Module

Reads and matches emails from the Email Monitor output directory to projects.

Source: Configured via EMAIL_MONITOR_PATH environment variable

Supports:
- Reading email metadata JSON files
- Auto-matching emails to projects using fuzzy matching
- Manual link override capability
- Status transitions based on email types
- Syncing emails to the database
"""

from .email_reader import EmailMonitorReader, EmailRecord
from .email_matcher import EmailProjectMatcher
from .status_transitions import EmailStatusUpdater, get_implied_status, should_update_status

__all__ = [
    'EmailMonitorReader',
    'EmailRecord',
    'EmailProjectMatcher',
    'EmailStatusUpdater',
    'get_implied_status',
    'should_update_status'
]
