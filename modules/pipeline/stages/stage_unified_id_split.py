"""
Stage 1: Unified ID & Split

Unified stage that:
1. Identifies document types (spec book vs drawing set)
2. Splits spec book into individual CSI section PDFs
3. Splits drawing set into individual sheet PDFs

Combines functionality from stage_split_specs and stage_split_drawings
into a single unified stage for the new 4-stage pipeline.

Output structure:
- Specs/Division-00-Procurement/
- Specs/Division-01-General/
- Specs/Division-08-Openings/
- Drawings/Architectural/
- Drawings/Structural/
- etc.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
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
class DocumentIdentification:
    """Identification result for project documents"""
    has_spec_book: bool = False
    has_drawing_set: bool = False
    spec_book_path: Optional[Path] = None
    drawing_set_paths: List[Path] = field(default_factory=list)
    other_pdfs: List[Path] = field(default_factory=list)


# Divisions to extract from spec book
DIVISIONS_TO_EXTRACT = ['00', '01', '08']

# Division folder names
DIVISION_FOLDERS = {
    '00': 'Division-00-Procurement',
    '01': 'Division-01-General',
    '08': 'Division-08-Openings',
}

# CSI Section titles (Division 8 focus)
CSI_SECTION_TITLES = {
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

# Discipline classifications for drawings
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


class UnifiedIDSplitStage:
    """
    Stage 1: Unified ID & Split

    Identifies document types and splits them:
    - Spec book -> individual CSI section PDFs
    - Drawing set -> individual sheet PDFs

    This is the first stage of the unified 4-stage pipeline.
    """

    # Sheet number patterns for drawings
    SHEET_PATTERNS = [
        re.compile(r'\b([ASMEPCLGFTI])-?(\d{1,3})(?:\.(\d+))?\b', re.IGNORECASE),
        re.compile(r'\b([ASMEPCLGFTI])\s*-\s*(\d{1,3})(?:\.(\d+))?\b', re.IGNORECASE),
        re.compile(r'\b([ASMEPCLGFTI])(\d{1,2})\.(\d+)\b', re.IGNORECASE),
        re.compile(r'\b(G|GI|GN)-?(\d{1,3})\b', re.IGNORECASE),
    ]

    # Keywords to exclude from drawing sets (cutsheets, reports, etc.)
    CUTSHEET_KEYWORDS = [
        'cutsheet', 'cut sheet', 'spec sheet', 'data sheet', 'datasheet',
        'product sheet', 'submittal', 'selection', 'brochure', 'catalog',
        'installation', 'instruction', 'manual', 'guide', 'report',
        'assessment', 'geotechnical', 'environmental', 'survey',
    ]

    def __init__(self, project_folder: Path, ai_provider=None):
        self.project_folder = Path(project_folder)
        self.ai = ai_provider

    async def run(self) -> StageResult:
        """Execute the unified ID & Split stage"""
        try:
            logger.info(f"[UnifiedIDSplit] Starting for: {self.project_folder.name}")

            # Step 1: Identify documents
            identification = self._identify_documents()
            logger.info(
                f"[UnifiedIDSplit] Found: spec_book={identification.has_spec_book}, "
                f"drawing_sets={len(identification.drawing_set_paths)}"
            )

            results = {
                'identification': {
                    'has_spec_book': identification.has_spec_book,
                    'has_drawing_set': identification.has_drawing_set,
                    'drawing_set_count': len(identification.drawing_set_paths),
                },
                'spec_splitting': {},
                'drawing_splitting': {},
            }

            # Step 2: Split spec book if found
            if identification.has_spec_book and identification.spec_book_path:
                spec_result = await self._split_spec_book(identification.spec_book_path)
                results['spec_splitting'] = spec_result

            # Step 3: Split drawing sets if found
            if identification.has_drawing_set and identification.drawing_set_paths:
                drawing_result = await self._split_drawing_sets(identification.drawing_set_paths)
                results['drawing_splitting'] = drawing_result

            # Calculate totals
            total_spec_sections = results['spec_splitting'].get('total_sections', 0)
            total_sheets = results['drawing_splitting'].get('total_sheets', 0)

            logger.info(
                f"[UnifiedIDSplit] Complete: {total_spec_sections} spec sections, "
                f"{total_sheets} drawing sheets"
            )

            return StageResult(
                success=True,
                data=results
            )

        except Exception as e:
            logger.error(f"[UnifiedIDSplit] Error: {e}")
            import traceback
            traceback.print_exc()
            return StageResult(
                success=False,
                data={},
                error=str(e)
            )

    def _identify_documents(self) -> DocumentIdentification:
        """Identify spec books and drawing sets in the project folder"""
        result = DocumentIdentification()

        # Search locations
        search_paths = [
            self.project_folder,
            self.project_folder / 'Specs',
            self.project_folder / 'Drawings',
            self.project_folder / 'Documents',
        ]

        all_pdfs = []
        for search_path in search_paths:
            if search_path.exists():
                all_pdfs.extend(search_path.glob("*.pdf"))

        # Remove duplicates
        all_pdfs = list(set(all_pdfs))

        # Classify each PDF
        for pdf_path in all_pdfs:
            file_type = self._classify_pdf_type(pdf_path)

            if file_type == 'spec_book':
                # Keep only the largest spec book
                if not result.spec_book_path:
                    result.spec_book_path = pdf_path
                    result.has_spec_book = True
                elif pdf_path.stat().st_size > result.spec_book_path.stat().st_size:
                    result.other_pdfs.append(result.spec_book_path)
                    result.spec_book_path = pdf_path
                else:
                    result.other_pdfs.append(pdf_path)

            elif file_type == 'drawing_set':
                result.drawing_set_paths.append(pdf_path)
                result.has_drawing_set = True

            else:
                result.other_pdfs.append(pdf_path)

        return result

    def _classify_pdf_type(self, pdf_path: Path) -> str:
        """
        Classify a PDF as spec_book, drawing_set, or other.

        Returns: 'spec_book', 'drawing_set', or 'other'
        """
        filename_lower = pdf_path.stem.lower()
        file_size = pdf_path.stat().st_size

        # Check for cutsheet keywords (always skip these for splitting)
        for keyword in self.CUTSHEET_KEYWORDS:
            if keyword in filename_lower:
                return 'other'

        # Spec book indicators
        spec_patterns = [
            r'spec', r'project\s*manual', r'technical\s*spec',
            r'division', r'section', r'volume',
        ]
        for pattern in spec_patterns:
            if re.search(pattern, filename_lower, re.IGNORECASE):
                return 'spec_book'

        # Drawing set indicators
        drawing_patterns = [
            r'drawing', r'plan', r'sheet', r'combined',
            r'architectural', r'structural', r'mechanical', r'electrical',
        ]
        for pattern in drawing_patterns:
            if re.search(pattern, filename_lower, re.IGNORECASE):
                return 'drawing_set'

        # Check content for large PDFs
        if file_size > 5_000_000:  # > 5MB
            content_type = self._classify_by_content(pdf_path)
            if content_type:
                return content_type

        # Default based on size
        # Spec books are typically larger than drawing sets
        if file_size > 20_000_000:  # > 20MB likely spec book
            return 'spec_book'
        elif file_size > 2_000_000:  # > 2MB could be drawings
            return 'drawing_set'

        return 'other'

    def _classify_by_content(self, pdf_path: Path) -> Optional[str]:
        """Classify by examining PDF content"""
        try:
            with fitz.open(str(pdf_path)) as doc:
                if len(doc) < 2:
                    return None

                # Sample first 3 pages
                sample_text = ""
                for i in range(min(3, len(doc))):
                    sample_text += doc[i].get_text()

                # Spec indicators
                spec_indicators = [
                    r'PART\s+\d', r'SECTION\s+\d', r'DIVISION\s+\d',
                    r'TABLE OF CONTENTS', r'SUBMITTALS', r'PRODUCTS',
                    r'\d{2}\s*\d{2}\s*\d{2}',  # CSI format
                ]
                spec_count = sum(1 for p in spec_indicators if re.search(p, sample_text, re.IGNORECASE))

                # Drawing indicators
                drawing_indicators = [
                    r'SHEET\s+(INDEX|LIST)', r'DRAWING\s+(INDEX|LIST)',
                    r'\b[ASMEP]-?\d{3}\b', r'SCALE[:=]',
                    r'NORTH\s*ARROW', r'TITLE\s*BLOCK',
                ]
                drawing_count = sum(1 for p in drawing_indicators if re.search(p, sample_text, re.IGNORECASE))

                if spec_count > drawing_count and spec_count >= 2:
                    return 'spec_book'
                elif drawing_count > spec_count and drawing_count >= 2:
                    return 'drawing_set'

        except Exception as e:
            logger.debug(f"[UnifiedIDSplit] Content classification failed for {pdf_path.name}: {e}")

        return None

    async def _split_spec_book(self, spec_book_path: Path) -> Dict:
        """Split spec book into CSI section PDFs"""
        logger.info(f"[UnifiedIDSplit] Splitting spec book: {spec_book_path.name}")

        try:
            # Import TOC parser for LLM-assisted parsing
            from modules.files.toc_parser import SpecTOCParser

            # Create output directories
            for div_code, folder_name in DIVISION_FOLDERS.items():
                output_dir = self.project_folder / 'Specs' / folder_name
                output_dir.mkdir(parents=True, exist_ok=True)

            # Use TOC parser to find division ranges
            parser = SpecTOCParser(self.ai)
            div_ranges = parser.find_division_ranges(spec_book_path)

            if not div_ranges:
                logger.warning("[UnifiedIDSplit] No divisions found in spec book")
                return {'message': 'No divisions found', 'total_sections': 0}

            # Process each division
            extracted = []
            divisions_extracted = {div: 0 for div in DIVISIONS_TO_EXTRACT}

            with fitz.open(str(spec_book_path)) as doc:
                for division in DIVISIONS_TO_EXTRACT:
                    if division not in div_ranges:
                        continue

                    start_page, end_page = div_ranges[division]
                    logger.info(f"[UnifiedIDSplit] Division {division}: pages {start_page}-{end_page}")

                    # Extract sections from this division
                    sections = await parser.extract_sections_from_division(
                        spec_book_path, division, start_page, end_page
                    )

                    if not sections:
                        continue

                    # Extract each section to its own PDF
                    for section in sections:
                        if not section.start_page or not section.end_page:
                            continue

                        # Sanitize title for filename
                        safe_title = re.sub(r'[<>:"/\\|?*]', '', section.title)[:80]

                        output_dir = self.project_folder / 'Specs' / DIVISION_FOLDERS[division]
                        output_path = output_dir / f"{section.section_id} - {safe_title}.pdf"

                        # Extract pages
                        new_doc = fitz.open()
                        for page_num in range(section.start_page - 1, section.end_page):
                            if 0 <= page_num < len(doc):
                                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

                        if len(new_doc) > 0:
                            new_doc.save(str(output_path), garbage=4, deflate=True, clean=True)
                            extracted.append({
                                'section_id': section.section_id,
                                'division': division,
                                'title': section.title,
                                'pages': len(new_doc),
                            })
                            divisions_extracted[division] += 1
                            logger.info(f"[UnifiedIDSplit] Extracted spec: {section.section_id} ({len(new_doc)} pages)")

                        new_doc.close()

            return {
                'total_sections': len(extracted),
                'by_division': divisions_extracted,
                'sections': extracted,
            }

        except ImportError:
            logger.warning("[UnifiedIDSplit] TOC parser not available, using fallback")
            return await self._split_spec_book_fallback(spec_book_path)
        except Exception as e:
            logger.error(f"[UnifiedIDSplit] Spec splitting error: {e}")
            return {'error': str(e), 'total_sections': 0}

    async def _split_spec_book_fallback(self, spec_book_path: Path) -> Dict:
        """Fallback spec splitting without TOC parser"""
        # Simple page-based extraction looking for Division 8 sections
        extracted = []

        with fitz.open(str(spec_book_path)) as doc:
            current_section = None
            current_pages = []
            csi_pattern = re.compile(r'(?:SECTION|^)\s*(08\s?\d{2}\s?\d{2})', re.MULTILINE | re.IGNORECASE)

            for page_num in range(len(doc)):
                text = doc[page_num].get_text()
                matches = csi_pattern.findall(text)

                for match in matches:
                    section_id = match.replace(' ', '')
                    if section_id != current_section:
                        # Save previous section
                        if current_section and current_pages:
                            self._save_section(doc, current_section, current_pages, extracted)

                        current_section = section_id
                        current_pages = [page_num]
                    else:
                        if page_num not in current_pages:
                            current_pages.append(page_num)

            # Save last section
            if current_section and current_pages:
                self._save_section(doc, current_section, current_pages, extracted)

        return {
            'total_sections': len(extracted),
            'by_division': {'08': len(extracted)},
            'sections': extracted,
        }

    def _save_section(self, doc, section_id: str, pages: List[int], extracted: List):
        """Save a spec section to PDF"""
        title = CSI_SECTION_TITLES.get(section_id, f"Section {section_id}")
        safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:80]

        output_dir = self.project_folder / 'Specs' / 'Division-08-Openings'
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{section_id} - {safe_title}.pdf"

        new_doc = fitz.open()
        for page_num in pages:
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

        if len(new_doc) > 0:
            new_doc.save(str(output_path), garbage=4, deflate=True, clean=True)
            extracted.append({
                'section_id': section_id,
                'division': '08',
                'title': title,
                'pages': len(new_doc),
            })

        new_doc.close()

    async def _split_drawing_sets(self, drawing_paths: List[Path]) -> Dict:
        """Split drawing sets into individual sheets"""
        logger.info(f"[UnifiedIDSplit] Splitting {len(drawing_paths)} drawing set(s)")

        # Create base drawings output directory
        output_base = self.project_folder / 'Drawings'
        output_base.mkdir(parents=True, exist_ok=True)

        all_sheets = []
        total_extracted = 0

        for drawing_path in drawing_paths:
            sheets = await self._split_single_drawing_set(drawing_path, output_base)
            all_sheets.extend(sheets)
            total_extracted += len(sheets)

        # Summarize by discipline
        discipline_summary = {}
        for sheet in all_sheets:
            disc = sheet.get('discipline', 'Uncategorized')
            if disc not in discipline_summary:
                discipline_summary[disc] = {'count': 0, 'sheets': []}
            discipline_summary[disc]['count'] += 1
            discipline_summary[disc]['sheets'].append(sheet.get('sheet_number'))

        return {
            'total_sheets': total_extracted,
            'drawing_sets_processed': len(drawing_paths),
            'disciplines': discipline_summary,
            'sheets': all_sheets,
        }

    async def _split_single_drawing_set(self, pdf_path: Path, output_base: Path) -> List[Dict]:
        """Split a single drawing set into individual sheets"""
        sheets = []

        try:
            # Try LLM-assisted TOC parsing
            toc_sheets = await self._parse_drawing_toc(pdf_path)

            with fitz.open(str(pdf_path)) as doc:
                total_pages = len(doc)

                # Build page mapping from TOC
                toc_map = {}
                if toc_sheets:
                    for ts in toc_sheets:
                        page_idx = ts.page_num - 1  # Convert to 0-indexed
                        if 0 <= page_idx < total_pages:
                            toc_map[page_idx] = ts
                    logger.info(f"[UnifiedIDSplit] TOC found {len(toc_map)} sheets")

                # Fall back to bookmarks
                bookmarks = {}
                if len(toc_map) < total_pages // 2:
                    bookmarks = self._extract_bookmarks(doc)

                # Process each page
                for page_num in range(total_pages):
                    page = doc[page_num]

                    # Get sheet info from TOC, bookmarks, or text extraction
                    if page_num in toc_map:
                        ts = toc_map[page_num]
                        sheet_info = {
                            'sheet_number': ts.sheet_id,
                            'title': ts.title,
                            'discipline': self._get_discipline(ts.sheet_id),
                        }
                    elif page_num in bookmarks:
                        sheet_num, title = bookmarks[page_num]
                        sheet_info = {
                            'sheet_number': sheet_num,
                            'title': title,
                            'discipline': self._get_discipline(sheet_num),
                        }
                    else:
                        sheet_info = self._extract_sheet_from_page(page, page_num)

                    if not sheet_info:
                        sheet_info = {
                            'sheet_number': f"SHEET-{page_num + 1:03d}",
                            'title': "Untitled Sheet",
                            'discipline': 'Uncategorized',
                        }

                    # Create discipline subfolder
                    discipline_folder = output_base / sheet_info['discipline']
                    discipline_folder.mkdir(parents=True, exist_ok=True)

                    # Create output filename
                    safe_title = self._sanitize_filename(sheet_info['title'])
                    output_filename = f"{sheet_info['sheet_number']} - {safe_title}.pdf"
                    output_path = discipline_folder / output_filename

                    # Extract single page
                    new_doc = fitz.open()
                    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    new_doc.save(str(output_path), garbage=4, deflate=True, clean=True)
                    new_doc.close()

                    sheets.append(sheet_info)
                    logger.info(f"[UnifiedIDSplit] Extracted sheet: {sheet_info['sheet_number']}")

        except Exception as e:
            logger.error(f"[UnifiedIDSplit] Drawing splitting error for {pdf_path.name}: {e}")
            import traceback
            traceback.print_exc()

        return sheets

    async def _parse_drawing_toc(self, pdf_path: Path) -> List:
        """Use LLM-assisted TOC parser for drawings"""
        try:
            from modules.files.toc_parser import DrawingTOCParser

            if not self.ai:
                return []

            parser = DrawingTOCParser(self.ai)
            return await parser.extract_toc(pdf_path)
        except ImportError:
            return []
        except Exception as e:
            logger.warning(f"[UnifiedIDSplit] Drawing TOC parsing failed: {e}")
            return []

    def _extract_bookmarks(self, doc: fitz.Document) -> Dict[int, Tuple[str, str]]:
        """Extract sheet info from PDF bookmarks"""
        bookmarks = {}

        try:
            toc = doc.get_toc()
            for level, title, page_num in toc:
                page_idx = page_num - 1
                sheet_num, sheet_title = self._parse_bookmark_title(title)
                if sheet_num:
                    bookmarks[page_idx] = (sheet_num, sheet_title)
        except Exception:
            pass

        return bookmarks

    def _parse_bookmark_title(self, title: str) -> Tuple[Optional[str], str]:
        """Parse bookmark title to extract sheet number and title"""
        for pattern in self.SHEET_PATTERNS:
            match = pattern.match(title)
            if match:
                groups = match.groups()
                discipline = groups[0].upper()
                number = groups[1]
                decimal = groups[2] if len(groups) > 2 and groups[2] else None

                if decimal:
                    sheet_num = f"{discipline}{number}.{decimal}"
                else:
                    sheet_num = f"{discipline}{number}"

                title_start = match.end()
                sheet_title = title[title_start:].strip()
                sheet_title = re.sub(r'^[\s\-\u2013\u2014:]+', '', sheet_title)

                return sheet_num, sheet_title if sheet_title else "Untitled"

        return None, title

    def _extract_sheet_from_page(self, page: fitz.Page, page_num: int) -> Optional[Dict]:
        """Extract sheet info from page text"""
        text = page.get_text()

        # Find sheet number
        sheet_number = None
        for pattern in self.SHEET_PATTERNS:
            matches = pattern.finditer(text)
            for match in matches:
                groups = match.groups()
                discipline = groups[0].upper()
                number = groups[1]
                decimal = groups[2] if len(groups) > 2 and groups[2] else None

                if decimal:
                    sheet_number = f"{discipline}{number}.{decimal}"
                else:
                    sheet_number = f"{discipline}{number}"
                break
            if sheet_number:
                break

        if not sheet_number:
            return None

        # Try to find title
        title = "Untitled Sheet"
        title_patterns = [
            re.compile(r'SHEET\s+TITLE[:\s]+([^\n]{5,80})', re.IGNORECASE),
            re.compile(r'DRAWING\s+TITLE[:\s]+([^\n]{5,80})', re.IGNORECASE),
        ]
        for pattern in title_patterns:
            match = pattern.search(text)
            if match:
                title = match.group(1).strip()[:80]
                break

        return {
            'sheet_number': sheet_number,
            'title': title,
            'discipline': self._get_discipline(sheet_number),
        }

    def _get_discipline(self, sheet_number: str) -> str:
        """Get discipline name from sheet number"""
        if not sheet_number:
            return 'Uncategorized'

        # Check multi-character disciplines first
        for disc_code in ['GI', 'GN']:
            if sheet_number.upper().startswith(disc_code):
                return DISCIPLINES.get(disc_code, ('Uncategorized', 'Uncategorized'))[1]

        # Single character
        first_char = sheet_number[0].upper()
        return DISCIPLINES.get(first_char, ('Uncategorized', 'Uncategorized'))[1]

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize string for use in filename"""
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = re.sub(r'\s+', ' ', filename)
        return filename.strip()[:100]
