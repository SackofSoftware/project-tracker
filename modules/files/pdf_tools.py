"""
PDF Tools Module

Comprehensive PDF processing utilities for construction documents:
- OCR text extraction (Tesseract)
- PDF merging and splitting (PyPDF2)
- High-quality rendering (pdf2image + Poppler)
- Text extraction (pdftotext via subprocess)
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Tuple, Union
from dataclasses import dataclass
from datetime import datetime

import fitz  # PyMuPDF - already installed
import pytesseract
from pdf2image import convert_from_path
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image


@dataclass
class OCRResult:
    """Result from OCR text extraction"""
    text: str
    confidence: float
    page_number: int
    processing_time: float
    method: str  # 'tesseract' or 'pdftotext'


@dataclass
class PDFInfo:
    """Basic PDF information"""
    path: str
    page_count: int
    title: Optional[str]
    author: Optional[str]
    file_size: int
    has_text: bool
    is_scanned: bool


class PDFTools:
    """
    Unified PDF processing toolkit for construction documents.

    Combines multiple tools for optimal results:
    - PyMuPDF (fitz): Fast rendering, basic text extraction
    - Tesseract: OCR for scanned documents
    - Poppler: High-quality rendering and text extraction
    - PyPDF2: PDF manipulation (merge, split, extract)
    """

    def __init__(self,
                 tesseract_path: Optional[str] = None,
                 poppler_path: Optional[str] = None,
                 default_dpi: int = 200):
        """
        Initialize PDF tools.

        Args:
            tesseract_path: Path to tesseract binary (auto-detected if None)
            poppler_path: Path to poppler binaries (auto-detected if None)
            default_dpi: Default DPI for rendering
        """
        self.default_dpi = default_dpi

        # Set Tesseract path if provided
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

        self.poppler_path = poppler_path

    # =========================================================================
    # PDF Information
    # =========================================================================

    def get_info(self, pdf_path: Union[str, Path]) -> PDFInfo:
        """Get basic information about a PDF file."""
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        doc = fitz.open(str(pdf_path))

        # Check if PDF has extractable text
        has_text = False
        text_sample = ""
        if doc.page_count > 0:
            text_sample = doc[0].get_text().strip()
            has_text = len(text_sample) > 50  # Meaningful text threshold

        # Estimate if scanned (has pages but no/little text)
        is_scanned = doc.page_count > 0 and not has_text

        info = PDFInfo(
            path=str(pdf_path),
            page_count=doc.page_count,
            title=doc.metadata.get('title'),
            author=doc.metadata.get('author'),
            file_size=pdf_path.stat().st_size,
            has_text=has_text,
            is_scanned=is_scanned
        )

        doc.close()
        return info

    # =========================================================================
    # Text Extraction
    # =========================================================================

    def extract_text(self,
                     pdf_path: Union[str, Path],
                     pages: Optional[List[int]] = None,
                     method: str = 'auto') -> str:
        """
        Extract text from PDF using best available method.

        Args:
            pdf_path: Path to PDF file
            pages: List of page numbers (1-indexed), or None for all
            method: 'auto', 'pymupdf', 'pdftotext', or 'ocr'

        Returns:
            Extracted text
        """
        pdf_path = Path(pdf_path)

        if method == 'auto':
            info = self.get_info(pdf_path)
            if info.is_scanned:
                method = 'ocr'
            else:
                method = 'pymupdf'

        if method == 'pymupdf':
            return self._extract_text_pymupdf(pdf_path, pages)
        elif method == 'pdftotext':
            return self._extract_text_pdftotext(pdf_path, pages)
        elif method == 'ocr':
            return self._extract_text_ocr(pdf_path, pages)
        else:
            raise ValueError(f"Unknown method: {method}")

    def _extract_text_pymupdf(self,
                               pdf_path: Path,
                               pages: Optional[List[int]] = None) -> str:
        """Extract text using PyMuPDF (fast, works on native PDFs)."""
        doc = fitz.open(str(pdf_path))
        text_parts = []

        page_indices = range(doc.page_count)
        if pages:
            page_indices = [p - 1 for p in pages if 0 < p <= doc.page_count]

        for i in page_indices:
            page = doc[i]
            text_parts.append(f"--- Page {i + 1} ---\n")
            text_parts.append(page.get_text())

        doc.close()
        return "\n".join(text_parts)

    def _extract_text_pdftotext(self,
                                 pdf_path: Path,
                                 pages: Optional[List[int]] = None) -> str:
        """Extract text using Poppler's pdftotext (better formatting)."""
        cmd = ['pdftotext', '-layout']

        if pages:
            # pdftotext uses -f (first) and -l (last) for page range
            cmd.extend(['-f', str(min(pages)), '-l', str(max(pages))])

        cmd.extend([str(pdf_path), '-'])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.stdout
        except subprocess.TimeoutExpired:
            return self._extract_text_pymupdf(pdf_path, pages)
        except FileNotFoundError:
            # pdftotext not installed, fallback
            return self._extract_text_pymupdf(pdf_path, pages)

    def _extract_text_ocr(self,
                          pdf_path: Path,
                          pages: Optional[List[int]] = None) -> str:
        """Extract text using Tesseract OCR (for scanned documents)."""
        # Convert PDF pages to images
        images = convert_from_path(
            str(pdf_path),
            dpi=self.default_dpi,
            first_page=min(pages) if pages else None,
            last_page=max(pages) if pages else None,
            poppler_path=self.poppler_path
        )

        text_parts = []
        for i, image in enumerate(images):
            page_num = pages[i] if pages else i + 1
            text_parts.append(f"--- Page {page_num} (OCR) ---\n")
            text = pytesseract.image_to_string(image)
            text_parts.append(text)

        return "\n".join(text_parts)

    def ocr_page(self,
                 pdf_path: Union[str, Path],
                 page: int,
                 lang: str = 'eng',
                 config: str = '') -> OCRResult:
        """
        Perform OCR on a single page with detailed results.

        Args:
            pdf_path: Path to PDF
            page: Page number (1-indexed)
            lang: Tesseract language code
            config: Additional Tesseract config

        Returns:
            OCRResult with text, confidence, and metadata
        """
        import time
        start = time.time()

        pdf_path = Path(pdf_path)

        # Convert page to image
        images = convert_from_path(
            str(pdf_path),
            dpi=self.default_dpi,
            first_page=page,
            last_page=page,
            poppler_path=self.poppler_path
        )

        if not images:
            return OCRResult(
                text="",
                confidence=0.0,
                page_number=page,
                processing_time=time.time() - start,
                method='tesseract'
            )

        image = images[0]

        # Get OCR data with confidence
        data = pytesseract.image_to_data(
            image,
            lang=lang,
            config=config,
            output_type=pytesseract.Output.DICT
        )

        # Calculate average confidence
        confidences = [int(c) for c in data['conf'] if int(c) > 0]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Get full text
        text = pytesseract.image_to_string(image, lang=lang, config=config)

        return OCRResult(
            text=text,
            confidence=avg_confidence / 100.0,  # Normalize to 0-1
            page_number=page,
            processing_time=time.time() - start,
            method='tesseract'
        )

    # =========================================================================
    # PDF Manipulation
    # =========================================================================

    def merge_pdfs(self,
                   pdf_paths: List[Union[str, Path]],
                   output_path: Union[str, Path]) -> Path:
        """
        Merge multiple PDFs into a single file.

        Args:
            pdf_paths: List of PDF files to merge (in order)
            output_path: Path for merged output

        Returns:
            Path to merged PDF
        """
        writer = PdfWriter()

        for pdf_path in pdf_paths:
            reader = PdfReader(str(pdf_path))
            for page in reader.pages:
                writer.add_page(page)

        output_path = Path(output_path)
        with open(output_path, 'wb') as f:
            writer.write(f)

        return output_path

    def split_pdf(self,
                  pdf_path: Union[str, Path],
                  output_dir: Union[str, Path],
                  pages_per_file: int = 1) -> List[Path]:
        """
        Split PDF into multiple files.

        Args:
            pdf_path: Source PDF
            output_dir: Directory for output files
            pages_per_file: Number of pages per output file

        Returns:
            List of output file paths
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        reader = PdfReader(str(pdf_path))
        total_pages = len(reader.pages)
        output_files = []

        stem = pdf_path.stem

        for start in range(0, total_pages, pages_per_file):
            end = min(start + pages_per_file, total_pages)

            writer = PdfWriter()
            for i in range(start, end):
                writer.add_page(reader.pages[i])

            if pages_per_file == 1:
                output_file = output_dir / f"{stem}_page_{start + 1}.pdf"
            else:
                output_file = output_dir / f"{stem}_pages_{start + 1}-{end}.pdf"

            with open(output_file, 'wb') as f:
                writer.write(f)

            output_files.append(output_file)

        return output_files

    def extract_pages(self,
                      pdf_path: Union[str, Path],
                      pages: List[int],
                      output_path: Union[str, Path]) -> Path:
        """
        Extract specific pages from a PDF.

        Args:
            pdf_path: Source PDF
            pages: List of page numbers to extract (1-indexed)
            output_path: Output file path

        Returns:
            Path to output PDF
        """
        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()

        for page_num in pages:
            if 0 < page_num <= len(reader.pages):
                writer.add_page(reader.pages[page_num - 1])

        output_path = Path(output_path)
        with open(output_path, 'wb') as f:
            writer.write(f)

        return output_path

    def rotate_pages(self,
                     pdf_path: Union[str, Path],
                     output_path: Union[str, Path],
                     rotation: int,
                     pages: Optional[List[int]] = None) -> Path:
        """
        Rotate pages in a PDF.

        Args:
            pdf_path: Source PDF
            output_path: Output file path
            rotation: Degrees to rotate (90, 180, 270)
            pages: Pages to rotate (1-indexed), or None for all

        Returns:
            Path to output PDF
        """
        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()

        for i, page in enumerate(reader.pages):
            if pages is None or (i + 1) in pages:
                page.rotate(rotation)
            writer.add_page(page)

        output_path = Path(output_path)
        with open(output_path, 'wb') as f:
            writer.write(f)

        return output_path

    # =========================================================================
    # High-Quality Rendering
    # =========================================================================

    def render_page(self,
                    pdf_path: Union[str, Path],
                    page: int,
                    dpi: Optional[int] = None,
                    format: str = 'PNG') -> Image.Image:
        """
        Render a PDF page as a high-quality image.

        Args:
            pdf_path: Path to PDF
            page: Page number (1-indexed)
            dpi: Resolution (default: self.default_dpi)
            format: Output format (PNG, JPEG)

        Returns:
            PIL Image
        """
        dpi = dpi or self.default_dpi

        images = convert_from_path(
            str(pdf_path),
            dpi=dpi,
            first_page=page,
            last_page=page,
            fmt=format.lower(),
            poppler_path=self.poppler_path
        )

        return images[0] if images else None

    def render_page_to_file(self,
                            pdf_path: Union[str, Path],
                            page: int,
                            output_path: Union[str, Path],
                            dpi: Optional[int] = None) -> Path:
        """
        Render a PDF page and save to file.

        Args:
            pdf_path: Path to PDF
            page: Page number (1-indexed)
            output_path: Output image path
            dpi: Resolution

        Returns:
            Path to output image
        """
        image = self.render_page(pdf_path, page, dpi)
        output_path = Path(output_path)
        image.save(str(output_path))
        return output_path

    def render_all_pages(self,
                         pdf_path: Union[str, Path],
                         output_dir: Union[str, Path],
                         dpi: Optional[int] = None,
                         format: str = 'png') -> List[Path]:
        """
        Render all pages of a PDF as images.

        Args:
            pdf_path: Path to PDF
            output_dir: Directory for output images
            dpi: Resolution
            format: Image format (png, jpg)

        Returns:
            List of output image paths
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        dpi = dpi or self.default_dpi

        images = convert_from_path(
            str(pdf_path),
            dpi=dpi,
            fmt=format,
            poppler_path=self.poppler_path
        )

        output_files = []
        stem = pdf_path.stem

        for i, image in enumerate(images):
            output_file = output_dir / f"{stem}_page_{i + 1}.{format}"
            image.save(str(output_file))
            output_files.append(output_file)

        return output_files

    # =========================================================================
    # Construction Document Utilities
    # =========================================================================

    def find_text_in_pdf(self,
                         pdf_path: Union[str, Path],
                         search_text: str,
                         case_sensitive: bool = False) -> List[Dict]:
        """
        Find all occurrences of text in a PDF.

        Args:
            pdf_path: Path to PDF
            search_text: Text to search for
            case_sensitive: Whether search is case-sensitive

        Returns:
            List of matches with page, position, and context
        """
        doc = fitz.open(str(pdf_path))
        matches = []

        flags = 0 if case_sensitive else fitz.TEXT_PRESERVE_WHITESPACE

        for page_num in range(doc.page_count):
            page = doc[page_num]
            text_instances = page.search_for(search_text)

            for rect in text_instances:
                matches.append({
                    'page': page_num + 1,
                    'x': rect.x0,
                    'y': rect.y0,
                    'width': rect.width,
                    'height': rect.height,
                    'text': search_text
                })

        doc.close()
        return matches

    def extract_drawing_title_block(self,
                                    pdf_path: Union[str, Path],
                                    page: int = 1) -> Dict:
        """
        Extract title block information from a drawing.

        Looks for common title block fields in the bottom-right area.

        Args:
            pdf_path: Path to PDF
            page: Page number

        Returns:
            Dictionary of extracted title block fields
        """
        doc = fitz.open(str(pdf_path))
        pdf_page = doc[page - 1]

        # Title blocks are typically in bottom-right corner
        # Get page dimensions
        rect = pdf_page.rect

        # Define title block region (bottom 15%, right 40%)
        title_block_rect = fitz.Rect(
            rect.width * 0.6,  # Left
            rect.height * 0.85,  # Top
            rect.width,  # Right
            rect.height  # Bottom
        )

        # Extract text from title block region
        text = pdf_page.get_text("text", clip=title_block_rect)

        doc.close()

        # Parse common fields
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        return {
            'raw_text': text,
            'lines': lines,
            'region': {
                'x': title_block_rect.x0,
                'y': title_block_rect.y0,
                'width': title_block_rect.width,
                'height': title_block_rect.height
            }
        }


