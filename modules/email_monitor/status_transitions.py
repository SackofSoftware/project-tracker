"""
Email-based Status Transition Logic

Maps email types to project status transitions following the workflow:
upcoming -> in_progress -> awarded -> complete

Status only progresses forward based on email evidence.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime


# Email type to status implications with priority levels
# Higher priority = later in the project lifecycle
EMAIL_STATUS_MAP = {
    'bid_invite': {
        'implies_status': 'upcoming',
        'priority': 1,
    },
    'deadline_reminder': {
        'implies_status': 'upcoming',
        'priority': 1,
    },
    'pre_bid_meeting': {
        'implies_status': 'upcoming',
        'priority': 1,
    },
    'addendum': {
        'implies_status': 'in_progress',
        'priority': 2,
    },
    'rfi': {
        'implies_status': 'in_progress',
        'priority': 2,
    },
    'project_update': {
        'implies_status': 'in_progress',
        'priority': 2,
    },
    'site_visit': {
        'implies_status': 'in_progress',
        'priority': 2,
    },
    'submittal': {
        'implies_status': 'awarded',
        'priority': 3,
    },
    'award_notification': {
        'implies_status': 'awarded',
        'priority': 4,
    },
    'shipping_notification': {
        'implies_status': 'awarded',
        'priority': 4,
    },
    'delivery_notice': {
        'implies_status': 'awarded',
        'priority': 4,
    },
    'change_order': {
        'implies_status': 'awarded',
        'priority': 4,
    },
    'invoice': {
        'implies_status': 'awarded',
        'priority': 5,
    },
    'payment_notice': {
        'implies_status': 'awarded',
        'priority': 5,
    },
}

# Status progression order (can only move forward)
STATUS_ORDER = {
    'unknown': 0,
    'upcoming': 1,
    'in_progress': 2,
    'bid_submitted': 3,
    'awarded': 4,
    'complete': 5,
}


def get_implied_status(email_types: List[str]) -> Tuple[str, int]:
    """
    Determine implied project status from list of email types.

    Returns the highest-priority status implied by the email types.

    Args:
        email_types: List of email type strings

    Returns:
        Tuple of (status_string, priority_level)
    """
    best_status = 'unknown'
    best_priority = 0

    for etype in email_types:
        mapping = EMAIL_STATUS_MAP.get(etype, {})
        priority = mapping.get('priority', 0)
        if priority > best_priority:
            best_priority = priority
            best_status = mapping.get('implies_status', 'unknown')

    return best_status, best_priority


def should_update_status(current_status: str, new_status: str) -> bool:
    """
    Determine if status should be updated based on progression logic.

    Status progression: upcoming -> in_progress -> awarded -> complete

    Only allows forward progression (can't go backwards).

    Args:
        current_status: Current project status
        new_status: Proposed new status from email

    Returns:
        True if status should be updated
    """
    current_order = STATUS_ORDER.get(current_status, 0)
    new_order = STATUS_ORDER.get(new_status, 0)

    # Only progress forward, never backwards
    return new_order > current_order


class EmailStatusUpdater:
    """
    Updates project status based on email classifications.

    Integrates with project status tracking for persistence.
    """

    def __init__(self, status_tracker=None):
        """
        Args:
            status_tracker: Optional ProjectStatusTracker instance for persistence
        """
        self.tracker = status_tracker
        self._updates = []  # Track updates for batch operations

    def get_status_for_emails(self, email_types: List[str]) -> Dict:
        """
        Calculate what status emails imply without updating anything.

        Args:
            email_types: List of email type strings

        Returns:
            Dict with implied_status and reasoning
        """
        implied_status, priority = get_implied_status(email_types)

        # Find which email type triggered the status
        trigger_type = None
        for etype in email_types:
            mapping = EMAIL_STATUS_MAP.get(etype, {})
            if mapping.get('priority', 0) == priority:
                trigger_type = etype
                break

        return {
            'implied_status': implied_status,
            'priority': priority,
            'trigger_email_type': trigger_type,
            'email_types_analyzed': email_types
        }

    def process_project_emails(
        self,
        project_id: str,
        email_types: List[str],
        current_status: str = None
    ) -> Dict:
        """
        Process emails for a project and determine if status should change.

        Args:
            project_id: Project identifier
            email_types: List of email type strings for this project
            current_status: Current project status (if known)

        Returns:
            Dict with update results
        """
        result = {
            'project_id': project_id,
            'status_updated': False,
            'old_status': current_status or 'unknown',
            'new_status': current_status or 'unknown',
            'trigger_email_type': None,
            'timestamp': datetime.now().isoformat()
        }

        # Get implied status from emails
        status_info = self.get_status_for_emails(email_types)
        implied_status = status_info['implied_status']

        # Check if we should update
        old_status = current_status or 'unknown'
        if should_update_status(old_status, implied_status):
            result['status_updated'] = True
            result['new_status'] = implied_status
            result['trigger_email_type'] = status_info['trigger_email_type']

            # Track for batch operations
            self._updates.append(result.copy())

            # Persist if tracker available
            if self.tracker:
                self._persist_status_update(project_id, old_status, implied_status, status_info)

        return result

    def _persist_status_update(
        self,
        project_id: str,
        old_status: str,
        new_status: str,
        status_info: Dict
    ):
        """
        Persist status update to tracker.

        Args:
            project_id: Project identifier
            old_status: Previous status
            new_status: New status
            status_info: Status calculation details
        """
        try:
            # Update email_status field
            self.tracker.set_status(project_id, {
                'email_status': new_status,
                'email_status_updated': datetime.now().isoformat(),
                'email_status_source': status_info.get('trigger_email_type'),
            })

            # Log timeline event if method exists
            if hasattr(self.tracker, 'add_timeline_event'):
                self.tracker.add_timeline_event(
                    project_id=project_id,
                    event_type='email_status_changed',
                    title=f'Email status: {old_status} → {new_status}',
                    description=f"Based on {status_info.get('trigger_email_type')} email",
                    source='email_monitor',
                    changes=[{
                        'field': 'email_status',
                        'old': old_status,
                        'new': new_status
                    }]
                )
        except Exception as e:
            print(f"Error persisting status update for {project_id}: {e}")

    def get_updates(self) -> List[Dict]:
        """Get list of all status updates made."""
        return self._updates.copy()

    def clear_updates(self):
        """Clear the updates list."""
        self._updates = []

    def batch_process(
        self,
        projects_emails: Dict[str, List[str]],
        current_statuses: Dict[str, str] = None
    ) -> Dict:
        """
        Process multiple projects at once.

        Args:
            projects_emails: Dict mapping project_id to list of email_types
            current_statuses: Optional dict mapping project_id to current status

        Returns:
            Summary of all updates
        """
        current_statuses = current_statuses or {}
        results = []

        for project_id, email_types in projects_emails.items():
            current = current_statuses.get(project_id, 'unknown')
            result = self.process_project_emails(project_id, email_types, current)
            results.append(result)

        updated = [r for r in results if r['status_updated']]

        return {
            'total_projects': len(results),
            'updated_count': len(updated),
            'updates': updated,
            'timestamp': datetime.now().isoformat()
        }
