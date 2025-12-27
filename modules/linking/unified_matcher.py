"""
Unified Project Matcher - Location-First Deduplication Algorithm

Implements a tiered matching system that prioritizes:
1. Geographic location (ZIP codes, city+state)
2. Temporal proximity (bid dates)
3. Project value similarity
4. Name matching (secondary validation)

Tier 1 (0.85+): Auto-match with high confidence
Tier 2 (0.60-0.84): Suggest match for review
Tier 3 (0.40-0.59): Weak match (show on request)
"""

from typing import Tuple, Dict, Optional, List
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import re

from modules.schema.unified_project import UnifiedProject


# ===== CONFIGURATION =====

# Match thresholds
AUTO_MATCH_THRESHOLD = 0.85      # Tier 1: Auto-link
SUGGEST_HIGH_THRESHOLD = 0.75    # Tier 2 High: Easy approve
SUGGEST_LOW_THRESHOLD = 0.60     # Tier 2 Low: Needs review
SHOW_WEAK_THRESHOLD = 0.40       # Tier 3: Show if user searches

# Date windows (days)
TIER1_DATE_WINDOW = 3            # Tier 1: Very close dates
TIER2_DATE_WINDOW = 7            # Tier 2: Close dates
EXTENDED_DATE_WINDOW = 14        # For high name similarity
FORECAST_DATE_WINDOW = 180       # GovWin LEAD → BID

# Value similarity (percentage)
VALUE_MATCH_TIGHT = 0.10         # Within 10%
VALUE_MATCH_MEDIUM = 0.20        # Within 20%
VALUE_MATCH_LOOSE = 0.50         # Within 50%

# Fuzzy matching thresholds
FUZZY_EXACT = 0.95               # Essentially identical
FUZZY_HIGH = 0.85                # Very similar
FUZZY_MEDIUM = 0.70              # Somewhat similar
FUZZY_LOW = 0.50                 # Barely similar


# ===== UTILITY FUNCTIONS =====

def fuzzy_match(str1: Optional[str], str2: Optional[str]) -> float:
    """Calculate fuzzy string similarity using SequenceMatcher."""
    if not str1 or not str2:
        return 0.0

    # Normalize
    s1 = str1.lower().strip()
    s2 = str2.lower().strip()

    return SequenceMatcher(None, s1, s2).ratio()


def get_primary_date(project: UnifiedProject) -> Optional[datetime]:
    """
    Get primary bid date from project, trying multiple fields.

    Priority:
    1. bid_date
    2. sub_bid_date
    3. response_date
    4. solicitation_date
    """
    # Try each field in order
    for date_str in [project.bid_date, project.sub_bid_date,
                     project.response_date, project.solicitation_date]:
        if date_str:
            try:
                # Parse ISO date string
                return datetime.fromisoformat(date_str)
            except (ValueError, TypeError, AttributeError):
                continue

    return None


def has_matching_street_address(proj1: UnifiedProject, proj2: UnifiedProject) -> bool:
    """Check if projects have matching street numbers and names."""
    addr1 = proj1.location.address
    addr2 = proj2.location.address

    if not addr1 or not addr2:
        return False

    # Extract street number (first digits)
    num1_match = re.match(r'^(\d+)', addr1.strip())
    num2_match = re.match(r'^(\d+)', addr2.strip())

    if not num1_match or not num2_match:
        return False

    # Street numbers must match
    if num1_match.group(1) != num2_match.group(1):
        return False

    # Extract street name (words after number, before apt/suite)
    street1 = re.sub(r'^\d+\s+', '', addr1.lower())
    street1 = re.split(r'\s+(apt|suite|unit|#)', street1)[0].strip()

    street2 = re.sub(r'^\d+\s+', '', addr2.lower())
    street2 = re.split(r'\s+(apt|suite|unit|#)', street2)[0].strip()

    # Fuzzy match street name
    return fuzzy_match(street1, street2) >= 0.8


def calculate_trade_overlap(trades1: List[str], trades2: List[str]) -> float:
    """
    Calculate Jaccard similarity between two trade lists.

    Normalizes trade keywords for comparison.
    """
    def normalize_trades(trades):
        keywords = set()
        for trade in trades:
            if isinstance(trade, str):
                # Extract keywords from spec sections like "08 51 00 - Windows"
                keywords.update(word.lower() for word in re.findall(r'[a-z]+', trade.lower()))
        return keywords

    keywords1 = normalize_trades(trades1)
    keywords2 = normalize_trades(trades2)

    if not keywords1 or not keywords2:
        return 0.0

    intersection = keywords1.intersection(keywords2)
    union = keywords1.union(keywords2)

    return len(intersection) / len(union) if union else 0.0


