"""
File Classifier Module

Classifies files in a project folder by analyzing:
- PDF dimensions (to identify drawings vs letter-size docs)
- Page count
- Filename patterns
- File size
- LLM fallback for ambiguous files

Saves classifications to database with JSON fallback for backward compatibility.
"""

import fitz  # PyMuPDF
import os
import requests
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class FileType(str, Enum):
    """Recognized file types for construction projects."""
    DRAWING_SET = 'drawing_set'          # Multi-page large format drawings
    SPEC_BOOK = 'spec_book'              # Project manual / specifications
    ADDENDUM = 'addendum'                # Contract addendum
    DRAWING_SHEET = 'drawing_sheet'      # Single sheet (revised drawing, etc.)
    SCHEDULE = 'schedule'                # Door/window/hardware schedule
    CUTSHEET = 'cutsheet'                # Product cutsheet/datasheet
    BID_FORM = 'bid_form'                # Bid form document
    INVITE_TO_BID = 'invite_to_bid'      # Invitation to bid document
    CONTRACT = 'contract'                # Contract documents
    REPORT = 'report'                    # Engineering/inspection reports
    GEOTECHNICAL = 'geotechnical'        # Geotech/foundation reports
    ENVIRONMENTAL = 'environmental'      # ESA, hazmat reports
    SURVEY = 'survey'                    # Site surveys, boundary surveys
    PERMIT = 'permit'                    # Building permits, approvals
    CORRESPONDENCE = 'correspondence'    # Letters, emails
    PHOTO = 'photo'                      # Site photos
    EMAIL = 'email'                      # .eml files
    UNKNOWN = 'unknown'


@dataclass
class FileClassification:
    """Result of file classification."""
    file_path: Path
    file_type: FileType
    confidence: float
    details: dict

    def to_dict(self) -> dict:
        return {
            'name': self.file_path.name,
            'path': str(self.file_path),
            'type': self.file_type.value,
            'confidence': self.confidence,
            'details': self.details
        }


