"""Active Project Detection - Scans folders for bidding activity indicators"""

from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ActivityIndicators:
    """Container for project activity indicators"""
    has_takeoffs: bool = False
    takeoff_count: int = 0
    takeoff_files: List[str] = field(default_factory=list)

    has_quotes: bool = False
    quote_count: int = 0
    quote_files: List[str] = field(default_factory=list)
    vendor_names: List[str] = field(default_factory=list)

    has_schedules: bool = False
    schedule_count: int = 0
    schedule_files: List[str] = field(default_factory=list)

    has_recent_activity: bool = False
    days_since_activity: int = 999
    most_recent_file: Optional[str] = None

    activity_score: float = 0.0  # 0.0 to 1.0


class ActivityDetector:
    """Detects active bidding work in project folders"""

    # Known patterns for takeoff files
    TAKEOFF_PATTERNS = ['takeoff', 'take-off', 'take_off', 'quantity', 'count', 'measurements']

    # Known patterns for vendor quotes
    QUOTE_PATTERNS = ['quote', 'proposal', 'vendor', 'supplier', 'agreement', 'pricing']

    # Known patterns for schedules
    SCHEDULE_PATTERNS = ['schedule', 'door_schedule', 'window_schedule',
                        'door schedule', 'window schedule', 'hardware_schedule']

    # Known vendor keywords
    VENDOR_KEYWORDS = ['TWI', 'Oldcastle', 'Kawneer', 'YKK', 'NEWS', 'Allegion',
                      'US Aluminum', 'Tubelite', 'CRL', 'Dorma', 'LCN']

    def __init__(self, bidding_folder: str):
        """
        Initialize activity detector.

        Args:
            bidding_folder: Path to bidding folder root
        """
        self.bidding_folder = Path(bidding_folder)

    def detect_activity(self, project_folder_name: str) -> ActivityIndicators:
        """
        Detect activity indicators in a project folder.

        Args:
            project_folder_name: Name of project folder (not full path)

        Returns:
            ActivityIndicators with detected activity
        """
        folder_path = self.bidding_folder / project_folder_name

        if not folder_path.exists() or not folder_path.is_dir():
            return ActivityIndicators()

        indicators = ActivityIndicators()

        # Get all files
        try:
            pdf_files = list(folder_path.rglob('*.pdf'))
            csv_files = list(folder_path.rglob('*.csv'))
            xlsx_files = list(folder_path.rglob('*.xlsx'))
            xls_files = list(folder_path.rglob('*.xls'))
            all_files = pdf_files + csv_files + xlsx_files + xls_files
        except (PermissionError, OSError):
            return indicators

        # 1. Detect takeoffs
        indicators.takeoff_files = [
            f.name for f in all_files
            if any(pattern in f.name.lower() for pattern in self.TAKEOFF_PATTERNS)
        ]
        indicators.has_takeoffs = len(indicators.takeoff_files) > 0
        indicators.takeoff_count = len(indicators.takeoff_files)

        # 2. Detect quotes
        indicators.quote_files = [
            f.name for f in pdf_files
            if any(pattern in f.name.lower() for pattern in self.QUOTE_PATTERNS)
        ]
        indicators.has_quotes = len(indicators.quote_files) > 0
        indicators.quote_count = len(indicators.quote_files)

        # Extract vendor names from quote filenames
        for quote_file in indicators.quote_files:
            for vendor in self.VENDOR_KEYWORDS:
                if vendor.lower() in quote_file.lower():
                    if vendor not in indicators.vendor_names:
                        indicators.vendor_names.append(vendor)

        # 3. Detect schedules
        indicators.schedule_files = [
            f.name for f in pdf_files + csv_files + xlsx_files
            if any(pattern in f.name.lower() for pattern in self.SCHEDULE_PATTERNS)
        ]
        indicators.has_schedules = len(indicators.schedule_files) > 0
        indicators.schedule_count = len(indicators.schedule_files)

        # 4. Check recent activity (last 30 days)
        now = datetime.now()
        recent_threshold = now - timedelta(days=30)

        most_recent = None
        most_recent_file = None

        for f in all_files:
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if most_recent is None or mtime > most_recent:
                    most_recent = mtime
                    most_recent_file = f.name
            except (OSError, ValueError):
                continue

        if most_recent:
            indicators.days_since_activity = (now - most_recent).days
            indicators.most_recent_file = most_recent_file
            indicators.has_recent_activity = indicators.days_since_activity <= 30

        # 5. Calculate activity score
        score = 0.0
        if indicators.has_takeoffs:
            score += 0.4
        if indicators.has_quotes:
            score += 0.3
        if indicators.has_schedules:
            score += 0.1
        if indicators.has_recent_activity:
            score += 0.2

        indicators.activity_score = min(score, 1.0)

        return indicators

    def is_active_bid(self, indicators: ActivityIndicators) -> bool:
        """
        Determine if project is an active bid based on indicators.

        A project is considered active if it has at least 2 of:
        - Takeoffs
        - Quotes
        - Recent activity (within 30 days)

        OR has an activity score >= 0.5

        Args:
            indicators: Activity indicators

        Returns:
            True if project is an active bid
        """
        major_indicators = sum([
            indicators.has_takeoffs,
            indicators.has_quotes,
            indicators.has_recent_activity
        ])

        return major_indicators >= 2 or indicators.activity_score >= 0.5