# ===== TIER 1 MATCHING =====

def check_tier1_match(proj1: UnifiedProject, proj2: UnifiedProject) -> Optional[Tuple[float, Dict]]:
    """
    Check for high-confidence Tier 1 match.
    Returns (confidence, details) if match, else None.
    """

    # Option A: Exact ZIP + Close Date
    if proj1.location.zip and proj2.location.zip:
        if proj1.location.zip == proj2.location.zip:
            date1 = get_primary_date(proj1)
            date2 = get_primary_date(proj2)

            if date1 and date2 and abs((date1 - date2).days) <= TIER1_DATE_WINDOW:
                confidence = 0.90
                details = {
                    'tier': 1,
                    'tier1_type': 'zip_date',
                    'zip_match': True,
                    'date_diff_days': abs((date1 - date2).days)
                }

                # Bonuses
                if proj1.owner and proj2.owner:
                    if fuzzy_match(proj1.owner, proj2.owner) >= FUZZY_MEDIUM:
                        confidence += 0.05
                        details['owner_bonus'] = True

                name_sim = fuzzy_match(proj1.title, proj2.title)
                if name_sim >= FUZZY_LOW:
                    confidence += 0.05
                    details['name_bonus'] = True
                    details['name_similarity'] = round(name_sim, 3)

                if confidence >= AUTO_MATCH_THRESHOLD:
                    details['confidence'] = round(confidence, 3)
                    return (confidence, details)

    # Option B: Exact ZIP + Owner + Date Window
    if proj1.location.zip and proj2.location.zip and proj1.owner and proj2.owner:
        if proj1.location.zip == proj2.location.zip:
            owner_sim = fuzzy_match(proj1.owner, proj2.owner)

            if owner_sim >= 0.8:
                date1 = get_primary_date(proj1)
                date2 = get_primary_date(proj2)

                if date1 and date2 and abs((date1 - date2).days) <= TIER2_DATE_WINDOW:
                    confidence = 0.88
                    details = {
                        'tier': 1,
                        'tier1_type': 'zip_owner_date',
                        'owner_similarity': round(owner_sim, 3),
                        'date_diff_days': abs((date1 - date2).days)
                    }

                    name_sim = fuzzy_match(proj1.title, proj2.title)
                    if name_sim >= 0.4:
                        confidence += 0.07
                        details['name_similarity'] = round(name_sim, 3)

                    if proj1.project_value and proj2.project_value:
                        pct_diff = abs(proj1.project_value - proj2.project_value) / \
                                   max(proj1.project_value, proj2.project_value)
                        if pct_diff <= VALUE_MATCH_MEDIUM:
                            confidence += 0.05
                            details['value_within_20pct'] = True

                    if confidence >= AUTO_MATCH_THRESHOLD:
                        details['confidence'] = round(confidence, 3)
                        return (confidence, details)

    # Option C: Extreme Name Match + Location
    name_sim = fuzzy_match(proj1.title, proj2.title)

    if name_sim >= FUZZY_EXACT:
        if proj1.location.city and proj2.location.city and \
           proj1.location.state and proj2.location.state:
            city_sim = fuzzy_match(proj1.location.city, proj2.location.city)
            state_match = proj1.location.state.upper() == proj2.location.state.upper()

            if city_sim >= 0.9 and state_match:
                date1 = get_primary_date(proj1)
                date2 = get_primary_date(proj2)

                # Dates within 14 days OR both missing
                date_ok = False
                if date1 and date2:
                    date_ok = abs((date1 - date2).days) <= EXTENDED_DATE_WINDOW
                elif not date1 and not date2:
                    date_ok = True

                if date_ok:
                    confidence = 0.90
                    details = {
                        'tier': 1,
                        'tier1_type': 'extreme_name',
                        'name_similarity': round(name_sim, 3),
                        'city_similarity': round(city_sim, 3)
                    }

                    if proj1.owner and proj2.owner:
                        if fuzzy_match(proj1.owner, proj2.owner) >= FUZZY_MEDIUM:
                            confidence += 0.05
                            details['owner_bonus'] = True

                    if proj1.project_type == proj2.project_type:
                        confidence += 0.05
                        details['type_match'] = True

                    if confidence >= AUTO_MATCH_THRESHOLD:
                        details['confidence'] = round(confidence, 3)
                        return (confidence, details)

    return None


# ===== TIER 2 MATCHING =====

