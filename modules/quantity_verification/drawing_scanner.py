"""
Drawing Scanner for Quantity Verification

Scans floor plans and exterior elevations for tag shapes.
Uses OCR + shape detection to count door/window tags.

IMPORTANT RESTRICTIONS:
- Only scans floor plans (A1xx sheets)
- Only scans exterior elevations (A2xx, A3xx sheets)
- Does NOT scan interior elevations, sections, or details

Shape detection:
- Hexagons (common for doors)
- Circles (common for windows)
- Custom shapes based on project patterns
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import fitz  # PyMuPDF

# Optional imports for OCR and shape detection
try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

from .pattern_learner import TagPattern

logger = logging.getLogger(__name__)


@dataclass
class TagLocation:
    """Location of a detected tag on a drawing"""
    tag: str                    # The tag text (e.g., "A", "W1")
    page_num: int               # PDF page number (0-indexed)
    x: float                    # X coordinate on page
    y: float                    # Y coordinate on page
    width: float                # Bounding box width
    height: float               # Bounding box height
    confidence: float = 0.0     # Detection confidence
    shape_type: str = ""        # Shape detected (hexagon, circle, etc.)


@dataclass
class ScanResult:
    """Result from scanning a single drawing"""
    success: bool
    sheet_number: str
    sheet_name: str
    file_path: str
    tags_found: List[TagLocation] = field(default_factory=list)
    tag_counts: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class FullScanResult:
    """Result from scanning all drawings"""
    success: bool
    total_sheets_scanned: int
    total_tags_found: int
    by_tag: Dict[str, int] = field(default_factory=dict)
    by_sheet: List[ScanResult] = field(default_factory=list)
    comparison: Dict[str, Dict] = field(default_factory=dict)
    error: Optional[str] = None


class DrawingScanner:
    """
    Scans drawings for tag shapes and counts.

    Only scans:
    - Floor plans (A100-A199 or similar)
    - Exterior elevations (A200-A399 or similar)

    Does NOT scan interior elevations, sections, details, schedules.
    """

    # Sheet number patterns to INCLUDE
    FLOOR_PLAN_PATTERNS = [
        r'^A1\d{2}',     # A100-A199
        r'^A0\d{2}',     # A001-A099 (some projects)
        r'FLOOR\s*PLAN',
        r'LEVEL\s*\d+\s*PLAN',
    ]

    EXTERIOR_ELEVATION_PATTERNS = [
        r'^A2\d{2}',     # A200-A299
        r'^A3\d{2}',     # A300-A399
        r'EXTERIOR\s*ELEVATION',
        r'(?:NORTH|SOUTH|EAST|WEST)\s*ELEVATION',
        r'BUILDING\s*ELEVATION',
    ]

    # Sheet patterns to EXCLUDE
    EXCLUDE_PATTERNS = [
        r'INTERIOR\s*ELEVATION',
        r'SECTION',
        r'DETAIL',
        r'ENLARGED',
        r'SCHEDULE',
        r'NOTES',
        r'SPEC',
    ]

    def __init__(self, patterns: List[TagPattern] = None, shape_type: str = 'hexagon'):
        """
        Initialize scanner with confirmed patterns.

        Args:
            patterns: List of TagPattern objects to search for
            shape_type: Shape to detect ('hexagon', 'circle', 'square')
        """
        self.patterns = patterns or []
        self.shape_type = shape_type

    def scan_project(self, project_folder: Path) -> FullScanResult:
        """
        Scan all floor plans and exterior elevations in project.

        Args:
            project_folder: Path to project folder

        Returns:
            FullScanResult with counts and comparison
        """
        logger.info(f"[DrawingScanner] Scanning project: {project_folder.name}")

        # Find drawings to scan
        drawings = self._find_scannable_drawings(project_folder)

        if not drawings:
            return FullScanResult(
                success=False,
                total_sheets_scanned=0,
                total_tags_found=0,
                error="No floor plans or exterior elevations found"
            )

        logger.info(f"[DrawingScanner] Found {len(drawings)} drawings to scan")

        # Scan each drawing
        results = []
        total_tags = 0
        all_tag_counts = {}

        for drawing_path in drawings:
            result = self._scan_drawing(drawing_path)
            results.append(result)

            if result.success:
                total_tags += len(result.tags_found)
                for tag, count in result.tag_counts.items():
                    all_tag_counts[tag] = all_tag_counts.get(tag, 0) + count

        # Build comparison with schedule quantities
        comparison = self._build_comparison(all_tag_counts)

        return FullScanResult(
            success=len(results) > 0,
            total_sheets_scanned=len(drawings),
            total_tags_found=total_tags,
            by_tag=all_tag_counts,
            by_sheet=results,
            comparison=comparison
        )

    def _find_scannable_drawings(self, project_folder: Path) -> List[Path]:
        """Find floor plans and exterior elevations only"""
        scannable = []

        # Search in Drawings/Architectural
        arch_folder = project_folder / 'Drawings' / 'Architectural'
        if arch_folder.exists():
            for pdf in arch_folder.glob("*.pdf"):
                if self._is_scannable_drawing(pdf):
                    scannable.append(pdf)

        # Also check root Drawings folder
        drawings_folder = project_folder / 'Drawings'
        if drawings_folder.exists():
            for pdf in drawings_folder.glob("*.pdf"):
                if self._is_scannable_drawing(pdf):
                    if pdf not in scannable:
                        scannable.append(pdf)

        return scannable

    def _is_scannable_drawing(self, pdf_path: Path) -> bool:
        """Check if drawing should be scanned (floor plan or exterior elevation)"""
        name_upper = pdf_path.stem.upper()

        # Check exclusions first
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, name_upper, re.IGNORECASE):
                return False

        # Check if floor plan
        for pattern in self.FLOOR_PLAN_PATTERNS:
            if re.search(pattern, name_upper, re.IGNORECASE):
                return True

        # Check if exterior elevation
        for pattern in self.EXTERIOR_ELEVATION_PATTERNS:
            if re.search(pattern, name_upper, re.IGNORECASE):
                return True

        return False

    def _scan_drawing(self, pdf_path: Path) -> ScanResult:
        """Scan a single drawing for tags"""
        logger.debug(f"[DrawingScanner] Scanning: {pdf_path.name}")

        try:
            tags_found = []
            tag_counts = {}

            with fitz.open(str(pdf_path)) as doc:
                for page_num in range(len(doc)):
                    page = doc[page_num]

                    # Method 1: Text-based search
                    text_tags = self._search_text(page)
                    for tag, loc in text_tags:
                        tags_found.append(TagLocation(
                            tag=tag,
                            page_num=page_num,
                            x=loc[0], y=loc[1],
                            width=loc[2], height=loc[3],
                            confidence=0.8,
                            shape_type='text'
                        ))
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1

                    # Method 2: Shape detection (if OpenCV available)
                    if HAS_CV2:
                        shape_tags = self._detect_shapes(page)
                        for tag, loc in shape_tags:
                            # Avoid duplicates from text search
                            is_duplicate = any(
                                abs(t.x - loc[0]) < 20 and abs(t.y - loc[1]) < 20
                                for t in tags_found
                            )
                            if not is_duplicate:
                                tags_found.append(TagLocation(
                                    tag=tag,
                                    page_num=page_num,
                                    x=loc[0], y=loc[1],
                                    width=loc[2], height=loc[3],
                                    confidence=0.7,
                                    shape_type=self.shape_type
                                ))
                                tag_counts[tag] = tag_counts.get(tag, 0) + 1

            return ScanResult(
                success=True,
                sheet_number=self._extract_sheet_number(pdf_path),
                sheet_name=pdf_path.stem,
                file_path=str(pdf_path),
                tags_found=tags_found,
                tag_counts=tag_counts
            )

        except Exception as e:
            logger.error(f"[DrawingScanner] Error scanning {pdf_path.name}: {e}")
            return ScanResult(
                success=False,
                sheet_number="",
                sheet_name=pdf_path.stem,
                file_path=str(pdf_path),
                error=str(e)
            )

    def _search_text(self, page: fitz.Page) -> List[Tuple[str, Tuple[float, float, float, float]]]:
        """Search for tag patterns in page text"""
        found = []

        if not self.patterns:
            return found

        # Build combined regex from all patterns
        pattern_regexes = []
        for p in self.patterns:
            if p.examples:
                # Use exact examples
                for example in p.examples:
                    pattern_regexes.append(re.escape(example))
            elif p.regex:
                pattern_regexes.append(p.regex)

        if not pattern_regexes:
            return found

        combined_regex = '|'.join(f'({r})' for r in pattern_regexes)

        # Search text with location
        try:
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # Not text
                    continue

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        bbox = span.get("bbox", (0, 0, 0, 0))

                        matches = re.finditer(combined_regex, text, re.IGNORECASE)
                        for match in matches:
                            found.append((match.group(), bbox))
        except Exception as e:
            logger.debug(f"[DrawingScanner] Text search error: {e}")

        return found

    def _detect_shapes(self, page: fitz.Page) -> List[Tuple[str, Tuple[float, float, float, float]]]:
        """Detect shapes and OCR text inside them"""
        found = []

        if not HAS_CV2:
            return found

        try:
            # Render page to image
            mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR
            pix = page.get_pixmap(matrix=mat)
            img = np.frombuffer(pix.samples, dtype=np.uint8)
            img = img.reshape(pix.height, pix.width, pix.n)

            # Convert to grayscale
            if pix.n == 4:  # RGBA
                gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
            else:
                gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

            # Find contours
            _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                # Filter by shape
                if self._is_target_shape(contour):
                    x, y, w, h = cv2.boundingRect(contour)

                    # OCR the shape region
                    if HAS_TESSERACT:
                        roi = gray[y:y+h, x:x+w]
                        text = pytesseract.image_to_string(roi, config='--psm 10').strip()
                        if text and len(text) <= 5:  # Tags are short
                            # Convert coordinates back (accounting for zoom)
                            found.append((text, (x/2, y/2, w/2, h/2)))

        except Exception as e:
            logger.debug(f"[DrawingScanner] Shape detection error: {e}")

        return found

    def _is_target_shape(self, contour) -> bool:
        """Check if contour matches target shape"""
        if not HAS_CV2:
            return False

        # Get contour properties
        area = cv2.contourArea(contour)
        if area < 100 or area > 5000:  # Filter by size
            return False

        # Approximate polygon
        epsilon = 0.04 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        if self.shape_type == 'hexagon':
            return 5 <= len(approx) <= 7
        elif self.shape_type == 'circle':
            # Check circularity
            perimeter = cv2.arcLength(contour, True)
            circularity = 4 * np.pi * area / (perimeter * perimeter)
            return circularity > 0.7
        elif self.shape_type == 'square':
            return len(approx) == 4

        return False

    def _extract_sheet_number(self, pdf_path: Path) -> str:
        """Extract sheet number from filename"""
        name = pdf_path.stem

        # Common patterns: "A101 - Floor Plan", "A-101", etc.
        match = re.match(r'^([A-Z]-?\d{1,3}(?:\.\d+)?)', name, re.IGNORECASE)
        if match:
            return match.group(1)

        return name[:10]  # First 10 chars as fallback

    def _build_comparison(self, drawing_counts: Dict[str, int]) -> Dict[str, Dict]:
        """Build comparison between schedule quantities and drawing counts"""
        comparison = {}

        for pattern in self.patterns:
            for tag in pattern.examples:
                schedule_qty = pattern.quantity if tag == pattern.examples[0] else 0
                drawing_qty = drawing_counts.get(tag, 0)

                comparison[tag] = {
                    'category': pattern.category,
                    'schedule_qty': schedule_qty,
                    'drawing_qty': drawing_qty,
                    'match': schedule_qty == drawing_qty if schedule_qty > 0 else None,
                    'difference': drawing_qty - schedule_qty if schedule_qty > 0 else None
                }

        return comparison
