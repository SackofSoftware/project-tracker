"""
Tag Cross-Reference System

Batch scans architectural drawings and cross-references tag counts
between floor plans and elevations for QA validation.

Includes zone-aware cross-referencing to provide spatial context like
"5 Type A windows on North Elevation".
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from .shape_detector import ShapeDetector, ShapeType, DetectedTag


# ============================================================================
# POINT-IN-POLYGON UTILITY
# ============================================================================

def point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """
    Determine if a point is inside a polygon using ray casting algorithm.

    Args:
        point: (x, y) coordinates of the point to test
        polygon: List of (x, y) coordinates defining the polygon vertices

    Returns:
        True if point is inside the polygon, False otherwise
    """
    x, y = point
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        # Check if point is on the same y-level as this edge
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside

        j = i

    return inside


def get_polygon_centroid(polygon: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Calculate the centroid of a polygon.

    Args:
        polygon: List of (x, y) coordinates defining the polygon vertices

    Returns:
        (x, y) coordinates of the centroid
    """
    if not polygon:
        return (0.0, 0.0)

    x_sum = sum(p[0] for p in polygon)
    y_sum = sum(p[1] for p in polygon)
    n = len(polygon)

    return (x_sum / n, y_sum / n)


class SheetType(Enum):
    FLOOR_PLAN = "floor_plan"
    EXTERIOR_ELEVATION = "exterior_elevation"
    INTERIOR_ELEVATION = "interior_elevation"
    OTHER = "other"


@dataclass
class SheetScanResult:
    """Result of scanning a single sheet"""
    sheet_name: str
    sheet_type: SheetType
    pdf_path: str
    page_number: int
    tags: List[Dict]
    tag_counts: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        # Calculate tag counts
        self.tag_counts = defaultdict(int)
        for tag in self.tags:
            label = tag.get('label', '').strip()
            if label:
                self.tag_counts[label] += 1


@dataclass
class TagComparison:
    """Comparison of a single tag across sheet types"""
    tag_label: str
    floor_plan_count: int = 0
    ext_elevation_count: int = 0
    int_elevation_count: int = 0
    floor_plan_sheets: List[str] = field(default_factory=list)
    ext_elevation_sheets: List[str] = field(default_factory=list)
    int_elevation_sheets: List[str] = field(default_factory=list)

    # Zone-aware counts: direction -> {sheet: count}
    zone_counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # Zone-aware sheet lists: direction -> [sheet names]
    zone_sheets: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def matches(self) -> bool:
        """Check if floor plans and exterior elevations match"""
        return self.floor_plan_count == self.ext_elevation_count

    @property
    def is_interior_only(self) -> bool:
        """Tag only appears on interior elevations"""
        return (self.floor_plan_count == 0 and
                self.ext_elevation_count == 0 and
                self.int_elevation_count > 0)

    @property
    def status(self) -> str:
        if self.matches and self.floor_plan_count > 0:
            return "match"
        elif self.is_interior_only:
            return "interior_only"
        elif self.floor_plan_count != self.ext_elevation_count:
            return "mismatch"
        else:
            return "unknown"

    def add_zone_count(self, direction: str, sheet_name: str, count: int = 1):
        """Add a count for a specific direction zone"""
        if direction not in self.zone_counts:
            self.zone_counts[direction] = {}
            self.zone_sheets[direction] = []

        if sheet_name not in self.zone_counts[direction]:
            self.zone_counts[direction][sheet_name] = 0
            if sheet_name not in self.zone_sheets[direction]:
                self.zone_sheets[direction].append(sheet_name)

        self.zone_counts[direction][sheet_name] += count

    def get_zone_total(self, direction: str) -> int:
        """Get total count for a specific direction"""
        if direction not in self.zone_counts:
            return 0
        return sum(self.zone_counts[direction].values())

    def to_dict(self) -> dict:
        # Calculate zone totals for output
        zone_totals = {
            direction: self.get_zone_total(direction)
            for direction in self.zone_counts
        }

        return {
            'tag': self.tag_label,
            'floor_plan_count': self.floor_plan_count,
            'ext_elevation_count': self.ext_elevation_count,
            'int_elevation_count': self.int_elevation_count,
            'floor_plan_sheets': self.floor_plan_sheets,
            'ext_elevation_sheets': self.ext_elevation_sheets,
            'int_elevation_sheets': self.int_elevation_sheets,
            'matches': self.matches,
            'is_interior_only': self.is_interior_only,
            'status': self.status,
            # Zone-aware data
            'zone_counts': self.zone_counts,
            'zone_sheets': self.zone_sheets,
            'zone_totals': zone_totals
        }


