"""
Project Repository - CRUD Operations for Database-Centric Project Management

Provides the data access layer for all project operations, replacing the
folder-scanning approach with instant database reads.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import or_, and_, func, desc
from sqlalchemy.orm import Session, joinedload

from .db import get_session, SessionLocal
from .models import (
    Project, ProjectStatus, ProjectSourceLink, ProjectContractor,
    DeduplicationLog, PendingDuplicate, Division8Scope, VendorQuote,
    ProjectNumber, GovLead
)


class ProjectRepository:
    """
    Repository pattern for project data access.
    All database operations go through this class.
    """

    # Workflow status constants
    STATUS_FORECAST = 'forecast'
    STATUS_BID_OPPORTUNITY = 'bid_opportunity'
    STATUS_BIDDING = 'bidding'
    STATUS_GC_AWARDED = 'gc_awarded'
    STATUS_UNDER_CONTRACT = 'under_contract'
    STATUS_LOST = 'lost'
    STATUS_COMPLETE = 'complete'

    VALID_STATUSES = [
        STATUS_FORECAST, STATUS_BID_OPPORTUNITY, STATUS_BIDDING,
        STATUS_GC_AWARDED, STATUS_UNDER_CONTRACT, STATUS_LOST, STATUS_COMPLETE
    ]

    def __init__(self, session: Session = None):
        """Initialize with optional session for transaction control."""
        self._session = session
        self._owns_session = session is None

    def _get_session(self) -> Session:
        """Get or create a database session."""
        if self._session:
            return self._session
        return SessionLocal()

    def _close_session(self, session: Session):
        """Close session if we own it."""
        if self._owns_session and session:
            session.close()

    # ==================== READ OPERATIONS ====================

    def get_all_projects(
        self,
        include_archived: bool = False,
        status: str = None,
        source: str = None,
        limit: int = None,
        offset: int = 0
    ) -> List[Project]:
        """
        Get all projects with optional filtering.
        This is the primary method for instant startup.
        """
        session = self._get_session()
        try:
            query = session.query(Project)

            if not include_archived:
                query = query.filter(Project.archived == False)

            if status:
                query = query.filter(Project.workflow_status == status)

            if source:
                query = query.filter(Project.source == source)

            # Order by bid date (soonest first), nulls last
            query = query.order_by(
                func.coalesce(Project.bid_date, datetime(9999, 12, 31))
            )

            if offset:
                query = query.offset(offset)

            if limit:
                query = query.limit(limit)

            return query.all()
        finally:
            self._close_session(session)

    def get_project(self, project_id: str) -> Optional[Project]:
        """Get a single project by ID with all relationships loaded."""
        session = self._get_session()
        try:
            return session.query(Project).options(
                joinedload(Project.status),
                joinedload(Project.division8_scope),
                joinedload(Project.source_links),
                joinedload(Project.contractors),
                joinedload(Project.quotes)
            ).filter(Project.id == project_id).first()
        finally:
            self._close_session(session)

    def get_bid_opportunities(self) -> List[Project]:
        """Get all projects in bid_opportunity status for assessment queue."""
        return self.get_all_projects(status=self.STATUS_BID_OPPORTUNITY)

    def get_active_bidding(self) -> List[Project]:
        """Get all projects actively being bid."""
        return self.get_all_projects(status=self.STATUS_BIDDING)

    def get_upcoming_bids(self, days: int = 30) -> List[Project]:
        """Get projects with bid dates in the next N days."""
        session = self._get_session()
        try:
            from datetime import timedelta
            today = datetime.now().date()
            future = today + timedelta(days=days)

            return session.query(Project).filter(
                Project.archived == False,
                Project.bid_date != None,
                Project.bid_date >= today,
                Project.bid_date <= future
            ).order_by(Project.bid_date).all()
        finally:
            self._close_session(session)

    def get_projects_by_source(self, source_type: str) -> List[Project]:
        """Get all projects from a specific source."""
        session = self._get_session()
        try:
            return session.query(Project).join(ProjectSourceLink).filter(
                ProjectSourceLink.source_type == source_type
            ).all()
        finally:
            self._close_session(session)

    def get_project_count(self, status: str = None) -> int:
        """Get count of projects, optionally by status."""
        session = self._get_session()
        try:
            query = session.query(func.count(Project.id)).filter(
                Project.archived == False
            )
            if status:
                query = query.filter(Project.workflow_status == status)
            return query.scalar()
        finally:
            self._close_session(session)

    def search_projects(self, query: str, limit: int = 20) -> List[Project]:
        """Search projects by title, address, or owner."""
        session = self._get_session()
        try:
            search = f"%{query}%"
            return session.query(Project).filter(
                Project.archived == False,
                or_(
                    Project.title.ilike(search),
                    Project.address.ilike(search),
                    Project.city.ilike(search),
                    Project.owner_name.ilike(search),
                    Project.architect_name.ilike(search)
                )
            ).limit(limit).all()
        finally:
            self._close_session(session)

    # ==================== CREATE OPERATIONS ====================

    def create_project(self, data: Dict[str, Any]) -> Project:
        """Create a new project from dictionary data."""
        session = self._get_session()
        try:
            # Generate ID if not provided
            if 'id' not in data:
                data['id'] = self._generate_project_id(data.get('title', 'untitled'))

            # Set default workflow status
            if 'workflow_status' not in data:
                data['workflow_status'] = self.STATUS_BID_OPPORTUNITY

            project = Project(**data)
            session.add(project)
            session.commit()
            session.refresh(project)
            return project
        except Exception as e:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    def create_or_update_project(self, project_id: str, data: Dict[str, Any]) -> Project:
        """Create or update a project (upsert operation)."""
        session = self._get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()

            if project:
                # Update existing
                for key, value in data.items():
                    if hasattr(project, key):
                        setattr(project, key, value)
                project.updated_at = datetime.now()
            else:
                # Create new
                data['id'] = project_id
                project = Project(**data)
                session.add(project)

            session.commit()
            session.refresh(project)
            return project
        except Exception as e:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    def _generate_project_id(self, title: str) -> str:
        """Generate a URL-safe project ID from title."""
        import re
        # Remove special characters, convert to lowercase, replace spaces with dashes
        slug = re.sub(r'[^\w\s-]', '', title.lower())
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')

        # Truncate and ensure uniqueness
        base_slug = slug[:50]
        session = self._get_session()
        try:
            # Check if exists, add number if needed
            existing = session.query(Project.id).filter(
                Project.id.like(f"{base_slug}%")
            ).all()
            if not existing:
                return base_slug

            existing_ids = {p[0] for p in existing}
            if base_slug not in existing_ids:
                return base_slug

            # Add incrementing number
            counter = 1
            while f"{base_slug}-{counter}" in existing_ids:
                counter += 1
            return f"{base_slug}-{counter}"
        finally:
            self._close_session(session)

    # ==================== UPDATE OPERATIONS ====================

    def update_project(self, project_id: str, data: Dict[str, Any]) -> Optional[Project]:
        """Update a project's fields."""
        session = self._get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if not project:
                return None

            for key, value in data.items():
                if hasattr(project, key) and key != 'id':
                    setattr(project, key, value)

            project.updated_at = datetime.now()
            session.commit()
            session.refresh(project)
            return project
        except Exception as e:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    def change_status(
        self,
        project_id: str,
        new_status: str,
        notes: str = None,
        changed_by: str = 'system'
    ) -> Optional[Project]:
        """
        Change a project's workflow status with audit logging.
        This is a critical operation with validation.
        """
        if new_status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}")

        session = self._get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if not project:
                return None

            old_status = project.workflow_status

            # Update project status
            project.workflow_status = new_status
            project.workflow_status_changed_at = datetime.now()
            if notes:
                project.workflow_status_notes = notes
            project.updated_at = datetime.now()

            # Handle special status transitions
            if new_status == self.STATUS_LOST:
                project.archived = True
                project.archived_date = datetime.now()
                project.archived_reason = 'lost'
            elif new_status == self.STATUS_COMPLETE:
                project.archived = True
                project.archived_date = datetime.now()
                project.archived_reason = 'completed'

            session.commit()
            session.refresh(project)
            return project
        except Exception as e:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    def accept_opportunity(
        self,
        project_id: str,
        folder_name: str = None,
        notes: str = None
    ) -> Optional[Project]:
        """
        Accept a bid opportunity - moves to bidding status.
        Optionally creates a folder.
        """
        session = self._get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if not project:
                return None

            if project.workflow_status != self.STATUS_BID_OPPORTUNITY:
                raise ValueError(f"Project is not in bid_opportunity status")

            # Update status
            project.workflow_status = self.STATUS_BIDDING
            project.workflow_status_changed_at = datetime.now()
            if notes:
                project.workflow_status_notes = notes

            # Set folder path if provided
            if folder_name:
                project.folder_path = folder_name

            project.updated_at = datetime.now()
            session.commit()
            session.refresh(project)
            return project
        except Exception as e:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    def decline_opportunity(
        self,
        project_id: str,
        reason: str,
        notes: str = None
    ) -> Optional[Project]:
        """
        Decline a bid opportunity - archives the project.
        """
        session = self._get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if not project:
                return None

            # Archive the project
            project.archived = True
            project.archived_date = datetime.now()
            project.archived_reason = f"declined:{reason}"
            project.workflow_status = self.STATUS_LOST
            project.workflow_status_changed_at = datetime.now()
            if notes:
                project.workflow_status_notes = notes

            project.updated_at = datetime.now()
            session.commit()
            session.refresh(project)
            return project
        except Exception as e:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    def archive_project(
        self,
        project_id: str,
        reason: str = 'manual'
    ) -> Optional[Project]:
        """Archive a project."""
        session = self._get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if not project:
                return None

            project.archived = True
            project.archived_date = datetime.now()
            project.archived_reason = reason
            project.updated_at = datetime.now()

            session.commit()
            session.refresh(project)
            return project
        except Exception as e:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    # ==================== SOURCE LINK OPERATIONS ====================

    def add_source_link(
        self,
        project_id: str,
        source_type: str,
        source_id: str,
        source_data: Dict = None,
        match_confidence: float = 1.0,
        match_type: str = 'manual'
    ) -> ProjectSourceLink:
        """Link a project to an external source."""
        session = self._get_session()
        try:
            link = ProjectSourceLink(
                project_id=project_id,
                source_type=source_type,
                source_id=source_id,
                source_data=source_data,
                match_confidence=match_confidence,
                match_type=match_type,
                matched_by='system'
            )
            session.add(link)
            session.commit()
            session.refresh(link)
            return link
        except Exception as e:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    def get_project_sources(self, project_id: str) -> List[ProjectSourceLink]:
        """Get all source links for a project."""
        session = self._get_session()
        try:
            return session.query(ProjectSourceLink).filter(
                ProjectSourceLink.project_id == project_id
            ).all()
        finally:
            self._close_session(session)

    def find_project_by_source(
        self,
        source_type: str,
        source_id: str
    ) -> Optional[Project]:
        """Find a project by its source link."""
        session = self._get_session()
        try:
            link = session.query(ProjectSourceLink).filter(
                ProjectSourceLink.source_type == source_type,
                ProjectSourceLink.source_id == source_id
            ).first()
            return link.project if link else None
        finally:
            self._close_session(session)

    # ==================== CONTRACTOR OPERATIONS ====================

    def add_contractor(
        self,
        project_id: str,
        company_name: str,
        role: str,
        **kwargs
    ) -> ProjectContractor:
        """Add a contractor (GC/sub) to a project."""
        session = self._get_session()
        try:
            contractor = ProjectContractor(
                project_id=project_id,
                company_name=company_name,
                role=role,
                **kwargs
            )
            session.add(contractor)
            session.commit()
            session.refresh(contractor)
            return contractor
        except Exception as e:
            session.rollback()
            raise
        finally:
            self._close_session(session)

    def get_project_contractors(
        self,
        project_id: str,
        role: str = None
    ) -> List[ProjectContractor]:
        """Get contractors for a project, optionally filtered by role."""
        session = self._get_session()
        try:
            query = session.query(ProjectContractor).filter(
                ProjectContractor.project_id == project_id
            )
            if role:
                query = query.filter(ProjectContractor.role == role)
            return query.all()
        finally:
            self._close_session(session)

    # ==================== STATISTICS ====================

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get statistics for dashboard display."""
        session = self._get_session()
        try:
            total = session.query(func.count(Project.id)).filter(
                Project.archived == False
            ).scalar()

            opportunity_count = session.query(func.count(Project.id)).filter(
                Project.archived == False,
                Project.workflow_status == self.STATUS_BID_OPPORTUNITY
            ).scalar()

            bidding_count = session.query(func.count(Project.id)).filter(
                Project.archived == False,
                Project.workflow_status == self.STATUS_BIDDING
            ).scalar()

            awarded_count = session.query(func.count(Project.id)).filter(
                Project.archived == False,
                Project.workflow_status.in_([
                    self.STATUS_GC_AWARDED,
                    self.STATUS_UNDER_CONTRACT
                ])
            ).scalar()

            archived_count = session.query(func.count(Project.id)).filter(
                Project.archived == True
            ).scalar()

            # By source
            by_source = session.query(
                Project.source,
                func.count(Project.id)
            ).filter(Project.archived == False).group_by(Project.source).all()

            return {
                'total': total,
                'bid_opportunities': opportunity_count,
                'active_bidding': bidding_count,
                'awarded': awarded_count,
                'archived': archived_count,
                'by_source': {s: c for s, c in by_source if s}
            }
        finally:
            self._close_session(session)


# Singleton instance for convenience
_repository = None


def get_repository() -> ProjectRepository:
    """Get the singleton repository instance."""
    global _repository
    if _repository is None:
        _repository = ProjectRepository()
    return _repository