class FileClassifier:
    """Classifies files in project folders."""

    # Dimension thresholds (in points, 72 points = 1 inch)
    DRAWING_MIN_WIDTH = 1500  # ~21 inches - typical ARCH D or larger
    LETTER_WIDTH_RANGE = (600, 650)  # 8.5 inches = 612 pt
    LETTER_HEIGHT_RANGE = (780, 800)  # 11 inches = 792 pt

    # Page count thresholds
    SPEC_MIN_PAGES = 50  # Spec books typically 50+ pages
    DRAWING_SET_MIN_PAGES = 5  # Drawing sets typically 5+ sheets

    # Filename patterns (lowercase)
    ADDENDUM_PATTERNS = ['addendum', 'add ', 'add_', 'add-', 'adden']
    SPEC_PATTERNS = ['spec', 'project manual', 'technical spec', 'division']
    SCHEDULE_PATTERNS = ['schedule', 'door schedule', 'window schedule', 'hardware']
    CUTSHEET_PATTERNS = ['cutsheet', 'datasheet', 'submittal', 'catalog', 'product data']
    BID_PATTERNS = ['bid form', 'bid proposal', 'proposal form']
    INVITE_PATTERNS = ['invitation to bid', 'invite to bid', 'itb', 'rfp', 'request for proposal',
                       'request for bid', 'bid invitation', 'bid package']
    CONTRACT_PATTERNS = ['contract', 'agreement', 'terms']

    # Report patterns - engineering, inspection, studies
    REPORT_PATTERNS = ['report', 'inspection', 'assessment', 'evaluation', 'analysis', 'study']
    GEOTECH_PATTERNS = ['geotech', 'geotechnical', 'foundation', 'soil', 'boring', 'subsurface',
                        'bedrock', 'contour']
    ENVIRONMENTAL_PATTERNS = ['esa', 'phase i', 'phase ii', 'environmental', 'hazardous',
                              'hazmat', 'asbestos', 'lead', 'abatement', 'remediation']
    SURVEY_PATTERNS = ['survey', 'boundary', 'topographic', 'topo', 'alta']
    PERMIT_PATTERNS = ['permit', 'approval', 'variance', 'zoning']

    # Drawing-related patterns (to help distinguish from reports)
    DRAWING_NAME_PATTERNS = ['plan', 'drawing', 'dwg', 'sheet', 'cd_', 'cd-', '100%', '50%', '90%',
                             'construction document', 'design development', 'dd_', 'sd_']

    CACHE_FILENAME = '.file_classifications.json'

    def __init__(self, project_id: str = None):
        """
        Initialize classifier.

        Args:
            project_id: Project ID for database storage (optional)
        """
        self.project_id = project_id

    def classify_folder(self, folder_path: Path, recursive: bool = True, use_cache: bool = True) -> list[FileClassification]:
        """
        Classify all files in a folder.

        Args:
            folder_path: Path to project folder
            recursive: If True, search subfolders too
            use_cache: If True, use cached results if available

        Returns:
            List of FileClassification objects
        """
        folder_path = Path(folder_path)

        # Try to load from database first (if project_id set)
        if use_cache and self.project_id:
            cached = self._load_from_database()
            if cached:
                logger.info(f"[FileClassifier] Loaded {len(cached)} classifications from database")
                return cached

        # Check for cached JSON results (backward compatibility)
        cache_file = folder_path / self.CACHE_FILENAME
        if use_cache and cache_file.exists():
            cached = self._load_cache(cache_file, folder_path)
            if cached:
                return cached

        results = []

        # Get files - either just root or recursive
        if recursive:
            files = [f for f in folder_path.rglob('*') if f.is_file() and not f.name.startswith('.')]
        else:
            files = [f for f in folder_path.iterdir() if f.is_file() and not f.name.startswith('.')]

        # Skip files in hidden folders or system folders
        skip_folders = {'.chroma', '.chroma_local', '__pycache__', '.git'}
        files = [f for f in files if not any(skip in f.parts for skip in skip_folders)]

        for item in files:
            classification = self.classify_file(item)
            results.append(classification)

        # Sort by confidence (highest first), then by type
        results.sort(key=lambda x: (-x.confidence, x.file_type.value))

        # Save to database first (if project_id set)
        if self.project_id:
            self._save_to_database(results)

        # Also save to JSON cache for backward compatibility
        self._save_cache(cache_file, results)

        return results

    def _load_cache(self, cache_file: Path, folder_path: Path) -> Optional[list[FileClassification]]:
        """Load cached classifications if still valid."""
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)

            # Check cache version
            if cache_data.get('version') != '1.0':
                return None

            # Rebuild FileClassification objects
            results = []
            for item in cache_data.get('files', []):
                file_path = Path(item['path'])
                # Skip if file no longer exists
                if not file_path.exists():
                    continue

                # Check if file was modified after cache
                file_mtime = file_path.stat().st_mtime
                if file_mtime > cache_data.get('timestamp', 0):
                    return None  # Cache is stale

                results.append(FileClassification(
                    file_path=file_path,
                    file_type=FileType(item['type']),
                    confidence=item['confidence'],
                    details=item['details']
                ))

            return results if results else None

        except Exception:
            return None

    def _save_cache(self, cache_file: Path, results: list[FileClassification]) -> None:
        """Save classifications to cache file."""
        try:
            import time
            cache_data = {
                'version': '1.0',
                'timestamp': time.time(),
                'files': [r.to_dict() for r in results]
            }
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception:
            pass  # Caching is optional, don't fail on errors

    def _load_from_database(self) -> Optional[list[FileClassification]]:
        """Load classifications from database."""
        try:
            from modules.database import queries

            files = queries.get_project_files(self.project_id)
            if not files:
                return None

            results = []
            for file_record in files:
                # Rebuild FileClassification from database record
                details = {
                    'pages': file_record.pages,
                    'size_mb': file_record.size_mb,
                    'width_pt': file_record.width_pt,
                    'height_pt': file_record.height_pt,
                    'dimensions': file_record.dimensions,
                    'extension': file_record.extension
                }
                # Remove None values
                details = {k: v for k, v in details.items() if v is not None}

                if file_record.classified_by:
                    details['classified_by'] = file_record.classified_by

                results.append(FileClassification(
                    file_path=Path(file_record.path),
                    file_type=FileType(file_record.file_type),
                    confidence=file_record.confidence or 0.5,
                    details=details
                ))

            return results if results else None

        except ImportError:
            logger.warning("[FileClassifier] Database module not available, falling back to JSON")
            return None
        except Exception as e:
            logger.warning(f"[FileClassifier] Could not load from database: {e}")
            return None

    def _save_to_database(self, results: list[FileClassification]) -> None:
        """Save classifications to database."""
        try:
            from modules.database import queries

            # Build file records for bulk insert
            files_data = []
            for classification in results:
                file_data = {
                    'name': classification.file_path.name,
                    'path': str(classification.file_path),
                    'file_type': classification.file_type.value,
                    'confidence': classification.confidence,
                    'pages': classification.details.get('pages'),
                    'size_mb': classification.details.get('size_mb'),
                    'width_pt': classification.details.get('width_pt'),
                    'height_pt': classification.details.get('height_pt'),
                    'dimensions': classification.details.get('dimensions'),
                    'extension': classification.details.get('extension'),
                    'classified_by': classification.details.get('classified_by', 'heuristic')
                }
                files_data.append(file_data)

            # Delete existing files for this project and insert new ones
            from modules.database.db import get_session
            with get_session() as session:
                # Delete old classifications
                from modules.database.models import ProjectFile
                session.query(ProjectFile).filter_by(project_id=self.project_id).delete()

                # Insert new classifications
                queries.bulk_add_files(self.project_id, files_data, session=session)

            logger.info(f"[FileClassifier] Saved {len(files_data)} classifications to database")

        except ImportError:
            logger.warning("[FileClassifier] Database module not available, only saving to JSON")
        except Exception as e:
            logger.warning(f"[FileClassifier] Could not save to database: {e}")
            # Continue - JSON fallback will still work

    def classify_file(self, file_path: Path) -> FileClassification:
        """
        Classify a single file.

        Args:
            file_path: Path to file

        Returns:
            FileClassification object
        """
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()
        name_lower = file_path.stem.lower()

        # Handle non-PDF files first
        if suffix == '.eml':
            return FileClassification(
                file_path=file_path,
                file_type=FileType.EMAIL,
                confidence=1.0,
                details={'extension': suffix}
            )

        if suffix in ('.jpg', '.jpeg', '.png', '.gif', '.heic'):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.PHOTO,
                confidence=0.9,
                details={'extension': suffix}
            )

        if suffix not in ('.pdf',):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.UNKNOWN,
                confidence=0.5,
                details={'extension': suffix, 'reason': 'unhandled extension'}
            )

        # Analyze PDF
        return self._classify_pdf(file_path, name_lower)

    def _classify_pdf(self, file_path: Path, name_lower: str) -> FileClassification:
        """Classify a PDF file by analyzing its properties."""
        try:
            doc = fitz.open(file_path)
            page = doc[0]
            width, height = page.rect.width, page.rect.height
            pages = len(doc)
            size_mb = file_path.stat().st_size / (1024 * 1024)
            doc.close()
        except Exception as e:
            return FileClassification(
                file_path=file_path,
                file_type=FileType.UNKNOWN,
                confidence=0.3,
                details={'error': str(e)}
            )

        details = {
            'pages': pages,
            'width_pt': round(width),
            'height_pt': round(height),
            'dimensions': f'{round(width)}x{round(height)}pt',
            'size_mb': round(size_mb, 2)
        }

        # Helper: check if name looks like drawings
        is_drawing_name = any(p in name_lower for p in self.DRAWING_NAME_PATTERNS)

        # Large format (drawings)
        is_large_format = width > self.DRAWING_MIN_WIDTH or height > self.DRAWING_MIN_WIDTH

        # Letter size
        is_letter = (
            (self.LETTER_WIDTH_RANGE[0] <= width <= self.LETTER_WIDTH_RANGE[1] and
             self.LETTER_HEIGHT_RANGE[0] <= height <= self.LETTER_HEIGHT_RANGE[1]) or
            (self.LETTER_WIDTH_RANGE[0] <= height <= self.LETTER_WIDTH_RANGE[1] and
             self.LETTER_HEIGHT_RANGE[0] <= width <= self.LETTER_HEIGHT_RANGE[1])
        )

        # ===== FILENAME PATTERN MATCHING (highest priority) =====

        # 1. Invitation to bid - check before other bid patterns
        if any(p in name_lower for p in self.INVITE_PATTERNS):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.INVITE_TO_BID,
                confidence=0.95,
                details=details
            )

        # 2. Environmental reports (ESA, hazmat, etc.)
        if any(p in name_lower for p in self.ENVIRONMENTAL_PATTERNS):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.ENVIRONMENTAL,
                confidence=0.95,
                details=details
            )

        # 3. Geotechnical reports
        if any(p in name_lower for p in self.GEOTECH_PATTERNS):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.GEOTECHNICAL,
                confidence=0.95,
                details=details
            )

        # 4. Surveys
        if any(p in name_lower for p in self.SURVEY_PATTERNS):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.SURVEY,
                confidence=0.9,
                details=details
            )

        # 5. Permits
        if any(p in name_lower for p in self.PERMIT_PATTERNS):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.PERMIT,
                confidence=0.9,
                details=details
            )

        # 6. Addendum - but NOT if it looks like a drawing set
        if any(p in name_lower for p in self.ADDENDUM_PATTERNS) and not is_drawing_name:
            return FileClassification(
                file_path=file_path,
                file_type=FileType.ADDENDUM,
                confidence=0.95,
                details=details
            )

        # 7. Schedule
        if any(p in name_lower for p in self.SCHEDULE_PATTERNS):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.SCHEDULE,
                confidence=0.9,
                details=details
            )

        # 8. Cutsheet
        if any(p in name_lower for p in self.CUTSHEET_PATTERNS):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.CUTSHEET,
                confidence=0.9,
                details=details
            )

        # 9. Bid form
        if any(p in name_lower for p in self.BID_PATTERNS):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.BID_FORM,
                confidence=0.9,
                details=details
            )

        # 10. Contract
        if any(p in name_lower for p in self.CONTRACT_PATTERNS):
            return FileClassification(
                file_path=file_path,
                file_type=FileType.CONTRACT,
                confidence=0.85,
                details=details
            )

        # 11. Generic reports (check after specific report types)
        if any(p in name_lower for p in self.REPORT_PATTERNS) and not is_drawing_name:
            return FileClassification(
                file_path=file_path,
                file_type=FileType.REPORT,
                confidence=0.85,
                details=details
            )

        # ===== DIMENSION-BASED CLASSIFICATION =====

        # Drawing set: large format, multiple pages
        if is_large_format and pages >= self.DRAWING_SET_MIN_PAGES:
            return FileClassification(
                file_path=file_path,
                file_type=FileType.DRAWING_SET,
                confidence=0.95,
                details=details
            )

        # Single drawing sheet: large format, 1-2 pages
        if is_large_format and pages <= 2:
            return FileClassification(
                file_path=file_path,
                file_type=FileType.DRAWING_SHEET,
                confidence=0.85,
                details=details
            )

        # Large format but 3-4 pages - could be either
        if is_large_format and 3 <= pages < self.DRAWING_SET_MIN_PAGES:
            return FileClassification(
                file_path=file_path,
                file_type=FileType.DRAWING_SET,
                confidence=0.7,
                details=details
            )

        # Spec book: letter size, many pages
        if is_letter and pages >= self.SPEC_MIN_PAGES:
            # Check for spec keywords in name
            if any(p in name_lower for p in self.SPEC_PATTERNS):
                confidence = 0.95
            else:
                confidence = 0.75
            return FileClassification(
                file_path=file_path,
                file_type=FileType.SPEC_BOOK,
                confidence=confidence,
                details=details
            )

        # ===== MEDIUM-LENGTH DOCUMENTS (20-50 pages) =====
        # These are often reports - try to classify intelligently
        if is_letter and 20 <= pages < 50:
            # Could be a report - use LLM if available, otherwise tag as report
            llm_result = self._llm_classify(file_path.name, pages, details)
            if llm_result:
                return FileClassification(
                    file_path=file_path,
                    file_type=llm_result['type'],
                    confidence=llm_result['confidence'],
                    details={**details, 'classified_by': 'llm'}
                )
            # Default to report for medium-length docs
            return FileClassification(
                file_path=file_path,
                file_type=FileType.REPORT,
                confidence=0.6,
                details=details
            )

        # ===== SHORT DOCUMENTS (<20 pages) =====
        if is_letter and pages < 20:
            # Try LLM for better classification
            llm_result = self._llm_classify(file_path.name, pages, details)
            if llm_result:
                return FileClassification(
                    file_path=file_path,
                    file_type=llm_result['type'],
                    confidence=llm_result['confidence'],
                    details={**details, 'classified_by': 'llm'}
                )
            # Default to correspondence for short docs
            return FileClassification(
                file_path=file_path,
                file_type=FileType.CORRESPONDENCE,
                confidence=0.5,
                details=details
            )

        # ===== FALLBACK: LLM or UNKNOWN =====
        llm_result = self._llm_classify(file_path.name, pages, details)
        if llm_result:
            return FileClassification(
                file_path=file_path,
                file_type=llm_result['type'],
                confidence=llm_result['confidence'],
                details={**details, 'classified_by': 'llm'}
            )

        return FileClassification(
            file_path=file_path,
            file_type=FileType.UNKNOWN,
            confidence=0.3,
            details=details
        )

    def _llm_classify(self, filename: str, pages: int, details: dict) -> Optional[dict]:
        """
        Use LLM to classify ambiguous files based on filename.

        Returns dict with 'type' and 'confidence' or None if LLM unavailable.
        """
        api_key = os.getenv('OPENROUTER_API_KEY')
        if not api_key:
            return None

        try:
            prompt = f"""Classify this construction project document based on its filename.

Filename: {filename}
Pages: {pages}
Size: {details.get('size_mb', 'unknown')} MB

Document types (pick ONE):
- drawing_set: Construction drawings, plans, architectural/engineering sheets
- spec_book: Project manual, specifications, CSI divisions
- addendum: Contract addendum, changes to bid documents
- invite_to_bid: Invitation to bid, ITB, RFP, bid package
- bid_form: Bid form, proposal form
- report: Generic engineering/inspection report
- geotechnical: Geotechnical report, foundation study, soil boring
- environmental: Phase I/II ESA, hazmat inspection, asbestos/lead report
- survey: Site survey, boundary survey, topographic survey
- permit: Building permit, zoning approval
- schedule: Door/window/hardware schedule
- cutsheet: Product data, submittal, catalog cut
- contract: Contract, agreement
- correspondence: Letter, memo, general document

Respond with ONLY a JSON object: {{"type": "document_type", "confidence": 0.8}}"""

            response = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': 'openai/gpt-oss-120b:free',
                    'messages': [{'role': 'user', 'content': prompt}],
                    'max_tokens': 100,
                    'temperature': 0.1
                },
                timeout=10
            )

            if response.status_code == 200:
                content = response.json()['choices'][0]['message']['content'].strip()
                # Parse JSON response
                result = json.loads(content)
                doc_type = result.get('type', '').lower()

                # Map to FileType enum
                type_map = {
                    'drawing_set': FileType.DRAWING_SET,
                    'spec_book': FileType.SPEC_BOOK,
                    'addendum': FileType.ADDENDUM,
                    'invite_to_bid': FileType.INVITE_TO_BID,
                    'bid_form': FileType.BID_FORM,
                    'report': FileType.REPORT,
                    'geotechnical': FileType.GEOTECHNICAL,
                    'environmental': FileType.ENVIRONMENTAL,
                    'survey': FileType.SURVEY,
                    'permit': FileType.PERMIT,
                    'schedule': FileType.SCHEDULE,
                    'cutsheet': FileType.CUTSHEET,
                    'contract': FileType.CONTRACT,
                    'correspondence': FileType.CORRESPONDENCE,
                }

                if doc_type in type_map:
                    return {
                        'type': type_map[doc_type],
                        'confidence': min(result.get('confidence', 0.7), 0.85)  # Cap LLM confidence
                    }

        except Exception as e:
            # Silently fail - LLM is optional
            pass

        return None

    def get_folder_summary(self, folder_path: Path) -> dict:
        """
        Get a summary of all files in a folder.

        Returns dict with:
        - file_count: total files
        - by_type: count by file type
        - drawing_sets: list of identified drawing sets
        - spec_books: list of identified spec books
        - emails: list of .eml files
        """
        classifications = self.classify_folder(folder_path)

        by_type = {}
        for c in classifications:
            t = c.file_type.value
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(c.to_dict())

        return {
            'folder': str(folder_path),
            'folder_name': folder_path.name,
            'file_count': len(classifications),
            'by_type': by_type,
            'drawing_sets': [c.to_dict() for c in classifications if c.file_type == FileType.DRAWING_SET],
            'spec_books': [c.to_dict() for c in classifications if c.file_type == FileType.SPEC_BOOK],
            'emails': [c.to_dict() for c in classifications if c.file_type == FileType.EMAIL],
            'addenda': [c.to_dict() for c in classifications if c.file_type == FileType.ADDENDUM],
            'all_files': [c.to_dict() for c in classifications]
        }


def classify_project_folder(folder_path: Path, project_id: str = None) -> dict:
    """
    Convenience function to classify all files in a project folder.

    Args:
        folder_path: Path to project folder
        project_id: Optional project ID for database storage

    Returns:
        Summary dict with file classifications
    """
    # Extract project_id from folder name if not provided
    if not project_id:
        project_id = Path(folder_path).name

    classifier = FileClassifier(project_id=project_id)
    return classifier.get_folder_summary(folder_path)
