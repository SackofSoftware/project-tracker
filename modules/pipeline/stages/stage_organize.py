"""
Stage 2: File Organization

Moves (NOT copies) files into structured folders based on
file type classification.

IMPORTANT: Uses shutil.move(), not shutil.copy2()

Integrates with FileClassifier for intelligent document detection.
Skips irrelevant documents (environmental, geotech, surveys, generic reports).
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import logging

# Import FileClassifier for intelligent document detection
try:
    from ...intake.file_classifier import FileClassifier, FileType
    HAS_FILE_CLASSIFIER = True
except ImportError:
    HAS_FILE_CLASSIFIER = False

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    """Result from a pipeline stage"""
    success: bool
    data: Dict
    error: Optional[str] = None


class OrganizeStage:
    """
    Stage 2: File Organization

    Moves files into structured folders:
    - Specs/
    - Drawings/
    - Quotes/
    - Addenda/
    - Schedules/
    """

    # Standard folder structure
    FOLDER_STRUCTURE = {
        'Specs': 'Project specifications and requirements',
        'Drawings': 'Architectural and construction drawings',
        'Quotes': 'Vendor quotes and pricing documents',
        'Addenda': 'Contract addenda and modifications',
        'Schedules': 'Door, window, hardware schedules',
        'Submittals': 'Product submittals and shop drawings',
        'Correspondence': 'Emails and communications',
        'Photos': 'Project photos and documentation',
        'Reference-Documents': 'Supporting documents (surveys, reports, environmental)',
    }

    # File types to skip from processing (moved to Reference-Documents)
    # These are not relevant to Division 8 scope analysis
    SKIP_FILE_TYPES = {
        'environmental',   # ESA, Phase I/II, hazmat reports
        'geotechnical',    # Geotech, foundation, soil boring
        'survey',          # Site surveys, boundary surveys
        'report',          # Generic engineering/inspection reports
    } if HAS_FILE_CLASSIFIER else set()

    # File classification patterns
    FILE_PATTERNS = {
        'specs': [
            r'spec',
            r'specification',
            r'project\s*manual',
            r'division\s*\d+',
            r'section\s*\d+',
            r'\d{2}\s*\d{2}\s*\d{2}',  # CSI numbers
        ],
        'drawings': [
            r'drawing',
            r'plan',
            r'elevation',
            r'detail',
            r'sheet',
            r'^[ASMEPCLG]\d{1,3}',  # A101, S100, etc.
            r'arch',
            r'struct',
        ],
        'quotes': [
            r'quote',
            r'pricing',
            r'proposal',
            r'bid',
            r'estimate',
            # Vendor names
            r'kawneer',
            r'oldcastle',
            r'pella',
            r'marvin',
            r'alpen',
            r'ykk',
        ],
        'addenda': [
            r'addend',
            r'supplement',
            r'revision',
            r'amendment',
            r'change\s*order',
            r'bulletin',
        ],
        'schedules': [
            r'schedule',
            r'door\s*schedule',
            r'window\s*schedule',
            r'hardware\s*schedule',
            r'finish\s*schedule',
        ],
    }

    def __init__(self, project_folder: Path, ai_provider=None):
        self.project_folder = Path(project_folder)
        self.ai = ai_provider  # Optional - for AI-assisted classification
        self.file_classifier = FileClassifier() if HAS_FILE_CLASSIFIER else None

    async def run(self) -> StageResult:
        """Execute the organization stage"""
        try:
            files_moved = 0
            folders_created = []
            move_log = []

            # Create folder structure
            for folder_name in self.FOLDER_STRUCTURE.keys():
                folder_path = self.project_folder / folder_name
                if not folder_path.exists():
                    folder_path.mkdir(parents=True, exist_ok=True)
                    folders_created.append(folder_name)
                    logger.info(f"[Organize] Created folder: {folder_name}")

            # Get all PDFs not already in organized folders
            pdfs = self._get_unorganized_files()
            logger.info(f"[Organize] Found {len(pdfs)} unorganized files")

            # Classify and move each file
            for pdf_path in pdfs:
                category = self._classify_file(pdf_path)
                if category:
                    dest_folder = self.project_folder / category.title()
                    dest_path = dest_folder / pdf_path.name

                    # Handle duplicates
                    if dest_path.exists():
                        dest_path = self._get_unique_path(dest_path)

                    # MOVE the file (not copy!)
                    try:
                        shutil.move(str(pdf_path), str(dest_path))
                        files_moved += 1
                        move_log.append({
                            'file': pdf_path.name,
                            'from': str(pdf_path.parent.relative_to(self.project_folder)),
                            'to': category,
                        })
                        logger.info(f"[Organize] Moved: {pdf_path.name} -> {category}/")
                    except Exception as e:
                        logger.error(f"[Organize] Failed to move {pdf_path.name}: {e}")

            return StageResult(
                success=True,
                data={
                    'files_moved': files_moved,
                    'folders_created': folders_created,
                    'move_log': move_log,
                }
            )

        except Exception as e:
            logger.error(f"[Organize] Error: {e}")
            return StageResult(
                success=False,
                data={},
                error=str(e)
            )

    def _get_unorganized_files(self) -> List[Path]:
        """Get all PDF files not already in organized folders"""
        organized_folders = set(self.FOLDER_STRUCTURE.keys())
        organized_folders.update([f.lower() for f in organized_folders])

        # Also exclude some special folders
        exclude_folders = organized_folders | {
            'extracted-data', 'extracted_data', 'organized',
            'takeoffs', 'archive', 'old', 'backup'
        }

        unorganized = []

        for pdf in self.project_folder.rglob("*.pdf"):
            # Check if file is in an organized folder
            relative = pdf.relative_to(self.project_folder)
            parts = relative.parts

            if len(parts) == 1:
                # File in root - needs organization
                unorganized.append(pdf)
            elif parts[0].lower() not in exclude_folders:
                # File in an unrecognized folder
                unorganized.append(pdf)

        return unorganized

    def _classify_file(self, file_path: Path) -> Optional[str]:
        """
        Classify a file based on FileClassifier or filename patterns.

        Returns category name or None if unclassifiable.
        Files classified as environmental/geotech/survey/report go to Reference-Documents.
        """
        # Use FileClassifier if available (more intelligent detection)
        if self.file_classifier and file_path.suffix.lower() == '.pdf':
            classification = self.file_classifier.classify_file(file_path)
            file_type = classification.file_type.value

            # Skip-worthy files go to Reference-Documents
            if file_type in self.SKIP_FILE_TYPES:
                logger.info(f"[Organize] Skipping {file_path.name} -> Reference-Documents ({file_type})")
                return 'reference-documents'

            # Map FileClassifier types to folder structure
            type_to_folder = {
                'drawing_set': 'drawings',
                'drawing_sheet': 'drawings',
                'spec_book': 'specs',
                'addendum': 'addenda',
                'schedule': 'schedules',
                'cutsheet': 'submittals',
                'bid_form': 'specs',
                'invite_to_bid': 'specs',
                'contract': 'specs',
                'permit': 'specs',
                'correspondence': 'correspondence',
                'photo': 'photos',
                'email': 'correspondence',
            }

            if file_type in type_to_folder:
                return type_to_folder[file_type]

        # Fallback: pattern-based classification
        filename = file_path.stem.lower()

        # Check each category's patterns
        for category, patterns in self.FILE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename, re.IGNORECASE):
                    return category

        # Default: check file size for drawings (typically large)
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > 5:
            # Large PDF - likely drawings
            return 'drawings'

        return None

    def _get_unique_path(self, dest_path: Path) -> Path:
        """Generate unique filename if destination exists"""
        if not dest_path.exists():
            return dest_path

        base = dest_path.stem
        ext = dest_path.suffix
        parent = dest_path.parent
        counter = 1

        while dest_path.exists():
            dest_path = parent / f"{base}_{counter}{ext}"
            counter += 1

        return dest_path

    async def classify_with_ai(self, file_path: Path, text_content: str) -> Optional[str]:
        """
        Use AI to classify a file when pattern matching fails.

        Only called if ai_provider is available.
        """
        if not self.ai:
            return None

        prompt = f"""Classify this construction document based on its filename and content.

Filename: {file_path.name}

Content preview (first 1000 chars):
{text_content[:1000]}

Categories:
- specs: Project specifications, divisions, technical requirements
- drawings: Architectural plans, elevations, sections, details
- quotes: Vendor pricing, proposals, estimates
- addenda: Addenda, bulletins, revisions
- schedules: Door/window/hardware schedules

Return JSON:
{{"category": "specs|drawings|quotes|addenda|schedules", "confidence": 0.0-1.0}}
"""

        result = await self.ai.reason(prompt)
        if result.success and result.data.get('confidence', 0) > 0.7:
            return result.data.get('category')

        return None
