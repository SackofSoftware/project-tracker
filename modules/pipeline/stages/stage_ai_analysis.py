"""
Stage 5: AI Analysis
Analyzes critical architectural pages using AI to extract door/window schedules,
curtain wall details, and storefront elevations.
"""

import asyncio
import base64
import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber
import fitz  # PyMuPDF
from PIL import Image

# AIProviderManager is passed in from master_pipeline, not imported directly


logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a pipeline stage"""
    success: bool
    data: Dict
    error: Optional[str] = None


class AIAnalysisStage:
    """
    Stage 5: AI Analysis

    Analyzes critical architectural pages to extract:
    - Window schedules
    - Door schedules (identifying Division 8 metal doors vs exclusions)
    - Curtain wall details
    - Storefront elevations

    Uses DeepSeek for text-based analysis and GPT-5 nano vision as fallback.
    """

    def __init__(self, project_folder: Path, ai_provider=None):
        """
        Initialize the AI Analysis stage.

        Args:
            project_folder: Path to the project folder
            ai_provider: AIProviderManager instance for AI operations
        """
        self.project_folder = Path(project_folder)
        self.ai = ai_provider
        self.logger = logging.getLogger(__name__)

        # Drawing Index / Table of Contents identification patterns
        # Most drawing sets have a TOC on the cover or G001/G002 sheets
        self.toc_page_indicators = [
            'DRAWING INDEX',
            'SHEET INDEX',
            'DRAWING LIST',
            'INDEX OF DRAWINGS',
            'TABLE OF CONTENTS',
            'SHEET LIST',
            'DRAWING SCHEDULE',
            'PROJECT SHEET INDEX',
            'SHEET REGISTER',
            'LIST OF DRAWINGS',
        ]

        # Regex patterns for extracting sheet info from TOC lines
        # These capture various formats like:
        #   A610   DOOR SCHEDULE
        #   A-610  DOOR SCHEDULE
        #   A610 - DOOR SCHEDULE
        #   SHEET A610: DOOR SCHEDULE
        #   A610.  DOOR SCHEDULE
        import re
        self.toc_line_patterns = [
            # Pattern 1: Sheet number at start, optional separator, title
            # Matches: A610   DOOR SCHEDULE, A-610  DOOR SCHEDULE, A610 - DOOR SCHEDULE
            re.compile(r'^([A-Z]{1,3}-?\d{2,4})\s*[-:.]?\s*(.+)$', re.IGNORECASE),

            # Pattern 2: "SHEET" prefix before number
            # Matches: SHEET A610: DOOR SCHEDULE, SHEET A-610 - DOOR SCHEDULE
            re.compile(r'^SHEET\s+([A-Z]{1,3}-?\d{2,4})\s*[-:.]?\s*(.+)$', re.IGNORECASE),

            # Pattern 3: Number with discipline prefix
            # Matches: A610  DOOR SCHEDULE (architectural), S201 FOUNDATION PLAN (structural)
            re.compile(r'^([A-Z]{1,3})\s*[-]?\s*(\d{2,4})\s+(.+)$', re.IGNORECASE),

            # Pattern 4: Tabular format with multiple spaces/tabs
            # Matches: A610            DOOR SCHEDULE (TOC tables often have wide spacing)
            re.compile(r'^([A-Z]{1,3}-?\d{2,4})\s{2,}(.+)$', re.IGNORECASE),
        ]

        # Title keywords for fuzzy matching TOC entries to categories
        # Used to map extracted sheet titles to our tracking categories
        self.toc_title_mapping = {
            'door_schedule': [
                'door', 'door schedule', 'door frame', 'door & frame', 'door and frame',
                'hollow metal', 'hm schedule', 'hm door', 'metal door',
            ],
            'window_schedule': [
                'window', 'window schedule', 'window type', 'window detail',
                'glazing', 'glazing schedule', 'fenestration',
            ],
            'elevations': [
                'elevation', 'exterior elevation', 'building elevation',
                'north elevation', 'south elevation', 'east elevation', 'west elevation',
            ],
            'storefront': [
                'storefront', 'store front', 'entrance', 'entry', 'vestibule',
                'entrance detail', 'entrance elevation', 'entry elevation',
            ],
            'curtain_wall': [
                'curtain wall', 'curtainwall', 'curtain-wall', 'unitized wall',
                'ribbon window', 'window wall', 'glazing wall',
            ],
        }

        # Sheet number patterns for Division 8 scope (architectural sheet numbering)
        # Common conventions: A6xx = Schedules, A2xx = Elevations, A1xx = Floor plans
        # Note: Numbering varies by firm, so we check BOTH sheet numbers AND titles
        self.sheet_patterns = {
            'door_schedule': [
                r'A-?6[01][0-9]',       # A610, A611, A-610 - Common door schedule sheets
                r'A-?62[0-9]',          # A620, A621 - Door frame details
                r'AD-?[0-9]+',          # AD series - Door schedules
                r'A-?D[0-9]+',          # A-D01, A-D02 - Alternative door notation
                r'A-?7[01][0-9]',       # Some firms use A710 for schedules
                r'A-?5[01][0-9]',       # Some firms use A510 for schedules
            ],
            'window_schedule': [
                r'A-?63[0-9]',          # A630, A631, A632 - Common window schedule sheets
                r'A-?64[0-9]',          # A640 - Window details
                r'AW-?[0-9]+',          # AW series - Window schedules
                r'A-?W[0-9]+',          # A-W01 - Alternative window notation
            ],
            'elevations': [
                r'A-?2[0-9]{2}',        # A200, A201, A202 - Exterior elevations
                r'A-?3[0-9]{2}',        # A300 series sometimes used for elevations
            ],
            'storefront': [
                r'A-?8[0-9]{2}',        # A800 series - Storefront/curtain wall details
                r'A-?85[0-9]',          # A850 - Specialty openings
                r'SF-?[0-9]+',          # SF series - Storefront
                r'CW-?[0-9]+',          # CW series - Curtain wall
            ],
            'curtain_wall': [
                r'A-?8[0-9]{2}',        # A800 series - Often curtain wall
                r'CW-?[0-9]+',          # CW series
                r'A-?86[0-9]',          # A860 - Curtain wall details
            ],
        }

        # Title keywords to match in sheet titles (primary identification method)
        # These are more reliable than sheet numbers which vary by firm
        self.title_keywords = {
            'door_schedule': [
                'door schedule',
                'door frame schedule',
                'door and frame schedule',
                'door & frame schedule',
                'hollow metal schedule',
                'hm schedule',
                'hm door',
            ],
            'window_schedule': [
                'window schedule',
                'window type',
                'window detail',
                'glazing schedule',
                'fenestration schedule',
            ],
            'elevations': [
                'exterior elevation',
                'building elevation',
                'north elevation',
                'south elevation',
                'east elevation',
                'west elevation',
            ],
            'storefront': [
                'storefront',
                'store front',
                'entrance detail',
                'entrance elevation',
                'entry elevation',
                'vestibule',
            ],
            'curtain_wall': [
                'curtain wall',
                'curtainwall',
                'curtain-wall',
                'unitized wall',
                'ribbon window',
            ],
        }

        # Text extraction confidence threshold
        self.text_confidence_threshold = 0.7

        # Performance limits
        self.max_pages_to_scan = 100  # Don't scan more than this many pages
        self.max_pages_per_category = 3  # Max pages to analyze per category
        self.pdf_open_timeout = 30  # Seconds to wait for PDF open operations

    def _validate_pdf(self, pdf_path: str) -> Tuple[bool, str]:
        """
        Quickly validate a PDF file is readable and not corrupted.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Quick check with fitz (MuPDF) - opens faster than pdfplumber
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            if page_count == 0:
                doc.close()
                return False, "PDF has no pages"
            # Try to access first page to catch lazy-loaded errors
            _ = doc[0].get_text()[:100]
            doc.close()
            return True, ""
        except Exception as e:
            error_msg = str(e)
            # Common MuPDF errors for corrupted files
            if 'stack overflow' in error_msg.lower():
                return False, "PDF is corrupted (stack overflow)"
            elif 'format error' in error_msg.lower():
                return False, "PDF has format errors"
            elif 'object out of range' in error_msg.lower():
                return False, "PDF structure is corrupted"
            else:
                return False, f"PDF validation failed: {error_msg[:100]}"

    async def run(self) -> StageResult:
        """
        Run the AI analysis stage.

        Returns:
            StageResult with analysis results
        """
        try:
            self.logger.info("Starting AI Analysis Stage")
            self.logger.info(f"  Project folder: {self.project_folder}")

            # Find drawing PDFs in the project folder
            drawings_folder = self.project_folder / 'Drawings'
            if not drawings_folder.exists():
                drawings_folder = self.project_folder

            # Look for the main drawings PDF or split sheets
            pdf_files = list(drawings_folder.glob('*.pdf'))
            if not pdf_files:
                return StageResult(
                    success=True,
                    data={'message': 'No drawing PDFs found to analyze', 'pages_analyzed': 0}
                )

            self.logger.info(f"  Found {len(pdf_files)} PDF files")

            # Check if AI is available
            if not self.ai:
                self.logger.info("  AI provider not configured - skipping analysis")
                return StageResult(
                    success=True,
                    data={'message': 'AI provider not configured', 'pages_analyzed': 0}
                )

            # For now, do a simplified scan - look for the largest PDF (likely drawings)
            pdf_files_sorted = sorted(pdf_files, key=lambda p: p.stat().st_size, reverse=True)
            main_pdf = pdf_files_sorted[0] if pdf_files_sorted else None

            if not main_pdf:
                return StageResult(
                    success=True,
                    data={'message': 'No PDFs found', 'pages_analyzed': 0}
                )

            self.logger.info(f"  Scanning main PDF: {main_pdf.name}")

            # Validate PDF before processing
            is_valid, error_msg = self._validate_pdf(str(main_pdf))
            if not is_valid:
                self.logger.warning(f"  PDF validation failed: {error_msg}")
                return StageResult(
                    success=True,  # Don't fail the pipeline, just skip
                    data={
                        'message': f'PDF validation failed: {error_msg}',
                        'pages_analyzed': 0,
                        'skipped': True
                    }
                )

            # Find relevant pages with timeout protection
            self.logger.info("  Identifying relevant pages for analysis")
            try:
                relevant_pages = await asyncio.wait_for(
                    self._find_relevant_pages(str(main_pdf)),
                    timeout=120  # 2 minute timeout for page finding
                )
            except asyncio.TimeoutError:
                self.logger.error("  Timeout while scanning PDF pages")
                return StageResult(
                    success=True,  # Don't fail pipeline, just skip
                    data={
                        'message': 'Timeout while scanning PDF - file may be corrupted',
                        'pages_analyzed': 0,
                        'skipped': True
                    }
                )

            if not relevant_pages:
                self.logger.warning("No relevant pages found for AI analysis")
                return StageResult(
                    success=True,
                    data={
                        'door_schedules': [],
                        'window_schedules': [],
                        'curtain_wall_details': [],
                        'storefront_elevations': [],
                        'analysis_summary': 'No relevant pages identified'
                    },
                    error=None
                )

            # Analyze each category of pages
            results = {
                'door_schedules': [],
                'window_schedules': [],
                'curtain_wall_details': [],
                'storefront_elevations': [],
                'analysis_summary': ''
            }

            # Process door schedules
            if relevant_pages.get('door'):
                self.logger.info(f"  Analyzing {len(relevant_pages['door'])} door schedule pages")
                door_results = await self._analyze_door_schedules(
                    str(main_pdf),
                    relevant_pages['door']
                )
                results['door_schedules'] = door_results

            # Process window schedules
            if relevant_pages.get('window'):
                self.logger.info(f"  Analyzing {len(relevant_pages['window'])} window schedule pages")
                window_results = await self._analyze_window_schedules(
                    str(main_pdf),
                    relevant_pages['window']
                )
                results['window_schedules'] = window_results

            # Process curtain wall details
            if relevant_pages.get('curtain_wall'):
                self.logger.info(f"  Analyzing {len(relevant_pages['curtain_wall'])} curtain wall pages")
                cw_results = await self._analyze_curtain_walls(
                    str(main_pdf),
                    relevant_pages['curtain_wall']
                )
                results['curtain_wall_details'] = cw_results

            # Process storefront elevations
            if relevant_pages.get('storefront'):
                self.logger.info(f"  Analyzing {len(relevant_pages['storefront'])} storefront pages")
                sf_results = await self._analyze_storefronts(
                    str(main_pdf),
                    relevant_pages['storefront']
                )
                results['storefront_elevations'] = sf_results

            # Generate summary
            results['analysis_summary'] = await self._generate_summary(results)

            self.logger.info("AI Analysis Stage completed successfully")
            return StageResult(success=True, data=results, error=None)

        except Exception as e:
            self.logger.error(f"AI Analysis Stage failed: {str(e)}", exc_info=True)
            return StageResult(
                success=False,
                data={},
                error=f"AI analysis failed: {str(e)}"
            )

    def _fuzzy_match_title_to_category(self, title: str) -> Optional[str]:
        """
        Fuzzy match a sheet title to a category using keyword matching.

        Args:
            title: Sheet title from TOC

        Returns:
            Category name or None if no match
        """
        title_lower = title.lower().strip()

        # Check each category's keywords
        for category, keywords in self.toc_title_mapping.items():
            for keyword in keywords:
                if keyword.lower() in title_lower:
                    return category

        return None

    async def _parse_toc_pages(self, pdf_path: str) -> List[Dict]:
        """
        Parse Table of Contents / Drawing Index pages to extract sheet information.

        Searches for pages containing TOC indicators, then extracts sheet numbers
        and titles using regex patterns. Maps titles to categories using fuzzy matching.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of dictionaries with sheet info:
            [{
                'sheet_number': 'A610',
                'title': 'DOOR SCHEDULE',
                'category': 'door',
                'page_number': 15  # estimated page in PDF
            }]
        """
        import re

        sheets = []
        sheet_to_page_map = {}  # Map sheet numbers to page numbers in PDF

        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)

                # Step 1: Find TOC pages (usually in first 10 pages)
                toc_pages = []
                for page_num in range(1, min(11, total_pages + 1)):
                    page = pdf.pages[page_num - 1]
                    text = page.extract_text() or ""
                    text_upper = text.upper()

                    # Check if this page contains TOC indicators
                    for indicator in self.toc_page_indicators:
                        if indicator in text_upper:
                            toc_pages.append(page_num)
                            self.logger.info(f"  Found TOC page {page_num} (contains '{indicator}')")
                            break

                if not toc_pages:
                    self.logger.info("  No TOC pages found")
                    return []

                # Step 2: Build a map of sheet numbers to page numbers by scanning all pages
                self.logger.info("  Building sheet number to page number map...")
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    # Look for sheet numbers in the title block area (first 500 chars)
                    title_block = text[:500] if len(text) > 500 else text

                    # Try to find sheet number patterns in title block
                    for pattern_category, patterns in self.sheet_patterns.items():
                        for pattern in patterns:
                            match = re.search(pattern, title_block, re.IGNORECASE)
                            if match:
                                sheet_num = match.group(0).upper()
                                if sheet_num not in sheet_to_page_map:
                                    sheet_to_page_map[sheet_num] = page_num

                # Step 3: Extract sheet info from TOC pages
                for toc_page_num in toc_pages:
                    page = pdf.pages[toc_page_num - 1]
                    text = page.extract_text() or ""

                    # Split into lines and process each line
                    lines = text.split('\n')

                    for line in lines:
                        line = line.strip()
                        if not line or len(line) < 5:
                            continue

                        # Try each TOC line pattern
                        for pattern in self.toc_line_patterns:
                            match = pattern.match(line)
                            if match:
                                groups = match.groups()

                                # Extract sheet number and title based on pattern
                                if len(groups) == 2:
                                    # Pattern 1, 2, or 4: (sheet_number, title)
                                    sheet_number = groups[0].upper()
                                    title = groups[1].strip()
                                elif len(groups) == 3:
                                    # Pattern 3: (discipline, number, title)
                                    sheet_number = f"{groups[0]}{groups[1]}".upper()
                                    title = groups[2].strip()
                                else:
                                    continue

                                # Clean up sheet number (remove spaces, normalize hyphens)
                                sheet_number = sheet_number.replace(' ', '').replace('--', '-')

                                # Skip if title is too short (likely not a real sheet)
                                if len(title) < 3:
                                    continue

                                # Fuzzy match title to category
                                category = self._fuzzy_match_title_to_category(title)

                                # Try to find the actual page number for this sheet
                                page_number = None

                                # Try exact match
                                if sheet_number in sheet_to_page_map:
                                    page_number = sheet_to_page_map[sheet_number]
                                else:
                                    # Try with/without hyphen
                                    sheet_num_no_hyphen = sheet_number.replace('-', '')
                                    sheet_num_with_hyphen = re.sub(r'^([A-Z]+)(\d+)$', r'\1-\2', sheet_number)

                                    for variant in [sheet_num_no_hyphen, sheet_num_with_hyphen]:
                                        if variant in sheet_to_page_map:
                                            page_number = sheet_to_page_map[variant]
                                            break

                                # Only add if we found a category and page number
                                if category and page_number:
                                    sheets.append({
                                        'sheet_number': sheet_number,
                                        'title': title,
                                        'category': category,
                                        'page_number': page_number
                                    })
                                    self.logger.debug(
                                        f"    TOC entry: {sheet_number} - {title} -> "
                                        f"{category} (page {page_number})"
                                    )

                                break  # Found a match, no need to try other patterns

        except Exception as e:
            self.logger.error(f"Error parsing TOC pages: {str(e)}", exc_info=True)

        return sheets

    async def _find_relevant_pages(self, pdf_path: str) -> Dict[str, List[int]]:
        """
        Find pages containing schedules and details using OPTIMIZED TRIPLE identification:
        1. TOC parsing - extract sheet info from drawing index (PRIORITY)
        2. Split PDF checking - check filenames if individual sheets
        3. Page-by-page scan with early exit (FALLBACK)

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary mapping category to list of page numbers
        """
        import re

        relevant_pages = {
            'door': [],
            'window': [],
            'curtain_wall': [],
            'storefront': []
        }

        # Map pattern categories to result categories
        category_mapping = {
            'door_schedule': 'door',
            'window_schedule': 'window',
            'elevations': 'storefront',  # Elevations can show storefront
            'storefront': 'storefront',
            'curtain_wall': 'curtain_wall',
        }

        try:
            # First check: If files are already split, check filenames
            pdf_file = Path(pdf_path)
            drawings_folder = pdf_file.parent

            # Check if we have split PDFs (individual sheets)
            split_pdfs = list(drawings_folder.glob('A*.pdf')) + list(drawings_folder.glob('AD*.pdf'))

            if len(split_pdfs) > 10:  # Likely have split sheets
                self.logger.info(f"  Found {len(split_pdfs)} split sheet PDFs - checking filenames")
                return await self._find_relevant_split_sheets(drawings_folder)

            # METHOD 0: Check for TOC/Drawing Index first (PRIORITY - most efficient)
            self.logger.info("  Attempting to parse Table of Contents...")
            toc_sheets = await self._parse_toc_pages(pdf_path)

            if toc_sheets:
                self.logger.info(f"  Found drawing index with {len(toc_sheets)} sheets")
                # Add TOC-identified pages to relevant_pages
                for sheet_info in toc_sheets:
                    category = sheet_info.get('category')
                    page_num = sheet_info.get('page_number')
                    if category and page_num and category in relevant_pages:
                        if page_num not in relevant_pages[category]:
                            relevant_pages[category].append(page_num)
                            self.logger.info(
                                f"    Page {page_num}: TOC match [{sheet_info['sheet_number']}] "
                                f"{sheet_info['title'][:40]} -> {category}"
                            )

                # If TOC provided useful results, skip full page scan
                if any(relevant_pages.values()):
                    self.logger.info("  TOC parsing successful - skipping full page scan")
                    for category, pages in relevant_pages.items():
                        if pages:
                            self.logger.info(f"  Found {len(pages)} {category} page(s) from TOC: {pages}")
                    return relevant_pages

            # Fall back to OPTIMIZED page-by-page scan with early exit
            self.logger.info(f"  TOC not found - performing optimized page scan...")

            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                self.logger.info(f"  PDF has {total_pages} pages")

                # Limit pages to scan for performance
                pages_to_scan = min(total_pages, self.max_pages_to_scan)
                if pages_to_scan < total_pages:
                    self.logger.info(f"  Limiting scan to first {pages_to_scan} pages (max: {self.max_pages_to_scan})")

                # Track which categories we still need
                categories_needed = set(relevant_pages.keys())

                for page_num, page in enumerate(pdf.pages[:pages_to_scan], start=1):
                    # Early exit if we've found all categories with sufficient pages
                    if not categories_needed:
                        self.logger.info(f"  Early exit at page {page_num} - all target categories found")
                        break

                    # Extract text from page
                    text = page.extract_text() or ""
                    text_upper = text.upper()

                    # Skip very short pages (likely blank or cover pages)
                    if len(text_upper) < 50:
                        continue

                    # METHOD 1: Check sheet number patterns in title block only (OPTIMIZED)
                    # Sheet numbers are usually in first 500 chars (title block area)
                    title_block_text = text_upper[:500] if len(text_upper) > 500 else text_upper

                    for pattern_category, patterns in self.sheet_patterns.items():
                        result_category = category_mapping.get(pattern_category)
                        if not result_category or result_category not in categories_needed:
                            continue

                        for pattern in patterns:
                            if re.search(pattern, title_block_text, re.IGNORECASE):
                                if page_num not in relevant_pages[result_category]:
                                    relevant_pages[result_category].append(page_num)
                                    self.logger.info(f"    Page {page_num}: Sheet number match [{pattern}] -> {result_category}")
                                    # Remove category if we have enough pages (3 max per category)
                                    if len(relevant_pages[result_category]) >= 3:
                                        categories_needed.discard(result_category)
                                break

                    # METHOD 2: Check title keywords (full page text)
                    for title_category, keywords in self.title_keywords.items():
                        result_category = category_mapping.get(title_category)
                        if not result_category or result_category not in categories_needed:
                            continue

                        for keyword in keywords:
                            if keyword.upper() in text_upper:
                                if page_num not in relevant_pages[result_category]:
                                    relevant_pages[result_category].append(page_num)
                                    self.logger.info(f"    Page {page_num}: Title match [{keyword}] -> {result_category}")
                                    # Remove category if we have enough pages
                                    if len(relevant_pages[result_category]) >= 3:
                                        categories_needed.discard(result_category)
                                break

            # Log summary
            for category, pages in relevant_pages.items():
                if pages:
                    self.logger.info(f"  Found {len(pages)} {category} page(s): {pages}")

            return relevant_pages

        except Exception as e:
            self.logger.error(f"Error finding relevant pages: {str(e)}", exc_info=True)
            return relevant_pages

    async def _find_relevant_split_sheets(self, drawings_folder: Path) -> Dict[str, List[int]]:
        """
        Find relevant pages from split sheet PDFs by checking filenames.

        When drawings are already split into individual PDFs, the filename
        contains the sheet number and title (e.g., "A610 - Door Schedule.pdf")

        Args:
            drawings_folder: Path to folder containing split PDFs

        Returns:
            Dictionary mapping category to list of (pdf_path, page_number) tuples
        """
        import re

        relevant_pages = {
            'door': [],
            'window': [],
            'curtain_wall': [],
            'storefront': []
        }

        category_mapping = {
            'door_schedule': 'door',
            'window_schedule': 'window',
            'elevations': 'storefront',
            'storefront': 'storefront',
            'curtain_wall': 'curtain_wall',
        }

        # Get all PDFs in the drawings folder
        pdf_files = sorted(drawings_folder.glob('*.pdf'))

        for pdf_path in pdf_files:
            filename = pdf_path.name.upper()
            filename_stem = pdf_path.stem.upper()

            # Check sheet number patterns in filename
            for pattern_category, patterns in self.sheet_patterns.items():
                result_category = category_mapping.get(pattern_category)
                if not result_category:
                    continue

                for pattern in patterns:
                    if re.search(pattern, filename_stem, re.IGNORECASE):
                        # For split sheets, page 1 is the sheet
                        relevant_pages[result_category].append({
                            'pdf_path': str(pdf_path),
                            'page': 1,
                            'sheet_name': pdf_path.stem
                        })
                        self.logger.info(f"    Split sheet: {pdf_path.name} -> {result_category}")
                        break

            # Also check title keywords in filename
            for title_category, keywords in self.title_keywords.items():
                result_category = category_mapping.get(title_category)
                if not result_category:
                    continue

                for keyword in keywords:
                    if keyword.upper().replace(' ', '') in filename.replace(' ', ''):
                        already_added = any(
                            p.get('pdf_path') == str(pdf_path)
                            for p in relevant_pages[result_category]
                            if isinstance(p, dict)
                        )
                        if not already_added:
                            relevant_pages[result_category].append({
                                'pdf_path': str(pdf_path),
                                'page': 1,
                                'sheet_name': pdf_path.stem
                            })
                            self.logger.info(f"    Split sheet (title): {pdf_path.name} -> {result_category}")
                        break

        # Log summary
        for category, pages in relevant_pages.items():
            if pages:
                self.logger.info(f"  Found {len(pages)} {category} sheet(s)")

        return relevant_pages

    async def _analyze_door_schedules(self, pdf_path: str, page_numbers: List[int]) -> List[Dict]:
        """
        Analyze door schedule pages to identify Division 8 scope.

        Args:
            pdf_path: Path to PDF file
            page_numbers: List of page numbers to analyze

        Returns:
            List of door schedule analysis results
        """
        results = []

        for page_num in page_numbers:
            try:
                # Extract text and tables
                text, tables, confidence = await self._extract_page_data(pdf_path, page_num)

                # Decide whether to use text or vision analysis
                if confidence >= self.text_confidence_threshold and tables:
                    # Use text-based analysis with DeepSeek
                    analysis = await self._analyze_door_schedule_text(
                        text, tables, page_num
                    )
                else:
                    # Fall back to vision analysis with GPT-5 nano
                    self.logger.info(f"Low text confidence for page {page_num}, using vision analysis")
                    image_base64 = await self._pdf_page_to_image(pdf_path, page_num)
                    analysis = await self._analyze_door_schedule_vision(
                        image_base64, page_num
                    )

                results.append(analysis)

            except Exception as e:
                self.logger.error(f"Error analyzing door schedule page {page_num}: {str(e)}")
                results.append({
                    'page': page_num,
                    'error': str(e),
                    'doors': []
                })

        return results

    async def _analyze_door_schedule_text(
        self,
        text: str,
        tables: List[List[List[str]]],
        page_num: int
    ) -> Dict:
        """
        Analyze door schedule using text extraction and DeepSeek.

        Args:
            text: Extracted text from page
            tables: Extracted tables from page
            page_num: Page number

        Returns:
            Analysis results
        """
        system_prompt = """You are an expert construction estimator analyzing architectural door schedules.
Your task is to identify doors within Division 8 scope (metal doors and frames) and exclude wood doors.

Division 8 scope includes:
- Hollow metal doors (HM)
- Aluminum doors
- Stainless steel doors
- Metal frames
- Glass and aluminum doors

Exclusions (not Division 8):
- Wood doors
- Wood frames
- Plastic laminate doors
- Specialty doors by others"""

        prompt = f"""Analyze this door schedule from page {page_num}.

TEXT CONTENT:
{text[:4000]}  # Limit text length

TABLE DATA:
{str(tables)[:4000]}  # Limit table length

For each door, identify:
1. Door mark/number
2. Material type (HM, aluminum, stainless, wood, etc.)
3. Size (width x height)
4. Fire rating (if specified)
5. Hardware group
6. Whether it's in Division 8 scope (YES/NO)

Return your analysis in JSON format:
{{
    "page": {page_num},
    "doors": [
        {{
            "mark": "101",
            "material": "HM",
            "size": "3070",
            "fire_rating": "90 min",
            "hardware": "HG-1",
            "division_8_scope": true,
            "notes": "Hollow metal door with frame"
        }}
    ],
    "division_8_count": 25,
    "exclusion_count": 5,
    "summary": "Brief summary of findings"
}}"""

        try:
            result = await self.ai.reason(prompt, system_prompt)

            # Parse the JSON response
            import json
            analysis = json.loads(result)
            return analysis

        except json.JSONDecodeError:
            # If JSON parsing fails, return raw text
            self.logger.warning(f"Could not parse JSON from DeepSeek response for page {page_num}")
            return {
                'page': page_num,
                'raw_analysis': result,
                'doors': [],
                'parse_error': True
            }

    async def _analyze_door_schedule_vision(self, image_base64: str, page_num: int) -> Dict:
        """
        Analyze door schedule using vision model (GPT-5 nano).

        Args:
            image_base64: Base64 encoded image of the page
            page_num: Page number

        Returns:
            Analysis results
        """
        prompt = f"""Analyze this door schedule from architectural drawings (page {page_num}).

Identify all doors and classify them:

Division 8 scope (INCLUDE):
- Hollow metal (HM) doors
- Aluminum doors
- Stainless steel doors
- Metal frames

Exclusions (EXCLUDE):
- Wood doors
- Wood frames

For each door, extract:
- Door mark/number
- Material type
- Size
- Fire rating
- Hardware group
- Division 8 scope (YES/NO)

Return JSON format:
{{
    "page": {page_num},
    "doors": [
        {{"mark": "101", "material": "HM", "size": "3070", "fire_rating": "90 min", "hardware": "HG-1", "division_8_scope": true}}
    ],
    "division_8_count": 25,
    "exclusion_count": 5,
    "summary": "Summary of findings"
}}"""

        try:
            result = await self.ai.vision(image_base64, prompt)

            # Parse the JSON response
            import json
            analysis = json.loads(result)
            return analysis

        except json.JSONDecodeError:
            self.logger.warning(f"Could not parse JSON from vision response for page {page_num}")
            return {
                'page': page_num,
                'raw_analysis': result,
                'doors': [],
                'parse_error': True
            }

    async def _analyze_window_schedules(self, pdf_path: str, page_numbers: List[int]) -> List[Dict]:
        """
        Analyze window schedule pages.

        Args:
            pdf_path: Path to PDF file
            page_numbers: List of page numbers to analyze

        Returns:
            List of window schedule analysis results
        """
        results = []

        for page_num in page_numbers:
            try:
                text, tables, confidence = await self._extract_page_data(pdf_path, page_num)

                if confidence >= self.text_confidence_threshold and tables:
                    analysis = await self._analyze_window_schedule_text(text, tables, page_num)
                else:
                    image_base64 = await self._pdf_page_to_image(pdf_path, page_num)
                    analysis = await self._analyze_window_schedule_vision(image_base64, page_num)

                results.append(analysis)

            except Exception as e:
                self.logger.error(f"Error analyzing window schedule page {page_num}: {str(e)}")
                results.append({
                    'page': page_num,
                    'error': str(e),
                    'windows': []
                })

        return results

    async def _analyze_window_schedule_text(
        self,
        text: str,
        tables: List[List[List[str]]],
        page_num: int
    ) -> Dict:
        """Analyze window schedule using text extraction and DeepSeek."""
        system_prompt = """You are an expert construction estimator analyzing architectural window schedules.
Identify all window types, sizes, glazing specifications, and frame materials."""

        prompt = f"""Analyze this window schedule from page {page_num}.

TEXT CONTENT:
{text[:4000]}

TABLE DATA:
{str(tables)[:4000]}

For each window, identify:
1. Window mark/number
2. Type (fixed, operable, etc.)
3. Size (width x height)
4. Frame material (aluminum, vinyl, etc.)
5. Glazing specification
6. Quantity

Return JSON format:
{{
    "page": {page_num},
    "windows": [
        {{
            "mark": "W1",
            "type": "Fixed",
            "size": "4x6",
            "frame_material": "Aluminum",
            "glazing": "1\" insulated",
            "quantity": 10
        }}
    ],
    "total_count": 50,
    "summary": "Summary of window types"
}}"""

        try:
            result = await self.ai.reason(prompt, system_prompt)
            import json
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                'page': page_num,
                'raw_analysis': result,
                'windows': [],
                'parse_error': True
            }

    async def _analyze_window_schedule_vision(self, image_base64: str, page_num: int) -> Dict:
        """Analyze window schedule using vision model."""
        prompt = f"""Analyze this window schedule from page {page_num}.

Extract all windows with:
- Mark/number
- Type
- Size
- Frame material
- Glazing
- Quantity

Return JSON:
{{
    "page": {page_num},
    "windows": [{{"mark": "W1", "type": "Fixed", "size": "4x6", "frame_material": "Aluminum", "glazing": "1\\" insulated", "quantity": 10}}],
    "total_count": 50,
    "summary": "Summary"
}}"""

        try:
            result = await self.ai.vision(image_base64, prompt)
            import json
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                'page': page_num,
                'raw_analysis': result,
                'windows': [],
                'parse_error': True
            }

    async def _analyze_curtain_walls(self, pdf_path: str, page_numbers: List[int]) -> List[Dict]:
        """
        Analyze curtain wall detail pages.

        Args:
            pdf_path: Path to PDF file
            page_numbers: List of page numbers to analyze

        Returns:
            List of curtain wall analysis results
        """
        results = []

        for page_num in page_numbers:
            try:
                # Curtain wall details are often better analyzed with vision
                image_base64 = await self._pdf_page_to_image(pdf_path, page_num)

                prompt = f"""Analyze this curtain wall detail from page {page_num}.

Identify:
1. System type (stick-built, unitized, etc.)
2. Frame material and finish
3. Glazing specification
4. Thermal performance requirements
5. Water/air infiltration requirements
6. Installation details

Return JSON:
{{
    "page": {page_num},
    "system_type": "Unitized curtain wall",
    "frame_material": "Aluminum with thermal break",
    "glazing": "1\\" insulated low-e",
    "thermal_performance": "U-0.45",
    "testing_requirements": ["ASTM E1105", "ASTM E283"],
    "key_details": ["Head detail", "Sill detail", "Jamb detail"],
    "summary": "Description of curtain wall system"
}}"""

                result = await self.ai.vision(image_base64, prompt)

                import json
                analysis = json.loads(result)
                results.append(analysis)

            except Exception as e:
                self.logger.error(f"Error analyzing curtain wall page {page_num}: {str(e)}")
                results.append({
                    'page': page_num,
                    'error': str(e)
                })

        return results

    async def _analyze_storefronts(self, pdf_path: str, page_numbers: List[int]) -> List[Dict]:
        """
        Analyze storefront elevation pages.

        Args:
            pdf_path: Path to PDF file
            page_numbers: List of page numbers to analyze

        Returns:
            List of storefront analysis results
        """
        results = []

        for page_num in page_numbers:
            try:
                image_base64 = await self._pdf_page_to_image(pdf_path, page_num)

                prompt = f"""Analyze this storefront elevation from page {page_num}.

Identify:
1. Storefront system type
2. Frame material and finish
3. Glazing type
4. Door types and locations
5. Overall dimensions
6. Special features (sidelites, transoms, etc.)

Return JSON:
{{
    "page": {page_num},
    "system_type": "Heavy-duty storefront",
    "frame_material": "Aluminum",
    "finish": "Dark bronze anodized",
    "glazing": "1\\" tempered insulated",
    "doors": ["Single entrance", "Double entrance"],
    "dimensions": "Width x Height",
    "special_features": ["Transom windows", "Sidelites"],
    "summary": "Description of storefront"
}}"""

                result = await self.ai.vision(image_base64, prompt)

                import json
                analysis = json.loads(result)
                results.append(analysis)

            except Exception as e:
                self.logger.error(f"Error analyzing storefront page {page_num}: {str(e)}")
                results.append({
                    'page': page_num,
                    'error': str(e)
                })

        return results

    async def _extract_page_data(
        self,
        pdf_path: str,
        page_num: int
    ) -> Tuple[str, List[List[List[str]]], float]:
        """
        Extract text and tables from a PDF page using pdfplumber.

        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-indexed)

        Returns:
            Tuple of (text, tables, confidence_score)
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                page = pdf.pages[page_num - 1]  # pdfplumber uses 0-indexing

                # Extract text
                text = page.extract_text() or ""

                # Extract tables
                tables = page.extract_tables()

                # Calculate confidence based on text quality and table presence
                confidence = self._calculate_extraction_confidence(text, tables)

                return text, tables, confidence

        except Exception as e:
            self.logger.error(f"Error extracting data from page {page_num}: {str(e)}")
            return "", [], 0.0

    def _calculate_extraction_confidence(
        self,
        text: str,
        tables: List[List[List[str]]]
    ) -> float:
        """
        Calculate confidence score for text extraction quality.

        Args:
            text: Extracted text
            tables: Extracted tables

        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.0

        # Base confidence on text length
        if len(text) > 500:
            confidence += 0.3
        elif len(text) > 200:
            confidence += 0.2
        elif len(text) > 50:
            confidence += 0.1

        # Add confidence if tables were found
        if tables and len(tables) > 0:
            confidence += 0.4

            # Check table quality (non-empty cells)
            for table in tables:
                non_empty_cells = sum(
                    1 for row in table for cell in row if cell and cell.strip()
                )
                if non_empty_cells > 10:
                    confidence += 0.1
                    break

        # Check for schedule-like patterns in text
        schedule_indicators = ['mark', 'type', 'size', 'qty', 'quantity', 'material', 'frame']
        text_lower = text.lower()
        if any(indicator in text_lower for indicator in schedule_indicators):
            confidence += 0.2

        return min(confidence, 1.0)  # Cap at 1.0

    async def _pdf_page_to_image(self, pdf_path: str, page_num: int) -> str:
        """
        Convert a PDF page to a base64-encoded image for vision analysis.

        Args:
            pdf_path: Path to PDF file
            page_num: Page number (1-indexed)

        Returns:
            Base64-encoded image string
        """
        try:
            doc = fitz.open(pdf_path)
            page = doc[page_num - 1]  # fitz uses 0-indexing

            # Render page to image at high resolution
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Convert to base64
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            doc.close()

            return img_base64

        except Exception as e:
            self.logger.error(f"Error converting page {page_num} to image: {str(e)}")
            raise

    async def _generate_summary(self, results: Dict) -> str:
        """
        Generate an overall summary of the AI analysis.

        Args:
            results: Analysis results dictionary

        Returns:
            Summary string
        """
        summary_parts = []

        # Door schedule summary
        door_count = len(results.get('door_schedules', []))
        if door_count > 0:
            total_div8_doors = 0
            total_exclusions = 0
            for schedule in results['door_schedules']:
                total_div8_doors += schedule.get('division_8_count', 0)
                total_exclusions += schedule.get('exclusion_count', 0)

            summary_parts.append(
                f"Analyzed {door_count} door schedule page(s): "
                f"{total_div8_doors} Division 8 doors, {total_exclusions} exclusions"
            )

        # Window schedule summary
        window_count = len(results.get('window_schedules', []))
        if window_count > 0:
            total_windows = sum(
                schedule.get('total_count', 0)
                for schedule in results['window_schedules']
            )
            summary_parts.append(
                f"Analyzed {window_count} window schedule page(s): "
                f"{total_windows} total windows"
            )

        # Curtain wall summary
        cw_count = len(results.get('curtain_wall_details', []))
        if cw_count > 0:
            summary_parts.append(f"Analyzed {cw_count} curtain wall detail page(s)")

        # Storefront summary
        sf_count = len(results.get('storefront_elevations', []))
        if sf_count > 0:
            summary_parts.append(f"Analyzed {sf_count} storefront elevation page(s)")

        if not summary_parts:
            return "No pages analyzed"

        return "; ".join(summary_parts)
