"""
Unified Project Schema

Defines a common schema that all data sources (PlanHub, GovWin, ProjectDog, Local) map to.
This ensures consistent data structure across the application and simplifies cross-source operations.

Author: AI Assistant
Created: 2025-12-20
"""

from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict


@dataclass
class Location:
    """Standardized location representation"""
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    raw: Optional[str] = None  # Original location string

    def __str__(self) -> str:
        """Return formatted location string"""
        parts = []
        if self.city:
            parts.append(self.city)
        if self.state:
            parts.append(self.state)
        return ", ".join(parts) if parts else (self.raw or "Unknown")

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Document:
    """Standardized document representation"""
    id: str
    title: str
    type: str  # e.g., "spec", "drawing", "addendum", "quote"
    url: Optional[str] = None
    local_path: Optional[str] = None
    file_size: Optional[int] = None  # bytes
    downloaded: bool = False
    upload_date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Division8Scope:
    """Division 8 scope details"""
    scope_summary: Optional[str] = None
    spec_sections: List[str] = field(default_factory=list)  # e.g., ["08 11 00 - Metal Doors"]
    matching_trades: List[str] = field(default_factory=list)  # e.g., ["Windows", "Doors"]

    # Quantity details
    windows: Dict[str, Any] = field(default_factory=lambda: {"count": 0, "types": []})
    doors: Dict[str, Any] = field(default_factory=lambda: {"count": 0, "types": []})
    hardware: List[str] = field(default_factory=list)
    glazing: List[str] = field(default_factory=list)
    storefront: bool = False
    curtain_wall: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class LinkedSource:
    """Reference to a linked project from another source"""
    source: str  # "planhub", "govwin", "projectdog", "local_bidding"
    id: str
    confidence: float  # 0.0 - 1.0
    match_reason: str  # Human-readable explanation

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class InternalStatus:
    """Internal tracking status (overlay data from StatusTracker)"""
    bid_decision: Optional[str] = None  # "bid", "no_bid", "lost", "awarded", "gc_awarded"
    bid_date_override: Optional[str] = None  # Manual override for bid date
    has_proposal: bool = False
    has_internal_estimate: bool = False
    internal_estimate_total: Optional[float] = None
    archived: bool = False
    archived_reason: Optional[str] = None
    notes: List[Dict[str, str]] = field(default_factory=list)  # [{timestamp, note}]
    tags: List[str] = field(default_factory=list)

    # New additions for enhanced tracking
    scope_status: Dict[str, str] = field(default_factory=dict)  # {category: "specified"|"not_specified"|"by_others"}
    timeline_adjustments: Dict[str, Any] = field(default_factory=dict)
    pricing_notes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class UnifiedProject:
    """
    Unified project schema for all data sources.

    All data sources (PlanHub, GovWin, ProjectDog, Local) should normalize
    their data to this format.
    """

    # ===== Identity =====
    id: str  # Source-prefixed: "planhub-123", "govwin-456", "projectdog-789", "local-folder-name"
    source: str  # "planhub" | "govwin" | "projectdog" | "local_bidding"
    source_id: str  # Original ID from source system
    url: Optional[str] = None  # Link back to source system

    # ===== Basic Info =====
    title: str = ""
    description: Optional[str] = None

    # ===== Location =====
    location: Location = field(default_factory=Location)

    # ===== Dates (ISO 8601 strings: YYYY-MM-DD) =====
    bid_date: Optional[str] = None
    sub_bid_date: Optional[str] = None
    response_date: Optional[str] = None  # GovWin uses this
    solicitation_date: Optional[str] = None

    # ===== Project Details =====
    owner: Optional[str] = None
    architect: Optional[str] = None
    general_contractors: List[str] = field(default_factory=list)
    project_value: Optional[float] = None
    project_value_str: Optional[str] = None  # Original string format
    project_size: Optional[str] = None  # e.g., "50,000 SF"

    # ===== Classification =====
    project_type: Optional[str] = None  # "Renovation" | "New Construction" | "Tenant Build-Out" | "Addition"
    sector: Optional[str] = None  # "Commercial" | "Retail" | "Industrial" | "Education" | "Healthcare"
    entity_type: Optional[str] = None  # GovWin: "BID" | "LEAD"
    tags: List[str] = field(default_factory=list)

    # ===== Division 8 Specific =====
    is_division_8: bool = False
    division_8: Division8Scope = field(default_factory=Division8Scope)

    # ===== Documents =====
    documents: List[Document] = field(default_factory=list)

    # ===== Source-Specific Flags =====
    is_sub_bidding: Optional[bool] = None  # PlanHub
    is_gc_awarded: Optional[bool] = None  # PlanHub
    is_rfq: Optional[bool] = None  # ProjectDog
    is_dcam: Optional[bool] = None  # ProjectDog
    is_active: Optional[bool] = None  # GovWin

    # ===== Internal Status (overlay data) =====
    internal_status: InternalStatus = field(default_factory=InternalStatus)

    # ===== Linked Projects =====
    linked_sources: List[LinkedSource] = field(default_factory=list)

    # ===== Metadata =====
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_sync: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, handling nested dataclasses"""
        result = {}

        for key, value in asdict(self).items():
            if isinstance(value, dict) and not value:
                # Skip empty dicts
                continue
            elif isinstance(value, list) and not value:
                # Skip empty lists
                continue
            elif value is None:
                # Skip None values
                continue
            else:
                result[key] = value

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UnifiedProject':
        """Create UnifiedProject from dictionary"""

        # Handle location
        location_data = data.get('location', {})
        if isinstance(location_data, dict):
            location = Location(**location_data)
        else:
            location = Location()

        # Handle division_8
        div8_data = data.get('division_8', {})
        if isinstance(div8_data, dict):
            division_8 = Division8Scope(**div8_data)
        else:
            division_8 = Division8Scope()

        # Handle internal_status
        status_data = data.get('internal_status', {})
        if isinstance(status_data, dict):
            internal_status = InternalStatus(**status_data)
        else:
            internal_status = InternalStatus()

        # Handle documents
        docs_data = data.get('documents', [])
        documents = [Document(**doc) if isinstance(doc, dict) else doc for doc in docs_data]

        # Handle linked_sources
        links_data = data.get('linked_sources', [])
        linked_sources = [LinkedSource(**link) if isinstance(link, dict) else link for link in links_data]

        # Create project with processed nested objects
        project_data = data.copy()
        project_data['location'] = location
        project_data['division_8'] = division_8
        project_data['internal_status'] = internal_status
        project_data['documents'] = documents
        project_data['linked_sources'] = linked_sources

        return cls(**project_data)

    def get_effective_bid_date(self) -> Optional[str]:
        """Get the effective bid date (with override support)"""
        return self.internal_status.bid_date_override or self.bid_date or self.response_date

    def get_display_location(self) -> str:
        """Get formatted location string for display"""
        return str(self.location)

    def is_upcoming(self, days: int = 30) -> bool:
        """Check if bid date is within the next N days"""
        bid_date = self.get_effective_bid_date()
        if not bid_date:
            return False

        try:
            bid_dt = datetime.fromisoformat(bid_date)
            today = datetime.now()
            days_until = (bid_dt - today).days
            return 0 <= days_until <= days
        except (ValueError, TypeError):
            return False

    def has_division_8_content(self) -> bool:
        """Check if project has meaningful Division 8 content"""
        return (
            self.is_division_8 or
            bool(self.division_8.spec_sections) or
            bool(self.division_8.matching_trades) or
            self.division_8.windows.get('count', 0) > 0 or
            self.division_8.doors.get('count', 0) > 0
        )


# ===== Helper Functions =====

def normalize_date(date_str: Optional[str]) -> Optional[str]:
    """
    Normalize date string to ISO 8601 format (YYYY-MM-DD).

    Handles various input formats:
    - "01/12/2026 12:00 PM"
    - "01/07/2026 02:00 PM (in 25 days)"
    - "2026-01-12"
    - "January 12, 2026"
    """
    if not date_str:
        return None

    # Already in ISO format
    if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
        return date_str

    # Try parsing various formats
    formats = [
        "%m/%d/%Y %I:%M %p",  # 01/12/2026 12:00 PM
        "%m/%d/%Y",           # 01/12/2026
        "%Y-%m-%d",           # 2026-01-12
        "%B %d, %Y",          # January 12, 2026
        "%b %d, %Y",          # Jan 12, 2026
    ]

    # Clean the string (remove " (in X days)" suffix)
    clean_str = date_str.split(' (')[0].strip()

    for fmt in formats:
        try:
            dt = datetime.strptime(clean_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # If all parsing fails, return None
    return None


def normalize_project_value(value_str: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """
    Normalize project value to both float and string.

    Args:
        value_str: String like "$1,500,000", "1.5M", "N/A", etc.

    Returns:
        Tuple of (float_value, original_string)
    """
    if not value_str:
        return None, None

    # Keep original string
    original = value_str

    # Try to extract numeric value
    try:
        # Remove common non-numeric characters
        clean = value_str.replace('$', '').replace(',', '').replace(' ', '').strip()

        # Handle suffixes
        multiplier = 1
        if clean.endswith('M') or clean.endswith('m'):
            multiplier = 1_000_000
            clean = clean[:-1]
        elif clean.endswith('K') or clean.endswith('k'):
            multiplier = 1_000
            clean = clean[:-1]

        # Parse to float
        value = float(clean) * multiplier
        return value, original

    except (ValueError, AttributeError):
        return None, original


def merge_division_8_scopes(scopes: List[Division8Scope]) -> Division8Scope:
    """
    Merge multiple Division8Scope objects into one.
    Used when combining data from multiple sources for the same project.
    """
    merged = Division8Scope()

    # Collect all data
    all_sections = []
    all_trades = []
    all_hardware = []
    all_glazing = []
    summaries = []

    total_windows = 0
    total_doors = 0
    all_window_types = []
    all_door_types = []

    has_storefront = False
    has_curtain_wall = False

    for scope in scopes:
        all_sections.extend(scope.spec_sections)
        all_trades.extend(scope.matching_trades)
        all_hardware.extend(scope.hardware)
        all_glazing.extend(scope.glazing)

        if scope.scope_summary:
            summaries.append(scope.scope_summary)

        total_windows += scope.windows.get('count', 0)
        total_doors += scope.doors.get('count', 0)
        all_window_types.extend(scope.windows.get('types', []))
        all_door_types.extend(scope.doors.get('types', []))

        if scope.storefront:
            has_storefront = True
        if scope.curtain_wall:
            has_curtain_wall = True

    # Deduplicate
    merged.spec_sections = sorted(list(set(all_sections)))
    merged.matching_trades = sorted(list(set(all_trades)))
    merged.hardware = sorted(list(set(all_hardware)))
    merged.glazing = sorted(list(set(all_glazing)))

    # Merge summaries
    if summaries:
        merged.scope_summary = " | ".join(summaries)

    # Merge quantities
    merged.windows = {
        'count': total_windows,
        'types': sorted(list(set(all_window_types)))
    }
    merged.doors = {
        'count': total_doors,
        'types': sorted(list(set(all_door_types)))
    }

    merged.storefront = has_storefront
    merged.curtain_wall = has_curtain_wall

    return merged


def dict_to_unified_project(data: Dict) -> UnifiedProject:
    """
    Convert a project dictionary to UnifiedProject instance.

    Handles both dict-based projects and already-instantiated UnifiedProject objects.
    """
    if isinstance(data, UnifiedProject):
        return data

    # Parse location
    location_data = data.get('location', {})
    if isinstance(location_data, Location):
        location = location_data
    elif isinstance(location_data, dict):
        location = Location(
            address=location_data.get('address'),
            city=location_data.get('city'),
            state=location_data.get('state'),
            zip=location_data.get('zip'),
            raw=location_data.get('raw')
        )
    else:
        location = Location()

    # Parse Division 8
    div8_data = data.get('division_8', {})
    if isinstance(div8_data, Division8Scope):
        division_8 = div8_data
    elif isinstance(div8_data, dict):
        division_8 = Division8Scope(
            scope_summary=div8_data.get('scope_summary'),
            spec_sections=div8_data.get('spec_sections', []),
            matching_trades=div8_data.get('matching_trades', []),
            windows=div8_data.get('windows', {"count": 0, "types": []}),
            doors=div8_data.get('doors', {"count": 0, "types": []}),
            hardware=div8_data.get('hardware', []),
            glazing=div8_data.get('glazing', []),
            storefront=div8_data.get('storefront', False),
            curtain_wall=div8_data.get('curtain_wall', False)
        )
    else:
        division_8 = Division8Scope()

    # Parse documents
    docs_data = data.get('documents', [])
    documents = []
    for doc in docs_data:
        if isinstance(doc, Document):
            documents.append(doc)
        elif isinstance(doc, dict):
            documents.append(Document(
                id=doc.get('id', ''),
                title=doc.get('title', ''),
                type=doc.get('type', 'unknown'),
                url=doc.get('url'),
                local_path=doc.get('local_path'),
                file_size=doc.get('file_size'),
                downloaded=doc.get('downloaded', False),
                upload_date=doc.get('upload_date'),
                metadata=doc.get('metadata', {})
            ))

    # Parse internal status
    status_data = data.get('internal_status', {})
    if isinstance(status_data, InternalStatus):
        internal_status = status_data
    elif isinstance(status_data, dict):
        internal_status = InternalStatus(
            bid_decision=status_data.get('bid_decision'),
            bid_date_override=status_data.get('bid_date_override'),
            has_proposal=status_data.get('has_proposal', False),
            has_internal_estimate=status_data.get('has_internal_estimate', False),
            internal_estimate_total=status_data.get('internal_estimate_total'),
            archived=status_data.get('archived', False),
            archived_reason=status_data.get('archived_reason'),
            notes=status_data.get('notes', [])
        )
    else:
        internal_status = InternalStatus()

    # Create UnifiedProject
    return UnifiedProject(
        id=data.get('id', ''),
        source=data.get('source', ''),
        source_id=data.get('source_id', ''),
        url=data.get('url'),
        title=data.get('title') or data.get('project_name') or data.get('name', ''),
        description=data.get('description'),
        location=location,
        bid_date=data.get('bid_date'),
        sub_bid_date=data.get('sub_bid_date'),
        response_date=data.get('response_date'),
        solicitation_date=data.get('solicitation_date'),
        owner=data.get('owner'),
        architect=data.get('architect'),
        general_contractors=data.get('general_contractors', []),
        project_value=data.get('project_value'),
        project_value_str=data.get('project_value_str'),
        project_size=data.get('project_size'),
        project_type=data.get('project_type'),
        sector=data.get('sector'),
        entity_type=data.get('entity_type'),
        tags=data.get('tags', []),
        is_division_8=data.get('is_division_8', False),
        division_8=division_8,
        documents=documents,
        is_sub_bidding=data.get('is_sub_bidding'),
        is_gc_awarded=data.get('is_gc_awarded'),
        is_rfq=data.get('is_rfq'),
        is_dcam=data.get('is_dcam'),
        is_active=data.get('is_active'),
        internal_status=internal_status,
        linked_sources=data.get('linked_sources', [])
    )


__all__ = [
    'UnifiedProject',
    'Location',
    'Document',
    'Division8Scope',
    'LinkedSource',
    'InternalStatus',
    'normalize_date',
    'normalize_project_value',
    'merge_division_8_scopes',
    'dict_to_unified_project',
]