def calculate_match_score(proj1: UnifiedProject, proj2: UnifiedProject) -> Tuple[float, Dict]:
    """
    Calculate match confidence score between two projects (Tier 2).

    Returns:
        (confidence_score, match_details_dict)
    """
    score = 0.0
    details = {'tier': 2}

    # ===== LOCATION SCORING (max 0.50) =====
    location_score = 0.0

    if proj1.location.zip and proj2.location.zip:
        if proj1.location.zip == proj2.location.zip:
            location_score = 0.40
            details['zip_match'] = True
            details['matched_zip'] = proj1.location.zip
        else:
            details['zip_match'] = False

    elif proj1.location.city and proj2.location.city and \
         proj1.location.state and proj2.location.state:
        city_sim = fuzzy_match(proj1.location.city, proj2.location.city)
        state_match = proj1.location.state.upper() == proj2.location.state.upper()

        if city_sim >= FUZZY_HIGH and state_match:
            location_score = 0.30
            details['location_match'] = 'exact'
            details['city_similarity'] = round(city_sim, 3)
        elif city_sim >= FUZZY_MEDIUM and state_match:
            location_score = 0.20
            details['location_match'] = 'fuzzy'
            details['city_similarity'] = round(city_sim, 3)
        elif state_match:
            location_score = 0.05
            details['location_match'] = 'state_only'

    # Address bonus
    if has_matching_street_address(proj1, proj2):
        location_score += 0.10
        details['address_match'] = True

    score += location_score
    details['location_score'] = round(location_score, 3)

    # ===== DATE PROXIMITY (max 0.25) =====
    date_score = 0.0
    date1 = get_primary_date(proj1)
    date2 = get_primary_date(proj2)

    if date1 and date2:
        days_diff = abs((date1 - date2).days)

        if days_diff <= 3:
            date_score = 0.25
        elif days_diff <= 7:
            date_score = 0.20
        elif days_diff <= 14:
            date_score = 0.15
        elif days_diff <= 30:
            date_score = 0.10
        elif days_diff <= 60:
            date_score = 0.05

        details['date_diff_days'] = days_diff
        details['date1'] = date1.isoformat()[:10]
        details['date2'] = date2.isoformat()[:10]
    else:
        date_score = 0.05  # Neutral (doesn't penalize missing dates)
        details['date_diff_days'] = None

    score += date_score
    details['date_score'] = round(date_score, 3)

    # ===== PROJECT VALUE (max 0.15) =====
    value_score = 0.0

    if proj1.project_value and proj2.project_value:
        pct_diff = abs(proj1.project_value - proj2.project_value) / \
                   max(proj1.project_value, proj2.project_value)

        if pct_diff <= VALUE_MATCH_TIGHT:
            value_score = 0.15
        elif pct_diff <= VALUE_MATCH_MEDIUM:
            value_score = 0.12
        elif pct_diff <= 0.30:
            value_score = 0.09
        elif pct_diff <= VALUE_MATCH_LOOSE:
            value_score = 0.06

        details['value_diff_pct'] = round(pct_diff, 3)
        details['value1'] = proj1.project_value
        details['value2'] = proj2.project_value
    else:
        value_score = 0.03  # Neutral
        details['value_diff_pct'] = None

    score += value_score
    details['value_score'] = round(value_score, 3)

    # ===== NAME SIMILARITY (0.10 normal, UP TO 0.70 if missing location data) =====
    name_sim = fuzzy_match(proj1.title, proj2.title)

    # Check if EITHER project is missing location data
    missing_location_1 = not (proj1.location.city or proj1.location.state or proj1.location.zip)
    missing_location_2 = not (proj2.location.city or proj2.location.state or proj2.location.zip)

    if missing_location_1 or missing_location_2:
        # At least ONE missing location - boost name importance (can't rely on location matching)
        if name_sim >= 0.9:
            name_score = 0.70
        elif name_sim >= 0.7:
            name_score = 0.50
        elif name_sim >= 0.5:
            name_score = 0.30
        elif name_sim >= 0.3:
            name_score = 0.15
        else:
            name_score = 0.00
        details['name_boosted'] = True
        if missing_location_1 and missing_location_2:
            details['boost_reason'] = 'both_missing_location'
        else:
            details['boost_reason'] = 'one_missing_location'
    else:
        # Normal name scoring (location-first approach)
        if name_sim >= 0.9:
            name_score = 0.10
        elif name_sim >= 0.7:
            name_score = 0.08
        elif name_sim >= 0.5:
            name_score = 0.05
        elif name_sim >= 0.3:
            name_score = 0.02
        else:
            name_score = 0.00

    score += name_score
    details['name_similarity'] = round(name_sim, 3)
    details['name_score'] = round(name_score, 3)

    # ===== OWNER/ARCHITECT BONUS (max +0.10) =====
    bonus = 0.0

    if proj1.owner and proj2.owner:
        owner_sim = fuzzy_match(proj1.owner, proj2.owner)
        if owner_sim >= 0.8:
            bonus += 0.05
            details['owner_match'] = True
            details['owner_similarity'] = round(owner_sim, 3)

    if proj1.architect and proj2.architect:
        arch_sim = fuzzy_match(proj1.architect, proj2.architect)
        if arch_sim >= 0.8:
            bonus += 0.05
            details['architect_match'] = True
            details['architect_similarity'] = round(arch_sim, 3)

    score += bonus
    details['entity_bonus'] = round(bonus, 3)

    # ===== DIVISION 8 TRADE OVERLAP (±0.10) =====
    div8_adj = 0.0

    if proj1.is_division_8 and proj2.is_division_8:
        # Both Division 8: calculate trade overlap
        overlap = calculate_trade_overlap(
            proj1.division_8.matching_trades or [],
            proj2.division_8.spec_sections or []
        )
        div8_adj = overlap * 0.10
        details['div8_overlap'] = round(overlap, 3)
        details['div8_bonus'] = round(div8_adj, 3)

    elif proj1.is_division_8 != proj2.is_division_8:
        # Mismatch penalty
        div8_adj = -0.10
        details['div8_mismatch'] = True

    score += div8_adj
    details['div8_adjustment'] = round(div8_adj, 3)

    # ===== TOTAL =====
    score = max(0.0, min(1.0, score))  # Clamp to [0, 1]
    details['confidence'] = round(score, 3)
    details['total_score'] = round(score, 3)

    return score, details


