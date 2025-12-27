"""
Base Project Matcher

Provides standardized fuzzy matching logic for linking external project sources
to canonical local projects. All source-specific matchers inherit from this.

Scoring formula:
- Name similarity: 0-0.70 points (fuzzy string matching)
- Location match: 0.20 points (city + state exact match)
- Bid date proximity: 0.10 points (within 7 days)

Thresholds:
- Auto-match: >= 0.65 confidence
- Suggested: >= 0.45 confidence
"""

from abc import ABC, abstractmethod
from difflib import SequenceMatcher
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import re
import logging

logger = logging.getLogger(__name__)


class BaseProjectMatcher(ABC):
    """Base class for all project source matchers"""

    # Matching thresholds
    AUTO_MATCH_THRESHOLD = 0.65
    SUGGEST_THRESHOLD = 0.45

    # Scoring weights
    NAME_WEIGHT = 0.70
    LOCATION_WEIGHT = 0.20
    DATE_WEIGHT = 0.10

    # Date proximity window
    DATE_PROXIMITY_DAYS = 7

    @abstractmethod
    def get_source_type(self) -> str:
        """Return the source type identifier (e.g., 'planhub', 'projectdog')"""
        pass

    @abstractmethod
    def get_source_id(self, source_project: Dict) -> str:
        """Extract the unique source ID from a source project dict"""
        pass

    @abstractmethod
    def get_source_name(self, source_project: Dict) -> str:
        """Extract the project name from a source project dict"""
        pass

    @abstractmethod
    def get_source_location(self, source_project: Dict) -> Tuple[Optional[str], Optional[str]]:
        """Extract (city, state) from a source project dict"""
        pass

    @abstractmethod
    def get_source_bid_date(self, source_project: Dict) -> Optional[datetime]:
        """Extract bid date from a source project dict"""
        pass

    def _normalize_name(self, name: str) -> str:
        """Normalize a project name for comparison"""
        if not name:
            return ""
        # Lowercase, remove special chars, collapse whitespace
        name = name.lower()
        name = re.sub(r'[^\w\s]', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def _name_similarity(self, source_project: Dict, local_project: Dict) -> float:
        """
        Calculate name similarity between source and local project.
        Compares against both title and folder name.
        """
        source_name = self._normalize_name(self.get_source_name(source_project))
        if not source_name:
            return 0.0

        # Get local project names
        local_title = self._normalize_name(local_project.get('title', ''))
        local_folder = self._normalize_name(local_project.get('folder', ''))

        # Calculate similarity against both
        title_sim = SequenceMatcher(None, source_name, local_title).ratio() if local_title else 0
        folder_sim = SequenceMatcher(None, source_name, local_folder).ratio() if local_folder else 0

        return max(title_sim, folder_sim)

    def _location_matches(self, source_project: Dict, local_project: Dict) -> bool:
        """Check if source and local project have matching city and state"""
        source_city, source_state = self.get_source_location(source_project)

        # Get local project location
        location = local_project.get('location', {})
        if isinstance(location, dict):
            local_city = location.get('city', '')
            local_state = location.get('state', '')
        else:
            local_city = local_project.get('city', '')
            local_state = local_project.get('state', '')

        # Normalize for comparison
        source_city = (source_city or '').lower().strip()
        source_state = (source_state or '').upper().strip()
        local_city = (local_city or '').lower().strip()
        local_state = (local_state or '').upper().strip()

        # Both city and state must match (if available)
        if source_state and local_state and source_state != local_state:
            return False

        if source_city and local_city:
            # Fuzzy city match (handles "N. Attleboro" vs "North Attleboro")
            city_sim = SequenceMatcher(None, source_city, local_city).ratio()
            return city_sim >= 0.8

        return False

    def _dates_within_days(self, source_project: Dict, local_project: Dict, days: int = None) -> bool:
        """Check if bid dates are within N days of each other"""
        days = days or self.DATE_PROXIMITY_DAYS

        source_date = self.get_source_bid_date(source_project)
        local_date_str = local_project.get('bid_date')

        if not source_date or not local_date_str:
            return False

        # Parse local date if string
        if isinstance(local_date_str, str):
            try:
                # Try common formats
                for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        local_date = datetime.strptime(local_date_str[:19], fmt)
                        break
                    except ValueError:
                        continue
                else:
                    return False
            except Exception:
                return False
        elif isinstance(local_date_str, datetime):
            local_date = local_date_str
        else:
            return False

        # Compare dates
        diff = abs((source_date - local_date).days)
        return diff <= days

    def calculate_match_score(self, source_project: Dict, local_project: Dict) -> float:
        """
        Calculate match confidence score between source and local project.

        Returns float between 0.0 and 1.0
        """
        score = 0.0

        # Name similarity (max 0.70)
        name_sim = self._name_similarity(source_project, local_project)
        score += min(name_sim * self.NAME_WEIGHT, self.NAME_WEIGHT)

        # Location match (0.20)
        if self._location_matches(source_project, local_project):
            score += self.LOCATION_WEIGHT

        # Bid date proximity (0.10)
        if self._dates_within_days(source_project, local_project):
            score += self.DATE_WEIGHT

        return min(score, 1.0)

    def find_matches(
        self,
        source_projects: List[Dict],
        local_projects: List[Dict],
        existing_links: Optional[Dict[str, str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Find matches between source projects and local projects.

        Args:
            source_projects: List of projects from external source
            local_projects: List of canonical local projects
            existing_links: Optional dict of {source_id: project_id} for already-linked projects

        Returns:
            {
                'auto': [{'source': {...}, 'local': {...}, 'confidence': 0.85, 'type': 'auto'}, ...],
                'suggested': [{'source': {...}, 'local': {...}, 'confidence': 0.52, 'type': 'suggested'}, ...]
            }
        """
        existing_links = existing_links or {}
        auto_matches = []
        suggested = []

        for source_proj in source_projects:
            source_id = self.get_source_id(source_proj)

            # Skip if already linked
            if source_id in existing_links:
                continue

            best_score = 0.0
            best_match = None

            for local_proj in local_projects:
                score = self.calculate_match_score(source_proj, local_proj)
                if score > best_score:
                    best_score = score
                    best_match = local_proj

            if best_score >= self.AUTO_MATCH_THRESHOLD and best_match:
                auto_matches.append({
                    'source': source_proj,
                    'source_id': source_id,
                    'local': best_match,
                    'local_id': best_match.get('id'),
                    'confidence': round(best_score, 3),
                    'type': 'auto'
                })
                logger.debug(f"Auto-match: {self.get_source_name(source_proj)} -> {best_match.get('title')} ({best_score:.2f})")

            elif best_score >= self.SUGGEST_THRESHOLD and best_match:
                suggested.append({
                    'source': source_proj,
                    'source_id': source_id,
                    'local': best_match,
                    'local_id': best_match.get('id'),
                    'confidence': round(best_score, 3),
                    'type': 'suggested'
                })
                logger.debug(f"Suggested: {self.get_source_name(source_proj)} -> {best_match.get('title')} ({best_score:.2f})")

        logger.info(f"{self.get_source_type()}: {len(auto_matches)} auto-matches, {len(suggested)} suggestions")
        return {'auto': auto_matches, 'suggested': suggested}

    def find_best_match(
        self,
        source_project: Dict,
        local_projects: List[Dict]
    ) -> Tuple[Optional[Dict], float]:
        """
        Find the best matching local project for a single source project.

        Returns (best_match, confidence) or (None, 0.0) if no good match
        """
        best_score = 0.0
        best_match = None

        for local_proj in local_projects:
            score = self.calculate_match_score(source_project, local_proj)
            if score > best_score:
                best_score = score
                best_match = local_proj

        if best_score >= self.SUGGEST_THRESHOLD:
            return (best_match, best_score)

        return (None, 0.0)
