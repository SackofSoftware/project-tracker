"""
Scope Takeoff Pipeline - Multi-phase Division 8 quantity extraction

This replaces "Full AI Parse" with a structured 5-phase workflow:

Phase 1: IDENTIFY - Document recognition (specs vs drawings by resolution)
Phase 2: PARSE - Extract Division 8 sections from spec book
Phase 3: EXTRACT - Parse door/window schedules into structured data
Phase 4: QUANTIFY - Count type tags on elevation drawings
Phase 5: VERIFY - Generate highlight lists for visual verification

IMPORTANT: Every project is different! This module uses flexible pattern matching
with fallbacks and learns from project context. No hard-coded assumptions.

Flexible patterns handle:
- Various sheet numbering: A600, A6.1, AD610, 501, etc.
- Various type markers: A, W1, WIN-A, Type 1, T-1, etc.
- Various door marks: 100, D1, 01, A.01, etc.
- Various CSI formats: 08 41 13, 084113, Section 08, etc.

Usage:
    takeoff = ScopeTakeoff(project_folder)
    result = await takeoff.run()
"""

import os
import re
import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple, Set
from datetime import datetime
from dataclasses import dataclass, asdict, field
from collections import Counter

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

# Import file organizer and database
from .file_organizer import organize_project_files
from modules.database import save_organized_file, get_or_create_project


# LLM Configuration - uses Grok 4.1 Fast via OpenRouter
LLM_MODEL = "x-ai/grok-4.1-fast"
LLM_FALLBACK = "amazon/nova-lite-v1"  # Fallback if Grok unavailable


class LLMClient:
    """OpenRouter LLM client for flexible document parsing"""

    def __init__(self, model: str = LLM_MODEL):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    def available(self) -> bool:
        return bool(self.api_key)

    def query(self, prompt: str, system: str = None, max_tokens: int = 4000) -> Optional[str]:
        """Send a query to the LLM and get response"""
        if not self.available():
            return None

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://project-tracker.local",
                    "X-Title": "Project Tracker Scope Takeoff"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.1  # Low temp for structured extraction
                },
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                print(f"LLM API error: {response.status_code}")
                return None

        except Exception as e:
            print(f"LLM query failed: {e}")
            return None

    def extract_json(self, prompt: str, system: str = None) -> Optional[Dict]:
        """Query LLM and parse JSON response"""
        response = self.query(prompt, system)
        if not response:
            return None

        # Try to extract JSON from response
        try:
            # Look for JSON in code blocks
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
            if json_match:
                return json.loads(json_match.group(1))

            # Try parsing entire response as JSON
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON-like structure
            try:
                start = response.find('{')
                end = response.rfind('}') + 1
                if start >= 0 and end > start:
                    return json.loads(response[start:end])
            except:
                pass
        return None


# Phase definitions
TAKEOFF_PHASES = {
    'identify': 'Document Recognition & Organization',
    'parse': 'Spec Analysis',
    'extract': 'Schedule Extraction',
    'quantify': 'Drawing Takeoff',
    'verify': 'Visual Verification'
}


@dataclass
class DocumentInfo:
    """Information about a detected document"""
    path: str
    filename: str
    doc_type: str  # 'spec', 'drawing', 'schedule', 'addendum', 'unknown'
    page_count: int = 0
    avg_dpi: float = 0.0
    has_text_layer: bool = True
    detected_sheets: List[str] = field(default_factory=list)


@dataclass
class ScheduleEntry:
    """Parsed schedule entry (door or window)"""
    mark: str
    entry_type: str  # Door type, window type
    material: str = ''
    width: str = ''
    height: str = ''
    hardware: str = ''
    glazing: str = ''
    notes: str = ''
    source_page: int = 0


@dataclass
class TypeCount:
    """Count of a type tag on drawings"""
    type_tag: str
    count: int
    pages_found: List[int] = field(default_factory=list)
    locations: List[Tuple[int, float, float]] = field(default_factory=list)  # (page, x, y)


@dataclass
class PageInfo:
    """Information about a drawing page"""
    page_num: int  # 1-indexed page number in original PDF
    sheet_id: str  # e.g., "A2.1", "A200"
    title: str  # e.g., "Exterior Elevations"
    page_type: str  # 'exterior_elevation', 'floor_plan', 'reflected_ceiling', 'door_schedule', etc.
    output_file: Optional[str] = None  # Path to extracted/highlighted PDF
    directional_info: Optional[str] = None  # N, S, E, W for elevations
    schedule_types: List[str] = field(default_factory=list)  # Types of schedules on this page
    is_excluded: bool = False  # True for RCP and other excluded page types


@dataclass
class TakeoffResult:
    """Complete takeoff result"""
    success: bool
    project_folder: str
    timestamp: str

    # Phase 1: Document identification
    documents: List[DocumentInfo] = field(default_factory=list)
    spec_file: Optional[str] = None
    drawing_file: Optional[str] = None

    # File organization (after Phase 1)
    organized_files: List[Dict] = field(default_factory=list)
    organization_stats: Dict = field(default_factory=dict)

    # Phase 2: Spec analysis
    division_8_sections: List[Dict] = field(default_factory=list)
    products_expected: List[str] = field(default_factory=list)

    # Phase 3: Schedule extraction
    door_schedule: List[ScheduleEntry] = field(default_factory=list)
    window_schedule: List[ScheduleEntry] = field(default_factory=list)
    storefront_schedule: List[ScheduleEntry] = field(default_factory=list)
    curtain_wall_schedule: List[ScheduleEntry] = field(default_factory=list)
    hardware_schedule: List[ScheduleEntry] = field(default_factory=list)
    glazing_schedule: List[ScheduleEntry] = field(default_factory=list)
    door_types: List[str] = field(default_factory=list)
    window_types: List[str] = field(default_factory=list)
    storefront_types: List[str] = field(default_factory=list)
    curtain_wall_types: List[str] = field(default_factory=list)

    # Phase 4: Drawing takeoff
    type_counts: List[TypeCount] = field(default_factory=list)
    elevation_pages: List[int] = field(default_factory=list)
    floor_plan_pages: List[int] = field(default_factory=list)
    schedule_pages: List[int] = field(default_factory=list)
    page_info: List[PageInfo] = field(default_factory=list)  # Detailed info about each page
    excluded_pages: List[PageInfo] = field(default_factory=list)  # RCP and other excluded pages

    # Phase 5: Highlight list
    highlight_list: List[Dict] = field(default_factory=list)
    highlighted_pdf: Optional[str] = None  # Legacy - single combined PDF
    highlighted_pages: List[str] = field(default_factory=list)  # Individual page PDFs

    errors: List[str] = field(default_factory=list)


