"""
TOC Parser - LLM-assisted Table of Contents parsing for PDFs

Parses spec books and drawing sets using:
1. Text search to find structure (divisions, pages)
2. LLM to extract section/sheet lists from TOC pages

Uses gpt-oss-120b:free via OpenRouter for zero-cost parsing.
"""

import re
import json
import fitz  # PyMuPDF
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SpecSection:
    """A section within a spec division"""
    section_id: str  # e.g., "08220"
    title: str  # e.g., "Fiber Reinforced Plastic (FRP) Doors"
    start_page: Optional[int] = None
    end_page: Optional[int] = None


@dataclass
class DrawingSheet:
    """A sheet in a drawing set"""
    page_num: int  # 1-indexed page number in PDF
    sheet_id: str  # e.g., "A-1"
    title: str  # e.g., "Life Safety Plan and Code Summary"
    discipline: str  # e.g., "Architectural"


class SpecTOCParser:
    """
    Parse spec book TOC using text search + LLM.

    Strategy:
    1. Search for "DIVISION X" headers to find division start pages
    2. Division end = next division start - 1
    3. LLM parses "Contents of Division" on division start page
    4. Search for "SECTION XXXXX" within division to find section boundaries
    """

    def __init__(self, ai_provider=None):
        """
        Args:
            ai_provider: AIProviderManager instance with classify_free() method
        """
        self.ai = ai_provider

    def find_division_ranges(self, pdf_path: Path) -> Dict[str, Tuple[int, int]]:
        """
        Find start/end pages for each division via text search.

        Returns:
            Dict mapping division code to (start_page, end_page) tuple (1-indexed)
            e.g., {'08': (398, 422), '09': (423, 432)}
        """
        pdf_path = Path(pdf_path)
        divisions = {}

        with fitz.open(str(pdf_path)) as doc:
            # First pass: find all division start pages
            for page_num in range(doc.page_count):
                page = doc[page_num]
                text = page.get_text()

                # Method 1: Look for standalone "DIVISION X" headers
                # Pattern: "DIVISION" followed by 1-2 digit number on its own line
                match = re.search(r'^\s*DIVISION\s+(\d{1,2})\s*$', text, re.MULTILINE | re.IGNORECASE)
                if match:
                    div_num = match.group(1).zfill(2)  # Pad to 2 digits
                    if div_num not in divisions:
                        divisions[div_num] = (page_num + 1, None)  # 1-indexed
                        logger.debug(f"Found Division {div_num} header at page {page_num + 1}")

                # Method 2: Look for "SECTION XX YY ZZ" format (e.g., "SECTION 08 11 13")
                # This finds first occurrence of each division by section number
                section_match = re.search(
                    r'SECTION\s+(\d{2})\s*\d{2}\s*\d{2}',
                    text,
                    re.IGNORECASE
                )
                if section_match:
                    div_num = section_match.group(1)
                    if div_num not in divisions:
                        divisions[div_num] = (page_num + 1, None)
                        logger.debug(f"Found Division {div_num} via section number at page {page_num + 1}")

            # If no divisions found with spaces, try compact format "SECTION XXXXXX"
            if not divisions:
                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    text = page.get_text()

                    # Pattern: SECTION followed by 6-digit number (e.g., "SECTION 081113")
                    section_match = re.search(r'SECTION\s+(\d{2})\d{4}', text, re.IGNORECASE)
                    if section_match:
                        div_num = section_match.group(1)
                        if div_num not in divisions:
                            divisions[div_num] = (page_num + 1, None)
                            logger.debug(f"Found Division {div_num} via compact section at page {page_num + 1}")

            # Second pass: calculate end pages
            sorted_divs = sorted(divisions.items(), key=lambda x: x[1][0])
            for i, (div, (start, _)) in enumerate(sorted_divs):
                if i + 1 < len(sorted_divs):
                    # End at page before next division starts
                    end = sorted_divs[i + 1][1][0] - 1
                else:
                    # Last division goes to end of document
                    end = doc.page_count
                divisions[div] = (start, end)

        logger.info(f"Found {len(divisions)} divisions in spec book")
        return divisions

    async def extract_sections_from_division(
        self,
        pdf_path: Path,
        division: str,
        start_page: int,
        end_page: int
    ) -> List[SpecSection]:
        """
        Extract CSI sections from a division using LLM to parse TOC.

        Args:
            pdf_path: Path to spec book PDF
            division: Division code (e.g., "08")
            start_page: Division start page (1-indexed)
            end_page: Division end page (1-indexed)

        Returns:
            List of SpecSection objects with section boundaries
        """
        pdf_path = Path(pdf_path)
        sections = []

        with fitz.open(str(pdf_path)) as doc:
            # Get text from division start page (contains "Contents of Division")
            div_start_text = doc[start_page - 1].get_text()

            # Try LLM parsing first
            if self.ai:
                llm_sections = await self._llm_parse_division_contents(div_start_text, division)
                if llm_sections:
                    sections = llm_sections

            # Fallback: regex parsing
            if not sections:
                sections = self._regex_parse_division_contents(div_start_text, division)

            # Find section boundaries by searching for "SECTION XXXXX" within division
            if sections:
                sections = self._find_section_boundaries(doc, sections, start_page, end_page)

        logger.info(f"Division {division}: found {len(sections)} sections")
        return sections

    async def _llm_parse_division_contents(self, text: str, division: str) -> List[SpecSection]:
        """Use LLM to parse Contents of Division list"""
        if not self.ai:
            return []

        prompt = f"""Extract the CSI section numbers and titles from this spec book division page.
Look for a "Contents of Division" or similar list that shows section numbers (like {division}XXXX) and their titles.

Return ONLY a JSON array with this exact format:
[{{"section": "{division}220", "title": "Example Section Title"}}, ...]

Text from Division {division} start page:
{text[:3000]}"""

        try:
            response = await self.ai.classify_free(prompt)
            if not response or not response.success:
                logger.warning(f"LLM call failed: {response.error if response else 'No response'}")
                return []

            # Extract text from AIResponse
            result = response.raw_response or response.data.get('content', '')
            if not result:
                return []

            # Parse JSON from response
            result = result.strip()
            # Handle markdown code blocks
            if '```' in result:
                result = re.sub(r'```\w*\n?', '', result)
                result = result.strip()

            # Find JSON array in response
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return [
                    SpecSection(section_id=item['section'], title=item['title'])
                    for item in data
                    if 'section' in item and 'title' in item
                ]
        except Exception as e:
            logger.warning(f"LLM parsing failed: {e}")

        return []

    def _regex_parse_division_contents(self, text: str, division: str) -> List[SpecSection]:
        """Fallback regex parsing for Contents of Division"""
        sections = []

        # Look for patterns like "08220 FRP Doors" or "08220  Fiber Reinforced Plastic"
        pattern = rf'({division}\d{{3,4}})\s+(.+?)(?:\n|$)'
        matches = re.findall(pattern, text, re.IGNORECASE)

        for section_id, title in matches:
            # Clean up title
            title = title.strip()
            title = re.sub(r'\s+', ' ', title)
            title = title[:100]  # Limit length

            if len(title) > 3:
                sections.append(SpecSection(section_id=section_id, title=title))

        return sections

    def _find_section_boundaries(
        self,
        doc: fitz.Document,
        sections: List[SpecSection],
        start_page: int,
        end_page: int
    ) -> List[SpecSection]:
        """Find page boundaries for each section by searching for SECTION headers"""

        section_ids = {s.section_id for s in sections}
        section_starts = {}

        # Search within division pages for SECTION headers
        for page_num in range(start_page - 1, end_page):
            text = doc[page_num].get_text()

            # Look for "SECTION XXXXX" patterns - handle both spaced and compact formats
            # Pattern 1: Spaced format like "SECTION 08 31 13" or "SECTION 08 3113"
            for match in re.finditer(r'SECTION\s+(\d{2})\s*(\d{2})\s*(\d{2})', text, re.IGNORECASE):
                section_id = match.group(1) + match.group(2) + match.group(3)
                self._match_section_to_list(section_id, sections, section_starts, page_num)

            # Pattern 2: Compact format like "SECTION 083113" (5-6 continuous digits)
            for match in re.finditer(r'SECTION\s+(\d{5,6})', text, re.IGNORECASE):
                section_id = match.group(1)
                # Normalize to 6 digits
                if len(section_id) == 5:
                    section_id = '0' + section_id  # Pad with leading zero
                self._match_section_to_list(section_id, sections, section_starts, page_num)

        # Assign boundaries
        sorted_sections = sorted(sections, key=lambda s: section_starts.get(s.section_id, 0))

        for i, section in enumerate(sorted_sections):
            section.start_page = section_starts.get(section.section_id)

            if section.start_page:
                # End at next section start - 1, or division end
                if i + 1 < len(sorted_sections) and sorted_sections[i + 1].start_page:
                    section.end_page = sorted_sections[i + 1].start_page - 1
                else:
                    section.end_page = end_page

        return sorted_sections

    def _match_section_to_list(
        self,
        section_id: str,
        sections: List[SpecSection],
        section_starts: Dict[str, int],
        page_num: int
    ):
        """
        Try to match a found section ID to our list of known sections.

        Handles format differences like 08220 vs 082200.
        """
        # Check if this matches one of our sections (ignoring format differences)
        for s in sections:
            # Match 08220 to 082200 etc.
            if s.section_id in section_id or section_id.startswith(s.section_id):
                if s.section_id not in section_starts:
                    section_starts[s.section_id] = page_num + 1  # 1-indexed
                    logger.debug(f"Found section {s.section_id} at page {page_num + 1}")


