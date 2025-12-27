"""
Project Link Service

Central service for all project source linking operations.
Handles creating, removing, and querying links between external sources
and canonical local projects.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from modules.database.db import get_session
from modules.database.models import ProjectSourceLink, Project

logger = logging.getLogger(__name__)


class ProjectLinkService:
    """Central service for managing project source links"""

    VALID_SOURCE_TYPES = {'planhub', 'projectdog', 'email', 'govwin'}

    def link_project(
        self,
        project_id: str,
        source_type: str,
        source_id: str,
        confidence: float = 1.0,
        match_type: str = 'manual',
        matched_by: str = 'user',
        source_data: Optional[Dict] = None
    ) -> Optional[ProjectSourceLink]:
        """
        Create a link between an external source and a local project.

        Args:
            project_id: Local project ID (canonical)
            source_type: External source type ('planhub', 'projectdog', etc.)
            source_id: ID in the external system
            confidence: Match confidence score (0-1)
            match_type: How the match was made ('auto', 'manual', 'suggested')
            matched_by: Who/what created the link ('system', 'user', username)
            source_data: Optional snapshot of external source data

        Returns:
            ProjectSourceLink instance or None if failed
        """
        if source_type not in self.VALID_SOURCE_TYPES:
            logger.error(f"Invalid source_type: {source_type}")
            return None

        with get_session() as session:
            # Check if project exists in projects table
            project = session.query(Project).filter(Project.id == project_id).first()

            if not project:
                # Project doesn't exist - create stub record
                logger.info(f"Project {project_id} not found in database, creating stub record")

                # Try to get project name from unified project list
                from utils import find_project_by_id
                unified_project = find_project_by_id(project_id)

                project_name = None
                if unified_project:
                    # Try different fields for the name
                    project_name = (
                        unified_project.get('name') or
                        unified_project.get('title') or
                        unified_project.get('folder') or
                        project_id
                    )
                else:
                    project_name = project_id

                # Create minimal stub Project record
                project = Project(
                    id=project_id,
                    title=project_name,
                    source='email'  # Default to email since that's the most common case for stub records
                )
                session.add(project)
                session.flush()  # Flush to ensure the project is in the database before creating the link
                logger.info(f"Created stub Project record for {project_id} with title '{project_name}'")

            # Check if link already exists
            existing = session.query(ProjectSourceLink).filter(
                ProjectSourceLink.source_type == source_type,
                ProjectSourceLink.source_id == source_id
            ).first()

            if existing:
                # Update existing link
                existing.project_id = project_id
                existing.match_confidence = confidence
                existing.match_type = match_type
                existing.matched_by = matched_by
                existing.source_data = source_data or existing.source_data
                existing.updated_at = datetime.utcnow()
                session.commit()
                # Access attributes to ensure they're loaded before session closes
                _ = (existing.id, existing.project_id, existing.source_type, existing.source_id,
                     existing.match_confidence, existing.match_type, existing.matched_by,
                     existing.created_at, existing.updated_at)
                session.expunge(existing)  # Detach from session to prevent lazy loading issues
                logger.info(f"Updated link: {source_type}:{source_id} -> {project_id}")
                return existing

            # Create new link
            link = ProjectSourceLink(
                project_id=project_id,
                source_type=source_type,
                source_id=source_id,
                match_confidence=confidence,
                match_type=match_type,
                matched_by=matched_by,
                source_data=source_data
            )
            session.add(link)
            session.commit()
            # Access attributes to ensure they're loaded before session closes
            _ = (link.id, link.project_id, link.source_type, link.source_id,
                 link.match_confidence, link.match_type, link.matched_by,
                 link.created_at, link.updated_at)
            session.expunge(link)  # Detach from session to prevent lazy loading issues
            logger.info(f"Created link: {source_type}:{source_id} -> {project_id}")
            return link

    def unlink_project(
        self,
        project_id: str,
        source_type: str,
        source_id: str
    ) -> bool:
        """
        Remove a link between an external source and a local project.

        Returns True if link was removed, False if not found
        """
        with get_session() as session:
            link = session.query(ProjectSourceLink).filter(
                ProjectSourceLink.project_id == project_id,
                ProjectSourceLink.source_type == source_type,
                ProjectSourceLink.source_id == source_id
            ).first()

            if link:
                session.delete(link)
                session.commit()
                logger.info(f"Removed link: {source_type}:{source_id} -> {project_id}")
                return True

            logger.warning(f"Link not found: {source_type}:{source_id} -> {project_id}")
            return False

    def get_linked_sources(self, project_id: str) -> List[Dict]:
        """
        Get all external sources linked to a project.

        Returns list of dicts with source info
        """
        with get_session() as session:
            links = session.query(ProjectSourceLink).filter(
                ProjectSourceLink.project_id == project_id
            ).all()

            return [
                {
                    'id': link.id,
                    'source_type': link.source_type,
                    'source_id': link.source_id,
                    'source_data': link.source_data,
                    'confidence': link.match_confidence,
                    'match_type': link.match_type,
                    'matched_by': link.matched_by,
                    'created_at': link.created_at.isoformat() if link.created_at else None,
                    'updated_at': link.updated_at.isoformat() if link.updated_at else None
                }
                for link in links
            ]

    def get_link_by_source(self, source_type: str, source_id: str) -> Optional[Dict]:
        """
        Find the local project linked to a specific external source.

        Returns dict with link info or None if not linked
        """
        with get_session() as session:
            link = session.query(ProjectSourceLink).filter(
                ProjectSourceLink.source_type == source_type,
                ProjectSourceLink.source_id == source_id
            ).first()

            if link:
                return {
                    'project_id': link.project_id,
                    'source_type': link.source_type,
                    'source_id': link.source_id,
                    'confidence': link.match_confidence,
                    'match_type': link.match_type
                }
            return None

    def get_all_links_by_source_type(self, source_type: str) -> Dict[str, str]:
        """
        Get all links for a source type as {source_id: project_id} mapping.

        Useful for batch matching operations.
        """
        with get_session() as session:
            links = session.query(ProjectSourceLink).filter(
                ProjectSourceLink.source_type == source_type
            ).all()

            return {link.source_id: link.project_id for link in links}

    def get_unlinked_by_source(
        self,
        source_type: str,
        source_ids: List[str]
    ) -> List[str]:
        """
        Given a list of source IDs, return those that are not linked.

        Args:
            source_type: The source type
            source_ids: List of source IDs to check

        Returns:
            List of source_ids that have no link
        """
        with get_session() as session:
            linked = session.query(ProjectSourceLink.source_id).filter(
                ProjectSourceLink.source_type == source_type,
                ProjectSourceLink.source_id.in_(source_ids)
            ).all()

            linked_ids = {row[0] for row in linked}
            return [sid for sid in source_ids if sid not in linked_ids]

    def bulk_create_links(
        self,
        links: List[Dict],
        matched_by: str = 'system'
    ) -> Dict[str, int]:
        """
        Create multiple links in a single transaction.

        Args:
            links: List of dicts with keys:
                - project_id, source_type, source_id, confidence, match_type
                - Optional: source_data
            matched_by: Who/what is creating these links

        Returns:
            {'created': N, 'updated': M, 'errors': K}
        """
        stats = {'created': 0, 'updated': 0, 'errors': 0}

        with get_session() as session:
            for link_data in links:
                try:
                    source_type = link_data.get('source_type')
                    source_id = link_data.get('source_id')

                    if not source_type or not source_id:
                        stats['errors'] += 1
                        continue

                    # Check existing
                    existing = session.query(ProjectSourceLink).filter(
                        ProjectSourceLink.source_type == source_type,
                        ProjectSourceLink.source_id == source_id
                    ).first()

                    if existing:
                        existing.project_id = link_data.get('project_id')
                        existing.match_confidence = link_data.get('confidence', 1.0)
                        existing.match_type = link_data.get('match_type', 'auto')
                        existing.matched_by = matched_by
                        existing.source_data = link_data.get('source_data')
                        existing.updated_at = datetime.utcnow()
                        stats['updated'] += 1
                    else:
                        link = ProjectSourceLink(
                            project_id=link_data.get('project_id'),
                            source_type=source_type,
                            source_id=source_id,
                            match_confidence=link_data.get('confidence', 1.0),
                            match_type=link_data.get('match_type', 'auto'),
                            matched_by=matched_by,
                            source_data=link_data.get('source_data')
                        )
                        session.add(link)
                        stats['created'] += 1

                except Exception as e:
                    logger.error(f"Error creating link: {e}")
                    stats['errors'] += 1

            session.commit()

        logger.info(f"Bulk link: created={stats['created']}, updated={stats['updated']}, errors={stats['errors']}")
        return stats

    def get_stats(self) -> Dict[str, Any]:
        """Get link statistics by source type"""
        with get_session() as session:
            from sqlalchemy import func

            stats = {}

            # Count by source type
            counts = session.query(
                ProjectSourceLink.source_type,
                func.count(ProjectSourceLink.id)
            ).group_by(ProjectSourceLink.source_type).all()

            for source_type, count in counts:
                stats[source_type] = {
                    'total_links': count,
                    'auto': 0,
                    'manual': 0,
                    'suggested': 0
                }

            # Count by match type
            type_counts = session.query(
                ProjectSourceLink.source_type,
                ProjectSourceLink.match_type,
                func.count(ProjectSourceLink.id)
            ).group_by(
                ProjectSourceLink.source_type,
                ProjectSourceLink.match_type
            ).all()

            for source_type, match_type, count in type_counts:
                if source_type in stats and match_type:
                    stats[source_type][match_type] = count

            return stats


# Module-level singleton
_link_service = None


def get_link_service() -> ProjectLinkService:
    """Get or create the global link service instance"""
    global _link_service
    if _link_service is None:
        _link_service = ProjectLinkService()
    return _link_service
