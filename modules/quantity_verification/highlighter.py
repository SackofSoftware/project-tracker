"""
PDF Highlighter for Quantity Verification

Generates highlighted PDFs showing where tags were counted.
Uses PyMuPDF annotations to mark tag locations.

Output:
- Creates highlighted copies in project folder
- Different colors for different tag categories
- Adds count summary to each page
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import fitz  # PyMuPDF

from .drawing_scanner import ScanResult, TagLocation

logger = logging.getLogger(__name__)


# Color definitions (RGB tuples, 0-1 range)
COLORS = {
    'door': (1.0, 0.4, 0.4),      # Red
    'window': (0.4, 0.6, 1.0),    # Blue
    'hardware': (0.5, 0.8, 0.5),  # Green
    'default': (1.0, 0.8, 0.2),   # Yellow
}

# Highlight styles
HIGHLIGHT_STYLES = {
    'circle': 'Circle',
    'square': 'Square',
    'underline': 'Underline',
    'highlight': 'Highlight',
}


@dataclass
class HighlightResult:
    """Result from highlighting a PDF"""
    success: bool
    source_file: str
    output_file: str
    tags_highlighted: int
    error: Optional[str] = None


class QuantityHighlighter:
    """
    Generates highlighted PDFs showing counted items.

    Creates annotated copies of drawings with:
    - Circles/highlights around detected tags
    - Color coding by category (door, window, hardware)
    - Count summary at bottom of each page
    """

    def __init__(
        self,
        output_folder: Path = None,
        style: str = 'circle',
        show_summary: bool = True
    ):
        """
        Initialize highlighter.

        Args:
            output_folder: Where to save highlighted PDFs (default: same as source)
            style: Highlight style ('circle', 'square', 'highlight')
            show_summary: Whether to add count summary to pages
        """
        self.output_folder = output_folder
        self.style = style
        self.show_summary = show_summary

    def highlight_scan_results(
        self,
        scan_results: List[ScanResult],
        project_folder: Path
    ) -> List[HighlightResult]:
        """
        Highlight all scan results.

        Args:
            scan_results: List of ScanResult from DrawingScanner
            project_folder: Project folder path

        Returns:
            List of HighlightResult for each processed PDF
        """
        results = []

        # Create output folder
        output_path = self.output_folder or (project_folder / 'Verification-Highlights')
        output_path.mkdir(parents=True, exist_ok=True)

        for scan_result in scan_results:
            if not scan_result.success or not scan_result.tags_found:
                continue

            result = self._highlight_single_pdf(scan_result, output_path)
            results.append(result)

        logger.info(f"[QuantityHighlighter] Highlighted {len(results)} PDFs")
        return results

    def _highlight_single_pdf(
        self,
        scan_result: ScanResult,
        output_folder: Path
    ) -> HighlightResult:
        """Highlight a single PDF with found tags"""
        source_path = Path(scan_result.file_path)
        output_path = output_folder / f"HIGHLIGHTED_{source_path.name}"

        logger.debug(f"[QuantityHighlighter] Highlighting: {source_path.name}")

        try:
            # Open and process PDF
            doc = fitz.open(str(source_path))

            # Group tags by page
            tags_by_page = {}
            for tag_loc in scan_result.tags_found:
                page_num = tag_loc.page_num
                if page_num not in tags_by_page:
                    tags_by_page[page_num] = []
                tags_by_page[page_num].append(tag_loc)

            # Highlight each page
            for page_num, tags in tags_by_page.items():
                if page_num < len(doc):
                    page = doc[page_num]
                    self._highlight_page(page, tags, scan_result.tag_counts)

            # Save highlighted PDF
            doc.save(str(output_path))
            doc.close()

            return HighlightResult(
                success=True,
                source_file=str(source_path),
                output_file=str(output_path),
                tags_highlighted=len(scan_result.tags_found)
            )

        except Exception as e:
            logger.error(f"[QuantityHighlighter] Error highlighting {source_path.name}: {e}")
            return HighlightResult(
                success=False,
                source_file=str(source_path),
                output_file="",
                tags_highlighted=0,
                error=str(e)
            )

    def _highlight_page(
        self,
        page: fitz.Page,
        tags: List[TagLocation],
        tag_counts: Dict[str, int]
    ):
        """Add highlights and summary to a single page"""
        # Highlight each tag
        for tag_loc in tags:
            color = self._get_color_for_tag(tag_loc)
            rect = fitz.Rect(
                tag_loc.x - 5,
                tag_loc.y - 5,
                tag_loc.x + tag_loc.width + 5,
                tag_loc.y + tag_loc.height + 5
            )

            if self.style == 'circle':
                # Draw circle annotation
                annot = page.add_circle_annot(rect)
                annot.set_colors(stroke=color, fill=None)
                annot.set_border(width=2)
                annot.update()

            elif self.style == 'square':
                # Draw rectangle annotation
                annot = page.add_rect_annot(rect)
                annot.set_colors(stroke=color, fill=None)
                annot.set_border(width=2)
                annot.update()

            elif self.style == 'highlight':
                # Use highlight annotation
                annot = page.add_highlight_annot(rect)
                annot.set_colors(stroke=color)
                annot.update()

        # Add summary box at bottom
        if self.show_summary and tag_counts:
            self._add_summary_box(page, tag_counts)

    def _get_color_for_tag(self, tag_loc: TagLocation) -> Tuple[float, float, float]:
        """Get color based on tag category"""
        # Try to determine category from tag
        tag_upper = tag_loc.tag.upper()

        if tag_upper.startswith('D') or tag_upper.startswith('HM'):
            return COLORS['door']
        elif tag_upper.startswith('W') or 'WIN' in tag_upper:
            return COLORS['window']
        elif tag_upper.startswith('H') and ('S' in tag_upper or 'W' in tag_upper):
            return COLORS['hardware']

        return COLORS['default']

    def _add_summary_box(self, page: fitz.Page, tag_counts: Dict[str, int]):
        """Add count summary box to page"""
        # Create summary text
        summary_lines = ["TAG COUNTS:"]
        for tag, count in sorted(tag_counts.items()):
            summary_lines.append(f"  {tag}: {count}")

        summary_text = "\n".join(summary_lines)

        # Calculate position (bottom-left corner with margin)
        page_rect = page.rect
        margin = 20
        box_width = 150
        box_height = 15 + (len(tag_counts) * 12)

        # Summary box rectangle
        box_rect = fitz.Rect(
            margin,
            page_rect.height - margin - box_height,
            margin + box_width,
            page_rect.height - margin
        )

        # Draw white background
        shape = page.new_shape()
        shape.draw_rect(box_rect)
        shape.finish(color=(0, 0, 0), fill=(1, 1, 1))
        shape.commit()

        # Add text
        page.insert_text(
            point=(margin + 5, page_rect.height - margin - box_height + 12),
            text=summary_text,
            fontsize=9,
            fontname="helv",
            color=(0, 0, 0)
        )

    def create_comparison_report(
        self,
        comparison: Dict[str, Dict],
        project_folder: Path
    ) -> Path:
        """
        Create a comparison report PDF showing schedule vs drawing counts.

        Args:
            comparison: Comparison data from DrawingScanner
            project_folder: Project folder path

        Returns:
            Path to generated report PDF
        """
        output_path = project_folder / 'Verification-Highlights' / 'COMPARISON_REPORT.pdf'
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create new PDF document
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)  # Letter size

        # Title
        page.insert_text(
            point=(72, 72),
            text="QUANTITY VERIFICATION REPORT",
            fontsize=18,
            fontname="helv-b",
            color=(0, 0, 0)
        )

        # Table headers
        y = 120
        headers = ["Tag", "Schedule Qty", "Drawing Qty", "Status"]
        x_positions = [72, 200, 320, 440]

        for i, header in enumerate(headers):
            page.insert_text(
                point=(x_positions[i], y),
                text=header,
                fontsize=11,
                fontname="helv-b",
                color=(0, 0, 0)
            )

        # Horizontal line
        y += 5
        shape = page.new_shape()
        shape.draw_line(fitz.Point(72, y), fitz.Point(540, y))
        shape.finish(color=(0, 0, 0), width=0.5)
        shape.commit()

        # Data rows
        y += 20
        for tag, data in sorted(comparison.items()):
            schedule_qty = data.get('schedule_qty', '-')
            drawing_qty = data.get('drawing_qty', 0)
            match = data.get('match')

            if match is None:
                status = "N/A"
                status_color = (0.5, 0.5, 0.5)
            elif match:
                status = "OK"
                status_color = (0, 0.6, 0)
            else:
                diff = data.get('difference', 0)
                status = f"DIFF: {diff:+d}"
                status_color = (0.8, 0, 0)

            # Tag
            page.insert_text(
                point=(x_positions[0], y),
                text=str(tag),
                fontsize=10,
                fontname="helv",
                color=(0, 0, 0)
            )

            # Schedule qty
            page.insert_text(
                point=(x_positions[1], y),
                text=str(schedule_qty),
                fontsize=10,
                fontname="helv",
                color=(0, 0, 0)
            )

            # Drawing qty
            page.insert_text(
                point=(x_positions[2], y),
                text=str(drawing_qty),
                fontsize=10,
                fontname="helv",
                color=(0, 0, 0)
            )

            # Status
            page.insert_text(
                point=(x_positions[3], y),
                text=status,
                fontsize=10,
                fontname="helv-b",
                color=status_color
            )

            y += 18
            if y > 720:  # New page if needed
                page = doc.new_page(width=612, height=792)
                y = 72

        # Save report
        doc.save(str(output_path))
        doc.close()

        logger.info(f"[QuantityHighlighter] Created comparison report: {output_path}")
        return output_path
