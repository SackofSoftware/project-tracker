"""
Stage 4: Drawing Splitting

Splits drawing set PDFs by individual page into separate sheet PDFs.
Uses LLM-assisted TOC parsing to extract sheet numbers and titles.
Falls back to PDF bookmarks and text patterns if TOC parsing fails.
Classifies sheets by discipline and organizes into subfolders.

Output format: {sheet_number} - {sheet_title}.pdf
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a pipeline stage"""
    success: bool
    data: Dict
    error: Optional[str] = None


@dataclass
class SheetInfo:
    """Information about a single drawing sheet"""
    page_number: int
    sheet_number: str
    sheet_title: str
    discipline: str
    discipline_name: str


class SplitDrawingsStage:
    """
    Stage 4: Drawing Splitting

    Splits drawing set PDFs into individual sheet PDFs.
    Extracts sheet numbers, titles, and classifies by discipline.
    """

    # Sheet number patterns
    # Matches: A101, A-101, A2.1, S-100, S100, M1.1, E-201, etc.
    SHEET_PATTERNS = [
        # Standard: A101, S100, E201
        re.compile(r'\b([ASMEPCLGFTI])-?(\d{1,3})(?:\.(\d+))?\b', re.IGNORECASE),
        # With dash: A-101, S-100
        re.compile(r'\b([ASMEPCLGFTI])\s*-\s*(\d{1,3})(?:\.(\d+))?\b', re.IGNORECASE),
        # With decimal: A2.1, S3.5
        re.compile(r'\b([ASMEPCLGFTI])(\d{1,2})\.(\d+)\b', re.IGNORECASE),
        # General index: G001, G-001, G1
        re.compile(r'\b(G|GI|GN)-?(\d{1,3})\b', re.IGNORECASE),
    ]

    # Discipline classifications
    DISCIPLINES = {
        'A': ('Architectural', 'Architectural'),
        'S': ('Structural', 'Structural'),
        'M': ('Mechanical', 'Mechanical'),
        'E': ('Electrical', 'Electrical'),
        'P': ('Plumbing', 'Plumbing'),
        'C': ('Civil', 'Civil'),
        'L': ('Landscape', 'Landscape'),
        'G': ('General', 'General'),
        'GI': ('General', 'General Information'),
        'GN': ('General', 'General Notes'),
        'F': ('Fire', 'Fire Protection'),
        'T': ('Telecom', 'Telecommunications'),
        'I': ('Interiors', 'Interiors'),
        'H': ('HVAC', 'HVAC'),
    }

    # Title extraction patterns
    TITLE_PATTERNS = [
        # Title appearing after scale notation (common in architectural drawings)
        # Matches: "SCALE: 1/8"=1'-0"\nTHIRD FLOOR PLAN"
        re.compile(r'SCALE:\s*[^\n]+\n\s*([A-Z][A-Z\s&,\-]{4,60})\s*(?:\n|$)', re.MULTILINE),
        # Common title block patterns
        re.compile(r'SHEET\s+TITLE[:\s]+([^\n]{5,80})', re.IGNORECASE),
        re.compile(r'DRAWING\s+TITLE[:\s]+([^\n]{5,80})', re.IGNORECASE),
        # Sheet number followed by title
        re.compile(r'[ASMEPCLGFTI]-?\d+\s+[-–—]\s+([^\n]{5,80})', re.IGNORECASE),
    ]

    # Patterns to EXCLUDE from title extraction (common metadata, not actual titles)
    EXCLUDED_TITLE_PATTERNS = [
        'SCALE AS NOTED',
        'NOT TO SCALE',
        'NTS',
        'SEE DETAILS',
        'SEE SHEET',
        'REFER TO',
        'AS NOTED',
        'VARIES',
        'AS SHOWN',
        'TYP',
        'TYPICAL',
        'N.T.S.',
        'DO NOT SCALE',
        'SCALE:',
        'DATE:',
        'DRAWN BY',
        'CHECKED BY',
        'PROJECT NO',
        'SHEET NO',
    ]

    def __init__(self, project_folder: Path, ai_provider=None):
        self.project_folder = Path(project_folder)
        self.ai = ai_provider

    async def run(self) -> StageResult:
        """Execute the drawing splitting stage"""
        try:
            # Find drawing set PDFs
            drawing_pdfs = self._find_drawing_sets()
            if not drawing_pdfs:
                logger.warning("[SplitDrawings] No drawing sets found")
                return StageResult(
                    success=True,  # Not a failure - just no drawings
                    data={'message': 'No drawing sets found', 'sheets_extracted': []},
                )

            logger.info(f"[SplitDrawings] Found {len(drawing_pdfs)} drawing set(s)")

            # Create base output directory
            output_base = self.project_folder / 'Drawings'
            output_base.mkdir(parents=True, exist_ok=True)

            # Process each drawing set
            all_sheets = []
            total_extracted = 0

            for drawing_pdf in drawing_pdfs:
                logger.info(f"[SplitDrawings] Processing: {drawing_pdf.name}")
                sheets = await self._process_drawing_set(drawing_pdf, output_base)
                all_sheets.extend(sheets)
                total_extracted += len(sheets)

            # Organize by discipline
            discipline_summary = self._summarize_by_discipline(all_sheets)

            return StageResult(
                success=True,
                data={
                    'sheets_extracted': total_extracted,
                    'drawing_sets_processed': len(drawing_pdfs),
                    'disciplines': discipline_summary,
                    'sheets': [
                        {
                            'sheet_number': s.sheet_number,
                            'title': s.sheet_title,
                            'discipline': s.discipline_name,
                        }
                        for s in all_sheets
                    ]
                }
            )

        except Exception as e:
            logger.error(f"[SplitDrawings] Error: {e}")
            return StageResult(
                success=False,
                data={},
                error=str(e)
            )

    # Keywords indicating cutsheets/equipment docs (NOT drawing sets)
    CUTSHEET_KEYWORDS = [
        'cutsheet', 'cut sheet', 'spec sheet', 'data sheet', 'datasheet',
        'product sheet', 'submittal', 'selection', 'brochure', 'catalog',
        'installation', 'instruction', 'manual', 'guide', 'report',
        'assessment', 'geotechnical', 'environmental', 'survey',
    ]

    # Keywords indicating actual drawing sets
    DRAWING_SET_KEYWORDS = [
        'drawings', 'drawing', 'combined', 'architectural', 'structural',
        'mechanical', 'electrical', 'plumbing', 'civil', 'landscape',
    ]

    def _find_drawing_sets(self) -> List[Path]:
        """Find drawing set PDFs in the Drawings folder (skip cutsheets/equipment docs)"""
        drawings_folder = self.project_folder / 'Drawings'

        if not drawings_folder.exists():
            return []

        # Look for PDFs directly in Drawings folder (not in subfolders)
        drawing_pdfs = []

        for pdf in drawings_folder.glob("*.pdf"):
            # Skip individual sheets (they have sheet numbers in filename)
            if self._looks_like_individual_sheet(pdf.name):
                continue

            # Skip cutsheets and equipment docs (don't split these)
            if self._looks_like_cutsheet(pdf.name):
                logger.debug(f"[SplitDrawings] Skipping cutsheet: {pdf.name}")
                continue

            # Skip very small files (< 500KB) - likely cutsheets
            if pdf.stat().st_size < 500 * 1024:
                logger.debug(f"[SplitDrawings] Skipping small file: {pdf.name}")
                continue

            drawing_pdfs.append(pdf)

        return drawing_pdfs

    def _looks_like_cutsheet(self, filename: str) -> bool:
        """Check if filename looks like a cutsheet/equipment doc (not a drawing set)"""
        filename_lower = filename.lower()

        # If it contains cutsheet keywords, it's not a drawing set
        for keyword in self.CUTSHEET_KEYWORDS:
            if keyword in filename_lower:
                return True

        # If it contains drawing set keywords, it IS a drawing set
        for keyword in self.DRAWING_SET_KEYWORDS:
            if keyword in filename_lower:
                return False

        # Check for common equipment model patterns (letters-numbers like "EF-5" or "HRSH090")
        if re.search(r'^[A-Z]{1,4}-?\d+', filename, re.IGNORECASE):
            return True

        # Check for vendor/manufacturer patterns
        vendor_patterns = ['daikin', 'berner', 'kelley', 'mac', 'cutsheet', 'essence']
        for vendor in vendor_patterns:
            if vendor in filename_lower:
                return True

        return False

    def _looks_like_individual_sheet(self, filename: str) -> bool:
        """Check if filename looks like an individual sheet (not a drawing set)"""
        # Individual sheets typically start with sheet number: "A101 - Floor Plan.pdf"
        for pattern in self.SHEET_PATTERNS:
            if pattern.match(filename):
                return True
        return False

    async def _process_drawing_set(self, pdf_path: Path, output_base: Path) -> List[SheetInfo]:
        """Process a single drawing set PDF into individual sheets"""
        sheets = []

        try:
            # Try LLM-assisted TOC parsing first (much more accurate)
            toc_sheets = await self._parse_toc_with_llm(pdf_path)

            with fitz.open(str(pdf_path)) as doc:
                total_pages = len(doc)

                # Build page-to-sheet mapping from TOC
                toc_map = {}
                if toc_sheets:
                    for toc_sheet in toc_sheets:
                        # TOC page numbers are 1-indexed, convert to 0-indexed
                        page_idx = toc_sheet.page_num - 1
                        if 0 <= page_idx < total_pages:
                            toc_map[page_idx] = toc_sheet
                    logger.info(f"[SplitDrawings] TOC parser found {len(toc_map)} sheets")

                # Fall back to bookmarks if TOC parsing didn't work well
                bookmarks = {}
                if len(toc_map) < total_pages // 2:  # Less than half pages mapped
                    bookmarks = self._extract_bookmarks(doc)
                    if bookmarks:
                        logger.info(f"[SplitDrawings] Using bookmarks for {len(bookmarks)} sheets")

                # Process each page
                for page_num in range(total_pages):
                    page = doc[page_num]

                    # Priority 1: TOC parser result
                    if page_num in toc_map:
                        toc_sheet = toc_map[page_num]
                        discipline = self._get_discipline(toc_sheet.sheet_id)
                        discipline_name = self.DISCIPLINES.get(discipline, ('Uncategorized', 'Uncategorized'))[1]

                        sheet_info = SheetInfo(
                            page_number=page_num,
                            sheet_number=toc_sheet.sheet_id,
                            sheet_title=toc_sheet.title,
                            discipline=discipline,
                            discipline_name=discipline_name
                        )
                    # Priority 2: Bookmark info
                    elif page_num in bookmarks:
                        sheet_number, sheet_title = bookmarks[page_num]
                        discipline = self._get_discipline(sheet_number)
                        discipline_name = self.DISCIPLINES.get(discipline, ('Uncategorized', 'Uncategorized'))[1]

                        sheet_info = SheetInfo(
                            page_number=page_num,
                            sheet_number=sheet_number,
                            sheet_title=sheet_title,
                            discipline=discipline,
                            discipline_name=discipline_name
                        )
                    # Priority 3: Text extraction
                    else:
                        sheet_info = self._extract_sheet_info(page, page_num, None)

                    if not sheet_info:
                        logger.warning(f"[SplitDrawings] Could not extract sheet info for page {page_num + 1}")
                        # Create fallback sheet info
                        sheet_info = SheetInfo(
                            page_number=page_num,
                            sheet_number=f"SHEET-{page_num + 1:03d}",
                            sheet_title="Untitled Sheet",
                            discipline="U",
                            discipline_name="Uncategorized"
                        )

                    # Create discipline subfolder
                    discipline_folder = output_base / sheet_info.discipline_name
                    discipline_folder.mkdir(parents=True, exist_ok=True)

                    # Create output filename
                    safe_title = self._sanitize_filename(sheet_info.sheet_title)
                    output_filename = f"{sheet_info.sheet_number} - {safe_title}.pdf"
                    output_path = discipline_folder / output_filename

                    # Extract single page to new PDF
                    new_doc = fitz.open()
                    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

                    new_doc.save(
                        str(output_path),
                        garbage=4,
                        deflate=True,
                        clean=True
                    )
                    new_doc.close()

                    sheets.append(sheet_info)
                    logger.info(f"[SplitDrawings] Extracted: {sheet_info.sheet_number} - {sheet_info.sheet_title}")

        except Exception as e:
            logger.error(f"[SplitDrawings] Error processing {pdf_path.name}: {e}")
            import traceback
            traceback.print_exc()

        return sheets

    async def _parse_toc_with_llm(self, pdf_path: Path) -> List:
        """Use LLM-assisted TOC parser to extract sheet list"""
        try:
            from modules.files.toc_parser import DrawingTOCParser

            if not self.ai:
                logger.debug("[SplitDrawings] No AI provider, skipping LLM TOC parsing")
                return []

            parser = DrawingTOCParser(self.ai)
            sheets = await parser.extract_toc(pdf_path)

            if sheets:
                logger.info(f"[SplitDrawings] LLM TOC parser extracted {len(sheets)} sheets")

            return sheets

        except ImportError:
            logger.warning("[SplitDrawings] toc_parser module not found")
            return []
        except Exception as e:
            logger.warning(f"[SplitDrawings] LLM TOC parsing failed: {e}")
            return []

    def _extract_bookmarks(self, doc: fitz.Document) -> Dict[int, Tuple[str, str]]:
        """
        Extract sheet numbers and titles from PDF bookmarks (TOC).

        Returns dict mapping page_number -> (sheet_number, title)
        """
        bookmarks = {}

        try:
            toc = doc.get_toc()  # Returns list of [level, title, page_num]

            for level, title, page_num in toc:
                # Convert to 0-indexed
                page_idx = page_num - 1

                # Try to parse sheet number from bookmark title
                sheet_num, sheet_title = self._parse_bookmark_title(title)
                if sheet_num:
                    bookmarks[page_idx] = (sheet_num, sheet_title)

        except Exception as e:
            logger.debug(f"[SplitDrawings] No bookmarks or error reading TOC: {e}")

        return bookmarks

    def _parse_bookmark_title(self, title: str) -> Tuple[Optional[str], str]:
        """
        Parse a bookmark title to extract sheet number and title.

        Examples:
        - "A101 - First Floor Plan" -> ("A101", "First Floor Plan")
        - "S-100 Structural Notes" -> ("S-100", "Structural Notes")
        - "General Notes" -> (None, "General Notes")
        """
        for pattern in self.SHEET_PATTERNS:
            match = pattern.match(title)
            if match:
                groups = match.groups()
                discipline = groups[0].upper()
                number = groups[1]
                decimal = groups[2] if len(groups) > 2 and groups[2] else None

                # Reconstruct sheet number
                if decimal:
                    sheet_num = f"{discipline}{number}.{decimal}"
                else:
                    sheet_num = f"{discipline}{number}"

                # Extract title (everything after sheet number)
                title_start = match.end()
                sheet_title = title[title_start:].strip()
                # Remove leading separators
                sheet_title = re.sub(r'^[\s\-–—:]+', '', sheet_title)

                return sheet_num, sheet_title if sheet_title else "Untitled"

        return None, title

    def _extract_sheet_info(
        self,
        page: fitz.Page,
        page_num: int,
        bookmark_info: Optional[Tuple[str, str]] = None
    ) -> Optional[SheetInfo]:
        """
        Extract sheet number and title from a page.

        Priority:
        1. Bookmark info (if available)
        2. Text extraction patterns
        3. Fallback to page number
        """
        # If we have bookmark info, use it
        if bookmark_info:
            sheet_number, sheet_title = bookmark_info
            discipline = self._get_discipline(sheet_number)
            discipline_name = self.DISCIPLINES.get(discipline, ('Uncategorized', 'Uncategorized'))[1]

            return SheetInfo(
                page_number=page_num,
                sheet_number=sheet_number,
                sheet_title=sheet_title,
                discipline=discipline,
                discipline_name=discipline_name
            )

        # Try text extraction
        text = page.get_text()

        # Find sheet number
        sheet_number = self._find_sheet_number(text)
        if not sheet_number:
            return None

        # Find sheet title
        sheet_title = self._find_sheet_title(text, sheet_number)

        # Determine discipline
        discipline = self._get_discipline(sheet_number)
        discipline_name = self.DISCIPLINES.get(discipline, ('Uncategorized', 'Uncategorized'))[1]

        return SheetInfo(
            page_number=page_num,
            sheet_number=sheet_number,
            sheet_title=sheet_title,
            discipline=discipline,
            discipline_name=discipline_name
        )

    def _find_sheet_number(self, text: str) -> Optional[str]:
        """Find sheet number in page text"""
        # Try each pattern
        for pattern in self.SHEET_PATTERNS:
            matches = pattern.finditer(text)
            for match in matches:
                groups = match.groups()
                discipline = groups[0].upper()
                number = groups[1]
                decimal = groups[2] if len(groups) > 2 and groups[2] else None

                # Reconstruct sheet number
                if decimal:
                    return f"{discipline}{number}.{decimal}"
                else:
                    return f"{discipline}{number}"

        return None

    def _find_sheet_title(self, text: str, sheet_number: str) -> str:
        """Find sheet title in page text, skipping common metadata patterns"""
        # Try title patterns - use finditer to get ALL matches, skip excluded ones
        for pattern in self.TITLE_PATTERNS:
            for match in pattern.finditer(text):
                title = match.group(1).strip()
                # Clean up
                title = re.sub(r'\s+', ' ', title)
                title = title[:80]  # Limit length
                # Skip if this looks like metadata, not a real title
                if len(title) > 3 and not self._is_excluded_title(title):
                    return title

        # Try finding text near sheet number
        sheet_pattern = re.escape(sheet_number)
        context_pattern = re.compile(
            rf'{sheet_pattern}\s*[-–—:]\s*([^\n]{{5,80}})',
            re.IGNORECASE
        )
        for match in context_pattern.finditer(text):
            title = match.group(1).strip()
            title = re.sub(r'\s+', ' ', title)
            title = title[:80]
            # Skip if excluded
            if not self._is_excluded_title(title):
                return title

        # Default
        return "Untitled Sheet"

    def _is_excluded_title(self, title: str) -> bool:
        """Check if a title matches excluded metadata patterns"""
        title_upper = title.upper().strip()
        for excluded in self.EXCLUDED_TITLE_PATTERNS:
            # Check if title starts with or equals excluded pattern
            if title_upper.startswith(excluded) or title_upper == excluded:
                return True
        return False

    def _get_discipline(self, sheet_number: str) -> str:
        """Extract discipline code from sheet number"""
        # Handle multi-character disciplines (GI, GN)
        for disc_code in ['GI', 'GN']:
            if sheet_number.upper().startswith(disc_code):
                return disc_code

        # Single character
        if sheet_number:
            return sheet_number[0].upper()

        return 'U'  # Unknown

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize string for use in filename"""
        # Remove invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace multiple spaces with single space
        filename = re.sub(r'\s+', ' ', filename)
        # Trim
        filename = filename.strip()
        # Limit length
        return filename[:100]

    def _summarize_by_discipline(self, sheets: List[SheetInfo]) -> Dict[str, Dict]:
        """Summarize sheet counts by discipline"""
        summary = {}

        for sheet in sheets:
            disc = sheet.discipline_name
            if disc not in summary:
                summary[disc] = {
                    'count': 0,
                    'sheets': []
                }

            summary[disc]['count'] += 1
            summary[disc]['sheets'].append(sheet.sheet_number)

        return summary
