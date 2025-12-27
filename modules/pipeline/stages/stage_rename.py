"""
Stage 1: Project Rename

Uses AI vision to extract the official project name from the cover sheet
and renames the project folder accordingly.
"""

import re
import shutil
import base64
from pathlib import Path
from typing import Dict, Optional, Tuple
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


class RenameStage:
    """
    Stage 1: Project Rename

    Extracts project name from cover sheet using AI vision,
    then renames the project folder.
    """

    # Patterns to identify cover sheets
    COVER_PATTERNS = [
        r'cover',
        r'title\s*sheet',
        r'title\s*page',
        r'general\s*info',
        r'^g[0-9]*0[0-9]',  # G001, G002, etc.
        r'^g-0',
    ]

    def __init__(self, project_folder: Path, ai_provider):
        self.project_folder = Path(project_folder)
        self.ai = ai_provider
        self.original_name = self.project_folder.name

    async def run(self) -> StageResult:
        """Execute the rename stage"""
        try:
            # Step 1: Find cover sheet
            cover_pdf, cover_page = self._find_cover_sheet()
            if not cover_pdf:
                return StageResult(
                    success=False,
                    data={"original_name": self.original_name},
                    error="No cover sheet found"
                )

            logger.info(f"[Rename] Found cover sheet: {cover_pdf.name}, page {cover_page}")

            # Step 2: Convert page to image
            image_base64 = self._pdf_page_to_base64(cover_pdf, cover_page)
            if not image_base64:
                return StageResult(
                    success=False,
                    data={"original_name": self.original_name},
                    error="Failed to convert cover sheet to image"
                )

            # Step 3: Use AI vision to extract project name
            prompt = """Analyze this construction project cover sheet or title page.

Extract the official project name/title. Look for:
- Project title in the title block
- Main header or prominent text
- Owner/project identification

Return JSON:
{
    "project_name": "The Official Project Name",
    "confidence": 0.0-1.0,
    "location": "City, State if visible",
    "owner": "Owner name if visible"
}

IMPORTANT: Return ONLY the project name, not "Cover Sheet" or similar."""

            result = await self.ai.vision(
                image_base64,
                prompt,
                system_prompt_key='cover_sheet'
            )

            if not result.success:
                return StageResult(
                    success=False,
                    data={"original_name": self.original_name},
                    error=f"AI extraction failed: {result.error}"
                )

            project_name = result.data.get('project_name', '')
            confidence = result.data.get('confidence', 0)

            if not project_name or confidence < 0.5:
                return StageResult(
                    success=False,
                    data={
                        "original_name": self.original_name,
                        "extracted_name": project_name,
                        "confidence": confidence
                    },
                    error="Could not confidently extract project name"
                )

            # Step 4: Sanitize folder name
            clean_name = self._sanitize_folder_name(project_name)

            # Step 5: Rename folder if different
            if clean_name.lower() != self.original_name.lower():
                new_path = self._rename_folder(clean_name)
                if new_path:
                    logger.info(f"[Rename] Renamed: {self.original_name} -> {clean_name}")
                    return StageResult(
                        success=True,
                        data={
                            "original_name": self.original_name,
                            "new_name": clean_name,
                            "new_path": str(new_path),
                            "confidence": confidence,
                            "location": result.data.get('location'),
                            "owner": result.data.get('owner')
                        }
                    )
                else:
                    return StageResult(
                        success=False,
                        data={
                            "original_name": self.original_name,
                            "attempted_name": clean_name
                        },
                        error="Failed to rename folder"
                    )
            else:
                return StageResult(
                    success=True,
                    data={
                        "original_name": self.original_name,
                        "new_name": self.original_name,
                        "message": "Name already matches extracted name"
                    }
                )

        except Exception as e:
            logger.error(f"[Rename] Error: {e}")
            return StageResult(
                success=False,
                data={"original_name": self.original_name},
                error=str(e)
            )

    def _find_cover_sheet(self) -> Tuple[Optional[Path], int]:
        """
        Find the cover sheet PDF and page number.

        Returns:
            Tuple of (PDF path, page number) or (None, 0)
        """
        pdfs = list(self.project_folder.rglob("*.pdf"))
        if not pdfs:
            return None, 0

        # First, look for PDFs with cover-related names
        for pdf in pdfs:
            name_lower = pdf.stem.lower()
            for pattern in self.COVER_PATTERNS:
                if re.search(pattern, name_lower, re.IGNORECASE):
                    return pdf, 0  # First page

        # Look in Drawings subfolder
        drawings_folder = self.project_folder / "Drawings"
        if drawings_folder.exists():
            drawing_pdfs = list(drawings_folder.glob("*.pdf"))
            for pdf in drawing_pdfs:
                name_lower = pdf.stem.lower()
                for pattern in self.COVER_PATTERNS:
                    if re.search(pattern, name_lower, re.IGNORECASE):
                        return pdf, 0

        # Fall back to first page of largest PDF
        largest_pdf = max(pdfs, key=lambda p: p.stat().st_size)
        return largest_pdf, 0

    def _pdf_page_to_base64(self, pdf_path: Path, page_num: int = 0, dpi: int = 200) -> Optional[str]:
        """Convert a PDF page to base64-encoded JPEG"""
        try:
            doc = fitz.open(str(pdf_path))
            if page_num >= len(doc):
                page_num = 0

            page = doc[page_num]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)

            # Convert to JPEG
            img_bytes = pix.tobytes("jpeg", jpg_quality=85)
            doc.close()

            return base64.b64encode(img_bytes).decode('utf-8')

        except Exception as e:
            logger.error(f"Error converting PDF to image: {e}")
            return None

    def _sanitize_folder_name(self, name: str) -> str:
        """
        Sanitize project name for use as folder name.

        - Remove/replace invalid characters
        - Trim whitespace
        - Limit length
        """
        # Remove characters invalid in folder names
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '')

        # Replace multiple spaces with single space
        name = re.sub(r'\s+', ' ', name)

        # Trim whitespace
        name = name.strip()

        # Remove trailing periods (Windows issue)
        name = name.rstrip('.')

        # Limit length (leave room for potential suffixes)
        max_length = 200
        if len(name) > max_length:
            name = name[:max_length].rsplit(' ', 1)[0]  # Don't cut mid-word

        return name

    def _rename_folder(self, new_name: str) -> Optional[Path]:
        """
        Rename the project folder.

        Handles conflicts by adding numeric suffix.
        Returns new path or None on failure.
        """
        new_path = self.project_folder.parent / new_name

        # Handle existing folder with same name
        if new_path.exists() and new_path != self.project_folder:
            # Add numeric suffix
            counter = 1
            while new_path.exists():
                new_path = self.project_folder.parent / f"{new_name} ({counter})"
                counter += 1

        try:
            shutil.move(str(self.project_folder), str(new_path))
            self.project_folder = new_path
            return new_path
        except Exception as e:
            logger.error(f"Error renaming folder: {e}")
            return None
