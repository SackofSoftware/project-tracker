"""
Project Numbering Service

Manages sequential project numbering with lifecycle prefixes and state transitions.
"""

from datetime import datetime
from typing import Optional, Dict, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.database.models import ProjectNumber, Project, ProjectStatus


class ProjectNumberingService:
    """
    Service for managing project numbers and lifecycle transitions.

    Prefixes:
    - B = Bidding (active bids in progress)
    - L = Lead (early stage/forecasting)
    - O = Opportunity (potential, not yet qualified)
    - A = Awarded (won)
    - X = Lost/Not Bid/Gone
    """

    PREFIXES = {
        'B': 'Bidding',
        'L': 'Lead',
        'O': 'Opportunity',
        'A': 'Awarded',
        'X': 'Lost/Not Bid/Gone'
    }

    # Valid lifecycle transitions
    VALID_TRANSITIONS = {
        'L': ['B', 'O', 'X'],      # Lead can become Bidding, Opportunity, or Lost
        'O': ['L', 'B', 'X'],      # Opportunity can become Lead, Bidding, or Lost
        'B': ['A', 'X'],           # Bidding can become Awarded or Lost
        'A': [],                   # Awarded is terminal (no transitions)
        'X': ['L', 'O', 'B'],      # Lost can be resurrected (rare)
    }

    def __init__(self, db_session: Session):
        """
        Initialize the numbering service.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    def _get_next_number(self) -> int:
        """
        Get the next sequential number (global across all prefixes).

        Returns:
            Next available number (1 if no projects exist)
        """
        max_num = self.db.query(func.max(ProjectNumber.number)).scalar()
        return (max_num or 0) + 1

    def _format_number(self, prefix: str, number: int) -> str:
        """
        Format a full project number.

        Args:
            prefix: Single character prefix (B, L, O, A, X)
            number: Sequential number

        Returns:
            Formatted number like 'B-042'
        """
        return f"{prefix}-{number:03d}"

    def assign_number(self, project_id: str, prefix: str = 'L') -> str:
        """
        Assign a new project number to a project.

        Args:
            project_id: Project ID to assign number to
            prefix: Lifecycle prefix (default: 'L' for Lead)

        Returns:
            Full project number (e.g., 'B-042')

        Raises:
            ValueError: If project already has a number or prefix is invalid
        """
        # Validate prefix
        if prefix not in self.PREFIXES:
            raise ValueError(f"Invalid prefix '{prefix}'. Must be one of: {list(self.PREFIXES.keys())}")

        # Check if project already has a number
        existing = self.db.query(ProjectNumber).filter_by(project_id=project_id).first()
        if existing:
            raise ValueError(f"Project {project_id} already has number {existing.full_number}")

        # Get next number
        number = self._get_next_number()
        full_number = self._format_number(prefix, number)

        # Create record
        project_number = ProjectNumber(
            project_id=project_id,
            number=number,
            prefix=prefix,
            full_number=full_number,
            created_at=datetime.now()
        )

        self.db.add(project_number)
        self.db.commit()

        return full_number

    def get_number(self, project_id: str) -> Optional[str]:
        """
        Get the project number for a project.

        Args:
            project_id: Project ID to look up

        Returns:
            Full project number or None if not assigned
        """
        record = self.db.query(ProjectNumber).filter_by(project_id=project_id).first()
        return record.full_number if record else None

    def get_prefix(self, project_id: str) -> Optional[str]:
        """
        Get the current prefix (lifecycle stage) for a project.

        Args:
            project_id: Project ID to look up

        Returns:
            Current prefix or None if not assigned
        """
        record = self.db.query(ProjectNumber).filter_by(project_id=project_id).first()
        return record.prefix if record else None

    def transition(self, project_id: str, new_prefix: str, reason: str = None) -> bool:
        """
        Transition project to a new lifecycle stage.

        Args:
            project_id: Project ID to transition
            new_prefix: New lifecycle prefix
            reason: Optional reason for transition

        Returns:
            True if transition was successful

        Raises:
            ValueError: If transition is not valid
        """
        # Validate prefix
        if new_prefix not in self.PREFIXES:
            raise ValueError(f"Invalid prefix '{new_prefix}'. Must be one of: {list(self.PREFIXES.keys())}")

        # Get current record
        record = self.db.query(ProjectNumber).filter_by(project_id=project_id).first()
        if not record:
            raise ValueError(f"Project {project_id} does not have a number assigned")

        current_prefix = record.prefix

        # Check if same prefix
        if current_prefix == new_prefix:
            return True  # No-op

        # Validate transition
        valid_targets = self.VALID_TRANSITIONS.get(current_prefix, [])
        if new_prefix not in valid_targets:
            raise ValueError(
                f"Invalid transition: {current_prefix} ({self.PREFIXES[current_prefix]}) -> "
                f"{new_prefix} ({self.PREFIXES[new_prefix]}). "
                f"Valid transitions: {[f'{p} ({self.PREFIXES[p]})' for p in valid_targets]}"
            )

        # Update record with audit trail
        record.previous_prefix = current_prefix
        record.prefix = new_prefix
        record.full_number = self._format_number(new_prefix, record.number)
        record.transition_date = datetime.now()
        record.transition_reason = reason
        record.updated_at = datetime.now()

        self.db.commit()
        return True

    def get_projects_by_prefix(self, prefix: str) -> List[Dict]:
        """
        Get all projects with a specific prefix.

        Args:
            prefix: Lifecycle prefix to filter by

        Returns:
            List of project number records as dicts
        """
        records = self.db.query(ProjectNumber).filter_by(prefix=prefix).all()
        return [r.to_dict() for r in records]

    def get_transition_history(self, project_id: str) -> Optional[Dict]:
        """
        Get transition history for a project.

        Args:
            project_id: Project ID to look up

        Returns:
            Dict with current state and last transition info
        """
        record = self.db.query(ProjectNumber).filter_by(project_id=project_id).first()
        if not record:
            return None

        return {
            'project_id': project_id,
            'current_number': record.full_number,
            'current_prefix': record.prefix,
            'current_stage': self.PREFIXES.get(record.prefix),
            'previous_prefix': record.previous_prefix,
            'previous_stage': self.PREFIXES.get(record.previous_prefix) if record.previous_prefix else None,
            'transition_date': record.transition_date.isoformat() if record.transition_date else None,
            'transition_reason': record.transition_reason
        }

    def migrate_existing_projects(self) -> Tuple[int, List[str]]:
        """
        Migrate all existing projects to the numbered format.

        Default prefix assignment based on bid_decision:
        - bid_decision = 'bid' -> B (Bidding)
        - bid_decision = 'awarded' -> A (Awarded)
        - bid_decision = 'lost' or 'no-bid' -> X (Lost)
        - All others -> L (Lead)

        Returns:
            Tuple of (count_migrated, list of errors)
        """
        # Get all projects without numbers
        existing_numbers = self.db.query(ProjectNumber.project_id).all()
        existing_ids = {r[0] for r in existing_numbers}

        # Get all projects ordered by creation date
        all_projects = self.db.query(Project).order_by(Project.created_at.asc()).all()

        migrated = 0
        errors = []

        for project in all_projects:
            if project.id in existing_ids:
                continue  # Already has a number

            # Determine prefix from bid_decision
            status = self.db.query(ProjectStatus).filter_by(project_id=project.id).first()
            bid_decision = status.bid_decision if status else None

            if bid_decision == 'bid':
                prefix = 'B'
            elif bid_decision == 'awarded':
                prefix = 'A'
            elif bid_decision in ('lost', 'no-bid', 'no_bid'):
                prefix = 'X'
            else:
                prefix = 'L'  # Default to Lead

            try:
                full_number = self.assign_number(project.id, prefix)
                migrated += 1
            except Exception as e:
                errors.append(f"{project.id}: {str(e)}")

        return migrated, errors

    def get_stats(self) -> Dict:
        """
        Get statistics about project numbers.

        Returns:
            Dict with counts by prefix and total
        """
        stats = {'total': 0}

        for prefix, name in self.PREFIXES.items():
            count = self.db.query(ProjectNumber).filter_by(prefix=prefix).count()
            stats[prefix] = {
                'name': name,
                'count': count
            }
            stats['total'] += count

        return stats


# Convenience functions for use without instantiating service

def get_numbering_service(db_session: Session = None) -> ProjectNumberingService:
    """
    Get a ProjectNumberingService instance.

    Args:
        db_session: SQLAlchemy session (will create one if not provided)

    Returns:
        ProjectNumberingService instance
    """
    if db_session is None:
        from modules.database import get_session
        db_session = get_session()

    return ProjectNumberingService(db_session)