class ScopeTakeoff:
    """
    Multi-phase scope takeoff for Division 8 projects.

    Workflow:
    1. Identify documents by type (spec vs drawing by image resolution)
    2. Parse spec Division 8 sections
    3. Extract door/window schedules
    4. Count type tags on elevations
    5. Generate highlight list for verification
    """

    # RCP (Reflected Ceiling Plan) exclusion patterns - these pages are NOT counted for openings
    RCP_EXCLUSION_PATTERNS = [
        r'REFLECTED\s+CEILING\s*(?:PLAN)?',
        r'\bRCP\b',
        r'CEILING\s+PLAN',
        r'\bR\.?C\.?P\.?\b',
        r'REFLECTED\s+CLG',
    ]

    # Storefront patterns for schedule detection
    STOREFRONT_PATTERNS = [
        r'STOREFRONT',
        r'STORE\s*FRONT',
        r'SF[-\s]?\d+',
        r'ALUMINUM[-\s]?FRAMED\s+ENTRANCE',
        r'ENTRANCE\s+(?:SYSTEM|DOOR)',
        r'STF[-\s]?\d+',
    ]

    # Curtain wall patterns for schedule detection
    CURTAIN_WALL_PATTERNS = [
        r'CURTAIN\s*WALL',
        r'CW[-\s]?\d+',
        r'UNITIZED\s+(?:WALL|SYSTEM)',
        r'GLAZED\s+(?:ALUMINUM\s+)?CURTAIN',
        r'CURTAINWALL',
    ]

    # Schedule detection patterns by type
    SCHEDULE_PATTERNS = {
        'door': [r'DOOR\s+SCHEDULE', r'DOOR\s+AND\s+FRAME\s+SCHEDULE', r'DOOR\s+TYPE'],
        'window': [r'WINDOW\s+SCHEDULE', r'WINDOW\s+TYPE', r'WINDOW\s+DETAIL'],
        'storefront': [r'STOREFRONT\s+SCHEDULE', r'SF\s+SCHEDULE', r'ENTRANCE\s+SCHEDULE', r'STOREFRONT\s+TYPE'],
        'curtain_wall': [r'CURTAIN\s*WALL\s+SCHEDULE', r'CW\s+SCHEDULE', r'CURTAIN\s*WALL\s+TYPE'],
        'hardware': [r'HARDWARE\s+SCHEDULE', r'DOOR\s+HARDWARE', r'HARDWARE\s+SET'],
        'glazing': [r'GLAZING\s+SCHEDULE', r'GLASS\s+(?:TYPE\s+)?SCHEDULE', r'GLAZING\s+TYPE'],
        'frame': [r'FRAME\s+SCHEDULE', r'FRAME\s+TYPE'],
    }

    # Directional patterns for elevation classification
    DIRECTIONAL_PATTERNS = [
        (r'(?:NORTH|N\.?)\s*(?:EXTERIOR\s+)?ELEVATION', 'N'),
        (r'(?:SOUTH|S\.?)\s*(?:EXTERIOR\s+)?ELEVATION', 'S'),
        (r'(?:EAST|E\.?)\s*(?:EXTERIOR\s+)?ELEVATION', 'E'),
        (r'(?:WEST|W\.?)\s*(?:EXTERIOR\s+)?ELEVATION', 'W'),
        (r'(?:FRONT)\s+ELEVATION', 'FRONT'),
        (r'(?:REAR|BACK)\s+ELEVATION', 'REAR'),
        (r'(?:LEFT|RIGHT|SIDE)\s+ELEVATION', 'SIDE'),
    ]

    def __init__(self, project_folder: str, stream_callback: Optional[Callable] = None, use_llm: bool = True):
        self.project_folder = Path(project_folder)
        self.stream_callback = stream_callback
        self.use_llm = use_llm
        self.llm = LLMClient() if use_llm else None
        self.result = TakeoffResult(
            success=False,
            project_folder=str(project_folder),
            timestamp=datetime.now().isoformat()
        )

    def stream(self, phase: str, message: str, progress: float = 0.0, data: Dict = None):
        """Send progress update"""
        if self.stream_callback:
            self.stream_callback({
                'phase': phase,
                'phase_name': TAKEOFF_PHASES.get(phase, phase),
                'message': message,
                'progress': progress,
                'data': data
            })

    def _build_bookmark_title_dict(self, bookmarks: list) -> dict:
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

    def _is_reflected_ceiling_plan(self, text: str, sheet_id: str = "", title: str = "") -> bool:
        """
        Check if a page is a Reflected Ceiling Plan (should be excluded from takeoff).

        Args:
            text: Page text content
            sheet_id: Sheet number if known
            title: Sheet title if known (from bookmarks or title block)

        Returns:
            True if page is RCP and should be excluded
        """
        # A9xx sheets are typically RCP in architectural drawings
        if sheet_id and re.match(r'A9[0-9]{2}', sheet_id.upper()):
            return True

        # Check if title explicitly indicates RCP
        if title:
            title_upper = title.upper()
            for pattern in self.RCP_EXCLUSION_PATTERNS:
                if re.search(pattern, title_upper):
                    return True

        # Only check page text if it appears in the title block area (first ~500 chars)
        # This avoids matching RCP mentioned in legends or notes
        title_block_text = text[:500].upper() if text else ""

        # Must have RCP indicator prominently (not just mentioned somewhere)
        # Look for it at start of line or as sheet title pattern
        rcp_title_patterns = [
            r'^REFLECTED\s+CEILING',  # At start of line
            r'SHEET\s+TITLE[:\s]+REFLECTED\s+CEILING',  # In title block
            r'\bRCP\s*[-–—:]\s',  # RCP as title prefix
        ]

        for pattern in rcp_title_patterns:
            if re.search(pattern, title_block_text, re.MULTILINE):
                return True

        return False

    def _get_directional_info(self, text: str) -> Optional[str]:
        """
        Extract directional info (N, S, E, W) from elevation title.

        Args:
            text: Page text content

        Returns:
            Direction code ('N', 'S', 'E', 'W', 'FRONT', 'REAR', 'SIDE') or None
        """
        text_upper = text.upper()
        for pattern, direction in self.DIRECTIONAL_PATTERNS:
            if re.search(pattern, text_upper):
                return direction
        return None

    def _classify_schedule_page(self, text: str) -> List[str]:
        """
        Classify what types of schedules are on a page.

        Args:
            text: Page text content

        Returns:
            List of schedule types found (e.g., ['door', 'hardware'])
        """
        text_upper = text.upper()
        found_types = []

        for stype, patterns in self.SCHEDULE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_upper):
                    found_types.append(stype)
                    break  # Only count each type once per page

        return found_types

    def _has_storefront_content(self, text: str) -> bool:
        """Check if page contains storefront-related content."""
        text_upper = text.upper()
        for pattern in self.STOREFRONT_PATTERNS:
            if re.search(pattern, text_upper):
                return True
        return False

    def _has_curtain_wall_content(self, text: str) -> bool:
        """Check if page contains curtain wall-related content."""
        text_upper = text.upper()
        for pattern in self.CURTAIN_WALL_PATTERNS:
            if re.search(pattern, text_upper):
                return True
        return False

    # ==================== PHASE 1: IDENTIFY ====================

    def phase_identify(self) -> None:
        """
        Phase 1: Identify documents by type.

        Uses image resolution to distinguish:
        - Specs: Low resolution, high text density
        - Drawings: High resolution (100+ DPI), low text density
        """
        self.stream('identify', 'Scanning project folder...', 0.1)

        # Get all PDFs, but exclude Extracted-Data folder (contains organized files from previous runs)
        pdf_files = [
            p for p in self.project_folder.rglob('*.pdf')
            if 'Extracted-Data' not in str(p) and 'extracted-data' not in str(p).lower()
        ]

        for i, pdf_path in enumerate(pdf_files):
            progress = 0.1 + (0.8 * i / max(len(pdf_files), 1))

            # Skip empty files
            try:
                if pdf_path.stat().st_size == 0:
                    self.result.errors.append(f"Skipping empty file: {pdf_path.name}")
                    continue
            except OSError:
                continue

            self.stream('identify', f'Analyzing: {pdf_path.name}', progress)

            doc_info = self._analyze_document(pdf_path)
            if not doc_info:
                continue  # Skip if analysis failed

            self.result.documents.append(doc_info)

            # Track spec and drawing files
            # 'consolidated' type serves as BOTH spec and drawing source
            if doc_info.doc_type == 'spec' and not self.result.spec_file:
                self.result.spec_file = str(pdf_path)
            elif doc_info.doc_type == 'consolidated':
                # Consolidated PDFs are used for BOTH spec extraction and drawing analysis
                if not self.result.spec_file:
                    self.result.spec_file = str(pdf_path)
                if not self.result.drawing_file:
                    self.result.drawing_file = str(pdf_path)
                self.stream('identify', f'Found consolidated PDF (specs + drawings): {pdf_path.name}', progress)
            elif doc_info.doc_type == 'drawing' and not self.result.drawing_file:
                self.result.drawing_file = str(pdf_path)

        # Summary of document types found
        doc_types = [d.doc_type for d in self.result.documents]
        type_summary = {t: doc_types.count(t) for t in set(doc_types)}

        self.stream('identify', f'Found {len(self.result.documents)} documents', 0.9, {
            'spec_file': self.result.spec_file,
            'drawing_file': self.result.drawing_file,
            'document_types': type_summary
        })

        # Organize files into folders
        self._organize_files()

        self.stream('identify', 'Document identification and organization complete', 1.0)

    def _analyze_document(self, pdf_path: Path) -> Optional[DocumentInfo]:
        """
        Analyze a PDF to determine its type.

        For consolidated PDFs (specs + drawings mixed), this will:
        1. Check PDF bookmarks for discipline/division structure
        2. Scan across the document for spec content (CSI sections, Division text)
        3. Identify pages with high text density as potential spec pages
        4. Mark consolidated PDFs as 'consolidated' type for special handling
        """
        doc_info = DocumentInfo(
            path=str(pdf_path),
            filename=pdf_path.name,
            doc_type='unknown'
        )

        if not PYMUPDF_AVAILABLE:
            # Fallback: guess from filename
            name_lower = pdf_path.name.lower()
            if 'spec' in name_lower or 'manual' in name_lower:
                doc_info.doc_type = 'spec'
            elif 'plan' in name_lower or 'drawing' in name_lower:
                doc_info.doc_type = 'drawing'
            elif 'addend' in name_lower:
                doc_info.doc_type = 'addendum'
            return doc_info

        try:
            with fitz.open(pdf_path) as doc:
                # Check for bookmarks - consolidated docs often have bookmark structure
                bookmarks = doc.get_toc()
                has_bookmarks = len(bookmarks) > 0

                # Analyze bookmark structure for discipline hints
                bookmark_hints = {'spec': False, 'drawing': False, 'divisions': []}
                if has_bookmarks:
                    for level, title, page in bookmarks[:50]:  # Check first 50 bookmarks
                        title_upper = title.upper()
                        # Look for spec indicators
                        if re.search(r'DIVISION\s*\d{2}|SPECIFICATION|SECTION\s*\d{2}', title_upper):
                            bookmark_hints['spec'] = True
                            # Extract division numbers
                            div_match = re.search(r'(?:DIVISION|DIV)\s*(\d{2})', title_upper)
                            if div_match:
                                bookmark_hints['divisions'].append(div_match.group(1))
                        # Look for drawing indicators
                        if re.search(r'DRAWING|ARCHITECTURAL|STRUCTURAL|ELECTRICAL|MECHANICAL|CIVIL', title_upper):
                            bookmark_hints['drawing'] = True
                        # Check for sheet numbers in bookmarks
                        if re.search(r'^[ASMEPCLG]\d{3}|^[ASMEPCLG]\d\.\d', title_upper):
                            bookmark_hints['drawing'] = True
                doc_info.page_count = doc.page_count

                # For larger documents, sample more pages distributed throughout
                if doc.page_count > 50:
                    # Sample pages at intervals: start, 25%, 50%, 75%, end
                    sample_indices = [0, 1, 2,  # First few pages
                                     doc.page_count // 4,
                                     doc.page_count // 2,
                                     3 * doc.page_count // 4,
                                     doc.page_count - 1]
                    sample_indices = [i for i in sample_indices if i < doc.page_count]
                else:
                    sample_indices = list(range(min(10, doc.page_count)))

                total_dpi = 0
                total_images = 0
                text_chars = 0
                detected_sheets = []

                # Spec content indicators
                spec_indicators = 0
                drawing_indicators = 0
                div8_pages = []  # Pages containing Division 8 content

                for page_num in sample_indices:
                    page = doc[page_num]

                    # Get text content
                    text = page.get_text()
                    text_chars += len(text)

                    # Check for sheet numbers (Axx, Sxx, etc.) - drawing indicator
                    sheet_matches = re.findall(r'\b([ASMEPCLG]\d{3}[A-Z]?)\b', text)
                    detected_sheets.extend(sheet_matches)
                    if sheet_matches:
                        drawing_indicators += 1

                    # Check for SPEC content indicators (must be specific to avoid matching drawing content)
                    spec_patterns = [
                        r'SECTION\s+0[1-9]\s*\d{2}\s*\d{2}',  # SECTION 08 41 13 (CSI format, divisions 01-09)
                        r'SECTION\s+[1-4]\d\s*\d{2}\s*\d{2}',  # SECTION 14 XX XX (CSI divisions 10-49)
                        r'DIVISION\s+0?[1-9]\s*[-–—:]',  # DIVISION 8 - (with separator)
                        r'PART\s+[123]\s*[-–—]\s*(?:GENERAL|PRODUCTS|EXECUTION)',  # PART 1 - GENERAL (spec format)
                        r'CSI\s+MASTERFORMAT',  # CSI MasterFormat reference
                        r'(?:^|\n)\s*1\.\d{2}\s+[A-Z]',  # Spec numbering like 1.01 SUMMARY
                        r'(?:^|\n)\s*2\.\d{2}\s+[A-Z]',  # Spec numbering like 2.01 MANUFACTURERS
                        r'(?:^|\n)\s*3\.\d{2}\s+[A-Z]',  # Spec numbering like 3.01 EXAMINATION
                        r'RELATED\s+(?:DOCUMENTS|SECTIONS|REQUIREMENTS)',  # Spec cross-reference
                        r'PROJECT\s+MANUAL',  # Project manual indicator
                        r'SPECIFICATIONS?\s+(?:INDEX|BOOK|VOLUME)',  # Spec index/book
                        r'END\s+OF\s+SECTION',  # End of spec section marker
                    ]

                    for pattern in spec_patterns:
                        if re.search(pattern, text, re.IGNORECASE):
                            spec_indicators += 1
                            break  # Only count once per page

                    # Check specifically for Division 8 content (stricter patterns)
                    div8_patterns = [
                        r'SECTION\s+08\s*\d{2}\s*\d{2}',  # SECTION 08 XX XX (requires SECTION prefix)
                        r'DIVISION\s*0?8\s*[-–—:]?\s*OPENINGS',  # DIVISION 8 - OPENINGS
                        r'08\s*\d{2}\s*\d{2}\s*[-–—:]\s*[A-Z]',  # 08 XX XX - Title (with separator + title)
                    ]

                    for pattern in div8_patterns:
                        if re.search(pattern, text, re.IGNORECASE):
                            div8_pages.append(page_num + 1)
                            break

                    # Get image info for DPI estimation
                    images = page.get_images()
                    for img in images[:3]:  # Check first 3 images per page
                        xref = img[0]
                        try:
                            base = doc.extract_image(xref)
                            if base:
                                img_width = base.get('width', 0)
                                page_width = page.rect.width
                                if page_width > 0 and img_width > 0:
                                    dpi = img_width / (page_width / 72)
                                    total_dpi += dpi
                                    total_images += 1
                        except:
                            pass

                doc_info.detected_sheets = list(set(detected_sheets))
                doc_info.has_text_layer = text_chars > 100

                if total_images > 0:
                    doc_info.avg_dpi = total_dpi / total_images

                # Enhanced classification logic
                # Include bookmark analysis in classification
                has_spec_content = spec_indicators >= 2 or bookmark_hints['spec']
                has_drawing_content = drawing_indicators >= 2 or doc_info.avg_dpi > 150 or bookmark_hints['drawing']
                has_div8_content = len(div8_pages) > 0 or '08' in bookmark_hints['divisions']

                # Check filename hints
                name_lower = pdf_path.name.lower()
                name_hints_spec = any(x in name_lower for x in ['spec', 'manual', 'project manual'])
                name_hints_drawing = any(x in name_lower for x in ['plan', 'drawing', 'sheet', 'arch', 'struct'])
                name_hints_addendum = 'addend' in name_lower
                name_hints_consolidated = 'consolidated' in name_lower or 'bid' in name_lower

                # Classification priority:
                # 1. Consolidated (has both spec and drawing content, OR filename indicates consolidated)
                # 2. Spec (has spec content or Division 8 content)
                # 3. Drawing (has sheets, high DPI)
                # 4. Addendum
                # 5. Unknown

                # Large files with bookmarks showing both spec and drawing content are consolidated
                if (has_spec_content and has_drawing_content) or (name_hints_consolidated and doc.page_count > 100):
                    doc_info.doc_type = 'consolidated'
                    if has_div8_content:
                        # Store div8 page hints for later extraction
                        doc_info.detected_sheets.extend([f'DIV8_P{p}' for p in div8_pages[:5]])
                    # Also store bookmark divisions found
                    if bookmark_hints['divisions']:
                        doc_info.detected_sheets.extend([f'DIV_{d}' for d in bookmark_hints['divisions'][:10]])
                elif has_spec_content or has_div8_content or name_hints_spec:
                    doc_info.doc_type = 'spec'
                elif has_drawing_content or name_hints_drawing:
                    doc_info.doc_type = 'drawing'
                elif name_hints_addendum:
                    doc_info.doc_type = 'addendum'
                elif len(detected_sheets) > 0:
                    doc_info.doc_type = 'drawing'

                # For large PDFs without clear indicators, do a deeper scan
                if doc_info.doc_type == 'unknown' and doc.page_count > 20:
                    doc_info.doc_type = self._deep_scan_for_spec_content(doc)

        except Exception as e:
            self.result.errors.append(f"Error analyzing {pdf_path.name}: {str(e)}")
            return None  # Return None for files that can't be opened

        return doc_info

    def _deep_scan_for_spec_content(self, doc) -> str:
        """
        Deep scan a large PDF for spec content when initial analysis is inconclusive.
        Scans every 10th page looking for Division 8 indicators.
        """
        div8_found = False
        spec_found = False

        for page_num in range(0, doc.page_count, 10):
            try:
                page = doc[page_num]
                text = page.get_text()[:3000]  # First 3000 chars per page

                # Look for Division 8 / CSI patterns (stricter - must have SECTION prefix or DIVISION context)
                if re.search(r'SECTION\s+08\s*\d{2}\s*\d{2}|DIVISION\s*0?8\s*[-–—:]?\s*OPENINGS', text, re.IGNORECASE):
                    div8_found = True

                # Look for spec format indicators
                if re.search(r'PART\s+[123]\s*[-–—]|SUBMITTALS|EXECUTION\s*\n|PRODUCTS\s*\n', text, re.IGNORECASE):
                    spec_found = True

                if div8_found and spec_found:
                    break

            except:
                continue

        if div8_found or spec_found:
            return 'consolidated'  # Likely a combined document
        return 'unknown'

    def _organize_files(self) -> None:
        """
        Organize identified documents into structured folders.

        Creates folder structure and splits PDFs as needed:
        - Specs: Copy as-is
        - Drawings: Split into individual sheets
        - Schedules: Copy as-is
        - Addenda: Copy as-is
        """
        if not self.result.documents:
            return

        self.stream('identify', 'Organizing files into folders...', 0.95)

        try:
            # Convert document dataclasses to dicts for file_organizer
            doc_dicts = [asdict(doc) for doc in self.result.documents]

            # Run file organization
            org_result = organize_project_files(
                str(self.project_folder),
                doc_dicts
            )

            # Store organized files in result
            self.result.organized_files = org_result.get('organized_files', [])
            self.result.organization_stats = org_result.get('stats', {})

            # Save to database
            project_id = self.project_folder.name

            # Ensure project exists in database
            get_or_create_project(
                project_id=project_id,
                folder_path=str(self.project_folder),
                title=project_id
            )

            # Save each organized file to database
            for file_record in self.result.organized_files:
                save_organized_file(
                    project_id=project_id,
                    original_path=file_record['original_path'],
                    organized_path=file_record['organized_path'],
                    doc_type=file_record['doc_type'],
                    sheet_number=file_record.get('sheet_number'),
                    sheet_title=file_record.get('sheet_title'),
                    page_number=file_record.get('page_number')
                )

            stats = self.result.organization_stats
            self.stream('identify', f'Organized {stats.get("total_sheets", 0)} drawing sheets, '
                                   f'{stats.get("specs", 0)} specs, '
                                   f'{stats.get("schedules", 0)} schedules',
                        0.98)

        except Exception as e:
            error_msg = f"Error organizing files: {str(e)}"
            self.result.errors.append(error_msg)
            print(error_msg)

    # ==================== PHASE 2: PARSE ====================

    def phase_parse(self) -> None:
        """
        Phase 2: Parse spec book for Division 8 sections.

        Uses LLM (Grok 4.1 Fast) for flexible extraction when regex fails.
        Extracts CSI section numbers and titles to know what products to expect.

        For consolidated PDFs, scans throughout the document looking for spec content.
        """
        if not self.result.spec_file:
            self.stream('parse', 'No spec file identified', 1.0)
            return

        self.stream('parse', 'Scanning for Division 8 specifications...', 0.1)

        spec_path = Path(self.result.spec_file)

        # Check if this is a consolidated PDF
        is_consolidated = any(
            d.doc_type == 'consolidated' and d.path == str(spec_path)
            for d in self.result.documents
        )

        if not PDFPLUMBER_AVAILABLE:
            self.result.errors.append("pdfplumber not available for spec parsing")
            return

        # For consolidated PDFs, first try bookmark-based extraction (faster)
        div8_bookmark_pages = []
        if is_consolidated and PYMUPDF_AVAILABLE:
            self.stream('parse', 'Checking PDF bookmarks for Division 8...', 0.12)
            try:
                with fitz.open(spec_path) as doc:
                    bookmarks = doc.get_toc()
                    if bookmarks:
                        for level, title, page in bookmarks:
                            title_upper = title.upper()
                            # Look for Division 8 / Openings in bookmarks (stricter matching)
                            if re.search(r'DIVISION\s*0?8|OPENINGS\s*[-–—:]|SECTION\s+08\s*\d{2}\s*\d{2}|08\s*\d{2}\s*\d{2}\s*[-–—:]', title_upper):
                                div8_bookmark_pages.append(page)
                                # Extract section info from bookmark title
                                section_match = re.search(r'(08\s*\d{2}\s*\d{2})', title_upper)
                                if section_match:
                                    section_id = section_match.group(1)
                                    # Get title after section number
                                    title_part = title_upper.split(section_id)[-1].strip(' -–—:')
                                    if title_part and len(title_part) > 2:
                                        section_data = {
                                            'section_id': section_id,
                                            'title': title_part.title()[:100],
                                            'page': page,
                                            'source': 'bookmark'
                                        }
                                        if not any(s['section_id'] == section_id for s in self.result.division_8_sections):
                                            self.result.division_8_sections.append(section_data)
                        if div8_bookmark_pages:
                            self.stream('parse', f'Found Division 8 content in bookmarks at pages: {div8_bookmark_pages[:5]}...', 0.18)
            except Exception as e:
                self.stream('parse', f'Bookmark extraction failed: {e}, falling back to text scan', 0.15)

        try:
            with pdfplumber.open(spec_path) as pdf:
                total_pages = len(pdf.pages)

                # For consolidated PDFs, scan more strategically
                if is_consolidated:
                    self.stream('parse', f'Consolidated PDF detected ({total_pages} pages) - scanning for spec content...', 0.15)
                    # If we found Division 8 pages from bookmarks, focus on those + nearby pages
                    if div8_bookmark_pages:
                        pages_to_scan = set()
                        for p in div8_bookmark_pages:
                            # Add the bookmark page and surrounding pages
                            for offset in range(-2, 20):  # 2 before, 20 after each bookmark
                                if 0 <= p + offset - 1 < total_pages:
                                    pages_to_scan.add(p + offset - 1)
                        # Also scan first 30 pages for TOC
                        pages_to_scan.update(range(min(30, total_pages)))
                        pages_to_scan = sorted(pages_to_scan)
                    else:
                        # No bookmarks found, scan all pages
                        pages_to_scan = range(total_pages)
                    scan_mode = 'full'
                else:
                    # Traditional spec book - focus on first 80 pages
                    pages_to_scan = range(min(80, total_pages))
                    scan_mode = 'front'

                # First pass: Find Table of Contents and Division 8 pages
                toc_text = ""
                div8_text = ""
                div8_page_numbers = []  # Track which pages have Division 8 content

                for page_num in pages_to_scan:
                    # Progress updates every 20 pages
                    if page_num % 20 == 0:
                        progress = 0.1 + (0.3 * page_num / max(len(pages_to_scan), 1))
                        self.stream('parse', f'Scanning page {page_num + 1} of {total_pages}...', progress)

                    try:
                        page = pdf.pages[page_num]
                        text = page.extract_text() or ""
                    except:
                        continue

                    # Collect TOC pages (usually first 10-30 pages)
                    if page_num < 30:
                        toc_text += f"\n--- Page {page_num + 1} ---\n" + text

                    # Look for Division 8 content (stricter patterns to avoid false matches from drawings)
                    div8_match = re.search(
                        r'(?:division|section)\s*0?8\s*[-–—:]|SECTION\s+08\s*\d{2}\s*\d{2}|08\s*\d{2}\s*\d{2}\s*[-–—:]\s*[A-Z]',
                        text, re.IGNORECASE
                    )

                    if div8_match:
                        div8_text += f"\n--- Page {page_num + 1} ---\n" + text
                        div8_page_numbers.append(page_num + 1)

                    # Regex patterns for various CSI formats
                    patterns = [
                        r'(?:SECTION\s+)?(08\s*\d{2}\s*\d{2})\s*[-–—:]\s*(.+?)(?:\n|$)',
                        r'(08\d{4})\s*[-–—:]\s*(.+?)(?:\n|$)',
                        r'Section\s+(08\s*\d{2}\s*\d{2})\s+(.+?)(?:\n|$)',
                        r'(08\s*\d{2}\s*\d{2})\s+([A-Z][A-Za-z\s]+?)(?:\n|$)',  # 08 XX XX Title
                    ]

                    for pattern in patterns:
                        sections = re.findall(pattern, text, re.IGNORECASE)
                        for section_num, title in sections:
                            normalized = re.sub(r'\s+', ' ', section_num).strip()
                            # Ensure it's a valid Division 8 section
                            if normalized.replace(' ', '').startswith('08'):
                                # Clean up title
                                clean_title = re.sub(r'\s+', ' ', title).strip()
                                # Skip if title looks like garbage
                                if len(clean_title) < 3 or clean_title.isdigit():
                                    continue

                                section_data = {
                                    'section_id': normalized,
                                    'title': clean_title[:100],
                                    'page': page_num + 1
                                }
                                if not any(s['section_id'] == normalized for s in self.result.division_8_sections):
                                    self.result.division_8_sections.append(section_data)

                # Log Division 8 pages found
                if div8_page_numbers:
                    self.stream('parse', f'Found Division 8 content on pages: {div8_page_numbers[:10]}{"..." if len(div8_page_numbers) > 10 else ""}', 0.45)

                # If regex found few/no sections, use LLM
                if len(self.result.division_8_sections) < 2 and self.llm and self.llm.available():
                    self.stream('parse', 'Using AI to find Division 8 sections...', 0.5)

                    # Use LLM to extract from TOC
                    llm_prompt = f"""Extract all Division 8 (Openings) specification sections from this construction spec book table of contents and content.

Division 8 sections typically include:
- Doors (08 1x xx)
- Windows (08 5x xx)
- Storefronts/Curtain Wall (08 4x xx)
- Hardware (08 7x xx)
- Glazing (08 8x xx)

Return JSON with this exact format:
{{
  "sections": [
    {{"section_id": "08 XX XX", "title": "Section Title"}},
    ...
  ],
  "products_expected": ["doors", "windows", "hardware", etc.]
}}

SPEC CONTENT:
{toc_text[:15000]}

{div8_text[:10000]}"""

                    llm_result = self.llm.extract_json(llm_prompt, system="You are a construction specification parser. Extract Division 8 CSI section numbers and titles. Return valid JSON only.")

                    if llm_result:
                        llm_sections = llm_result.get('sections', [])
                        for section in llm_sections:
                            section_id = section.get('section_id', '')
                            title = section.get('title', '')
                            if section_id and not any(s['section_id'] == section_id for s in self.result.division_8_sections):
                                self.result.division_8_sections.append({
                                    'section_id': section_id,
                                    'title': title,
                                    'page': 0,
                                    'source': 'llm'
                                })

                        # Also get products expected from LLM
                        llm_products = llm_result.get('products_expected', [])
                        self.result.products_expected.extend(llm_products)

        except Exception as e:
            self.result.errors.append(f"Error parsing spec: {str(e)}")

        # Derive products from section titles
        for section in self.result.division_8_sections:
            title_lower = section.get('title', '').lower()
            if 'door' in title_lower:
                self.result.products_expected.append('doors')
            if 'window' in title_lower:
                self.result.products_expected.append('windows')
            if 'storefront' in title_lower or 'curtain' in title_lower:
                self.result.products_expected.append('storefronts')
            if 'hardware' in title_lower:
                self.result.products_expected.append('hardware')
            if 'glazing' in title_lower or 'glass' in title_lower:
                self.result.products_expected.append('glazing')
            if 'coiling' in title_lower or 'overhead' in title_lower:
                self.result.products_expected.append('overhead_doors')

        self.result.products_expected = list(set(self.result.products_expected))

        self.stream('parse', f'Found {len(self.result.division_8_sections)} Division 8 sections', 1.0, {
            'sections': self.result.division_8_sections,
            'products': self.result.products_expected
        })

    # ==================== PHASE 3: EXTRACT ====================

    def phase_extract(self) -> None:
        """
        Phase 3: Extract door/window schedules from drawings.

        Looks for schedule pages (A6xx) and parses tabular data.
        Uses LLM (Grok 4.1 Fast) as fallback when regex parsing fails.
        """
        if not self.result.drawing_file:
            self.stream('extract', 'No drawing file identified', 1.0)
            return

        self.stream('extract', 'Finding schedule pages...', 0.1)

        drawing_path = Path(self.result.drawing_file)

        if not PYMUPDF_AVAILABLE:
            self.result.errors.append("PyMuPDF not available for schedule extraction")
            return

        try:
            with fitz.open(drawing_path) as doc:
                # Find door schedule pages (A600, A601)
                # Find window schedule pages (A610)
                schedule_pages = []
                schedule_texts = {}  # Store text for LLM fallback

                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    text = page.get_text()
                    text_upper = text.upper()

                    # Use SCHEDULE_PATTERNS for comprehensive detection
                    for stype, patterns in self.SCHEDULE_PATTERNS.items():
                        for pattern in patterns:
                            if re.search(pattern, text_upper):
                                schedule_pages.append((stype, page_num))
                                schedule_texts[(stype, page_num)] = text
                                break  # Only add once per type per page

                    # Additional detection for storefront and curtain wall content
                    if self._has_storefront_content(text):
                        if ('storefront', page_num) not in schedule_pages:
                            schedule_pages.append(('storefront', page_num))
                            schedule_texts[('storefront', page_num)] = text

                    if self._has_curtain_wall_content(text):
                        if ('curtain_wall', page_num) not in schedule_pages:
                            schedule_pages.append(('curtain_wall', page_num))
                            schedule_texts[('curtain_wall', page_num)] = text

                # Group by type for reporting
                schedule_type_counts = {}
                for stype, _ in schedule_pages:
                    schedule_type_counts[stype] = schedule_type_counts.get(stype, 0) + 1

                self.stream('extract', f'Found {len(schedule_pages)} schedule pages: {schedule_type_counts}', 0.3)

                # Parse schedules with regex first
                for sched_type, page_num in schedule_pages:
                    progress = 0.3 + (0.4 * schedule_pages.index((sched_type, page_num)) / max(len(schedule_pages), 1))
                    self.stream('extract', f'Parsing {sched_type} schedule on page {page_num + 1}...', progress)

                    text = schedule_texts.get((sched_type, page_num), '')

                    if sched_type == 'door':
                        self._parse_door_schedule(text, page_num)
                    elif sched_type == 'window':
                        self._parse_window_schedule(text, page_num)
                    elif sched_type == 'storefront':
                        self._parse_storefront_schedule(text, page_num)
                    elif sched_type == 'curtain_wall':
                        self._parse_curtain_wall_schedule(text, page_num)
                    elif sched_type == 'hardware':
                        self._parse_hardware_schedule(text, page_num)
                    elif sched_type == 'glazing':
                        self._parse_glazing_schedule(text, page_num)

                # LLM fallback if regex found few/no entries
                if (len(self.result.door_schedule) < 3 or len(self.result.window_schedule) < 2) and self.llm and self.llm.available():
                    self.stream('extract', 'Using AI to parse schedules...', 0.7)

                    # Combine schedule page texts for LLM
                    all_schedule_text = ""
                    for (sched_type, page_num), text in schedule_texts.items():
                        all_schedule_text += f"\n--- {sched_type.upper()} SCHEDULE (Page {page_num + 1}) ---\n"
                        all_schedule_text += text[:8000]  # Limit per schedule

                    if all_schedule_text:
                        llm_prompt = f"""Extract door and window schedule data from these architectural drawing pages.

For DOOR schedules, extract:
- Door mark/number (e.g., "100", "101A", "D1")
- Door type (e.g., "A", "AC-1", "F", "OHC")
- Material (e.g., "Aluminum Clad", "Fiberglass", "Wood", "Metal")
- Size if shown (e.g., "3'-0\" x 7'-0\"")

For WINDOW schedules/types, extract:
- Window type mark (e.g., "A", "B", "W1", "WIN-1")
- Description
- Size if shown

Return JSON with this exact format:
{{
  "door_schedule": [
    {{"mark": "100", "type": "A", "material": "Wood", "size": "3'-0\" x 7'-0\""}}
  ],
  "window_types": [
    {{"mark": "A", "description": "Fixed window", "size": "4'-0\" x 5'-0\""}}
  ],
  "door_types_found": ["A", "F", "OHC"],
  "window_types_found": ["A", "B", "C"]
}}

SCHEDULE TEXT:
{all_schedule_text[:20000]}"""

                        llm_result = self.llm.extract_json(
                            llm_prompt,
                            system="You are an architectural drawing parser. Extract door and window schedule data accurately. Return valid JSON only."
                        )

                        if llm_result:
                            # Add LLM-extracted doors
                            for door in llm_result.get('door_schedule', []):
                                entry = ScheduleEntry(
                                    mark=door.get('mark', ''),
                                    entry_type=door.get('type', ''),
                                    material=door.get('material', ''),
                                    width=door.get('size', ''),
                                    source_page=0
                                )
                                # Avoid duplicates
                                if not any(d.mark == entry.mark for d in self.result.door_schedule):
                                    self.result.door_schedule.append(entry)

                            # Add LLM-extracted windows
                            for window in llm_result.get('window_types', []):
                                entry = ScheduleEntry(
                                    mark=window.get('mark', ''),
                                    entry_type=window.get('mark', ''),
                                    notes=window.get('description', ''),
                                    width=window.get('size', ''),
                                    source_page=0
                                )
                                if not any(w.mark == entry.mark for w in self.result.window_schedule):
                                    self.result.window_schedule.append(entry)

                            # Update types lists
                            self.result.door_types.extend(llm_result.get('door_types_found', []))
                            self.result.window_types.extend(llm_result.get('window_types_found', []))

        except Exception as e:
            self.result.errors.append(f"Error extracting schedules: {str(e)}")

        # Extract unique types
        self.result.door_types = list(set(d.entry_type for d in self.result.door_schedule if d.entry_type))
        self.result.window_types = list(set(w.entry_type for w in self.result.window_schedule if w.entry_type))
        self.result.storefront_types = list(set(self.result.storefront_types))
        self.result.curtain_wall_types = list(set(self.result.curtain_wall_types))

        self.stream('extract', 'Schedule extraction complete', 1.0, {
            'door_count': len(self.result.door_schedule),
            'window_count': len(self.result.window_schedule),
            'storefront_count': len(self.result.storefront_schedule),
            'curtain_wall_count': len(self.result.curtain_wall_schedule),
            'hardware_count': len(self.result.hardware_schedule),
            'glazing_count': len(self.result.glazing_schedule),
            'door_types': self.result.door_types,
            'window_types': self.result.window_types,
            'storefront_types': self.result.storefront_types,
            'curtain_wall_types': self.result.curtain_wall_types
        })

    def _parse_door_schedule(self, text: str, page_num: int) -> None:
        """Parse door schedule text into structured entries"""
        # Look for door number patterns: 100, 101, 101A, etc.
        door_pattern = r'\b(\d{3}[A-Z]?)\b\s+(.+?)(?:\n|$)'

        lines = text.split('\n')
        for line in lines:
            # Look for lines that start with a 3-digit door number
            match = re.match(r'^\s*(\d{3}[A-Z]?)\s+(.+)', line)
            if match:
                door_num = match.group(1)
                rest = match.group(2)

                # Try to extract door type (AC-1, F, OHC, etc.)
                type_match = re.search(r'\b(AC-\d|[A-Z]{1,3}(?:-\d)?)\b', rest)
                door_type = type_match.group(1) if type_match else ''

                # Extract material
                material = ''
                if 'ALUM' in rest.upper():
                    material = 'Aluminum Clad'
                elif 'FIBERGLASS' in rest.upper():
                    material = 'Fiberglass'
                elif 'WOOD' in rest.upper():
                    material = 'Wood'

                entry = ScheduleEntry(
                    mark=door_num,
                    entry_type=door_type,
                    material=material,
                    source_page=page_num + 1
                )
                self.result.door_schedule.append(entry)

    def _parse_window_schedule(self, text: str, page_num: int) -> None:
        """Parse window schedule text into structured entries"""
        # Window types are often single letters (A, B, C) or with numbers (W1, W2)
        # Look for window type definitions

        # Pattern for window type rows
        lines = text.split('\n')
        for line in lines:
            # Look for window type markers
            match = re.match(r'^\s*([A-Z]|W\d+)\s+', line)
            if match:
                window_type = match.group(1)

                # Extract size info
                size_match = re.search(r"(\d+['\"]\s*-?\s*\d*['\"]?\s*[xX×]\s*\d+['\"]\s*-?\s*\d*['\"]?)", line)
                size = size_match.group(1) if size_match else ''

                entry = ScheduleEntry(
                    mark=window_type,
                    entry_type=window_type,
                    width=size,
                    source_page=page_num + 1
                )
                self.result.window_schedule.append(entry)

    def _parse_storefront_schedule(self, text: str, page_num: int) -> None:
        """Parse storefront schedule text into structured entries"""
        lines = text.split('\n')
        for line in lines:
            # Look for storefront type markers: SF-1, STF-1, SF1, etc.
            match = re.match(r'^\s*(SF[-\s]?\d+|STF[-\s]?\d+)\s+(.+)?', line, re.IGNORECASE)
            if match:
                sf_type = match.group(1).upper().replace(' ', '-')
                rest = match.group(2) or ''

                # Extract size info
                size_match = re.search(r"(\d+['\"]\s*-?\s*\d*['\"]?\s*[xX×]\s*\d+['\"]\s*-?\s*\d*['\"]?)", rest)
                size = size_match.group(1) if size_match else ''

                entry = ScheduleEntry(
                    mark=sf_type,
                    entry_type=sf_type,
                    width=size,
                    material='Aluminum',  # Storefronts are typically aluminum
                    source_page=page_num + 1
                )
                if not any(s.mark == sf_type for s in self.result.storefront_schedule):
                    self.result.storefront_schedule.append(entry)
                    self.result.storefront_types.append(sf_type)

    def _parse_curtain_wall_schedule(self, text: str, page_num: int) -> None:
        """Parse curtain wall schedule text into structured entries"""
        lines = text.split('\n')
        for line in lines:
            # Look for curtain wall type markers: CW-1, CW1, etc.
            match = re.match(r'^\s*(CW[-\s]?\d+)\s+(.+)?', line, re.IGNORECASE)
            if match:
                cw_type = match.group(1).upper().replace(' ', '-')
                rest = match.group(2) or ''

                # Extract size info
                size_match = re.search(r"(\d+['\"]\s*-?\s*\d*['\"]?\s*[xX×]\s*\d+['\"]\s*-?\s*\d*['\"]?)", rest)
                size = size_match.group(1) if size_match else ''

                entry = ScheduleEntry(
                    mark=cw_type,
                    entry_type=cw_type,
                    width=size,
                    material='Aluminum',
                    source_page=page_num + 1
                )
                if not any(c.mark == cw_type for c in self.result.curtain_wall_schedule):
                    self.result.curtain_wall_schedule.append(entry)
                    self.result.curtain_wall_types.append(cw_type)

    def _parse_hardware_schedule(self, text: str, page_num: int) -> None:
        """Parse hardware schedule text into structured entries"""
        lines = text.split('\n')
        for line in lines:
            # Look for hardware set markers: HW-1, HS-1, Set 1, etc.
            match = re.match(r'^\s*(HW[-\s]?\d+|HS[-\s]?\d+|SET\s*\d+)\s+(.+)?', line, re.IGNORECASE)
            if match:
                hw_set = match.group(1).upper().replace(' ', '-')
                rest = match.group(2) or ''

                entry = ScheduleEntry(
                    mark=hw_set,
                    entry_type='hardware_set',
                    hardware=rest[:100] if rest else '',
                    source_page=page_num + 1
                )
                if not any(h.mark == hw_set for h in self.result.hardware_schedule):
                    self.result.hardware_schedule.append(entry)

    def _parse_glazing_schedule(self, text: str, page_num: int) -> None:
        """Parse glazing schedule text into structured entries"""
        lines = text.split('\n')
        for line in lines:
            # Look for glazing type markers: GL-1, G1, Type 1, etc.
            match = re.match(r'^\s*(GL[-\s]?\d+|G[-\s]?\d+|TYPE\s*\d+)\s+(.+)?', line, re.IGNORECASE)
            if match:
                gl_type = match.group(1).upper().replace(' ', '-')
                rest = match.group(2) or ''

                entry = ScheduleEntry(
                    mark=gl_type,
                    entry_type='glazing',
                    glazing=rest[:100] if rest else '',
                    source_page=page_num + 1
                )
                if not any(g.mark == gl_type for g in self.result.glazing_schedule):
                    self.result.glazing_schedule.append(entry)

    # ==================== PHASE 4: QUANTIFY ====================

    def phase_quantify(self) -> None:
        """
        Phase 4: Count type tags on exterior elevations and floor plans ONLY.

        Searches:
        - Exterior elevation pages (A200, A201, A202, etc.)
        - Floor plan pages (A100, A101, A102, etc.)
        - Schedule pages (A6xx, A8xx) - tracked but not counted

        Excludes:
        - Reflected Ceiling Plans (A9xx, "REFLECTED CEILING", "RCP")

        Counts door/window type markers (A, B, C, W1, SF-1, CW-1, etc.)
        """
        if not self.result.drawing_file:
            self.stream('quantify', 'No drawing file identified', 1.0)
            return

        self.stream('quantify', 'Finding elevation and floor plan pages...', 0.1)

        drawing_path = Path(self.result.drawing_file)

        # Combine types to search for - use types from schedules if available
        search_types = set()

        # Add window types if we found them in schedules
        if self.result.window_types:
            search_types.update(self.result.window_types)
        else:
            # Default single letters for window types
            search_types.update(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'])

        # Add door types from schedule (but NOT door marks like 100, 101)
        for dt in self.result.door_types:
            # Only add short type codes, not door numbers
            if len(dt) <= 4 and not dt.isdigit():
                search_types.update([dt])

        # Add storefront types
        if self.result.storefront_types:
            search_types.update(self.result.storefront_types)
        else:
            # Common storefront type patterns
            search_types.update(['SF-1', 'SF-2', 'SF-3', 'STF-1', 'STF-2'])

        # Add curtain wall types
        if self.result.curtain_wall_types:
            search_types.update(self.result.curtain_wall_types)
        else:
            # Common curtain wall type patterns
            search_types.update(['CW-1', 'CW-2', 'CW-3'])

        if not PYMUPDF_AVAILABLE:
            self.result.errors.append("PyMuPDF not available for quantity takeoff")
            return

        type_counter = Counter()
        type_locations = {t: [] for t in search_types}

        try:
            with fitz.open(drawing_path) as doc:
                # Get bookmarks and build sheet_number -> title dictionary
                # This is more reliable than matching by page number (which can be wrong)
                bookmarks = doc.get_toc()
                bookmark_titles = self._build_bookmark_title_dict(bookmarks)

                # First pass: identify and classify all architectural pages
                for page_num in range(doc.page_count):
                    page = doc[page_num]
                    text = page.get_text()[:4000]  # Check first part of page

                    # Extract sheet ID first (expanded patterns for AD204, ST-1, etc.)
                    sheet_patterns = [
                        r'\b([A-Z]{1,2}\d{3}[A-Za-z]?)\b',      # A101, AD204, S201A
                        r'\b([A-Z]{1,2}\d+\.\d+[A-Za-z]?)\b',   # A2.1, A250.a, S1.0
                        r'\b([A-Z]{1,2}-\d+)\b',                 # ST-1, L-100
                        r'\b([ASMEPCLGI]\d{2,3})\b',             # A01, S100, I200
                    ]
                    sheet_id = ""
                    for pattern in sheet_patterns:
                        sheet_match = re.search(pattern, text)
                        if sheet_match:
                            sheet_id = sheet_match.group(1).upper()
                            break

                    # Get title from bookmark by sheet number (not page number - page numbers are often wrong)
                    bookmark_title = bookmark_titles.get(sheet_id, "")

                    # CHECK FOR RCP FIRST - exclusion takes priority (pass title for smarter detection)
                    if self._is_reflected_ceiling_plan(text, sheet_id, bookmark_title):
                        # Extract title for reference (prefer bookmark title)
                        if bookmark_title and 'CEILING' in bookmark_title.upper():
                            title = bookmark_title.title()
                        else:
                            title_match = re.search(r'(REFLECTED\s+CEILING\s*(?:PLAN)?|RCP)', text, re.IGNORECASE)
                            title = title_match.group(1).title() if title_match else "Reflected Ceiling Plan"
                        title = re.sub(r'\s+', ' ', title).strip()

                        excluded_page = PageInfo(
                            page_num=page_num + 1,
                            sheet_id=sheet_id if sheet_id else f"RCP-{page_num + 1}",
                            title=title,
                            page_type='reflected_ceiling',
                            is_excluded=True
                        )
                        self.result.excluded_pages.append(excluded_page)
                        self.stream('quantify', f'Excluding RCP: {sheet_id} - {title}', 0.15)
                        continue  # Skip to next page - do NOT count tags on RCP

                    # Check for schedule pages
                    schedule_types = self._classify_schedule_page(text)
                    if schedule_types:
                        self.result.schedule_pages.append(page_num + 1)
                        # Get title based on schedule types
                        schedule_title = ' & '.join([st.replace('_', ' ').title() for st in schedule_types[:2]]) + ' Schedule'

                        schedule_page = PageInfo(
                            page_num=page_num + 1,
                            sheet_id=sheet_id if sheet_id else f"Sched-{page_num + 1}",
                            title=schedule_title,
                            page_type='schedule',
                            schedule_types=schedule_types
                        )
                        self.result.page_info.append(schedule_page)
                        # Note: We still process schedule pages but track them separately

                    # Detect exterior elevations by:
                    # - Sheet number A2xx (A200, A201, A202, A2.0, A2.1)
                    # - OR title contains "EXTERIOR ELEVATION"
                    has_a2xx_sheet = bool(re.search(r'\bA2[0-9]{2}\b|\bA2\.[0-9]\b', text))
                    has_elevation_title = bool(re.search(r'EXTERIOR\s+ELEVATION', text, re.IGNORECASE))
                    is_ext_elevation = has_a2xx_sheet or has_elevation_title

                    # Detect floor plans by:
                    # - Sheet number A1xx (A100, A101, A102, A1.0, A1.1)
                    # - OR title contains floor plan indicators
                    has_a1xx_sheet = bool(re.search(r'\bA1[0-9]{2}\b|\bA1\.[0-9]\b', text))
                    has_plan_title = bool(re.search(
                        r'FLOOR\s+PLAN|LEVEL\s+\d|FIRST\s+FLOOR|SECOND\s+FLOOR|GROUND\s+FLOOR',
                        text, re.IGNORECASE
                    ))
                    is_floor_plan = (has_a1xx_sheet or has_plan_title) and not is_ext_elevation

                    page_type = None
                    title = ""
                    directional = None

                    if is_ext_elevation:
                        self.result.elevation_pages.append(page_num + 1)
                        page_type = 'exterior_elevation'
                        if not sheet_id:
                            sheet_id = f"Elev-{page_num + 1}"

                        # Get directional info (N, S, E, W)
                        directional = self._get_directional_info(text)

                        # Extract title with directional info
                        if directional:
                            title_match = re.search(
                                r'((?:NORTH|SOUTH|EAST|WEST|N|S|E|W)\.?\s*(?:EXTERIOR\s+)?ELEVATION[S]?)',
                                text, re.IGNORECASE
                            )
                            title = title_match.group(1).title() if title_match else f"{directional} Exterior Elevation"
                        else:
                            title_match = re.search(r'(EXTERIOR\s+ELEVATIONS?)', text, re.IGNORECASE)
                            title = title_match.group(1).title() if title_match else "Exterior Elevations"
                        title = re.sub(r'\s+', ' ', title).strip()

                    elif is_floor_plan:
                        self.result.floor_plan_pages.append(page_num + 1)
                        page_type = 'floor_plan'
                        if not sheet_id:
                            sheet_id = f"Plan-{page_num + 1}"
                        # Extract title
                        title_match = re.search(
                            r'((?:FIRST|SECOND|THIRD|GROUND|BASEMENT|LOWER|UPPER)?\s*(?:FLOOR|LEVEL)\s*(?:PLAN)?|\d(?:ST|ND|RD|TH)\s+FLOOR)',
                            text, re.IGNORECASE
                        )
                        title = title_match.group(1).strip().title() if title_match else "Floor Plan"
                        title = re.sub(r'\s+', ' ', title).strip()

                    if page_type and page_type in ['exterior_elevation', 'floor_plan']:
                        # Store page info
                        page_info = PageInfo(
                            page_num=page_num + 1,
                            sheet_id=sheet_id,
                            title=title,
                            page_type=page_type,
                            directional_info=directional
                        )
                        self.result.page_info.append(page_info)

                        progress = 0.2 + (0.7 * (len(self.result.elevation_pages) + len(self.result.floor_plan_pages)) / 10)
                        self.stream('quantify', f'Counting types on {sheet_id} - {title}...', progress)

                        # Search for type tags
                        words = page.get_text("words")
                        for word_data in words:
                            x0, y0, x1, y1, text_word, block, line, word_idx = word_data

                            # Check if this word is a type tag
                            text_upper = text_word.strip().upper()

                            if text_upper in search_types:
                                # Type tags are usually 1-4 chars, isolated
                                if len(text_word.strip()) <= 5:
                                    type_counter[text_upper] += 1
                                    type_locations[text_upper].append((page_num + 1, x0, y0))

                            # Also check for hyphenated types like SF-1, CW-2
                            if '-' in text_word:
                                parts = text_word.strip().upper().split('-')
                                if len(parts) == 2 and parts[0] in ['SF', 'CW', 'STF', 'W', 'D']:
                                    full_type = text_word.strip().upper()
                                    type_counter[full_type] += 1
                                    type_locations.setdefault(full_type, []).append((page_num + 1, x0, y0))

        except Exception as e:
            self.result.errors.append(f"Error in quantity takeoff: {str(e)}")

        # Build type counts
        for type_tag, count in type_counter.items():
            if count > 0:
                locations = type_locations.get(type_tag, [])
                pages = list(set(loc[0] for loc in locations))

                self.result.type_counts.append(TypeCount(
                    type_tag=type_tag,
                    count=count,
                    pages_found=pages,
                    locations=locations[:20]  # Limit stored locations
                ))

        # Sort by count
        self.result.type_counts.sort(key=lambda x: x.count, reverse=True)

        self.stream('quantify', 'Quantity takeoff complete', 1.0, {
            'elevation_pages': self.result.elevation_pages,
            'floor_plan_pages': self.result.floor_plan_pages,
            'schedule_pages': self.result.schedule_pages,
            'excluded_pages': len(self.result.excluded_pages),
            'types_found': len(self.result.type_counts),
            'total_tags': sum(tc.count for tc in self.result.type_counts)
        })

    # ==================== PHASE 5: VERIFY ====================

    # Unique colors for different type tags (RGB tuples)
    TYPE_COLORS = [
        (1.0, 0.4, 0.0),    # Orange
        (0.2, 0.6, 1.0),    # Blue
        (0.1, 0.8, 0.3),    # Green
        (1.0, 0.2, 0.6),    # Pink
        (0.8, 0.2, 0.8),    # Purple
        (0.0, 0.8, 0.8),    # Cyan
        (1.0, 0.8, 0.0),    # Gold
        (0.6, 0.4, 0.2),    # Brown
        (0.4, 0.8, 0.4),    # Light Green
        (1.0, 0.5, 0.5),    # Salmon
        (0.5, 0.5, 1.0),    # Periwinkle
        (0.8, 0.6, 0.0),    # Dark Gold
    ]

    def phase_verify(self) -> None:
        """
        Phase 5: Extract and highlight individual elevation/floor plan pages.

        For each detected page:
        1. Extract as individual PDF
        2. Apply type tag highlights
        3. Name like "A2.1 - Exterior Elevations.pdf"
        """
        self.stream('verify', 'Extracting highlighted pages...', 0.1)

        if not self.result.drawing_file or not PYMUPDF_AVAILABLE:
            self.stream('verify', 'Cannot generate highlights - no drawing file or PyMuPDF', 1.0)
            return

        if not self.result.page_info:
            self.stream('verify', 'No pages detected for extraction', 1.0)
            return

        # Create output folder for highlighted pages
        output_folder = self.project_folder / 'Extracted-Data' / 'Highlighted-Pages'
        output_folder.mkdir(parents=True, exist_ok=True)

        # Assign unique color to each type
        color_map = {}
        for i, type_count in enumerate(self.result.type_counts):
            color_idx = i % len(self.TYPE_COLORS)
            color_map[type_count.type_tag] = self.TYPE_COLORS[color_idx]

        # Build highlight entries with color info
        for type_count in self.result.type_counts:
            tag = type_count.type_tag
            rgb = color_map.get(tag, (1.0, 1.0, 0.0))

            self.result.highlight_list.append({
                'Term': tag,
                'Color': f'rgb({int(rgb[0]*255)},{int(rgb[1]*255)},{int(rgb[2]*255)})',
                'RGB': list(rgb),
                'Count': type_count.count,
                'Pages': type_count.pages_found
            })

        # Extract and highlight each page
        try:
            drawing_path = Path(self.result.drawing_file)

            with fitz.open(drawing_path) as doc:
                total_pages = len(self.result.page_info)

                for idx, page_info in enumerate(self.result.page_info):
                    page_num = page_info.page_num - 1  # Convert to 0-indexed
                    page = doc[page_num]

                    progress = 0.1 + (0.8 * (idx + 1) / total_pages)
                    self.stream('verify', f'Extracting {page_info.sheet_id} - {page_info.title}...', progress)

                    # Apply highlights to this page
                    highlight_count = 0
                    words = page.get_text("words")

                    for word_data in words:
                        x0, y0, x1, y1, text_word, block, line, word_idx = word_data
                        text_upper = text_word.strip().upper()

                        if text_upper in color_map:
                            rgb = color_map[text_upper]

                            # Create highlight rectangle with slight expansion
                            rect = fitz.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)

                            # Draw filled rectangle with transparency
                            shape = page.new_shape()
                            shape.draw_rect(rect)
                            shape.finish(
                                color=rgb,
                                fill=rgb,
                                fill_opacity=0.4,
                                stroke_opacity=0.8,
                                width=0.5
                            )
                            shape.commit()
                            highlight_count += 1

                    # Create clean filename: "A2.1 - Exterior Elevations (p24).pdf"
                    # Clean the title for filename (remove special chars and extra whitespace)
                    clean_title = re.sub(r'[<>:"/\\|?*\n\r]', '', page_info.title)
                    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                    # Include page number to avoid duplicates
                    filename = f"{page_info.sheet_id} - {clean_title} (p{page_info.page_num}).pdf"
                    output_path = output_folder / filename

                    # Extract this single page to a new PDF
                    new_doc = fitz.open()
                    new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    new_doc.save(str(output_path))
                    new_doc.close()

                    # Update page_info with output file path
                    page_info.output_file = str(output_path)
                    self.result.highlighted_pages.append(str(output_path))

                    self.stream('verify', f'Saved {filename} ({highlight_count} highlights)', progress)

        except Exception as e:
            self.result.errors.append(f"Error extracting highlighted pages: {str(e)}")

        # Save highlight list JSON
        highlight_file = output_folder.parent / 'highlight_list.json'
        with open(highlight_file, 'w') as f:
            json.dump(self.result.highlight_list, f, indent=2)

        # Save page info JSON
        page_info_file = output_folder.parent / 'page_info.json'
        page_info_data = [asdict(p) for p in self.result.page_info]
        with open(page_info_file, 'w') as f:
            json.dump(page_info_data, f, indent=2)

        self.stream('verify', f'Extracted {len(self.result.highlighted_pages)} highlighted pages', 1.0, {
            'highlight_folder': str(output_folder),
            'pages_extracted': len(self.result.highlighted_pages),
            'page_files': [Path(p).name for p in self.result.highlighted_pages]
        })

    # ==================== RUN PIPELINE ====================

    async def run(self) -> TakeoffResult:
        """Run the complete 5-phase takeoff pipeline"""
        self.stream('pipeline', 'Starting Scope Takeoff...', 0.0)

        try:
            # Phase 1: Identify documents
            self.stream('pipeline', 'Phase 1: Document Recognition', 0.1)
            self.phase_identify()

            # Phase 2: Parse spec
            self.stream('pipeline', 'Phase 2: Spec Analysis', 0.3)
            self.phase_parse()

            # Phase 3: Extract schedules
            self.stream('pipeline', 'Phase 3: Schedule Extraction', 0.5)
            self.phase_extract()

            # Phase 4: Quantify
            self.stream('pipeline', 'Phase 4: Drawing Takeoff', 0.7)
            self.phase_quantify()

            # Phase 5: Verify
            self.stream('pipeline', 'Phase 5: Visual Verification', 0.9)
            self.phase_verify()

            self.result.success = len(self.result.errors) == 0

        except Exception as e:
            self.result.errors.append(f"Pipeline error: {str(e)}")
            self.result.success = False

        # Save full result
        output_folder = self.project_folder / 'Extracted-Data'
        output_folder.mkdir(exist_ok=True)

        result_file = output_folder / 'scope_takeoff_result.json'
        with open(result_file, 'w') as f:
            # Convert dataclasses to dicts for JSON serialization
            result_dict = asdict(self.result)
            json.dump(result_dict, f, indent=2, default=str)

        self.stream('pipeline', 'Scope Takeoff complete!', 1.0, {
            'success': self.result.success,
            'result_file': str(result_file)
        })

        return self.result


def run_scope_takeoff(project_folder: str,
                       stream_callback: Optional[Callable] = None) -> Dict:
    """Run scope takeoff synchronously (for API endpoints)"""
    import asyncio

    takeoff = ScopeTakeoff(project_folder, stream_callback)
    result = asyncio.run(takeoff.run())
    return asdict(result)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python takeoff_pipeline.py <project_folder>")
        sys.exit(1)

    folder = sys.argv[1]

    def print_progress(data):
        phase = data.get('phase_name', data.get('phase', ''))
        msg = data.get('message', '')
        pct = data.get('progress', 0) * 100
        print(f"[{phase}] {msg} ({pct:.0f}%)")

    result = run_scope_takeoff(folder, print_progress)

    print("\n" + "="*60)
    print("TAKEOFF SUMMARY:")
    print(f"  Division 8 Sections: {len(result.get('division_8_sections', []))}")
    print(f"  Door Schedule Entries: {len(result.get('door_schedule', []))}")
    print(f"  Window Schedule Entries: {len(result.get('window_schedule', []))}")
    print(f"  Type Tags Found: {sum(tc['count'] for tc in result.get('type_counts', []))}")
    print(f"  Highlight List Items: {len(result.get('highlight_list', []))}")
