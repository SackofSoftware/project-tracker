"""
ProjectDog Project Matcher

Matches ProjectDog scraped projects to canonical local projects.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging

from .base_matcher import BaseProjectMatcher

logger = logging.getLogger(__name__)


class ProjectDogMatcher(BaseProjectMatcher):
    """Matcher for ProjectDog projects"""

    def get_source_type(self) -> str:
        return 'projectdog'

    def get_source_id(self, source_project: Dict) -> str:
        """ProjectDog uses project_code as unique ID"""
        return source_project.get('project_code', '')

    def get_source_name(self, source_project: Dict) -> str:
        """Get project title"""
        return source_project.get('title', '')

    def get_source_location(self, source_project: Dict) -> Tuple[Optional[str], Optional[str]]:
        """Extract city and state from ProjectDog project"""
        city = source_project.get('city')
        state = source_project.get('state')

        # Also check location_raw if city/state not set
        if not city and source_project.get('location_raw'):
            import re
            # Try to parse "City, STATE" pattern
            match = re.search(r'([^,]+),\s*([A-Z]{2})', source_project.get('location_raw', ''))
            if match:
                city = match.group(1).strip()
                state = match.group(2)

        return (city, state)

    def get_source_bid_date(self, source_project: Dict) -> Optional[datetime]:
        """Extract bid date from ProjectDog project"""
        bid_date = source_project.get('bid_date')

        if not bid_date:
            return None

        if isinstance(bid_date, datetime):
            return bid_date

        if isinstance(bid_date, str):
            # Try common formats
            for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%m/%d/%Y']:
                try:
                    return datetime.strptime(bid_date[:19], fmt)
                except ValueError:
                    continue

        return None


def match_projectdog_projects(
    projectdog_projects: List[Dict],
    local_projects: List[Dict],
    existing_links: Optional[Dict[str, str]] = None
) -> Dict[str, List[Dict]]:
    """
    Convenience function to match ProjectDog projects to local projects.

    Args:
        projectdog_projects: List of ProjectDog project dicts
        local_projects: List of local project dicts
        existing_links: Optional {project_code: local_project_id} for already-linked

    Returns:
        {'auto': [...], 'suggested': [...]}
    """
    matcher = ProjectDogMatcher()
    return matcher.find_matches(projectdog_projects, local_projects, existing_links)
