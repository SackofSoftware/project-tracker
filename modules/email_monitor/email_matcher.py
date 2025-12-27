"""
Email-Project Matcher

Matches emails from Email Monitor to local bidding projects using:
- Fuzzy string matching on project names
- Location matching (city, state extraction)
- Bid date proximity
- Manual override capability

Based on PlanHubLocalMatcher pattern with similar scoring weights.
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from .email_reader import EmailRecord


class EmailProjectMatcher:
    """
    Matcher for linking Email Monitor emails to projects.

    Scoring (mirrors PlanHub matcher):
    - Name similarity: 0-0.70 points (primary signal)
    - Location match: 0.20 points (city+state)
    - Bid date proximity: 0.10 points (within 7 days)

    Manual links take precedence (confidence = 1.0)
    Auto-match threshold: 0.65
    """

    def __init__(self, data_dir: str = None):
        """
        Initialize the matcher.

        Args:
            data_dir: Path to data directory containing email_project_links.json.
                     Defaults to static/data in project root.
        """
        if data_dir is None:
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "static" / "data"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.links_file = self.data_dir / "email_project_links.json"
        self.match_cache_file = self.data_dir / "email_match_cache.json"
        self.manual_links = self._load_manual_links()

    def _load_manual_links(self) -> Dict[str, str]:
        """
        Load manual email-project links from JSON file.

        Returns:
            Dict mapping email IDs to project IDs
        """
        if not self.links_file.exists():
            return {}

        try:
            with open(self.links_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading email links: {e}")
            return {}

    def _save_manual_links(self) -> bool:
        """
        Save manual links to JSON file.

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(self.links_file, 'w') as f:
                json.dump(self.manual_links, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving email links: {e}")
            return False

    def link_email(self, email_id: str, project_id: str) -> bool:
        """
        Manually link an email to a project.

        Args:
            email_id: Email identifier
            project_id: Project ID to link to

        Returns:
            True if link was saved successfully
        """
        self.manual_links[email_id] = project_id
        return self._save_manual_links()

    def unlink_email(self, email_id: str) -> bool:
        """
        Remove a manual link for an email.

        Args:
            email_id: Email identifier

        Returns:
            True if unlink was saved successfully
        """
        if email_id in self.manual_links:
            del self.manual_links[email_id]
            return self._save_manual_links()
        return True

    def get_link(self, email_id: str) -> Optional[str]:
        """
        Get the manual link for an email.

        Args:
            email_id: Email identifier

        Returns:
            Project ID if linked, None otherwise
        """
        return self.manual_links.get(email_id)

    def _string_similarity(self, str1: str, str2: str) -> float:
        """
        Calculate similarity ratio between two strings.

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity ratio between 0 and 1
        """
        if not str1 or not str2:
            return 0.0

        # Normalize strings: lowercase, remove extra whitespace
        s1 = ' '.join(str1.lower().split())
        s2 = ' '.join(str2.lower().split())

        return SequenceMatcher(None, s1, s2).ratio()

    def _extract_location_from_email(self, email: EmailRecord) -> Tuple[str, str]:
        """
        Extract city and state from email project folder name or project name.

        Common patterns:
        - "Project Name - City, State"
        - "Project Name City State (GC Name)"
        - "2025-MM-DD_City, State"

        Args:
            email: EmailRecord to extract location from

        Returns:
            Tuple of (city, state)
        """
        # Try project name first, then folder name
        sources = [email.project_name, email.project_folder]

        for source in sources:
            if not source:
                continue

            # Strip GC name in parentheses
            source = re.sub(r'\s*\([^)]+\)\s*$', '', source)

            # Pattern: "- City, STATE" or "- City STATE"
            match = re.search(r'[-_]\s*([A-Za-z\s]+),?\s*([A-Z]{2})\s*$', source)
            if match:
                return match.group(1).strip(), match.group(2)

            # Pattern: "City, STATE" anywhere
            match = re.search(r'([A-Za-z\s]+),\s*([A-Z]{2})(?:\s|$)', source)
            if match:
                return match.group(1).strip(), match.group(2)

        return '', ''

    def _parse_date(self, date_val) -> Optional[datetime]:
        """
        Parse date from various formats.

        Args:
            date_val: Date value (string or datetime)

        Returns:
            datetime object or None
        """
        if isinstance(date_val, datetime):
            return date_val

        if not date_val:
            return None

        date_str = str(date_val)

        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%Y-%m-%dT%H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.split('T')[0], fmt.split('T')[0])
            except ValueError:
                continue

        return None

    def _dates_within_days(self, date1, date2, days: int = 7) -> bool:
        """
        Check if two dates are within N days of each other.

        Args:
            date1: First date
            date2: Second date
            days: Maximum days apart

        Returns:
            True if dates are within the threshold
        """
        d1 = self._parse_date(date1)
        d2 = self._parse_date(date2)

        if not d1 or not d2:
            return False

        delta = abs((d1 - d2).days)
        return delta <= days

    def _calculate_match_score(
        self,
        email: EmailRecord,
        project: Dict
    ) -> Tuple[float, Dict]:
        """
        Calculate match score between an email and a project.

        Same scoring as PlanHub matcher for consistency.

        Args:
            email: EmailRecord to match
            project: Project dict

        Returns:
            Tuple of (confidence_score, match_details)
        """
        score = 0.0
        details = {
            'name_similarity': 0.0,
            'location_match': False,
            'bid_date_match': False
        }

        # Name similarity - compare against project title and folder
        email_name = email.project_name or email.project_folder
        project_name = project.get('title') or project.get('folder', '')
        project_folder = project.get('folder', '')

        # Try both title and folder name, use best match
        name_sim = self._string_similarity(email_name, project_name)
        folder_sim = self._string_similarity(email_name, project_folder)

        # Also try email subject for additional signals
        subject_sim = self._string_similarity(email.subject, project_name)

        best_sim = max(name_sim, folder_sim, subject_sim * 0.8)  # Subject weighted slightly less
        details['name_similarity'] = best_sim

        # Name similarity scoring (same as PlanHub)
        # >= 0.8 gets up to 0.7 points
        # >= 0.5 gets up to 0.5 points
        if best_sim >= 0.8:
            score += 0.5 + (0.2 * ((best_sim - 0.8) / 0.2))
        elif best_sim >= 0.5:
            score += 0.5 * ((best_sim - 0.5) / 0.3)

        # Location match (0.20 points)
        email_city, email_state = self._extract_location_from_email(email)
        project_loc = project.get('location', {})

        if isinstance(project_loc, dict):
            project_city = (project_loc.get('city') or '').lower().strip()
            project_state = (project_loc.get('state') or '').upper().strip()

            if email_city and email_state and project_city and project_state:
                if email_city.lower() == project_city and email_state.upper() == project_state:
                    details['location_match'] = True
                    score += 0.20
                    # Bonus for location + name combo
                    if best_sim >= 0.4:
                        score += 0.10

        # Bid date proximity (0.10 points if within 7 days)
        if email.bid_date:
            project_bid = project.get('bid_date')
            if project_bid and self._dates_within_days(email.bid_date, project_bid, 7):
                details['bid_date_match'] = True
                score += 0.10

        return score, details

    def get_best_match(
        self,
        email: EmailRecord,
        projects: List[Dict]
    ) -> Optional[Dict]:
        """
        Find the best local match for an email.

        Args:
            email: EmailRecord to match
            projects: List of project dicts

        Returns:
            Dict with match info or None if no good match found
        """
        # Check for manual link first
        manual_link = self.get_link(email.id)
        if manual_link:
            for proj in projects:
                if proj.get('id') == manual_link:
                    return {
                        'email_id': email.id,
                        'project_id': manual_link,
                        'confidence': 1.0,
                        'match_type': 'manual',
                        'match_details': {'manually_linked': True}
                    }

        # Auto-match: find best scoring match
        best_score = 0.0
        best_match = None
        best_details = None

        for proj in projects:
            score, details = self._calculate_match_score(email, proj)

            if score > best_score:
                best_score = score
                best_match = proj
                best_details = details

        # Return matches with confidence >= 0.65
        if best_score >= 0.65 and best_match:
            return {
                'email_id': email.id,
                'project_id': best_match.get('id'),
                'confidence': round(best_score, 3),
                'match_type': 'auto',
                'match_details': best_details
            }

        return None

    def get_match_suggestions(
        self,
        email: EmailRecord,
        projects: List[Dict],
        limit: int = 3
    ) -> List[Dict]:
        """
        Get top N suggested matches for an email.

        Useful for presenting match options to users for manual linking.

        Args:
            email: EmailRecord to find suggestions for
            projects: List of project dicts
            limit: Maximum number of suggestions to return

        Returns:
            List of match dicts sorted by confidence
        """
        suggestions = []

        for proj in projects:
            score, details = self._calculate_match_score(email, proj)

            # Only include suggestions with minimum score (0.3)
            if score >= 0.3:
                suggestions.append({
                    'project_id': proj.get('id'),
                    'project_title': proj.get('title') or proj.get('folder', ''),
                    'project_folder': proj.get('folder', ''),
                    'confidence': round(score, 3),
                    'match_details': details
                })

        suggestions.sort(key=lambda x: x['confidence'], reverse=True)
        return suggestions[:limit]

    def _get_cache_key(self, emails: List[EmailRecord], projects: List[Dict]) -> str:
        """Generate a cache key based on email and project counts/IDs."""
        import hashlib
        email_ids = sorted([e.id for e in emails])
        project_ids = sorted([p.get('id', '') for p in projects])
        key_str = f"{len(emails)}:{len(projects)}:{email_ids[:5]}:{project_ids[:5]}"
        return hashlib.md5(key_str.encode()).hexdigest()[:12]

    def _load_match_cache(self, cache_key: str) -> Optional[List[Dict]]:
        """Load matches from cache if valid."""
        if not self.match_cache_file.exists():
            return None
        try:
            with open(self.match_cache_file, 'r') as f:
                cache = json.load(f)
            if cache.get('key') == cache_key:
                return cache.get('matches', [])
        except Exception:
            pass
        return None

    def _save_match_cache(self, cache_key: str, matches: List[Dict]):
        """Save matches to cache."""
        try:
            with open(self.match_cache_file, 'w') as f:
                json.dump({'key': cache_key, 'matches': matches}, f)
        except Exception:
            pass

    def find_matches(
        self,
        emails: List[EmailRecord],
        projects: List[Dict],
        use_cache: bool = True
    ) -> List[Dict]:
        """
        Find all matches between emails and projects.

        Args:
            emails: List of EmailRecord objects
            projects: List of project dicts
            use_cache: Whether to use cached results (default True)

        Returns:
            List of match dicts
        """
        # Try cache first
        if use_cache:
            cache_key = self._get_cache_key(emails, projects)
            cached = self._load_match_cache(cache_key)
            if cached is not None:
                return cached

        # Compute matches
        matches = []
        for email in emails:
            match = self.get_best_match(email, projects)
            if match:
                matches.append(match)

        # Save to cache
        if use_cache:
            self._save_match_cache(cache_key, matches)

        return matches

    def get_unmatched_emails(
        self,
        emails: List[EmailRecord],
        projects: List[Dict]
    ) -> List[EmailRecord]:
        """
        Get emails that have no match in projects.

        Args:
            emails: List of EmailRecord objects
            projects: List of project dicts

        Returns:
            List of unmatched EmailRecord objects
        """
        matches = self.find_matches(emails, projects)
        matched_ids = {m['email_id'] for m in matches}

        return [e for e in emails if e.id not in matched_ids]

    def get_match_stats(
        self,
        emails: List[EmailRecord],
        projects: List[Dict]
    ) -> Dict:
        """
        Get statistics about matching between emails and projects.

        Args:
            emails: List of EmailRecord objects
            projects: List of project dicts

        Returns:
            Dict with matching statistics
        """
        matches = self.find_matches(emails, projects)

        manual_matches = [m for m in matches if m['match_type'] == 'manual']
        auto_matches = [m for m in matches if m['match_type'] == 'auto']

        return {
            'total_emails': len(emails),
            'total_projects': len(projects),
            'total_matches': len(matches),
            'manual_matches': len(manual_matches),
            'auto_matches': len(auto_matches),
            'unmatched_emails': len(emails) - len(matches),
            'match_rate': round(len(matches) / len(emails), 2) if emails else 0
        }


# Example usage
if __name__ == "__main__":
    from .email_reader import EmailMonitorReader

    reader = EmailMonitorReader()
    matcher = EmailProjectMatcher()

    emails = reader.read_all_emails()[:10]  # Sample

    # Example project for testing
    test_projects = [
        {
            'id': 'neptune-project',
            'title': 'Neptune Building',
            'folder': 'Neptune',
            'location': {'city': 'Boston', 'state': 'MA'},
            'bid_date': '2025-12-15'
        }
    ]

    stats = matcher.get_match_stats(emails, test_projects)
    print(f"Match stats: {stats}")