class DrawingTOCParser:
    """
    Parse drawing set TOC using LLM.

    Strategy:
    1. Extract text from page 2 (usually contains TOC)
    2. LLM parses table to extract: page_num, sheet_id, title
    3. Fall back to regex if LLM fails
    """

    # Discipline mapping
    DISCIPLINES = {
        'A': 'Architectural',
        'S': 'Structural',
        'M': 'Mechanical',
        'E': 'Electrical',
        'P': 'Plumbing',
        'C': 'Civil',
        'L': 'Landscape',
        'G': 'General',
        'F': 'Fire Protection',
        'T': 'Telecommunications',
        'I': 'Interiors',
        'H': 'HVAC',
    }

    def __init__(self, ai_provider=None):
        self.ai = ai_provider

    async def extract_toc(self, pdf_path: Path, toc_page: int = 2) -> List[DrawingSheet]:
        """
        Extract Table of Contents from drawing set.

        Args:
            pdf_path: Path to drawing set PDF
            toc_page: Page number containing TOC (1-indexed, default=2)

        Returns:
            List of DrawingSheet objects
        """
        pdf_path = Path(pdf_path)
        sheets = []

        with fitz.open(str(pdf_path)) as doc:
            if toc_page > doc.page_count:
                logger.warning(f"TOC page {toc_page} exceeds document pages ({doc.page_count})")
                return sheets

            # Get TOC page text
            toc_text = doc[toc_page - 1].get_text()

            # Try LLM parsing first
            if self.ai:
                sheets = await self._llm_parse_toc(toc_text, doc.page_count)

            # Fallback to regex
            if not sheets:
                sheets = self._regex_parse_toc(toc_text, doc.page_count)

            # Add discipline classification
            for sheet in sheets:
                sheet.discipline = self._get_discipline(sheet.sheet_id)

        logger.info(f"Extracted {len(sheets)} sheets from drawing set TOC")
        return sheets

    async def _llm_parse_toc(self, toc_text: str, total_pages: int) -> List[DrawingSheet]:
        """Use LLM to parse drawing TOC table"""
        if not self.ai:
            return []

        prompt = f"""This is the Table of Contents from a construction drawing set with {total_pages} pages.
The TOC has columns: Page Number | Sheet ID | Sheet Title

Extract ALL sheet entries. The text is messy with notes mixed in - IGNORE the notes and focus on the TOC rows.

Sheet IDs are letters followed by numbers like: COV, G-1, C-1, A-1, S-1, P-1, E-1, M-1, H-1
Look for patterns like "9 A-1 LIFE SAFETY PLAN" where 9 is page, A-1 is sheet ID, rest is title.

Return a JSON array with ALL {total_pages} sheets:
[{{"page": 1, "sheet_id": "COV", "title": "Cover Sheet"}}, {{"page": 2, "sheet_id": "G-1", "title": "Table of Contents"}}, ...]

Text:
{toc_text[:5000]}"""

        try:
            response = await self.ai.classify_free(prompt)
            if not response or not response.success:
                logger.warning(f"LLM call failed: {response.error if response else 'No response'}")
                return []

            # Extract text from AIResponse
            result = response.raw_response or response.data.get('content', '')
            if not result:
                return []

            # Parse JSON from response
            result = result.strip()
            if '```' in result:
                result = re.sub(r'```\w*\n?', '', result)
                result = result.strip()

            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                sheets = []
                for item in data:
                    if 'page' in item and 'sheet_id' in item:
                        sheets.append(DrawingSheet(
                            page_num=int(item['page']),
                            sheet_id=str(item['sheet_id']),
                            title=item.get('title', 'Untitled'),
                            discipline=''  # Set later
                        ))
                return sheets
        except Exception as e:
            logger.warning(f"LLM TOC parsing failed: {e}")

        return []

    def _regex_parse_toc(self, toc_text: str, total_pages: int) -> List[DrawingSheet]:
        """Fallback regex parsing for drawing TOC"""
        sheets = []

        # Pattern: page_number sheet_id title
        # Sheet IDs can use regular dash - or em-dash —
        # Examples: "9 A-1 LIFE SAFETY PLAN" or "2 G—1 TABLE OF CONTENTS"

        # More robust patterns
        patterns = [
            # page, sheet_id (letter + dash/emdash + number), title
            r'(\d{1,2})\s+([A-Z][—\-]?\d+)\s+([A-Z][A-Z\s&,\-]+)',
            # Handle COV specially
            r'(\d{1,2})\s+(cov|COV)\s+(.+?)(?:\n|$)',
            # Generic fallback
            r'(\d{1,2})\s+([A-Z][—\-]?\d+)\s+(.+?)(?:\n|$)',
        ]

        seen_pages = set()  # Avoid duplicates

        for pattern in patterns:
            matches = re.findall(pattern, toc_text, re.IGNORECASE)
            for page, sheet_id, title in matches:
                page_num = int(page)
                if 1 <= page_num <= total_pages and page_num not in seen_pages:
                    # Normalize sheet_id - replace em-dash with regular dash
                    sheet_id = sheet_id.replace('—', '-').upper()

                    # Clean title
                    title = title.strip()
                    title = re.sub(r'\s+', ' ', title)
                    title = title[:100]

                    # Skip if title looks like noise
                    if len(title) < 3 or title.startswith('THE ') or title.startswith('ALL '):
                        continue

                    sheets.append(DrawingSheet(
                        page_num=page_num,
                        sheet_id=sheet_id,
                        title=title,
                        discipline=''
                    ))
                    seen_pages.add(page_num)

        # Sort by page number
        sheets.sort(key=lambda s: s.page_num)
        return sheets

    def _get_discipline(self, sheet_id: str) -> str:
        """Get discipline name from sheet ID prefix"""
        if not sheet_id:
            return 'Uncategorized'

        # Handle multi-character prefixes first
        prefix = sheet_id.upper()
        if prefix.startswith('GI') or prefix.startswith('GN'):
            return 'General'

        # Single character prefix
        first_char = prefix[0]
        return self.DISCIPLINES.get(first_char, 'Uncategorized')


