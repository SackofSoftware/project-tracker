"""
File Organization Module for Scope Takeoff

Organizes project documents into structured folders after identification:
- Specs/ - Specification documents
- Drawings/ - Drawing files (split into individual sheets)
- Schedules/ - Door/window schedules
- Addenda/ - Addendum documents

Each drawing sheet is extracted as a separate PDF with proper naming.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False


class FileOrganizer:
    """
    Organizes project documents into structured folders.

    Creates folder structure:
    - Extracted-Data/
      - Organized/
        - Specs/
        - Drawings/
        - Schedules/
        - Addenda/
    """

    def __init__(self, project_folder: Path):
        self.project_folder = Path(project_folder)
        self.organized_root = self.project_folder / 'Extracted-Data' / 'Organized'
        self.organized_files = []

        # Create folder structure
        self.folders = {
            'spec': self.organized_root / 'Specs',
            'drawing': self.organized_root / 'Drawings',
            'schedule': self.organized_root / 'Schedules',
            'addendum': self.organized_root / 'Addenda'
        }

        for folder in self.folders.values():
            folder.mkdir(parents=True, exist_ok=True)

    def organize_document(self, doc_info: Dict) -> List[Dict]:
        """
        Organize a document based on its type.

        Args:
            doc_info: Document info dict with 'path', 'doc_type', 'filename', etc.

        Returns:
            List of organized file records
        """
        doc_type = doc_info.get('doc_type', 'unknown')
        original_path = Path(doc_info.get('path', ''))

        if not original_path.exists() or doc_type == 'unknown':
            return []

        # Handle different document types
        if doc_type == 'drawing':
            return self._organize_drawings(original_path, doc_info)
        elif doc_type == 'consolidated':
            # Consolidated PDFs contain both specs and drawings
            # Copy to Specs folder (for spec extraction) but also process as drawings
            records = []
            # Copy whole file to Specs for reference
            spec_records = self._copy_document(original_path, 'spec')
            records.extend(spec_records)
            # Also split into individual drawing sheets
            drawing_records = self._organize_drawings(original_path, doc_info)
            records.extend(drawing_records)
            return records
        elif doc_type in ['spec', 'schedule', 'addendum']:
            return self._copy_document(original_path, doc_type)

        return []

    def _copy_document(self, original_path: Path, doc_type: str) -> List[Dict]:
        """
        Copy a non-drawing document to appropriate folder.

        Args:
            original_path: Path to original PDF
            doc_type: 'spec', 'schedule', or 'addendum'

        Returns:
            List with single organized file record
        """
        dest_folder = self.folders.get(doc_type)
        if not dest_folder:
            return []

        # Create clean filename
        dest_path = dest_folder / original_path.name

        # Skip if source and destination are the same file
        if original_path.resolve() == dest_path.resolve():
            # Already in the right place, just record it
            pass
        else:
            # Copy file (overwrite if exists)
            shutil.copy2(original_path, dest_path)

        record = {
            'original_path': str(original_path),
            'organized_path': str(dest_path),
            'doc_type': doc_type,
            'sheet_number': None,
            'sheet_title': None,
            'page_number': None
        }

        self.organized_files.append(record)
        return [record]

    def _organize_drawings(self, original_path: Path, doc_info: Dict) -> List[Dict]:
        """
        Split drawing PDF into individual sheets and organize.

        Each sheet becomes a separate PDF named by sheet number.

        Args:
            original_path: Path to original drawing PDF
            doc_info: Document info with detected_sheets list

        Returns:
            List of organized file records (one per sheet)
        """
        if not PYMUPDF_AVAILABLE:
            # Fallback: copy entire file
            return self._copy_document(original_path, 'drawing')

        organized_records = []
        dest_folder = self.folders['drawing']

        try:
            with fitz.open(original_path) as doc:
                page_count = doc.page_count

                # Extract bookmarks and build sheet_number -> title lookup dictionary
                # This is more reliable than matching by page number (which can be wrong)
                bookmarks = doc.get_toc()  # Returns [(level, title, page_num), ...]
                bookmark_titles = self._build_bookmark_title_dict(bookmarks)

                for page_num in range(page_count):
                    page = doc[page_num]
                    text = page.get_text()

                    # Extract sheet info from page (with bookmark title dict for lookup)
                    sheet_info = self._extract_sheet_info(text, page_num, bookmarks, bookmark_titles)

                    # Create individual PDF for this sheet
                    sheet_filename = self._create_sheet_filename(sheet_info)
                    sheet_path = dest_folder / sheet_filename

                    # Extract single page to new PDF with optimization
                    new_doc = fitz.open()
                    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    # Save with garbage collection and compression to reduce file size
                    new_doc.save(
                        str(sheet_path),
                        garbage=4,      # Maximum garbage collection (removes unused objects)
                        deflate=True,   # Compress streams
                        clean=True      # Clean up redundant content
                    )
                    new_doc.close()

                    # Create record
                    record = {
                        'original_path': str(original_path),
                        'organized_path': str(sheet_path),
                        'doc_type': 'drawing',
                        'sheet_number': sheet_info['sheet_number'],
                        'sheet_title': sheet_info['sheet_title'],
                        'page_number': page_num + 1,
                        'title_source': sheet_info.get('source', 'unknown')
                    }

                    organized_records.append(record)
                    self.organized_files.append(record)

        except Exception as e:
            print(f"Error organizing drawings: {e}")
            # Fallback: copy entire file
            return self._copy_document(original_path, 'drawing')

        return organized_records

    # Directional elevation patterns
    DIRECTIONAL_PATTERNS = [
        r'((?:NORTH|SOUTH|EAST|WEST)\s*(?:EXTERIOR\s+)?ELEVATION[S]?)',
        r'((?:N|S|E|W)\.?\s*(?:EXTERIOR\s+)?ELEVATION[S]?)',
        r'((?:FRONT|REAR|LEFT|RIGHT|SIDE)\s+ELEVATION[S]?)',
        r'((?:NORTH|SOUTH|EAST|WEST)[-\s]+(?:FACING|SIDE)\s+ELEVATION[S]?)',
    ]

    def _build_bookmark_title_dict(self, bookmarks: list) -> Dict[str, str]:
        """
        Build a dictionary mapping sheet numbers to titles from PDF bookmarks.

        Bookmarks often have format "A101 - Title" or "C100 - LEGEND AND GENERAL NOTES".
        Page numbers in bookmarks can be wrong, so we extract by sheet number.

        Args:
            bookmarks: List of PDF bookmarks [(level, title, page_num), ...]

        Returns:
            Dict mapping sheet numbers (uppercase) to titles
        """
        title_dict = {}
        if not bookmarks:
            return title_dict

        # Patterns to extract sheet number and title from bookmark text
        bookmark_patterns = [
            r'^([A-Z]{1,2}\d{2,3}[A-Za-z]?)\s*[-–—:]\s*(.+)',      # A101 - Title, AD204 - Title
            r'^([A-Z]{1,2}\d+\.\d+[A-Za-z]?)\s*[-–—:]\s*(.+)',     # A2.1 - Title, A250.a - Title
            r'^([A-Z]{1,2}-?\d+)\s*[-–—:]\s*(.+)',                  # ST-1 - Title
        ]

        for level, bm_title, bm_page in bookmarks:
            bm_title = bm_title.strip()
            for pattern in bookmark_patterns:
                match = re.match(pattern, bm_title, re.IGNORECASE)
                if match:
                    sheet_num = match.group(1).upper()
                    title = match.group(2).strip()
                    # Store title (don't overwrite if already exists)
                    if sheet_num not in title_dict:
                        title_dict[sheet_num] = title
                    break

        return title_dict

    def _extract_sheet_info(self, text: str, page_num: int, bookmarks: list = None, bookmark_titles: Dict[str, str] = None) -> Dict:
        """
        Extract sheet number and title from page text.

        Priority:
        1. Extract sheet number from page text
        2. Look up title in bookmark_titles dict by sheet number (most reliable)
        3. Fall back to text patterns if no bookmark match
        4. Default title based on sheet number prefix

        Args:
            text: Page text content
            page_num: Page number (0-indexed)
            bookmarks: List of PDF bookmarks (kept for compatibility)
            bookmark_titles: Dict mapping sheet numbers to titles

        Returns:
            Dict with 'sheet_number' and 'sheet_title'
        """
        sheet_number = None
        sheet_title = None

        # Step 1: Extract sheet number from page text (A101, A2.1, S200, AD204, ST-1, etc.)
        sheet_patterns = [
            r'\b([A-Z]{1,2}\d{3}[A-Za-z]?)\b',      # A101, AD204, S201A
            r'\b([A-Z]{1,2}\d+\.\d+[A-Za-z]?)\b',   # A2.1, A250.a, S1.0
            r'\b([A-Z]{1,2}-\d+)\b',                 # ST-1, L-100
            r'\b([ASMEPCLGI]\d{2,3})\b',             # A01, S100, I200
        ]

        for pattern in sheet_patterns:
            match = re.search(pattern, text)
            if match:
                sheet_number = match.group(1).upper()
                break

        # Fallback if no sheet number found
        if not sheet_number:
            sheet_number = f"Sheet-{page_num + 1:03d}"

        # Step 2: Look up title from bookmark_titles dictionary by sheet number
        if bookmark_titles and sheet_number in bookmark_titles:
            title = bookmark_titles[sheet_number]
            sheet_title = title.title() if title.isupper() else title
            if len(sheet_title) > 50:
                sheet_title = sheet_title[:47] + '...'
            return {
                'sheet_number': sheet_number,
                'sheet_title': sheet_title,
                'source': 'bookmark'
            }

        # Step 3: Check for directional elevation titles (most specific pattern match)
        text_upper = text.upper()
        for pattern in self.DIRECTIONAL_PATTERNS:
            match = re.search(pattern, text_upper)
            if match:
                title = match.group(1)
                sheet_title = re.sub(r'\s+', ' ', title).strip().title()
                return {
                    'sheet_number': sheet_number,
                    'sheet_title': sheet_title,
                    'source': 'directional_pattern'
                }

        # Extract title from common patterns
        title_patterns = [
            r'SHEET\s+TITLE[:\s]+([A-Z][A-Z\s&]+)',
            r'(EXTERIOR\s+ELEVATION[S]?)',
            r'(BUILDING\s+ELEVATION[S]?)',
            r'(FLOOR\s+PLAN[S]?)',
            r'(FIRST\s+FLOOR\s+PLAN|SECOND\s+FLOOR\s+PLAN|GROUND\s+FLOOR\s+PLAN)',
            r'(BASEMENT\s+(?:FLOOR\s+)?PLAN)',
            r'(REFLECTED\s+CEILING\s+PLAN|RCP)',
            r'(DOOR\s+SCHEDULE|WINDOW\s+SCHEDULE)',
            r'(STOREFRONT\s+(?:SCHEDULE|TYPES?|DETAILS?))',
            r'(CURTAIN\s*WALL\s+(?:SCHEDULE|TYPES?|DETAILS?))',
            r'(SITE\s+PLAN|ROOF\s+PLAN|FOUNDATION\s+PLAN)',
            r'(SECTION[S]?\s+[A-Z0-9\-]+)',
            r'(DETAIL[S]?\s+SHEET)',
            r'(WALL\s+SECTION[S]?)',
        ]

        for pattern in title_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                title = match.group(1)
                sheet_title = re.sub(r'\s+', ' ', title).strip().title()
                if len(sheet_title) > 50:
                    sheet_title = sheet_title[:47] + '...'
                break

        # Priority 3: Default title based on sheet number prefix
        if not sheet_title:
            if sheet_number.startswith('A0'):
                sheet_title = 'General'
            elif sheet_number.startswith('A1'):
                sheet_title = 'Floor Plan'
            elif sheet_number.startswith('A2'):
                sheet_title = 'Elevations'
            elif sheet_number.startswith('A3'):
                sheet_title = 'Sections'
            elif sheet_number.startswith('A4'):
                sheet_title = 'Details'
            elif sheet_number.startswith('A5'):
                sheet_title = 'Details'
            elif sheet_number.startswith('A6'):
                sheet_title = 'Schedules'
            elif sheet_number.startswith('A7'):
                sheet_title = 'Finish Schedule'
            elif sheet_number.startswith('A8'):
                sheet_title = 'Door-Window Schedule'
            elif sheet_number.startswith('A9'):
                sheet_title = 'Reflected Ceiling Plan'
            elif sheet_number.startswith('S'):
                sheet_title = 'Structural'
            elif sheet_number.startswith('M'):
                sheet_title = 'Mechanical'
            elif sheet_number.startswith('E'):
                sheet_title = 'Electrical'
            elif sheet_number.startswith('P'):
                sheet_title = 'Plumbing'
            elif sheet_number.startswith('L'):
                sheet_title = 'Landscape'
            elif sheet_number.startswith('C'):
                sheet_title = 'Civil'
            elif sheet_number.startswith('G'):
                sheet_title = 'General'
            else:
                sheet_title = 'Drawing'

        return {
            'sheet_number': sheet_number,
            'sheet_title': sheet_title,
            'source': 'text_pattern' if sheet_title != 'Drawing' else 'fallback'
        }

    def _create_sheet_filename(self, sheet_info: Dict) -> str:
        """
        Create clean filename for a sheet.

        Args:
            sheet_info: Dict with 'sheet_number' and 'sheet_title'

        Returns:
            Filename like "A101 - Floor Plan.pdf"
        """
        sheet_number = sheet_info['sheet_number']
        sheet_title = sheet_info['sheet_title']

        # Clean title for filename (remove invalid chars)
        clean_title = re.sub(r'[<>:"/\\|?*]', '', sheet_title)
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()

        filename = f"{sheet_number} - {clean_title}.pdf"

        return filename

    def get_organized_files(self) -> List[Dict]:
        """Get list of all organized files"""
        return self.organized_files

    def get_organized_files_by_type(self, doc_type: str) -> List[Dict]:
        """Get organized files filtered by document type"""
        return [f for f in self.organized_files if f['doc_type'] == doc_type]


def organize_project_files(project_folder: str, documents: List[Dict]) -> Dict:
    """
    Organize all project files into structured folders.

    Args:
        project_folder: Path to project folder
        documents: List of document info dicts from phase_identify

    Returns:
        Dict with organization summary
    """
    organizer = FileOrganizer(Path(project_folder))

    all_records = []
    stats = {
        'specs': 0,
        'drawings': 0,
        'schedules': 0,
        'addenda': 0,
        'consolidated': 0,
        'total_sheets': 0
    }

    for doc_info in documents:
        records = organizer.organize_document(doc_info)
        all_records.extend(records)

        doc_type = doc_info.get('doc_type', 'unknown')
        if doc_type == 'spec':
            stats['specs'] += 1
        elif doc_type == 'drawing':
            stats['drawings'] += 1
            stats['total_sheets'] += len(records)
        elif doc_type == 'consolidated':
            stats['consolidated'] += 1
            # Consolidated docs produce both spec copies and drawing sheets
            drawing_records = [r for r in records if r.get('doc_type') == 'drawing']
            stats['total_sheets'] += len(drawing_records)
        elif doc_type == 'schedule':
            stats['schedules'] += 1
        elif doc_type == 'addendum':
            stats['addenda'] += 1

    return {
        'organized_files': all_records,
        'stats': stats,
        'organized_root': str(organizer.organized_root)
    }