class TagCrossReference:
    """Cross-reference tag counts across architectural sheets"""

    # Sheet name patterns for auto-classification
    SHEET_PATTERNS = {
        SheetType.FLOOR_PLAN: [
            r'^A[012]\d{2}',  # A100-A299 (floor plans, enlarged plans)
            r'FLOOR\s*PLAN',
            r'LEVEL\s*PLAN',
            r'PLAN\s*-',
        ],
        SheetType.EXTERIOR_ELEVATION: [
            r'^A3[0-4]\d',  # A300-A349
            r'EXTERIOR\s*ELEV',
            r'EXT\.?\s*ELEV',
            r'BUILDING\s*ELEV',
        ],
        SheetType.INTERIOR_ELEVATION: [
            r'^A3[5-9]\d',  # A350-A399
            r'^A[456]\d{2}',  # A400-A699 (often interior elevations/details)
            r'INTERIOR\s*ELEV',
            r'INT\.?\s*ELEV',
            r'ROOM\s*ELEV',
        ]
    }

    def __init__(self, project_folder: Path):
        self.project_folder = Path(project_folder)
        self.detector = ShapeDetector(render_scale=2.0)
        self.scan_results: List[SheetScanResult] = []

    def classify_sheet(self, sheet_name: str) -> SheetType:
        """Classify a sheet based on its name"""
        sheet_upper = sheet_name.upper()

        for sheet_type, patterns in self.SHEET_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, sheet_upper, re.IGNORECASE):
                    return sheet_type

        return SheetType.OTHER

    def find_architectural_sheets(self) -> Dict[SheetType, List[Path]]:
        """Find all architectural sheets in the project, grouped by type"""
        drawings_folder = self.project_folder / "Drawings" / "Architectural"

        if not drawings_folder.exists():
            # Try without subfolder
            drawings_folder = self.project_folder / "Drawings"

        if not drawings_folder.exists():
            return {st: [] for st in SheetType}

        sheets = {st: [] for st in SheetType}

        for pdf_file in sorted(drawings_folder.glob("*.pdf")):
            sheet_type = self.classify_sheet(pdf_file.stem)
            sheets[sheet_type].append(pdf_file)

        return sheets

    def scan_sheet(
        self,
        pdf_path: Path,
        sheet_type: Optional[SheetType] = None,
        shape_type: ShapeType = ShapeType.HEXAGON,
        page_number: int = 1
    ) -> SheetScanResult:
        """Scan a single sheet for tags"""
        if sheet_type is None:
            sheet_type = self.classify_sheet(pdf_path.stem)

        tags = self.detector.detect_shapes(
            str(pdf_path),
            page_number,
            shape_type,
            min_confidence=0.6
        )

        # Convert to dicts
        tag_dicts = [t.to_dict() for t in tags]

        # Filter out likely keynote numbers (numeric-only labels)
        filtered_tags = []
        for tag in tag_dicts:
            label = tag.get('label', '').strip()
            # Keep if it has letters or is empty (will be manually identified)
            if not label or not label.replace('.', '').replace('-', '').isdigit():
                filtered_tags.append(tag)

        result = SheetScanResult(
            sheet_name=pdf_path.stem,
            sheet_type=sheet_type,
            pdf_path=str(pdf_path.relative_to(self.project_folder)),
            page_number=page_number,
            tags=filtered_tags
        )

        return result

    def batch_scan(
        self,
        sheet_types: Optional[List[SheetType]] = None,
        shape_type: ShapeType = ShapeType.HEXAGON,
        progress_callback=None
    ) -> List[SheetScanResult]:
        """Batch scan multiple sheets"""
        if sheet_types is None:
            sheet_types = [
                SheetType.FLOOR_PLAN,
                SheetType.EXTERIOR_ELEVATION,
                SheetType.INTERIOR_ELEVATION
            ]

        sheets = self.find_architectural_sheets()
        self.scan_results = []

        total_sheets = sum(len(sheets[st]) for st in sheet_types)
        processed = 0

        for sheet_type in sheet_types:
            for pdf_path in sheets[sheet_type]:
                if progress_callback:
                    progress_callback(processed, total_sheets, pdf_path.name)

                try:
                    result = self.scan_sheet(pdf_path, sheet_type, shape_type)
                    self.scan_results.append(result)
                except Exception as e:
                    print(f"Error scanning {pdf_path.name}: {e}")

                processed += 1

        return self.scan_results

    def generate_comparison(self) -> List[TagComparison]:
        """Generate cross-reference comparison from scan results"""
        # Collect all unique tags
        all_tags = set()
        for result in self.scan_results:
            all_tags.update(result.tag_counts.keys())

        comparisons = []

        for tag_label in sorted(all_tags):
            comparison = TagComparison(tag_label=tag_label)

            for result in self.scan_results:
                count = result.tag_counts.get(tag_label, 0)
                if count > 0:
                    if result.sheet_type == SheetType.FLOOR_PLAN:
                        comparison.floor_plan_count += count
                        comparison.floor_plan_sheets.append(result.sheet_name)
                    elif result.sheet_type == SheetType.EXTERIOR_ELEVATION:
                        comparison.ext_elevation_count += count
                        comparison.ext_elevation_sheets.append(result.sheet_name)
                    elif result.sheet_type == SheetType.INTERIOR_ELEVATION:
                        comparison.int_elevation_count += count
                        comparison.int_elevation_sheets.append(result.sheet_name)

            comparisons.append(comparison)

        return comparisons

    def get_summary(self) -> dict:
        """Get summary statistics"""
        comparisons = self.generate_comparison()

        matches = [c for c in comparisons if c.status == "match"]
        mismatches = [c for c in comparisons if c.status == "mismatch"]
        interior_only = [c for c in comparisons if c.status == "interior_only"]

        return {
            'total_tags': len(comparisons),
            'matches': len(matches),
            'mismatches': len(mismatches),
            'interior_only': len(interior_only),
            'match_rate': len(matches) / len(comparisons) * 100 if comparisons else 0,
            'sheets_scanned': len(self.scan_results),
            'floor_plans': len([r for r in self.scan_results if r.sheet_type == SheetType.FLOOR_PLAN]),
            'ext_elevations': len([r for r in self.scan_results if r.sheet_type == SheetType.EXTERIOR_ELEVATION]),
            'int_elevations': len([r for r in self.scan_results if r.sheet_type == SheetType.INTERIOR_ELEVATION]),
        }

    def to_dict(self) -> dict:
        """Export full results as dictionary"""
        comparisons = self.generate_comparison()

        return {
            'summary': self.get_summary(),
            'comparisons': [c.to_dict() for c in comparisons],
            'scan_results': [
                {
                    'sheet_name': r.sheet_name,
                    'sheet_type': r.sheet_type.value,
                    'pdf_path': r.pdf_path,
                    'tag_counts': dict(r.tag_counts),
                    'total_tags': len(r.tags)
                }
                for r in self.scan_results
            ]
        }