# ===== MAIN MATCHER CLASS =====

class UnifiedProjectMatcher:
    """
    Unified project matcher using location-first algorithm.

    Implements 3-tier matching:
    - Tier 1 (0.85+): Auto-match with high confidence
    - Tier 2 (0.60-0.84): Suggest match for review
    - Tier 3 (0.40-0.59): Weak match (show on request)
    """

    def __init__(self):
        self.stats = {
            'total_comparisons': 0,
            'tier1_matches': 0,
            'tier2_matches': 0,
            'tier3_matches': 0,
            'no_matches': 0
        }

    def match_projects(self, proj1: UnifiedProject, proj2: UnifiedProject,
                      min_confidence: float = SHOW_WEAK_THRESHOLD) -> Optional[Tuple[float, Dict]]:
        """
        Calculate match confidence between two projects.

        Args:
            proj1: First project
            proj2: Second project
            min_confidence: Minimum confidence to return (default: 0.40)

        Returns:
            (confidence, details_dict) if confidence >= min_confidence, else None
        """
        self.stats['total_comparisons'] += 1

        # Early exit: Different states (unlikely to match)
        # BUT only if BOTH have state data - don't penalize missing data
        if proj1.location.state and proj2.location.state:
            if proj1.location.state.upper() != proj2.location.state.upper():
                self.stats['no_matches'] += 1
                return None

        # Try Tier 1 first (fast path)
        tier1_result = check_tier1_match(proj1, proj2)
        if tier1_result:
            confidence, details = tier1_result
            self.stats['tier1_matches'] += 1
            return (confidence, details)

        # Tier 2 scoring
        confidence, details = calculate_match_score(proj1, proj2)

        # Classify by tier
        if confidence >= AUTO_MATCH_THRESHOLD:
            self.stats['tier1_matches'] += 1
            details['tier'] = 1
        elif confidence >= SUGGEST_LOW_THRESHOLD:
            self.stats['tier2_matches'] += 1
        elif confidence >= SHOW_WEAK_THRESHOLD:
            self.stats['tier3_matches'] += 1
        else:
            self.stats['no_matches'] += 1

        if confidence >= min_confidence:
            return (confidence, details)

        return None

    def get_tier_label(self, confidence: float) -> str:
        """Get human-readable tier label for a confidence score."""
        if confidence >= AUTO_MATCH_THRESHOLD:
            return "Auto-matched"
        elif confidence >= SUGGEST_HIGH_THRESHOLD:
            return "Likely Match"
        elif confidence >= SUGGEST_LOW_THRESHOLD:
            return "Possible Match"
        elif confidence >= SHOW_WEAK_THRESHOLD:
            return "Weak Match"
        else:
            return "No Match"

    def get_stats(self) -> Dict:
        """Get matching statistics."""
        return self.stats.copy()
