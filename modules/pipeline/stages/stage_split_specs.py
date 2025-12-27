"""
Stage 3: Spec Book Splitting

Splits the project specification book into individual CSI section PDFs.
Uses pdfplumber for text extraction and PyMuPDF for splitting.

Extracts Divisions 0, 1, and 8:
- Division 00: Procurement and Contracting Requirements
- Division 01: General Requirements
- Division 08: Openings (doors, windows, hardware, glazing)

Output format: 081100 - Hollow Metal Doors and Frames.pdf
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import fitz  # PyMuPDF
import logging

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logging.warning("pdfplumber not installed - using PyMuPDF for text extraction")

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a pipeline stage"""
    success: bool
    data: Dict
    error: Optional[str] = None


# Divisions to extract (0=procurement, 1=general, 8=openings)
DIVISIONS_TO_EXTRACT = ['00', '01', '08']

# Division folder names
DIVISION_FOLDERS = {
    '00': 'Division-00-Procurement',
    '01': 'Division-01-General',
    '08': 'Division-08-Openings',
}

# CSI Section titles for Divisions 0, 1, and 8
CSI_SECTION_TITLES = {
    # Division 00 - Procurement and Contracting Requirements
    '001100': 'Summary of Work',
    '001113': 'Work Covered by Contract Documents',
    '001116': 'Work Under Other Contracts',
    '002100': 'Instructions to Bidders',
    '002113': 'Instructions to Bidders',
    '002200': 'Supplementary Instructions to Bidders',
    '003100': 'Available Project Information',
    '004100': 'Bid Forms',
    '004313': 'Bid Security Forms',
    '005200': 'Agreement Forms',
    '006100': 'Performance Bond Forms',
    '006200': 'Payment Bond Forms',
    '007100': 'General Conditions',
    '007200': 'Supplementary Conditions',
    '007300': 'Special Conditions',

    # Division 01 - General Requirements
    '010000': 'General Requirements',
    '011000': 'Summary',
    '011100': 'Summary of Work',
    '012000': 'Price and Payment Procedures',
    '012100': 'Allowances',
    '012200': 'Unit Prices',
    '012300': 'Alternates',
    '012500': 'Substitution Procedures',
    '012600': 'Contract Modification Procedures',
    '013000': 'Administrative Requirements',
    '013100': 'Project Management and Coordination',
    '013200': 'Construction Progress Documentation',
    '013300': 'Submittal Procedures',
    '014000': 'Quality Requirements',
    '014100': 'Regulatory Requirements',
    '014200': 'References',
    '014300': 'Quality Assurance',
    '015000': 'Temporary Facilities and Controls',
    '015100': 'Temporary Utilities',
    '015200': 'Construction Facilities',
    '015600': 'Temporary Barriers and Enclosures',
    '016000': 'Product Requirements',
    '017000': 'Execution and Closeout Requirements',
    '017300': 'Execution',
    '017700': 'Closeout Procedures',
    '017800': 'Closeout Submittals',
    '017823': 'Operation and Maintenance Data',
    '017839': 'Project Record Documents',
    '017900': 'Demonstration and Training',

    # Division 08 - Openings
    '081100': 'Metal Doors and Frames',
    '081113': 'Hollow Metal Doors and Frames',
    '081116': 'Aluminum Doors and Frames',
    '081119': 'Stainless Steel Doors and Frames',
    '081213': 'Hollow Metal Frames',
    '081416': 'Flush Wood Doors',
    '081433': 'Stile and Rail Wood Doors',
    '082113': 'Flush Wood Doors',
    '083100': 'Access Doors and Panels',
    '083113': 'Access Doors and Frames',
    '083213': 'Sliding Glass Doors',
    '083323': 'Overhead Coiling Doors',
    '083613': 'Sectional Doors',
    '084113': 'Aluminum-Framed Entrances and Storefronts',
    '084126': 'All-Glass Entrances and Storefronts',
    '084213': 'Aluminum-Framed Entrances',
    '084229': 'Automatic Entrances',
    '084233': 'Revolving Door Entrances',
    '084313': 'Aluminum-Framed Storefronts',
    '084413': 'Glazed Aluminum Curtain Walls',
    '084500': 'Translucent Wall and Roof Assemblies',
    '085113': 'Aluminum Windows',
    '085116': 'Aluminum-Clad-Wood Windows',
    '085119': 'Plastic-Clad-Wood Windows',
    '085123': 'Steel Windows',
    '085153': 'Vinyl Windows',
    '085200': 'Wood Windows',
    '086100': 'Roof Windows and Skylights',
    '086113': 'Metal-Framed Skylights',
    '087100': 'Door Hardware',
    '087111': 'Door Hardware (Descriptive)',
    '087112': 'Door Hardware (Scheduled)',
    '087113': 'Door Hardware (Sets)',
    '088000': 'Glazing',
    '088100': 'Glass Glazing',
    '088105': 'Glass Glazing for Doors and Frames',
    '088110': 'Glass Glazing for Windows',
    '088113': 'Unit Skylights',
    '088800': 'Special Function Glazing',
    '088813': 'Ballistic-Resistant Glazing',
    '089100': 'Louvers',
    '089113': 'Stationary Louvers',
    '089119': 'Operable Louvers',
}