def run_crossref(project_folder: str, shape_type: str = "hexagon") -> dict:
    """
    Convenience function to run cross-reference on a project.

    Args:
        project_folder: Path to project folder
        shape_type: Shape type to detect

    Returns:
        Cross-reference results as dictionary
    """
    crossref = TagCrossReference(Path(project_folder))
    crossref.batch_scan(shape_type=ShapeType(shape_type))
    return crossref.to_dict()


# ============================================================================
# ZONE-AWARE CROSS-REFERENCE
# ============================================================================

class ZoneAwareCrossReference:
    """
    Cross-reference tag annotations with zone annotations to provide
    spatial context (e.g., "5 Type A windows on North Elevation").

    This class works with database annotations rather than live PDF scanning.
    """

    def __init__(self, annotations: List[Dict[str, Any]]):
        """
        Initialize with a list of annotation dictionaries.

        Args:
            annotations: List of annotation dicts from database
        """
        self.annotations = annotations
        self.tags = []
        self.zones = []

        # Separate tags and zones
        for ann in annotations:
            ann_type = ann.get('annotation_type', '')
            if ann_type.endswith('_zone'):
                self.zones.append(ann)
            elif ann_type == 'tag_marker':
                self.tags.append(ann)

    def get_tag_center(self, tag: Dict) -> Optional[Tuple[float, float]]:
        """Get the center point of a tag annotation"""
        geometry = tag.get('geometry', {})
        points = geometry.get('points', [])

        if not points:
            return None

        return get_polygon_centroid([(p[0], p[1]) for p in points])

    def get_zone_polygon(self, zone: Dict) -> List[Tuple[float, float]]:
        """Get the polygon points of a zone annotation"""
        geometry = zone.get('geometry', {})
        points = geometry.get('points', [])
        return [(p[0], p[1]) for p in points]

    def find_containing_zone(self, tag: Dict) -> Optional[Dict]:
        """Find the zone that contains a tag (if any)"""
        center = self.get_tag_center(tag)
        if not center:
            return None

        # Only check zones on the same page
        tag_page = tag.get('page_number', 1)
        tag_pdf = tag.get('pdf_path', '')

        for zone in self.zones:
            if zone.get('page_number') != tag_page:
                continue
            if zone.get('pdf_path') != tag_pdf:
                continue

            polygon = self.get_zone_polygon(zone)
            if polygon and point_in_polygon(center, polygon):
                return zone

        return None

    def get_zone_direction(self, zone: Dict) -> Optional[str]:
        """Extract direction from a zone's classification"""
        classification = zone.get('classification', {})

        # Elevation zones have 'direction'
        if 'direction' in classification:
            return classification['direction']

        # Floor plan zones have 'side'
        if 'side' in classification:
            return classification['side']

        return None

    def generate_zone_aware_comparison(self) -> List[TagComparison]:
        """
        Generate cross-reference with zone context.

        Returns list of TagComparison objects with zone_counts populated.
        """
        # Group tags by label
        tags_by_label: Dict[str, List[Dict]] = defaultdict(list)
        for tag in self.tags:
            label = tag.get('classification', {}).get('typeLabel', '')
            if label:
                tags_by_label[label].append(tag)

        comparisons = []

        for label, label_tags in sorted(tags_by_label.items()):
            comparison = TagComparison(tag_label=label)

            for tag in label_tags:
                # Find containing zone
                zone = self.find_containing_zone(tag)
                direction = self.get_zone_direction(zone) if zone else None

                # Get sheet info
                pdf_path = tag.get('pdf_path', '')
                sheet_name = Path(pdf_path).stem if pdf_path else 'unknown'

                # Update zone counts if we have direction info
                if direction:
                    comparison.add_zone_count(direction, sheet_name)

                # Also track by sheet type (would need sheet classification here)
                # For now just count total
                comparison.ext_elevation_count += 1
                if sheet_name not in comparison.ext_elevation_sheets:
                    comparison.ext_elevation_sheets.append(sheet_name)

            comparisons.append(comparison)

        return comparisons

    def get_tags_in_zone(self, zone_id: str) -> List[Dict]:
        """Get all tags that fall within a specific zone"""
        # Find the zone
        zone = None
        for z in self.zones:
            if z.get('id') == zone_id:
                zone = z
                break

        if not zone:
            return []

        polygon = self.get_zone_polygon(zone)
        if not polygon:
            return []

        zone_page = zone.get('page_number', 1)
        zone_pdf = zone.get('pdf_path', '')

        matching_tags = []
        for tag in self.tags:
            if tag.get('page_number') != zone_page:
                continue
            if tag.get('pdf_path') != zone_pdf:
                continue

            center = self.get_tag_center(tag)
            if center and point_in_polygon(center, polygon):
                matching_tags.append(tag)

        return matching_tags

    def get_summary_by_zone(self) -> Dict[str, Dict[str, int]]:
        """
        Get tag counts grouped by zone direction.

        Returns:
            Dict mapping direction -> {tag_label: count}
        """
        summary: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for tag in self.tags:
            label = tag.get('classification', {}).get('typeLabel', '')
            if not label:
                continue

            zone = self.find_containing_zone(tag)
            direction = self.get_zone_direction(zone) if zone else 'unassigned'

            summary[direction][label] += 1

        # Convert to regular dicts
        return {k: dict(v) for k, v in summary.items()}

    def to_dict(self) -> Dict:
        """Export results as dictionary"""
        comparisons = self.generate_zone_aware_comparison()
        zone_summary = self.get_summary_by_zone()

        return {
            'comparisons': [c.to_dict() for c in comparisons],
            'zone_summary': zone_summary,
            'total_tags': len(self.tags),
            'total_zones': len(self.zones)
        }
