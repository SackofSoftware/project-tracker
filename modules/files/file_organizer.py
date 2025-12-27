"""
File Organizer
Intelligently categorizes and organizes project files using pattern matching and AI
"""

import os
import re
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import requests
import PyPDF2


class FileOrganizer:
    """Intelligent file organization for construction project folders"""

    # Standard folder structure for organized projects
    STANDARD_FOLDERS = {
        'Quotes': 'Vendor quotes and pricing documents',
        'Specs': 'Project specifications and requirements',
        'Drawings': 'Architectural and construction drawings',
        'Takeoffs': 'Quantity takeoffs and measurements',
        'Submittals': 'Product submittals and shop drawings',
        'RFIs': 'Requests for information',
        'Addenda': 'Contract addenda and modifications',
        'Correspondence': 'Emails and communications',
        'Photos': 'Project photos and documentation',
        'Contracts': 'Contracts and agreements',
        # Fallback categories - ensure EVERY file gets organized
        'Images': 'Image files (renderings, logos, photos)',
        'CAD-Files': 'CAD and BIM files (DWG, DXF, RVT)',
        'Documents': 'General documents (Word, text, etc)',
        'Spreadsheets': 'Excel and data files',
        'Archives': 'Compressed files (ZIP, RAR)',
        'Reference-Documents': 'General reference materials',
    }

    # File categorization patterns (filename-based)
    CATEGORY_PATTERNS = {
        'Quotes': [
            r'quote', r'pricing', r'proposal', r'bid\b', r'estimate',
            r'price\s*list', r'quotation', r'offer',
            # Vendor name patterns
            r'twi\s*supply', r'zenith', r'kawneer', r'oldcastle', r'tubelite',
            r'ykk', r'allegion', r'assa', r'stanley', r'crl', r'viracon',
            r'ppg', r'guardian', r'pella', r'marvin', r'andersen',
            r'alpen', r'inline', r'serious', r'loewen',
        ],
        'Specs': [
            r'spec', r'division\s*\d', r'section\s*\d', r'08\d{4}',
            r'requirements', r'specification', r'project\s*manual',
        ],
        'Drawings': [
            r'^[a-z]\d{3}', r'elevation', r'detail', r'plan\b', r'floor\s*plan',
            r'section', r'schedule', r'sheet', r'arch\s*set', r'dwg',
            r'drawings\.pdf$', r'drawing\s*set', r'arch\s*drawings', r'struct\s*drawings',
        ],
        'Takeoffs': [
            r'takeoff', r'take-off', r'quantity', r'count', r'measure',
            r'bluebeam', r'on-screen',
        ],
        'Submittals': [
            r'submittal', r'shop\s*draw', r'cut\s*sheet', r'product\s*data',
        ],
        'RFIs': [
            r'rfi', r'request\s*for\s*info',
        ],
        'Addenda': [
            r'addend', r'amendment', r'revision', r'bulletin',
        ],
        'Correspondence': [
            r'email', r'letter', r'memo', r'correspondence',
        ],
        'Contracts': [
            r'contract', r'subcontract', r'agreement', r'exhibit\s*[a-z]',
            r'coi\s*sample', r'insurance', r'certificate',
        ],
    }

    # File extensions by category - COMPREHENSIVE mapping
    # Every common file extension should map to a category
    EXTENSION_HINTS = {
        # CAD/BIM files
        'CAD-Files': ['.dwg', '.dxf', '.rvt', '.rfa', '.rte', '.rft', '.dwf', '.dwfx',
                      '.ifc', '.skp', '.3dm', '.nwd', '.nwc', '.nwf', '.pln', '.dgn'],
        # Image files (non-photo renders, logos, etc)
        'Images': ['.bmp', '.gif', '.tif', '.psd', '.ai', '.eps', '.svg', '.webp', '.ico'],
        # Photos
        'Photos': ['.jpg', '.jpeg', '.png', '.heic', '.heif', '.tiff', '.raw', '.cr2', '.nef', '.arw'],
        # Documents
        'Documents': ['.doc', '.docx', '.rtf', '.txt', '.odt', '.pages'],
        # Spreadsheets
        'Spreadsheets': ['.xls', '.xlsx', '.xlsm', '.csv', '.ods', '.numbers'],
        # Specs (Word docs often contain specs)
        'Specs': [],  # Pattern-based, not extension
        # Archives
        'Archives': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'],
        # Reference documents (PDFs handled specially)
        'Reference-Documents': ['.pdf'],  # Default for unclassified PDFs
    }

    # Extensions that should NEVER be organized (system files, temp files)
    SKIP_EXTENSIONS = ['.ds_store', '.db', '.ini', '.tmp', '.bak', '.swp', '.lock']

    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    MODEL = "amazon/nova-lite-v1"

    def __init__(self, project_folder: str, api_key: str = None):
        self.project_folder = Path(project_folder)
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.files_cache = {}
        self.categorization_cache = {}

    def _call_ai(self, prompt: str, content: str) -> Optional[str]:
        """Make API call for AI classification"""
        if not self.api_key:
            return None

        try:
            response = requests.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.MODEL,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": content}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return None
        except Exception as e:
            print(f"AI call failed: {e}")
            return None

    def _extract_pdf_preview(self, filepath: Path, max_chars: int = 2000) -> str:
        """Extract first portion of PDF text for AI analysis"""
        try:
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                if len(reader.pages) == 0:
                    return ""

                text = reader.pages[0].extract_text() or ""
                return text[:max_chars]
        except Exception:
            return ""

    def _pattern_categorize(self, filename: str) -> Optional[str]:
        """Categorize file using pattern matching"""
        filename_lower = filename.lower()

        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    return category

        return None

    def _extension_categorize(self, filepath: Path) -> Optional[str]:
        """Categorize file by extension"""
        ext = filepath.suffix.lower()

        for category, extensions in self.EXTENSION_HINTS.items():
            if ext in extensions:
                return category

        return None

    def _ai_categorize(self, filepath: Path) -> Optional[Dict]:
        """Use AI to categorize a file based on content"""
        if not self.api_key:
            return None

        filename = filepath.name
        content_preview = ""

        if filepath.suffix.lower() == '.pdf':
            content_preview = self._extract_pdf_preview(filepath)

        prompt = """You are a construction document classifier. Analyze the filename and content preview to categorize this file.

Categories:
- Quotes: Vendor quotes, pricing, proposals, bids from suppliers
- Specs: Project specifications, division documents (08xxxx numbers = openings/glazing)
- Drawings: Architectural drawings, plans, elevations, details, schedules
- Takeoffs: Quantity takeoffs, measurements, counts
- Submittals: Product submittals, shop drawings, cut sheets
- RFIs: Requests for information
- Addenda: Contract addenda, amendments
- Correspondence: Emails, letters, memos
- Contracts: Contracts, agreements
- Photos: Project photos
- Unknown: Cannot determine

Return ONLY a JSON object:
{"category": "CategoryName", "confidence": 0.0-1.0, "vendor_name": "if quote, vendor name or null", "reason": "brief explanation"}"""

        user_content = f"Filename: {filename}\n\nContent preview:\n{content_preview[:1500]}"

        result = self._call_ai(prompt, user_content)
        if not result:
            return None

        try:
            # Clean JSON
            result = result.strip()
            if result.startswith("```"):
                result = re.sub(r'^```\w*\n?', '', result)
                result = re.sub(r'\n?```$', '', result)

            return json.loads(result)
        except json.JSONDecodeError:
            return None

    def _get_fallback_category(self, filepath: Path) -> str:
        """Get fallback category based on file extension - ensures NO files are left uncategorized"""
        ext = filepath.suffix.lower()

        # Skip system/temp files
        if ext in self.SKIP_EXTENSIONS or filepath.name.lower() in ['.ds_store', 'thumbs.db']:
            return None  # Signal to skip this file entirely

        # Try extension mapping first
        for category, extensions in self.EXTENSION_HINTS.items():
            if ext in extensions:
                return category

        # Additional fallback mapping for less common extensions
        fallback_map = {
            # Presentation files
            '.ppt': 'Documents', '.pptx': 'Documents', '.key': 'Documents', '.odp': 'Documents',
            # Database files
            '.mdb': 'Documents', '.accdb': 'Documents', '.sqlite': 'Documents',
            # Video files
            '.mp4': 'Photos', '.mov': 'Photos', '.avi': 'Photos', '.mkv': 'Photos',
            # Audio files
            '.mp3': 'Reference-Documents', '.wav': 'Reference-Documents', '.m4a': 'Reference-Documents',
            # Email files
            '.msg': 'Correspondence', '.eml': 'Correspondence',
            # Log files
            '.log': 'Reference-Documents',
            # HTML files
            '.html': 'Reference-Documents', '.htm': 'Reference-Documents',
            # XML files
            '.xml': 'Reference-Documents',
            # JSON files
            '.json': 'Reference-Documents',
        }

        if ext in fallback_map:
            return fallback_map[ext]

        # Final fallback: Reference-Documents for anything else
        # This ensures ZERO files are left at root level
        return 'Reference-Documents'

    def scan_folder(self, include_subfolders: bool = True, use_ai: bool = False) -> Dict:
        """Scan project folder and categorize all files

        Args:
            include_subfolders: Whether to scan subdirectories
            use_ai: Whether to use AI for uncategorized files (slower but more accurate)

        NOTE: This method ensures EVERY file gets a category - no files are left as 'Unknown'.
        Files that don't match patterns get categorized by extension, with 'Reference-Documents'
        as the ultimate fallback.
        """
        files = []
        categorized = {cat: [] for cat in self.STANDARD_FOLDERS.keys()}
        uncategorized_for_ai = []
        skipped_files = []  # System/temp files we intentionally skip

        # Collect all files
        if include_subfolders:
            all_files = list(self.project_folder.rglob('*'))
        else:
            all_files = list(self.project_folder.glob('*'))

        for filepath in all_files:
            if not filepath.is_file():
                continue
            if filepath.name.startswith('.') or filepath.name.startswith('~$'):
                skipped_files.append(str(filepath))
                continue

            # Skip system/temp files by extension
            if filepath.suffix.lower() in self.SKIP_EXTENSIONS:
                skipped_files.append(str(filepath))
                continue

            # Skip files already in standard folders
            relative = filepath.relative_to(self.project_folder)
            parts = relative.parts

            # Skip files in system/cache folders (anywhere in path)
            skip_dirs = {'.chroma_local', '__pycache__', '.git', 'node_modules', 'Extracted-Data', 'Duplicates'}
            if any(part in skip_dirs for part in parts):
                skipped_files.append(str(filepath))
                continue

            if len(parts) > 1 and parts[0] in self.STANDARD_FOLDERS:
                # Already organized
                categorized[parts[0]].append({
                    'path': str(filepath),
                    'name': filepath.name,
                    'category': parts[0],
                    'method': 'already_organized',
                    'confidence': 1.0,
                    'size': filepath.stat().st_size,
                    'modified': datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
                })
                continue

            file_info = {
                'path': str(filepath),
                'name': filepath.name,
                'relative_path': str(relative),
                'size': filepath.stat().st_size,
                'modified': datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
                'extension': filepath.suffix.lower(),
            }

            # Try pattern matching first (highest confidence)
            category = self._pattern_categorize(filepath.name)
            if category:
                file_info['category'] = category
                file_info['method'] = 'pattern'
                file_info['confidence'] = 0.8
                categorized[category].append(file_info)
                continue

            # Try extension matching
            category = self._extension_categorize(filepath)
            if category:
                file_info['category'] = category
                file_info['method'] = 'extension'
                file_info['confidence'] = 0.6
                categorized[category].append(file_info)
                continue

            # Queue for AI categorization (PDFs only for now)
            if use_ai and filepath.suffix.lower() == '.pdf':
                uncategorized_for_ai.append(file_info)
            else:
                # FALLBACK: Use extension-based fallback - NEVER leave Unknown
                fallback = self._get_fallback_category(filepath)
                if fallback:
                    file_info['category'] = fallback
                    file_info['method'] = 'fallback'
                    file_info['confidence'] = 0.3
                    categorized[fallback].append(file_info)
                else:
                    # Only system files should reach here - skip them
                    skipped_files.append(str(filepath))

        # AI categorization for remaining files (only if use_ai=True)
        if use_ai:
            for file_info in uncategorized_for_ai:
                filepath = Path(file_info['path'])
                ai_result = self._ai_categorize(filepath)

                if ai_result and ai_result.get('category') in categorized:
                    file_info['category'] = ai_result['category']
                    file_info['method'] = 'ai'
                    file_info['confidence'] = ai_result.get('confidence', 0.7)
                    file_info['vendor_name'] = ai_result.get('vendor_name')
                    file_info['ai_reason'] = ai_result.get('reason')
                    categorized[ai_result['category']].append(file_info)
                else:
                    # AI failed - use fallback category (never leave Unknown)
                    fallback = self._get_fallback_category(filepath)
                    file_info['category'] = fallback or 'Reference-Documents'
                    file_info['method'] = 'ai_failed_fallback'
                    file_info['confidence'] = 0.2
                    categorized[file_info['category']].append(file_info)

        # Build summary - filter out empty categories
        non_empty_categories = {cat: files for cat, files in categorized.items() if files}

        summary = {
            'total_files': sum(len(files) for files in categorized.values()),
            'by_category': {cat: len(files) for cat, files in non_empty_categories.items()},
            'needs_organization': sum(
                len(files) for cat, files in categorized.items()
                if any(f.get('method') != 'already_organized' for f in files)
            ),
            'skipped_files': len(skipped_files),
            'files_at_root': sum(
                1 for cat, files in categorized.items()
                for f in files if f.get('method') != 'already_organized'
            ),
        }

        return {
            'categorized': non_empty_categories,
            'summary': summary,
            'project_folder': str(self.project_folder),
            'skipped': skipped_files,
        }

    def get_organization_plan(self, use_ai: bool = False) -> Dict:
        """Generate a plan for organizing files - ensures ALL files get moved

        Args:
            use_ai: Whether to use AI classification for better accuracy
        """
        scan_result = self.scan_folder(use_ai=use_ai)

        moves = []
        for category, files in scan_result['categorized'].items():
            # Process ALL categories - no more skipping

            target_folder = self.project_folder / category

            for file_info in files:
                if file_info.get('method') == 'already_organized':
                    continue

                source = Path(file_info['path'])
                target = target_folder / source.name

                # Handle duplicates in target
                if target.exists():
                    stem = target.stem
                    suffix = target.suffix
                    counter = 1
                    while target.exists():
                        target = target_folder / f"{stem}_{counter}{suffix}"
                        counter += 1

                moves.append({
                    'source': str(source),
                    'target': str(target),
                    'category': category,
                    'confidence': file_info.get('confidence', 0),
                    'method': file_info.get('method'),
                    'vendor_name': file_info.get('vendor_name'),
                })

        # Determine which folders need to be created
        categories_with_moves = set(m['category'] for m in moves)
        folders_to_create = [
            cat for cat in categories_with_moves
            if not (self.project_folder / cat).exists()
        ]

        return {
            'moves': moves,
            'total_moves': len(moves),
            'folders_to_create': folders_to_create,
            'scan_result': scan_result,
            'files_at_root_after': 0,  # Should always be 0 now!
        }

    def execute_organization(self, moves: List[Dict] = None, dry_run: bool = False) -> Dict:
        """Execute file organization moves"""
        if moves is None:
            plan = self.get_organization_plan()
            moves = plan['moves']

        results = {
            'moved': [],
            'errors': [],
            'folders_created': [],
        }

        # Create necessary folders
        folders_needed = set(Path(m['target']).parent for m in moves)
        for folder in folders_needed:
            if not folder.exists():
                if not dry_run:
                    folder.mkdir(parents=True, exist_ok=True)
                results['folders_created'].append(str(folder))

        # Execute moves
        for move in moves:
            source = Path(move['source'])
            target = Path(move['target'])

            try:
                if not dry_run:
                    shutil.move(str(source), str(target))
                results['moved'].append({
                    'source': move['source'],
                    'target': move['target'],
                    'category': move['category'],
                })
            except Exception as e:
                results['errors'].append({
                    'source': move['source'],
                    'error': str(e),
                })

        results['dry_run'] = dry_run
        results['total_moved'] = len(results['moved'])
        results['total_errors'] = len(results['errors'])

        return results

    def identify_quotes(self) -> List[Dict]:
        """Specifically identify and extract vendor quote information"""
        scan_result = self.scan_folder()
        quotes = scan_result['categorized'].get('Quotes', [])

        identified = []
        for quote_file in quotes:
            info = {
                'path': quote_file['path'],
                'filename': quote_file['name'],
                'vendor_name': quote_file.get('vendor_name'),
                'confidence': quote_file.get('confidence', 0),
                'method': quote_file.get('method'),
            }

            # Try to extract vendor name from filename if not already set
            if not info['vendor_name']:
                filename_lower = quote_file['name'].lower()
                vendor_patterns = [
                    (r'twi[\s_-]*supply', 'TWI Supply'),
                    (r'zenith', 'Zenith'),
                    (r'alpen', 'Alpen'),
                    (r'pella', 'Pella'),
                    (r'marvin', 'Marvin'),
                    (r'andersen', 'Andersen'),
                    (r'kawneer', 'Kawneer'),
                    (r'oldcastle', 'Oldcastle'),
                    (r'ykk', 'YKK'),
                ]
                for pattern, name in vendor_patterns:
                    if re.search(pattern, filename_lower):
                        info['vendor_name'] = name
                        break

            identified.append(info)

        return identified