class SplitSpecsStage:
    """
    Stage 3: Spec Book Splitting

    Splits spec book by CSI section into individual PDFs.
    Uses LLM-assisted TOC parsing to find division boundaries and sections.
    Focus on Division 8 sections for glazing scope.
    """

    def __init__(self, project_folder: Path, ai_provider=None):
        self.project_folder = Path(project_folder)
        self.ai = ai_provider

    async def run(self) -> StageResult:
        """Execute the spec splitting stage using TOC parser"""
        try:
            # Import TOC parser
            from modules.files.toc_parser import SpecTOCParser

            # Find spec book PDF
            spec_pdf = self._find_spec_book()
            if not spec_pdf:
                logger.warning("[SplitSpecs] No spec book found")
                return StageResult(
                    success=True,  # Not a failure - just no specs
                    data={'message': 'No spec book found', 'sections_extracted': []},
                )

            logger.info(f"[SplitSpecs] Found spec book: {spec_pdf.name}")

            # Use TOC parser to find division ranges
            parser = SpecTOCParser(self.ai)
            div_ranges = parser.find_division_ranges(spec_pdf)

            if not div_ranges:
                logger.warning("[SplitSpecs] No divisions found in spec book")
                return StageResult(
                    success=True,
                    data={'message': 'No divisions found in spec book', 'sections_extracted': []},
                )

            logger.info(f"[SplitSpecs] Found {len(div_ranges)} divisions")

            # Create output directories for each division
            for div_code, folder_name in DIVISION_FOLDERS.items():
                output_dir = self.project_folder / 'Specs' / folder_name
                output_dir.mkdir(parents=True, exist_ok=True)

            # Process each division we care about
            extracted = []
            divisions_extracted = {div: 0 for div in DIVISIONS_TO_EXTRACT}

            with fitz.open(str(spec_pdf)) as doc:
                for division in DIVISIONS_TO_EXTRACT:
                    if division not in div_ranges:
                        continue

                    start_page, end_page = div_ranges[division]
                    logger.info(f"[SplitSpecs] Processing Division {division}: pages {start_page}-{end_page}")

                    # Use LLM to extract sections from this division
                    sections = await parser.extract_sections_from_division(
                        spec_pdf, division, start_page, end_page
                    )

                    if not sections:
                        logger.warning(f"[SplitSpecs] No sections found in Division {division}")
                        continue

                    logger.info(f"[SplitSpecs] Division {division}: found {len(sections)} sections")

                    # Extract each section to its own PDF
                    for section in sections:
                        if not section.start_page or not section.end_page:
                            logger.warning(f"[SplitSpecs] No page range for section {section.section_id}")
                            continue

                        # Sanitize title for filename
                        safe_title = re.sub(r'[<>:"/\\|?*]', '', section.title)
                        safe_title = safe_title[:80]  # Limit length

                        output_dir = self.project_folder / 'Specs' / DIVISION_FOLDERS[division]
                        output_path = output_dir / f"{section.section_id} - {safe_title}.pdf"

                        # Extract pages (convert from 1-indexed to 0-indexed)
                        new_doc = fitz.open()
                        for page_num in range(section.start_page - 1, section.end_page):
                            if 0 <= page_num < len(doc):
                                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

                        if len(new_doc) > 0:
                            new_doc.save(
                                str(output_path),
                                garbage=4,
                                deflate=True,
                                clean=True
                            )
                            extracted.append({
                                'section_id': section.section_id,
                                'division': division,
                                'title': section.title,
                                'pages': len(new_doc),
                                'output_file': output_path.name
                            })
                            divisions_extracted[division] += 1
                            logger.info(f"[SplitSpecs] Extracted: {section.section_id} - {section.title} ({len(new_doc)} pages)")

                        new_doc.close()

            # Log summary by division
            for div, count in divisions_extracted.items():
                if count > 0:
                    logger.info(f"[SplitSpecs] Division {div}: {count} sections extracted")

            return StageResult(
                success=True,
                data={
                    'sections_extracted': [s['section_id'] for s in extracted],
                    'total_sections': len(extracted),
                    'by_division': divisions_extracted,
                    'details': extracted
                }
            )

        except Exception as e:
            logger.error(f"[SplitSpecs] Error: {e}")
            import traceback
            traceback.print_exc()
            return StageResult(
                success=False,
                data={},
                error=str(e)
            )

    def _find_spec_book(self) -> Optional[Path]:
        """Find the main spec book PDF"""
        specs_folder = self.project_folder / 'Specs'

        # Search locations in priority order
        search_locations = [
            specs_folder,
            self.project_folder,
            self.project_folder / 'Documents',
        ]

        spec_patterns = [
            r'spec',
            r'project\s*manual',
            r'technical\s*spec',
            r'division',
        ]

        for location in search_locations:
            if not location.exists():
                continue

            pdfs = list(location.glob("*.pdf"))

            # Look for spec-named files
            for pdf in pdfs:
                name_lower = pdf.stem.lower()
                for pattern in spec_patterns:
                    if re.search(pattern, name_lower, re.IGNORECASE):
                        return pdf

            # Fall back to largest PDF (specs are usually big)
            if pdfs:
                largest = max(pdfs, key=lambda p: p.stat().st_size)
                if largest.stat().st_size > 1_000_000:  # > 1MB
                    return largest

        return None

    def _parse_spec_sections(self, spec_pdf: Path) -> List[Tuple[str, List[int], str]]:
        """
        Parse spec book to identify CSI sections and their page ranges.

        Returns list of (section_id, page_numbers, title) tuples.
        """
        sections = []
        current_section = None
        current_pages = []
        current_title = ""

        if HAS_PDFPLUMBER:
            sections = self._parse_with_pdfplumber(spec_pdf)
        else:
            sections = self._parse_with_pymupdf(spec_pdf)

        return sections

    def _parse_with_pdfplumber(self, spec_pdf: Path) -> List[Tuple[str, List[int], str]]:
        """Parse using pdfplumber for cleaner text extraction"""
        sections = []
        current_section = None
        current_pages = []
        current_title = ""

        with pdfplumber.open(str(spec_pdf)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""

                # Look for CSI section headers
                matches = list(self.CSI_PATTERN.finditer(text))

                for match in matches:
                    div, sub1, sub2 = match.groups()
                    section_id = f"{div}{sub1}{sub2}"

                    # Only care about Division 8
                    if not div.startswith('08'):
                        continue

                    if section_id != current_section:
                        # Save previous section
                        if current_section and current_pages:
                            sections.append((current_section, current_pages, current_title))

                        # Start new section
                        current_section = section_id
                        current_pages = [page_num]

                        # Try to extract title
                        current_title = self._get_section_title(section_id, text)

                    elif page_num not in current_pages:
                        current_pages.append(page_num)

                # If on same section, add page
                if current_section and not matches and page_num not in current_pages:
                    # Check if this looks like a continuation
                    if self._is_spec_content(text):
                        current_pages.append(page_num)

            # Don't forget last section
            if current_section and current_pages:
                sections.append((current_section, current_pages, current_title))

        return sections

    def _parse_with_pymupdf(self, spec_pdf: Path) -> List[Tuple[str, List[int], str]]:
        """Fallback parsing using PyMuPDF"""
        sections = []
        current_section = None
        current_pages = []
        current_title = ""

        with fitz.open(str(spec_pdf)) as doc:
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()

                matches = list(self.CSI_PATTERN.finditer(text))

                for match in matches:
                    div, sub1, sub2 = match.groups()
                    section_id = f"{div}{sub1}{sub2}"

                    if not div.startswith('08'):
                        continue

                    if section_id != current_section:
                        if current_section and current_pages:
                            sections.append((current_section, current_pages, current_title))

                        current_section = section_id
                        current_pages = [page_num]
                        current_title = self._get_section_title(section_id, text)

                    elif page_num not in current_pages:
                        current_pages.append(page_num)

                if current_section and not matches and page_num not in current_pages:
                    if self._is_spec_content(text):
                        current_pages.append(page_num)

            if current_section and current_pages:
                sections.append((current_section, current_pages, current_title))

        return sections

    def _get_section_title(self, section_id: str, text: str = "") -> str:
        """Get the title for a CSI section"""
        # First try our lookup table
        if section_id in CSI_SECTION_TITLES:
            return CSI_SECTION_TITLES[section_id]

        # Try to extract from text
        title_match = self.TITLE_PATTERN.search(text)
        if title_match:
            title = title_match.group(1).strip()
            # Clean up
            title = re.sub(r'\s+', ' ', title)
            title = title[:100]  # Limit length
            if len(title) > 5:
                return title

        # Default
        return f"Section {section_id}"

    def _is_spec_content(self, text: str) -> bool:
        """Check if page text looks like spec content (not drawings/schedules)"""
        # Spec pages typically have numbered paragraphs
        spec_indicators = [
            r'^\d+\.\d+',  # 1.1, 2.3, etc.
            r'PART\s+\d',  # PART 1, PART 2, etc.
            r'SECTION',
            r'SUBMITTALS',
            r'PRODUCTS',
            r'EXECUTION',
            r'GENERAL',
        ]

        for pattern in spec_indicators:
            if re.search(pattern, text, re.MULTILINE | re.IGNORECASE):
                return True

        return False
