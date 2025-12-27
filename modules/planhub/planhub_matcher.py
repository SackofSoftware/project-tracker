"""
PlanHub-Local Project Matcher

Matches PlanHub leads with local bidding folders to identify when a PlanHub project
corresponds to a local folder that's already been downloaded.

Uses fuzzy string matching, location matching, and bid date proximity to auto-match
projects, with support for manual linking overrides.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple


class PlanHubLocalMatcher:
    """
    Matcher for linking PlanHub projects to local bidding folder projects.

    Provides both automated fuzzy matching and manual linking capabilities.
    Manual links are stored in static/data/planhub_links.json and take
    precedence over auto-matches.
    """

    def __init__(self, data_dir: str = None):
        """
        Initialize the matcher.

        Args:
            data_dir: Path to data directory containing planhub_links.json.
                     Defaults to static/data in project root.
        """
        if data_dir is None:
            # Default to static/data relative to project root
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "static" / "data"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.links_file = self.data_dir / "planhub_links.json"
        self.manual_links = self._load_manual_links()

    def _load_manual_links(self) -> Dict[str, str]:
        """
        Load manual project links from JSON file.

        Returns:
            Dict mapping PlanHub IDs to local project IDs
        """
        if not self.links_file.exists():
            return {}

        try:
            with open(self.links_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading manual links: {e}")
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
            print(f"Error saving manual links: {e}")
            return False

    def link_projects(self, planhub_id: str, local_id: str) -> bool:
        """
        Manually link a PlanHub project to a local project.

        Args:
            planhub_id: PlanHub project ID (e.g., "510142" or "planhub-510142")
            local_id: Local project ID

        Returns:
            True if link was saved successfully
        """
        # Normalize planhub_id (remove "planhub-" prefix if present)
        planhub_id = planhub_id.replace("planhub-", "")

        self.manual_links[planhub_id] = local_id
        return self._save_manual_links()

    def unlink_project(self, planhub_id: str) -> bool:
        """
        Remove a manual link for a PlanHub project.

        Args:
            planhub_id: PlanHub project ID

        Returns:
            True if unlink was saved successfully
        """
        # Normalize planhub_id
        planhub_id = planhub_id.replace("planhub-", "")

        if planhub_id in self.manual_links:
            del self.manual_links[planhub_id]
            return self._save_manual_links()
        return True

    def get_link(self, planhub_id: str) -> Optional[str]:
        """
        Get the manual link for a PlanHub project.

        Args:
            planhub_id: PlanHub project ID

        Returns:
            Local project ID if linked, None otherwise
        """
        # Normalize planhub_id
        planhub_id = planhub_id.replace("planhub-", "")
        return self.manual_links.get(planhub_id)

    def _get_planhub_id(self, planhub_project: Dict) -> str:
        """Extract normalized PlanHub ID from project dict."""
        # Try project_id first, then id with prefix removed
        pid = planhub_project.get('project_id') or planhub_project.get('id', '')
        return pid.replace("planhub-", "")

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

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string in various formats.

        Args:
            date_str: Date string (ISO format YYYY-MM-DD or MM/DD/YYYY)

        Returns:
            datetime object or None if parsing fails
        """
        if not date_str:
            return None

        # Try ISO format (YYYY-MM-DD)
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            pass

        # Try MM/DD/YYYY format
        try:
            return datetime.strptime(date_str, "%m/%d/%Y")
        except ValueError:
            pass

        return None

    def _date_within_days(self, date1_str: str, date2_str: str, days: int = 7) -> bool:
        """
        Check if two dates are within N days of each other.

        Args:
            date1_str: First date string
            date2_str: Second date string
            days: Maximum days apart (default: 7)

        Returns:
            True if dates are within the threshold
        """
        date1 = self._parse_date(date1_str)
        date2 = self._parse_date(date2_str)

        if not date1 or not date2:
            return False

        delta = abs((date1 - date2).days)
        return delta <= days

    def _is_division_8_project(self, project: Dict) -> bool:
        """
        Check if project has Division 8 scope (windows, doors, glazing, etc.).

        Args:
            project: Project dict (PlanHub or local format)

        Returns:
            True if project has Division 8 scope indicators
        """
        # Check explicit flag (PlanHub projects)
        if project.get('is_division_8'):
            return True

        # Check matching_trades for Division 8 keywords (PlanHub projects)
        trades = project.get('matching_trades', [])
        div8_keywords = [
            'window', 'door', 'glazing', 'storefront', 'curtain wall',
            'glass', 'entrance', 'aluminum', 'hardware', 'shower door',
            'framing', 'vestibule'
        ]

        for trade in trades:
            if any(kw in trade.lower() for kw in div8_keywords):
                return True

        # Check division_8 field for local projects
        if 'division_8' in project:
            div8_data = project.get('division_8', {})

            # Check if has spec sections
            spec_sections = div8_data.get('spec_sections', [])
            if spec_sections:
                return True

            # Check if has window/door counts
            windows = div8_data.get('windows', {})
            doors = div8_data.get('doors', {})
            if windows or doors:
                return True

        return False

    def _calculate_trade_overlap(self, planhub_trades: List[str], local_project: Dict) -> float:
        """
        Calculate overlap between PlanHub trades and local Division 8 scope.

        Uses Jaccard similarity: intersection / union of keyword sets.

        Args:
            planhub_trades: List of trade names from PlanHub (e.g., ["Windows", "Exterior Doors"])
            local_project: Local project dict with division_8 data

        Returns:
            Overlap ratio between 0.0 and 1.0
        """
        if not planhub_trades:
            return 0.0

        # Get local Division 8 scope
        local_div8 = local_project.get('division_8', {})
        local_sections = local_div8.get('spec_sections', [])

        if not local_sections:
            return 0.0

        # Convert PlanHub trades to keywords
        planhub_keywords = set()
        for trade in planhub_trades:
            # Split on whitespace and common delimiters
            words = trade.lower().replace('/', ' ').replace('-', ' ').split()
            planhub_keywords.update(words)

        # Convert local spec sections to keywords
        local_keywords = set()
        for section in local_sections:
            # Extract just the section name part (after the code)
            # e.g., "08 11 00 - Metal Doors" -> "metal doors"
            section_name = section.lower()
            if '-' in section_name:
                section_name = section_name.split('-', 1)[1].strip()
            words = section_name.replace('/', ' ').split()
            local_keywords.update(words)

        # Calculate Jaccard similarity
        intersection = planhub_keywords & local_keywords
        union = planhub_keywords | local_keywords

        return len(intersection) / len(union) if union else 0.0

    def _location_matches(self, planhub_project: Dict, local_project: Dict) -> bool:
        """
        Check if project locations match (city and state).

        Args:
            planhub_project: PlanHub project dict
            local_project: Local project dict

        Returns:
            True if both city and state match exactly (case-insensitive)
        """
        # Get city and state from PlanHub project
        ph_city = (planhub_project.get('city') or '').lower().strip()
        ph_state = (planhub_project.get('state') or '').lower().strip()

        # Get city and state from local project
        # Local project might have location as dict or string
        local_location = local_project.get('location', {})
        if isinstance(local_location, dict):
            local_city = (local_location.get('city') or '').lower().strip()
            local_state = (local_location.get('state') or '').lower().strip()
        else:
            # If location is a string, try to parse it
            local_city = ''
            local_state = ''

        # Both city and state must match
        if not ph_city or not local_city or not ph_state or not local_state:
            return False

        return ph_city == local_city and ph_state == local_state

    def _calculate_match_score(
        self,
        planhub_project: Dict,
        local_project: Dict
    ) -> Tuple[float, Dict[str, any]]:
        """
        Calculate match score between a PlanHub and local project.

        Improved scoring factors:
        - Project name similarity (0-0.7 points, with bonus for very high matches)
        - Location match (0.20 points if both city and state match)
        - Bid date proximity (0.10 points if within 7 days)
        - Division 8 trade matching (0-0.25 bonus if both Division 8 with trade overlap)
        - Division 8 mismatch penalty (-0.15 if only one is Division 8)

        Very high name similarity (>0.8) can qualify for auto-match alone.
        Division 8 scoring improves match accuracy by preventing false matches
        between Division 8 and non-Division 8 projects.

        Args:
            planhub_project: PlanHub project dict
            local_project: Local project dict

        Returns:
            Tuple of (confidence_score, match_details)
        """
        score = 0.0
        details = {
            'name_similarity': 0.0,
            'location_match': False,
            'bid_date_match': False
        }

        # Name similarity - compare against folder name too
        ph_name = planhub_project.get('project_name') or planhub_project.get('title', '')
        local_name = local_project.get('title') or local_project.get('folder', '')
        local_folder = local_project.get('folder', '')

        # Try both title and folder name, use best match
        name_sim = self._string_similarity(ph_name, local_name)
        folder_sim = self._string_similarity(ph_name, local_folder)
        best_sim = max(name_sim, folder_sim)
        details['name_similarity'] = best_sim

        # Name similarity scoring - more generous for high matches
        # >= 0.8 gets up to 0.7 points (can auto-match on name alone)
        # >= 0.5 gets up to 0.5 points
        if best_sim >= 0.8:
            # Very strong name match: 0.5 + extra 0.2 = 0.7 max
            score += 0.5 + (0.2 * ((best_sim - 0.8) / 0.2))  # 0.8->0.5, 1.0->0.7
        elif best_sim >= 0.5:
            # Good name match: scale from 0 to 0.5
            score += 0.5 * ((best_sim - 0.5) / 0.3)  # 0.5->0, 0.8->0.5

        # Location match (0.20 points) - bonus when combined with name
        location_match = self._location_matches(planhub_project, local_project)
        details['location_match'] = location_match

        if location_match:
            score += 0.20
            # Bonus: If location matches AND name has some similarity (>0.4), boost
            if best_sim >= 0.4:
                score += 0.10  # Extra bonus for location+name combo

        # Bid date proximity (0.10 points if within 7 days)
        ph_bid_date = planhub_project.get('bid_date') or planhub_project.get('bid_due_date', '')
        local_bid_date = local_project.get('bid_date', '')

        date_match = self._date_within_days(ph_bid_date, local_bid_date, days=7)
        details['bid_date_match'] = date_match

        if date_match:
            score += 0.10

        # Division 8 trade scoring (0.25 bonus for matches, -0.15 penalty for mismatches)
        planhub_is_div8 = self._is_division_8_project(planhub_project)
        local_is_div8 = self._is_division_8_project(local_project)
        details['planhub_is_div8'] = planhub_is_div8
        details['local_is_div8'] = local_is_div8

        if planhub_is_div8 and local_is_div8:
            # Both are Division 8: Calculate trade overlap bonus
            planhub_trades = planhub_project.get('matching_trades', [])
            trade_overlap = self._calculate_trade_overlap(planhub_trades, local_project)
            trade_bonus = trade_overlap * 0.25
            score += trade_bonus
            details['trade_overlap'] = round(trade_overlap, 3)
            details['trade_bonus'] = round(trade_bonus, 3)

        elif planhub_is_div8 != local_is_div8:
            # Mismatch: One is Division 8, other isn't
            # This prevents false matches between Division 8 and non-Division 8 projects
            score -= 0.15
            details['trade_mismatch_penalty'] = -0.15

        return score, details

    def get_best_match(
        self,
        planhub_project: Dict,
        local_projects: List[Dict]
    ) -> Optional[Dict]:
        """
        Find the best local match for a single PlanHub project.

        Args:
            planhub_project: PlanHub project dict
            local_projects: List of local project dicts

        Returns:
            Dict with match info or None if no good match found:
            {
                'planhub_id': str,
                'local_id': str,
                'confidence': float,
                'match_type': 'manual' or 'auto',
                'match_details': dict
            }
        """
        planhub_id = self._get_planhub_id(planhub_project)

        # Check for manual link first
        manual_link = self.get_link(planhub_id)
        if manual_link:
            # Find the local project with this ID
            for local_proj in local_projects:
                if local_proj.get('id') == manual_link:
                    return {
                        'planhub_id': planhub_id,
                        'local_id': manual_link,
                        'confidence': 1.0,
                        'match_type': 'manual',
                        'match_details': {
                            'manually_linked': True
                        }
                    }

        # Auto-match: find best scoring match
        best_score = 0.0
        best_match = None
        best_details = None

        for local_proj in local_projects:
            score, details = self._calculate_match_score(planhub_project, local_proj)

            if score > best_score:
                best_score = score
                best_match = local_proj
                best_details = details

        # Return matches with confidence >= 0.65 (lowered from 0.8)
        # This allows name+location matches to qualify
        if best_score >= 0.65 and best_match:
            return {
                'planhub_id': planhub_id,
                'local_id': best_match.get('id'),
                'confidence': round(best_score, 3),
                'match_type': 'auto',
                'match_details': best_details
            }

        return None

    def get_match_suggestions(
        self,
        planhub_project: Dict,
        local_projects: List[Dict],
        limit: int = 3
    ) -> List[Dict]:
        """
        Get top N suggested matches for a PlanHub project.

        Useful for presenting match options to users for manual linking.

        Args:
            planhub_project: PlanHub project dict
            local_projects: List of local project dicts
            limit: Maximum number of suggestions to return (default: 3)

        Returns:
            List of match dicts sorted by confidence (highest first)
        """
        suggestions = []

        for local_proj in local_projects:
            score, details = self._calculate_match_score(planhub_project, local_proj)

            # Only include suggestions with some minimum score (0.3)
            if score >= 0.3:
                suggestions.append({
                    'local_id': local_proj.get('id'),
                    'local_title': local_proj.get('title') or local_proj.get('folder', ''),
                    'local_folder': local_proj.get('folder', ''),
                    'confidence': round(score, 3),
                    'match_details': details
                })

        # Sort by confidence descending
        suggestions.sort(key=lambda x: x['confidence'], reverse=True)

        return suggestions[:limit]

    def find_matches(
        self,
        planhub_projects: List[Dict],
        local_projects: List[Dict]
    ) -> List[Dict]:
        """
        Find all matches between PlanHub and local projects.

        Args:
            planhub_projects: List of PlanHub project dicts
            local_projects: List of local project dicts

        Returns:
            List of match dicts:
            [
                {
                    'planhub_id': str,
                    'local_id': str,
                    'confidence': float,
                    'match_type': 'manual' or 'auto',
                    'match_details': dict
                },
                ...
            ]
        """
        matches = []

        for ph_proj in planhub_projects:
            match = self.get_best_match(ph_proj, local_projects)
            if match:
                matches.append(match)

        return matches

    def get_unmatched_planhub_projects(
        self,
        planhub_projects: List[Dict],
        local_projects: List[Dict]
    ) -> List[Dict]:
        """
        Get PlanHub projects that have no match in local projects.

        Args:
            planhub_projects: List of PlanHub project dicts
            local_projects: List of local project dicts

        Returns:
            List of unmatched PlanHub project dicts
        """
        matches = self.find_matches(planhub_projects, local_projects)
        matched_ids = {m['planhub_id'] for m in matches}

        unmatched = []
        for ph_proj in planhub_projects:
            planhub_id = self._get_planhub_id(ph_proj)
            if planhub_id not in matched_ids:
                unmatched.append(ph_proj)

        return unmatched

    def get_match_stats(
        self,
        planhub_projects: List[Dict],
        local_projects: List[Dict]
    ) -> Dict:
        """
        Get statistics about matching between PlanHub and local projects.

        Args:
            planhub_projects: List of PlanHub project dicts
            local_projects: List of local project dicts

        Returns:
            Dict with matching statistics
        """
        matches = self.find_matches(planhub_projects, local_projects)

        manual_matches = [m for m in matches if m['match_type'] == 'manual']
        auto_matches = [m for m in matches if m['match_type'] == 'auto']

        return {
            'total_planhub': len(planhub_projects),
            'total_local': len(local_projects),
            'total_matches': len(matches),
            'manual_matches': len(manual_matches),
            'auto_matches': len(auto_matches),
            'unmatched_planhub': len(planhub_projects) - len(matches),
            'match_rate': round(len(matches) / len(planhub_projects), 2) if planhub_projects else 0
        }