# =============================================================================
# Convenience Functions
# =============================================================================

# Global instance
_pdf_tools: Optional[PDFTools] = None


def get_pdf_tools() -> PDFTools:
    """Get or create global PDFTools instance."""
    global _pdf_tools
    if _pdf_tools is None:
        _pdf_tools = PDFTools()
    return _pdf_tools


def extract_text(pdf_path: Union[str, Path], **kwargs) -> str:
    """Convenience function to extract text from PDF."""
    return get_pdf_tools().extract_text(pdf_path, **kwargs)


def ocr_page(pdf_path: Union[str, Path], page: int, **kwargs) -> OCRResult:
    """Convenience function to OCR a single page."""
    return get_pdf_tools().ocr_page(pdf_path, page, **kwargs)


def merge_pdfs(pdf_paths: List[Union[str, Path]], output_path: Union[str, Path]) -> Path:
    """Convenience function to merge PDFs."""
    return get_pdf_tools().merge_pdfs(pdf_paths, output_path)


def split_pdf(pdf_path: Union[str, Path], output_dir: Union[str, Path], **kwargs) -> List[Path]:
    """Convenience function to split PDF."""
    return get_pdf_tools().split_pdf(pdf_path, output_dir, **kwargs)


def get_pdf_info(pdf_path: Union[str, Path]) -> PDFInfo:
    """Convenience function to get PDF info."""
    return get_pdf_tools().get_info(pdf_path)
