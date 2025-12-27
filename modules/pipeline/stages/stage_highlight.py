"""
Stage 7: PDF Highlighting
Highlights Division 8 scope items (doors, windows, storefront, curtain walls)
on floor plans and exterior elevations only.
"""

import os
import re
import fitz  # PyMuPDF
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result of a pipeline stage execution."""
    success: bool
    data: Dict
    error: Optional[str] = None


class HighlightStage:
    """
    Stage 7: PDF Highlighting

    Highlights Division 8 scope items on specific sheet types:
    - Floor plans (A1xx sheets)
    - Exterior elevations (A2xx sheets)

    Excludes: RCPs, interior elevations, sections, details, schedules
    """

    # Patterns for sheets to INCLUDE for highlighting
    INCLUDE_PATTERNS = [
        r'\bA1[0-9]{2}\b',  # Floor plans A101, A102, etc.
        r'\bA2[0-9]{2}\b',  # Exterior elevations A201, A202, etc.
        r'(?:NORTH|SOUTH|EAST|WEST)\s+(?:EXTERIOR\s+)?ELEVATION',
        r'FLOOR\s+PLAN',
        r'FIRST\s+FLOOR',
        r'SECOND\s+FLOOR',
        r'THIRD\s+FLOOR',
        r'GROUND\s+FLOOR',
        r'BASEMENT',
    ]

    # Patterns for sheets to EXCLUDE from highlighting
    EXCLUSION_PATTERNS = [
        r'REFLECTED\s+CEILING',
        r'\bRCP\b',
        r'\bA9[0-9]{2}\b',  # RCP sheets
        r'INTERIOR\s+ELEVATION',
        r'SECTION\s+[A-Z0-9]',
        r'DETAIL',
        r'SCHEDULE',
        r'ENLARGED',
        r'PARTITION',
    ]

    # Division 8 scope items to highlight
    HIGHLIGHT_KEYWORDS = [
        # Doors
        r'\bDOOR\b',
        r'\bENTRY\b',
        r'\bENTRANCE\b',
        r'\bDR\b',

        # Windows
        r'\bWINDOW\b',
        r'\bWDW\b',
        r'\bWIN\b',

        # Storefront
        r'\bSTOREFRONT\b',
        r'\bSTORE\s+FRONT\b',
        r'\bSF\b',

        # Curtain Wall
        r'\bCURTAIN\s+WALL\b',
        r'\bCW\b',

        # Glazing
        r'\bGLAZING\b',
        r'\bGLASS\b',

        # Hardware
        r'\bHARDWARE\b',
        r'\bHDW\b',
    ]

    def __init__(self, project_folder: Path, ai_provider=None):
        """
        Initialize the highlighting stage.

        Args:
            project_folder: Path to the project folder
            ai_provider: Optional AI provider (not used in this stage)
        """
        self.project_folder = Path(project_folder)
        self.highlight_color = (1, 1, 0)  # Yellow (RGB normalized to 0-1)
        self.highlight_opacity = 0.3

    async def run(self) -> StageResult:
        """
        Execute the PDF highlighting stage.

        Returns:
            StageResult with success status and highlighted file information
        """
        try:
            logger.info("Starting PDF highlighting stage...")

            # Get PDF files from project data
            pdf_files = self._get_pdf_files()
            if not pdf_files:
                logger.info("No PDF files found to highlight - this is OK for projects without drawings")
                return StageResult(
                    success=True,
                    data={'message': 'No PDF files found to highlight', 'highlighted_files': [], 'skipped_files': []},
                    error=None
                )

            highlighted_files = []
            skipped_files = []

            for pdf_path in pdf_files:
                result = await self._process_pdf(pdf_path)
                if result['highlighted']:
                    highlighted_files.append(result)
                else:
                    skipped_files.append(result)

            logger.info(f"Highlighted {len(highlighted_files)} PDF(s), skipped {len(skipped_files)}")

            return StageResult(
                success=True,
                data={
                    'highlighted_files': highlighted_files,
                    'skipped_files': skipped_files,
                    'total_processed': len(pdf_files),
                    'total_highlighted': len(highlighted_files),
                    'total_skipped': len(skipped_files)
                }
            )

        except Exception as e:
            logger.error(f"Error in PDF highlighting stage: {str(e)}", exc_info=True)
            return StageResult(
                success=False,
                data={},
                error=f"Highlighting stage failed: {str(e)}"
            )

    def _get_pdf_files(self) -> List[str]:
        """
        Find PDF files in the project - checks Drawings folder and project root.

        Returns:
            List of PDF file paths (prioritizes Drawings folder if exists)
        """
        pdf_files = []

        # Look in Drawings folder first
        drawings_folder = self.project_folder / 'Drawings'
        if drawings_folder.exists() and drawings_folder.is_dir():
            pdf_files = [str(p) for p in drawings_folder.glob('*.pdf')]
            logger.info(f"  Found {len(pdf_files)} PDFs in Drawings/ folder")

        # Also check project root for architectural PDFs (A-xxx sheets)
        root_pdfs = [str(p) for p in self.project_folder.glob('*.pdf')]
        # Filter for likely drawing files (not specs)
        for pdf in root_pdfs:
            pdf_name = Path(pdf).name.lower()
            # Include architectural sheets or drawing sets
            if (pdf_name.startswith('a-') or
                pdf_name.startswith('a0') or
                pdf_name.startswith('a1') or
                pdf_name.startswith('a2') or
                'plan' in pdf_name or
                'elevation' in pdf_name or
                'arch' in pdf_name):
                if pdf not in pdf_files:
                    pdf_files.append(pdf)

        logger.info(f"  Found {len(pdf_files)} PDF files to check for highlighting")
        return pdf_files

    def _should_highlight_sheet(self, text: str) -> bool:
        """
        Determine if a sheet should be highlighted based on its content.

        Args:
            text: Text content of the sheet

        Returns:
            True if sheet should be highlighted, False otherwise
        """
        text_upper = text.upper()

        # First check exclusion patterns - if any match, do NOT highlight
        for pattern in self.EXCLUSION_PATTERNS:
            if re.search(pattern, text_upper, re.IGNORECASE):
                logger.debug(f"Sheet excluded due to pattern: {pattern}")
                return False

        # Then check inclusion patterns - must match at least one to highlight
        for pattern in self.INCLUDE_PATTERNS:
            if re.search(pattern, text_upper, re.IGNORECASE):
                logger.debug(f"Sheet included due to pattern: {pattern}")
                return True

        return False

    def _find_highlight_areas(self, page: fitz.Page) -> List[fitz.Rect]:
        """
        Find areas on the page that should be highlighted.

        Args:
            page: PyMuPDF page object

        Returns:
            List of rectangles to highlight
        """
        highlight_rects = []

        # Search for each keyword
        for keyword_pattern in self.HIGHLIGHT_KEYWORDS:
            # Use text search to find instances
            text_instances = page.search_for(
                keyword_pattern,
                flags=fitz.TEXT_DEHYPHENATE | fitz.TEXT_PRESERVE_WHITESPACE
            )

            # Also try regex-based search for more complex patterns
            try:
                text = page.get_text()
                matches = re.finditer(keyword_pattern, text, re.IGNORECASE)
                for match in matches:
                    # Get the matched text and search for it
                    matched_text = match.group()
                    rects = page.search_for(matched_text)
                    text_instances.extend(rects)
            except Exception as e:
                logger.debug(f"Regex search failed for {keyword_pattern}: {e}")

            highlight_rects.extend(text_instances)

        # Remove duplicates and merge overlapping rectangles
        if highlight_rects:
            highlight_rects = self._merge_overlapping_rects(highlight_rects)

        return highlight_rects

    def _merge_overlapping_rects(self, rects: List[fitz.Rect]) -> List[fitz.Rect]:
        """
        Merge overlapping or nearby rectangles to reduce clutter.

        Args:
            rects: List of rectangles

        Returns:
            List of merged rectangles
        """
        if not rects:
            return []

        # Sort by x-coordinate
        sorted_rects = sorted(rects, key=lambda r: (r.y0, r.x0))
        merged = [sorted_rects[0]]

        for current in sorted_rects[1:]:
            previous = merged[-1]

            # Check if rectangles are close enough to merge (within 10 points)
            if (abs(current.y0 - previous.y0) < 10 and
                abs(current.x0 - previous.x1) < 50):
                # Merge rectangles
                merged[-1] = fitz.Rect(
                    min(previous.x0, current.x0),
                    min(previous.y0, current.y0),
                    max(previous.x1, current.x1),
                    max(previous.y1, current.y1)
                )
            else:
                merged.append(current)

        return merged

    def _create_output_path(self, input_path: str) -> str:
        """
        Create output path for highlighted PDF.

        Args:
            input_path: Original PDF file path

        Returns:
            Path for the highlighted PDF
        """
        input_file = Path(input_path)
        output_dir = input_file.parent / "Highlighted"
        output_dir.mkdir(exist_ok=True)

        # Create output filename
        output_filename = f"{input_file.stem}_highlighted{input_file.suffix}"
        output_path = output_dir / output_filename

        return str(output_path)

    async def _process_pdf(self, pdf_path: str) -> Dict:
        """
        Process a single PDF file for highlighting.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Dictionary with processing results
        """
        result = {
            'input_file': pdf_path,
            'output_file': None,
            'highlighted': False,
            'pages_highlighted': 0,
            'total_pages': 0,
            'highlights_added': 0,
            'reason': None
        }

        try:
            # Open the PDF
            doc = fitz.open(pdf_path)
            result['total_pages'] = len(doc)

            # Check if any pages should be highlighted
            pages_to_highlight = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()

                if self._should_highlight_sheet(text):
                    pages_to_highlight.append(page_num)

            if not pages_to_highlight:
                result['reason'] = "No eligible sheets found (not floor plans or exterior elevations)"
                doc.close()
                return result

            # Create output document
            output_path = self._create_output_path(pdf_path)

            # Process each page that should be highlighted
            total_highlights = 0
            for page_num in pages_to_highlight:
                page = doc[page_num]

                # Find areas to highlight
                highlight_rects = self._find_highlight_areas(page)

                # Add highlights
                for rect in highlight_rects:
                    # Add yellow highlight annotation
                    highlight = page.add_highlight_annot(rect)
                    highlight.set_colors(stroke=self.highlight_color)
                    highlight.set_opacity(self.highlight_opacity)
                    highlight.update()
                    total_highlights += 1

                if highlight_rects:
                    result['pages_highlighted'] += 1

            # Save the highlighted PDF
            if total_highlights > 0:
                doc.save(output_path, garbage=4, deflate=True)
                result['output_file'] = output_path
                result['highlighted'] = True
                result['highlights_added'] = total_highlights
                logger.info(f"Created highlighted PDF: {output_path} ({total_highlights} highlights)")
            else:
                result['reason'] = "No Division 8 items found to highlight"

            doc.close()

        except Exception as e:
            logger.error(f"Error processing PDF {pdf_path}: {str(e)}", exc_info=True)
            result['reason'] = f"Error: {str(e)}"

        return result

    def get_stage_name(self) -> str:
        """Return the name of this stage."""
        return "PDF Highlighting"

    def get_stage_number(self) -> int:
        """Return the stage number."""
        return 7
