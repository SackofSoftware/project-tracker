"""
Deduplication Service - Cross-Source Project Matching

Handles intelligent deduplication across all project sources:
- Auto-merges high confidence matches (>=90%)
- Queues medium confidence (70-89%) for user review
- Ignores low confidence (<50%)
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import re

from sqlalchemy.orm import Session

from .db import get_session, SessionLocal
from .models import (
    Project, ProjectSourceLink, DeduplicationLog, PendingDuplicate
)
from .project_repository import ProjectRepository


class DeduplicationService:
    """
    Service for finding and merging duplicate projects across sources.
    """

    # Matching thresholds
    AUTO_MERGE_THRESHOLD = 0.90
    REVIEW_THRESHOLD = 0.70
    IGNORE_THRESHOLD = 0.50

    # Scoring weights
    WEIGHTS = {
        'name_similarity': 0.35,
        'address_match': 0.25,
        'zip_match': 0.15,
        'city_state_match': 0.10,
        'bid_date_proximity': 0.10,
        'owner_match': 0.05,
    }

    # Division 8 bonuses/penalties
    DIV8_MATCH_BONUS = 0.15
    DIV8_MISMATCH_PENALTY = 0.10

    def __init__(self, session: Session = None):
        self._session = session
        self._owns_session = session is None

    def _get_session(self) -> Session:
        if self._session:
            return self._session
        return SessionLocal()

    def _close_session(self, session: Session):
        if self._owns_session and session:
            session.close()

    # ==================== MATCHING ALGORITHM ====================

    def calculate_match_score(
        self,
        project_a: Dict[str, Any],
        project_b: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate match confidence between two projects.
        Returns (total_score, breakdown_dict).
        """
        scores = {}

        # Name similarity (fuzzy matching)
        name_a = self._normalize_name(project_a.get('title', ''))
        name_b = self._normalize_name(project_b.get('title', ''))
        name_sim = SequenceMatcher(None, name_a, name_b).ratio()
        scores['name_similarity'] = name_sim * self.WEIGHTS['name_similarity']

        # Bonus for very high name similarity
        if name_sim >= 0.85:
            scores['name_similarity'] += 0.10

        # Address match
        addr_a = self._normalize_address(project_a.get('address', ''))
        addr_b = self._normalize_address(project_b.get('address', ''))
        if addr_a and addr_b:
            addr_sim = SequenceMatcher(None, addr_a, addr_b).ratio()
            if addr_sim >= 0.90:
                scores['address_match'] = self.WEIGHTS['address_match']
            elif addr_sim >= 0.70:
                scores['address_match'] = self.WEIGHTS['address_match'] * 0.5
            else:
                scores['address_match'] = 0
        else:
            scores['address_match'] = 0

        # ZIP code match
        zip_a = self._extract_zip(project_a)
        zip_b = self._extract_zip(project_b)
        if zip_a and zip_b:
            if zip_a == zip_b:
                scores['zip_match'] = self.WEIGHTS['zip_match']
            elif zip_a[:3] == zip_b[:3]:
                scores['zip_match'] = self.WEIGHTS['zip_match'] * 0.5
            else:
                scores['zip_match'] = 0
        else:
            scores['zip_match'] = 0

        # City + State match
        city_a = (project_a.get('city', '') or '').lower().strip()
        city_b = (project_b.get('city', '') or '').lower().strip()
        state_a = (project_a.get('state', '') or '').upper().strip()
        state_b = (project_b.get('state', '') or '').upper().strip()

        if city_a and city_b and city_a == city_b:
            if state_a and state_b and state_a == state_b:
                scores['city_state_match'] = self.WEIGHTS['city_state_match']
            else:
                scores['city_state_match'] = self.WEIGHTS['city_state_match'] * 0.5
        else:
            scores['city_state_match'] = 0

        # Bid date proximity
        date_a = project_a.get('bid_date')
        date_b = project_b.get('bid_date')
        if date_a and date_b:
            if isinstance(date_a, str):
                date_a = datetime.fromisoformat(date_a.replace('Z', '+00:00'))
            if isinstance(date_b, str):
                date_b = datetime.fromisoformat(date_b.replace('Z', '+00:00'))

            # Handle date objects
            if hasattr(date_a, 'date'):
                date_a = date_a.date() if hasattr(date_a, 'date') else date_a
            if hasattr(date_b, 'date'):
                date_b = date_b.date() if hasattr(date_b, 'date') else date_b

            try:
                diff_days = abs((date_a - date_b).days)
                if diff_days <= 3:
                    scores['bid_date_proximity'] = self.WEIGHTS['bid_date_proximity']
                elif diff_days <= 7:
                    scores['bid_date_proximity'] = self.WEIGHTS['bid_date_proximity'] * 0.7
                elif diff_days <= 14:
                    scores['bid_date_proximity'] = self.WEIGHTS['bid_date_proximity'] * 0.3
                else:
                    scores['bid_date_proximity'] = 0
            except:
                scores['bid_date_proximity'] = 0
        else:
            scores['bid_date_proximity'] = 0

        # Owner match
        owner_a = self._normalize_name(project_a.get('owner_name', '') or project_a.get('owner', ''))
        owner_b = self._normalize_name(project_b.get('owner_name', '') or project_b.get('owner', ''))
        if owner_a and owner_b:
            owner_sim = SequenceMatcher(None, owner_a, owner_b).ratio()
            scores['owner_match'] = owner_sim * self.WEIGHTS['owner_match']
        else:
            scores['owner_match'] = 0

        # Division 8 trade matching
        div8_a = self._is_division_8(project_a)
        div8_b = self._is_division_8(project_b)

        if div8_a and div8_b:
            # Both are Division 8 - bonus based on trade overlap
            trades_a = self._extract_trades(project_a)
            trades_b = self._extract_trades(project_b)
            if trades_a and trades_b:
                overlap = len(trades_a & trades_b) / max(len(trades_a | trades_b), 1)
                scores['div8_bonus'] = overlap * self.DIV8_MATCH_BONUS
            else:
                scores['div8_bonus'] = self.DIV8_MATCH_BONUS * 0.5
        elif div8_a != div8_b and (div8_a or div8_b):
            # One is Division 8, other isn't - penalty
            scores['div8_penalty'] = -self.DIV8_MISMATCH_PENALTY
        else:
            scores['div8_bonus'] = 0

        # Calculate total
        total = sum(scores.values())

        return min(total, 1.0), scores

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison."""
        if not name:
            return ''
        # Remove common prefixes/suffixes
        name = re.sub(r'\b(the|a|an|at|for)\b', '', name.lower())
        # Remove special characters
        name = re.sub(r'[^\w\s]', '', name)
        # Collapse whitespace
        name = re.sub(r'\s+', ' ', name).strip()
        return name

    def _normalize_address(self, address: str) -> str:
        """Normalize an address for comparison."""
        if not address:
            return ''
        address = address.lower()
        # Standardize abbreviations
        replacements = {
            r'\bstreet\b': 'st',
            r'\bst\.\b': 'st',
            r'\bavenue\b': 'ave',
            r'\bave\.\b': 'ave',
            r'\bdrive\b': 'dr',
            r'\bdr\.\b': 'dr',
            r'\broad\b': 'rd',
            r'\brd\.\b': 'rd',
            r'\bboulevard\b': 'blvd',
            r'\bblvd\.\b': 'blvd',
        }
        for pattern, repl in replacements.items():
            address = re.sub(pattern, repl, address)
        # Remove apartment/suite numbers
        address = re.sub(r'\b(apt|suite|ste|unit|#)\s*\d+\b', '', address)
        # Collapse whitespace
        address = re.sub(r'\s+', ' ', address).strip()
        return address

    def _extract_zip(self, project: Dict[str, Any]) -> str:
        """Extract ZIP code from project."""
        zip_code = project.get('zip_code', '') or ''
        if zip_code:
            # Extract 5-digit ZIP
            match = re.search(r'\d{5}', str(zip_code))
            if match:
                return match.group()
        return ''

    def _is_division_8(self, project: Dict[str, Any]) -> bool:
        """Check if project has Division 8 scope."""
        # Check explicit flag
        if project.get('is_division_8'):
            return True

        # Check trades
        trades = project.get('trades', '') or ''
        div8_keywords = ['window', 'door', 'glazing', 'storefront', 'curtain wall', 'hardware']
        return any(kw in trades.lower() for kw in div8_keywords)

    def _extract_trades(self, project: Dict[str, Any]) -> set:
        """Extract Division 8 trade keywords from project."""
        trades_str = (project.get('trades', '') or '').lower()
        keywords = {'window', 'door', 'glazing', 'storefront', 'curtainwall', 'hardware', 'glass'}
        return {kw for kw in keywords if kw in trades_str}

    # ==================== DUPLICATE DETECTION ====================

    def find_duplicates_for_project(
        self,
        project: Dict[str, Any],
        existing_projects: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Find potential duplicates for a single project.
        Returns list of {project, score, reasons} dicts.
        """
        matches = []

        for existing in existing_projects:
            if existing.get('id') == project.get('id'):
                continue  # Skip self

            score, reasons = self.calculate_match_score(project, existing)

            if score >= self.IGNORE_THRESHOLD:
                matches.append({
                    'project': existing,
                    'score': score,
                    'reasons': reasons
                })

        # Sort by score descending
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches

    def find_all_potential_duplicates(self) -> List[PendingDuplicate]:
        """
        Scan all projects and find potential duplicates.
        Creates PendingDuplicate records for review.
        """
        session = self._get_session()
        try:
            # Get all active projects
            projects = session.query(Project).filter(
                Project.archived == False
            ).all()

            project_dicts = [self._project_to_dict(p) for p in projects]
            new_duplicates = []

            # Compare each pair (N^2 but necessary)
            for i, proj_a in enumerate(project_dicts):
                for proj_b in project_dicts[i+1:]:
                    score, reasons = self.calculate_match_score(proj_a, proj_b)

                    # Only track if in review range
                    if self.REVIEW_THRESHOLD <= score < self.AUTO_MERGE_THRESHOLD:
                        # Check if already tracked
                        existing = session.query(PendingDuplicate).filter(
                            PendingDuplicate.project_a_id == proj_a['id'],
                            PendingDuplicate.project_b_id == proj_b['id']
                        ).first()

                        if not existing:
                            dup = PendingDuplicate(
                                project_a_id=proj_a['id'],
                                project_b_id=proj_b['id'],
                                project_b_type='project',
                                match_confidence=score,
                                match_reasons=reasons
                            )
                            session.add(dup)
                            new_duplicates.append(dup)

            session.commit()
            return new_duplicates
        finally:
            self._close_session(session)

    def _project_to_dict(self, project: Project) -> Dict[str, Any]:
        """Convert Project model to dict for matching."""
        return {
            'id': project.id,
            'title': project.title,
            'address': project.address,
            'city': project.city,
            'state': project.state,
            'zip_code': project.zip_code,
            'owner_name': project.owner_name,
            'bid_date': project.bid_date,
            'trades': project.trades,
            'is_division_8': getattr(project, 'is_division_8', False),
            'source': project.source
        }

    # ==================== MERGE OPERATIONS ====================

    def auto_merge_if_confident(
        self,
        new_project: Dict[str, Any],
        source_type: str,
        source_id: str
    ) -> Optional[Project]:
        """
        Attempt to auto-merge a new project with existing if confidence >= 90%.
        Returns the canonical project if merged, None otherwise.
        """
        session = self._get_session()
        try:
            # Get existing projects to compare
            existing = session.query(Project).filter(
                Project.archived == False
            ).all()

            best_match = None
            best_score = 0
            best_reasons = {}

            for proj in existing:
                proj_dict = self._project_to_dict(proj)
                score, reasons = self.calculate_match_score(new_project, proj_dict)

                if score > best_score:
                    best_score = score
                    best_match = proj
                    best_reasons = reasons

            if best_score >= self.AUTO_MERGE_THRESHOLD and best_match:
                # Auto-merge: link source to existing project
                repo = ProjectRepository(session)
                repo.add_source_link(
                    project_id=best_match.id,
                    source_type=source_type,
                    source_id=source_id,
                    source_data=new_project,
                    match_confidence=best_score,
                    match_type='auto'
                )

                # Log the merge
                log = DeduplicationLog(
                    canonical_project_id=best_match.id,
                    merged_source_type=source_type,
                    merged_source_id=source_id,
                    match_confidence=best_score,
                    match_reasons=best_reasons,
                    decision='auto_merged',
                    decided_by='system',
                    pre_merge_snapshot=new_project
                )
                session.add(log)
                session.commit()

                return best_match

            elif best_score >= self.REVIEW_THRESHOLD and best_match:
                # Create pending duplicate for review
                pending = PendingDuplicate(
                    project_a_id=best_match.id,
                    project_b_id=source_id,
                    project_b_type=source_type,
                    match_confidence=best_score,
                    match_reasons=best_reasons
                )
                session.add(pending)
                session.commit()

            return None
        finally:
            self._close_session(session)

    def merge_projects(
        self,
        canonical_id: str,
        source_type: str,
        source_id: str,
        source_data: Dict[str, Any],
        merged_by: str = 'user'
    ) -> Project:
        """
        Manually merge a source into a canonical project.
        """
        session = self._get_session()
        try:
            repo = ProjectRepository(session)

            # Get canonical project
            canonical = session.query(Project).filter(
                Project.id == canonical_id
            ).first()
            if not canonical:
                raise ValueError(f"Canonical project not found: {canonical_id}")

            # Add source link
            repo.add_source_link(
                project_id=canonical_id,
                source_type=source_type,
                source_id=source_id,
                source_data=source_data,
                match_confidence=1.0,
                match_type='manual'
            )

            # Log the merge
            log = DeduplicationLog(
                canonical_project_id=canonical_id,
                merged_source_type=source_type,
                merged_source_id=source_id,
                match_confidence=1.0,
                match_reasons={'manual_merge': True},
                decision='user_approved',
                decided_by=merged_by,
                pre_merge_snapshot=source_data
            )
            session.add(log)

            # Remove from pending if exists
            session.query(PendingDuplicate).filter(
                PendingDuplicate.project_a_id == canonical_id,
                PendingDuplicate.project_b_id == source_id
            ).delete()

            session.commit()
            return canonical
        finally:
            self._close_session(session)

    def reject_duplicate(
        self,
        pending_id: int,
        rejected_by: str = 'user',
        notes: str = None
    ):
        """Mark a pending duplicate as not a duplicate."""
        session = self._get_session()
        try:
            pending = session.query(PendingDuplicate).filter(
                PendingDuplicate.id == pending_id
            ).first()

            if pending:
                pending.status = 'rejected'
                pending.reviewed_by = rejected_by
                pending.reviewed_at = datetime.now()
                pending.review_notes = notes

                # Log the rejection
                log = DeduplicationLog(
                    canonical_project_id=pending.project_a_id,
                    merged_source_type=pending.project_b_type,
                    merged_source_id=pending.project_b_id,
                    match_confidence=pending.match_confidence,
                    match_reasons=pending.match_reasons,
                    decision='user_rejected',
                    decided_by=rejected_by
                )
                session.add(log)
                session.commit()
        finally:
            self._close_session(session)

    # ==================== PENDING REVIEW ====================

    def get_pending_duplicates(self, limit: int = 50) -> List[PendingDuplicate]:
        """Get pending duplicates for review, ordered by confidence."""
        session = self._get_session()
        try:
            return session.query(PendingDuplicate).filter(
                PendingDuplicate.status == 'pending'
            ).order_by(
                PendingDuplicate.match_confidence.desc()
            ).limit(limit).all()
        finally:
            self._close_session(session)

    def get_pending_count(self) -> int:
        """Get count of pending duplicates."""
        session = self._get_session()
        try:
            return session.query(PendingDuplicate).filter(
                PendingDuplicate.status == 'pending'
            ).count()
        finally:
            self._close_session(session)


# Singleton instance
_service = None


def get_dedup_service() -> DeduplicationService:
    """Get the singleton deduplication service."""
    global _service
    if _service is None:
        _service = DeduplicationService()
    return _service