# Example usage and testing
if __name__ == "__main__":
    # Example test data
    planhub_projects = [
        {
            "id": "planhub-510142",
            "project_id": "510142",
            "project_name": "RIC Track Support Bldg.",
            "city": "Providence",
            "state": "RI",
            "bid_date": "2026-01-08",
            "bid_due_date": "01/08/2026"
        },
        {
            "id": "planhub-509331",
            "project_id": "509331",
            "project_name": "Chick fil A Seabrook NH",
            "city": "Seabrook",
            "state": "NH",
            "bid_date": "2026-01-02",
            "bid_due_date": "01/02/2026"
        }
    ]

    local_projects = [
        {
            "id": "ric-track-support-building",
            "title": "RIC Track Support Building",
            "folder": "RIC Track Support Building - Providence RI",
            "location": {
                "city": "Providence",
                "state": "RI"
            },
            "bid_date": "2026-01-08"
        },
        {
            "id": "chick-fil-a-seabrook",
            "title": "Chick-fil-A Restaurant",
            "folder": "Chick-fil-A - Seabrook NH",
            "location": {
                "city": "Seabrook",
                "state": "NH"
            },
            "bid_date": "2026-01-02"
        }
    ]

    # Test matcher
    matcher = PlanHubLocalMatcher()

    print("=== Testing PlanHub-Local Matcher ===\n")

    # Test auto-matching
    print("1. Auto-matching:")
    matches = matcher.find_matches(planhub_projects, local_projects)
    for match in matches:
        print(f"   PlanHub {match['planhub_id']} -> Local {match['local_id']}")
        print(f"   Confidence: {match['confidence']}, Type: {match['match_type']}")
        print(f"   Details: {match['match_details']}\n")

    # Test match suggestions
    print("2. Match suggestions for first PlanHub project:")
    suggestions = matcher.get_match_suggestions(planhub_projects[0], local_projects)
    for i, sug in enumerate(suggestions, 1):
        print(f"   {i}. {sug['local_title']} (confidence: {sug['confidence']})")
    print()

    # Test manual linking
    print("3. Testing manual link:")
    success = matcher.link_projects("510142", "ric-track-support-building")
    print(f"   Manual link created: {success}")
    link = matcher.get_link("510142")
    print(f"   Retrieved link: {link}\n")

    # Test stats
    print("4. Match statistics:")
    stats = matcher.get_match_stats(planhub_projects, local_projects)
    for key, value in stats.items():
        print(f"   {key}: {value}")