def organize_project(project_folder: str, api_key: str = None, dry_run: bool = True) -> Dict:
    """Convenience function to organize a project folder"""
    organizer = FileOrganizer(project_folder, api_key)
    plan = organizer.get_organization_plan()

    if not dry_run:
        result = organizer.execute_organization(plan['moves'])
        return result

    return plan


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    # Get folder from args or env
    if len(sys.argv) > 1:
        test_folder = sys.argv[1]
    else:
        bidding_folder = os.getenv("BIDDING_FOLDER", "")
        if not bidding_folder:
            print("Error: Provide folder path as argument or set BIDDING_FOLDER in .env")
            sys.exit(1)
        # Use first project in bidding folder
        test_folder = str(next(Path(bidding_folder).iterdir()))

    organizer = FileOrganizer(test_folder)

    print("Scanning folder...")
    scan = organizer.scan_folder()

    print(f"\nSummary: {scan['summary']}")

    print("\nFiles by category:")
    for cat, files in scan['categorized'].items():
        if files:
            print(f"\n{cat} ({len(files)} files):")
            for f in files[:5]:  # Show first 5
                print(f"  - {f['name']} ({f.get('method', 'unknown')})")

    print("\nIdentified quotes:")
    quotes = organizer.identify_quotes()
    for q in quotes:
        print(f"  - {q['filename']} -> {q.get('vendor_name', 'Unknown vendor')}")
