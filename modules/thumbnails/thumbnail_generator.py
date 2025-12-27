"""
Project Thumbnail Generator
Extracts cover page from drawing set PDFs in project folder as thumbnail
"""

import os
import subprocess
import hashlib
import re
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor


class ThumbnailGenerator:
    """Generates thumbnails from project PDF cover sheets"""

    # Patterns that indicate a PDF is likely a drawing set
    DRAWING_PATTERNS = [
        r'drawing', r'plan', r'bid\s*set', r'sheet', r'architectural',
        r'elevat', r'floor', r'detail', r'cover', r'A-\d', r'A\d{3}',
        r'combined', r'full\s*set', r'construction\s*doc', r'cd\s*set'
    ]

    # Patterns that indicate NOT a drawing set (specs, addenda, etc)
    EXCLUDE_PATTERNS = [
        r'spec', r'addend', r'rfi', r'submittal', r'manual', r'bid\s*form',
        r'wage', r'insurance', r'bond', r'contract', r'general\s*condition',
        r'front\s*end', r'div\d', r'section\s*\d'
    ]

    def __init__(self, cache_dir: str, thumbnail_width: int = 400):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_width = thumbnail_width
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._generating = set()
        self._lock = threading.Lock()

    def get_thumbnail_path(self, project_folder: str) -> Optional[Path]:
        """Get cached thumbnail path if it exists"""
        thumb_name = self._get_cache_name(project_folder)
        thumb_path = self.cache_dir / thumb_name
        if thumb_path.exists():
            return thumb_path
        return None

    def _get_cache_name(self, project_folder: str) -> str:
        """Generate consistent cache filename for project"""
        folder_hash = hashlib.md5(project_folder.encode()).hexdigest()[:12]
        return f"{folder_hash}.jpg"

    def _get_pdf_info(self, pdf_path: Path) -> Dict:
        """Get PDF metadata including page count and dimensions"""
        info = {
            'path': pdf_path,
            'size': 0,
            'page_count': 0,
            'is_drawing_size': False,
            'name_score': 0
        }

        try:
            info['size'] = pdf_path.stat().st_size

            # Get page count using pdfinfo
            result = subprocess.run(
                ['pdfinfo', str(pdf_path)],
                capture_output=True,
                text=True,
                timeout=10
            )

            for line in result.stdout.split('\n'):
                if line.startswith('Pages:'):
                    info['page_count'] = int(line.split(':')[1].strip())
                elif line.startswith('Page size:'):
                    # Parse page dimensions (e.g., "792 x 612 pts (letter)")
                    # Large format drawings are typically > 1000 pts in one dimension
                    dims = re.findall(r'(\d+\.?\d*)\s*x\s*(\d+\.?\d*)', line)
                    if dims:
                        width, height = float(dims[0][0]), float(dims[0][1])
                        # ARCH D is ~2592x1728 pts, letter is 612x792 pts
                        if max(width, height) > 1000:
                            info['is_drawing_size'] = True

        except (subprocess.TimeoutExpired, Exception) as e:
            pass

        # Score the filename
        name_lower = pdf_path.name.lower()

        # Add points for drawing patterns
        for pattern in self.DRAWING_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                info['name_score'] += 10

        # Subtract points for exclude patterns
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, name_lower, re.IGNORECASE):
                info['name_score'] -= 15

        return info

    def find_best_drawing_pdf(self, project_path: Path) -> Optional[Path]:
        """Find the best PDF for thumbnail (should be a drawing set with cover sheet)"""
        if not project_path.exists():
            return None

        # Collect all PDFs with their info
        pdf_candidates: List[Tuple[Path, Dict]] = []

        for pdf in project_path.rglob("*.pdf"):
            try:
                info = self._get_pdf_info(pdf)

                # Skip very small files (< 500KB probably not a drawing set)
                if info['size'] < 500 * 1024:
                    continue

                # Calculate a score for this PDF
                score = 0

                # Prefer PDFs with many pages (drawing sets have 10+ pages)
                if info['page_count'] >= 10:
                    score += 30
                elif info['page_count'] >= 5:
                    score += 15
                elif info['page_count'] == 0:
                    # Couldn't get page count, use size as proxy
                    if info['size'] > 10 * 1024 * 1024:  # > 10MB
                        score += 20

                # Prefer large format pages (actual drawings)
                if info['is_drawing_size']:
                    score += 25

                # Add filename score
                score += info['name_score']

                # Size bonus for large files (likely more drawings)
                if info['size'] > 50 * 1024 * 1024:  # > 50MB
                    score += 15
                elif info['size'] > 20 * 1024 * 1024:  # > 20MB
                    score += 10

                # PDFs in "Drawings" subfolder get a boost
                if 'drawing' in str(pdf.parent).lower():
                    score += 20

                info['final_score'] = score
                pdf_candidates.append((pdf, info))

            except OSError:
                continue

        if not pdf_candidates:
            return None

        # Sort by score descending
        pdf_candidates.sort(key=lambda x: x[1]['final_score'], reverse=True)

        # Return the best candidate
        best = pdf_candidates[0]
        return best[0]

    def _extract_cover_image(self, pdf_path: Path, thumb_path: Path) -> bool:
        """Try to extract largest embedded image from cover page using PyMuPDF"""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(pdf_path))
            if len(doc) == 0:
                return False

            # Check first page for images
            page = doc[0]
            images = page.get_images(full=True)

            if not images:
                doc.close()
                return False

            # Find the largest image (by area)
            best_image = None
            best_area = 0

            for img_info in images:
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue

                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)
                    area = width * height

                    # Skip tiny images (icons, logos < 100x100)
                    if width < 100 or height < 100:
                        continue

                    # Prefer images that are reasonably sized for a cover
                    if area > best_area:
                        best_area = area
                        best_image = base_image
                except Exception:
                    continue

            doc.close()

            if not best_image or best_area < 10000:  # < 100x100 effective
                return False

            # Save the image
            image_data = best_image["image"]
            ext = best_image.get("ext", "png")

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                tmp.write(image_data)
                tmp_path = tmp.name

            # Resize using sips (macOS native)
            subprocess.run(
                ["sips", "-Z", str(self.thumbnail_width), tmp_path,
                 "--out", str(thumb_path)],
                capture_output=True,
                timeout=10
            )

            os.unlink(tmp_path)
            return thumb_path.exists()

        except ImportError:
            return False  # PyMuPDF not installed
        except Exception as e:
            print(f"Error extracting cover image: {e}")
            return False

    def _render_pdf_page(self, pdf_path: Path, thumb_path: Path) -> bool:
        """Fallback: Render first page of PDF using pdftoppm"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_png = Path(tmpdir) / "page"

            # Extract first page only (-f 1 -l 1) at 72 DPI
            result = subprocess.run(
                ["pdftoppm", "-jpeg", "-f", "1", "-l", "1", "-r", "72",
                 str(pdf_path), str(tmp_png)],
                capture_output=True,
                timeout=30
            )

            # pdftoppm creates page-1.jpg or page-01.jpg
            tmp_image = Path(tmpdir) / "page-1.jpg"
            if not tmp_image.exists():
                tmp_image = Path(tmpdir) / "page-01.jpg"
                if not tmp_image.exists():
                    # Try to find any jpg created
                    jpgs = list(Path(tmpdir).glob("*.jpg"))
                    if jpgs:
                        tmp_image = jpgs[0]
                    else:
                        return False

            # Resize using sips (macOS native)
            subprocess.run(
                ["sips", "-Z", str(self.thumbnail_width), str(tmp_image),
                 "--out", str(thumb_path)],
                capture_output=True,
                timeout=10
            )

            return thumb_path.exists()

    def generate_thumbnail(self, project_folder: str, project_path: str, force: bool = False) -> Optional[str]:
        """Generate thumbnail synchronously - returns path to thumbnail"""
        thumb_name = self._get_cache_name(project_folder)
        thumb_path = self.cache_dir / thumb_name

        # Return cached if exists and not forcing
        if thumb_path.exists() and not force:
            return str(thumb_path)

        # Check if already generating
        with self._lock:
            if project_folder in self._generating:
                return None
            self._generating.add(project_folder)

        try:
            project_path = Path(project_path)
            pdf_file = self.find_best_drawing_pdf(project_path)

            if not pdf_file:
                return None

            # First try: Extract embedded image from cover page (faster, cleaner)
            if self._extract_cover_image(pdf_file, thumb_path):
                return str(thumb_path)

            # Fallback: Render the PDF page
            if self._render_pdf_page(pdf_file, thumb_path):
                return str(thumb_path)

        except subprocess.TimeoutExpired:
            print(f"Timeout generating thumbnail for {project_folder}")
        except Exception as e:
            print(f"Error generating thumbnail for {project_folder}: {e}")
        finally:
            with self._lock:
                self._generating.discard(project_folder)

        return None

    def generate_thumbnail_async(self, project_folder: str, project_path: str) -> None:
        """Queue thumbnail generation in background"""
        thumb_path = self.get_thumbnail_path(project_folder)
        if thumb_path:
            return  # Already cached

        # Submit to thread pool
        self._executor.submit(self.generate_thumbnail, project_folder, project_path)

    def get_or_generate(self, project_folder: str, project_path: str) -> Optional[str]:
        """Get cached thumbnail or start generation"""
        thumb_path = self.get_thumbnail_path(project_folder)
        if thumb_path:
            return str(thumb_path)

        self.generate_thumbnail_async(project_folder, project_path)
        return None

    def get_all_cached(self) -> Dict[str, str]:
        """Get all cached thumbnails"""
        thumbnails = {}
        for thumb in self.cache_dir.glob("*.jpg"):
            thumbnails[thumb.stem] = str(thumb)
        return thumbnails

    def clear_cache(self):
        """Clear all cached thumbnails"""
        for thumb in self.cache_dir.glob("*.jpg"):
            thumb.unlink()


# Module-level singleton
_generator = None


def get_thumbnail_generator(cache_dir: str = None) -> ThumbnailGenerator:
    """Get or create the global thumbnail generator"""
    global _generator
    if _generator is None:
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "static" / "thumbnails"
        _generator = ThumbnailGenerator(str(cache_dir))
    return _generator


if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) > 1:
        project_path = sys.argv[1]
        gen = ThumbnailGenerator("/tmp/thumb_test")

        # Find best PDF
        best_pdf = gen.find_best_drawing_pdf(Path(project_path))
        print(f"Best PDF found: {best_pdf}")

        if best_pdf:
            result = gen.generate_thumbnail(
                Path(project_path).name,
                project_path,
                force=True
            )
            print(f"Generated: {result}")