# Convenience functions (async)
async def parse_drawing_toc(pdf_path: str, ai_provider=None) -> List[Dict]:
    """
    Parse drawing set TOC and return as list of dicts.

    Args:
        pdf_path: Path to drawing set PDF
        ai_provider: Optional AIProviderManager

    Returns:
        List of dicts with keys: page_num, sheet_id, title, discipline
    """
    parser = DrawingTOCParser(ai_provider)
    sheets = await parser.extract_toc(Path(pdf_path))

    return [
        {
            'page_num': s.page_num,
            'sheet_id': s.sheet_id,
            'title': s.title,
            'discipline': s.discipline
        }
        for s in sheets
    ]


async def parse_spec_divisions(pdf_path: str, ai_provider=None, divisions: List[str] = None) -> Dict:
    """
    Parse spec book and extract sections for specified divisions.

    Args:
        pdf_path: Path to spec book PDF
        ai_provider: Optional AIProviderManager
        divisions: List of division codes to extract (default: ['00', '01', '08'])

    Returns:
        Dict mapping division code to list of section dicts
    """
    divisions = divisions or ['00', '01', '08']
    parser = SpecTOCParser(ai_provider)

    # Find all division ranges
    div_ranges = parser.find_division_ranges(Path(pdf_path))

    result = {}
    for div in divisions:
        if div in div_ranges:
            start, end = div_ranges[div]
            sections = await parser.extract_sections_from_division(
                Path(pdf_path), div, start, end
            )
            result[div] = [
                {
                    'section_id': s.section_id,
                    'title': s.title,
                    'start_page': s.start_page,
                    'end_page': s.end_page
                }
                for s in sections
            ]

    return result
