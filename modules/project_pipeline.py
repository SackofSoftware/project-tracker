"""
Project Pipeline - Unified Document Organization and Analysis

Two-phase workflow:
1. ORGANIZE: Categorize and structure project documents
2. ANALYZE: Extract data from organized structure

This creates a standardized folder structure that makes analysis
more efficient and accurate.
"""

import os
import re
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, asdict
import asyncio

# Import existing modules
from modules.files.file_organizer import FileOrganizer
from modules.doc_classification.division_extractor import extract_divisions_from_pdf
from modules.doc_classification.drawing_discipline_identifier import (
    DISCIPLINE_CODES,
    extract_discipline_from_sheet_id
)

# Optional imports
try:
    from modules.csi import CSIService, get_section_info, categorize_section
    CSI_AVAILABLE = True
except ImportError:
    CSI_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


@dataclass
class OrganizationResult:
    """Result from document organization phase"""
    success: bool
    folders_created: List[str]
    files_organized: int
    files_by_category: Dict[str, int]
    specs_by_division: Dict[str, int]
    drawings_by_discipline: Dict[str, int]
    errors: List[str]
    timestamp: str


# Standard folder structure for organized projects
STANDARD_STRUCTURE = {
    'Specs': {
        'Division-08-Openings': 'Division 8 specifications (doors, windows, glazing)',
        'Division-01-General': 'General requirements',
        'Other-Divisions': 'Other specification divisions',
    },
    'Drawings': {
        'A-Architectural': 'Architectural drawings',
        'S-Structural': 'Structural drawings',
        'M-Mechanical': 'Mechanical/HVAC drawings',
        'E-Electrical': 'Electrical drawings',
        'P-Plumbing': 'Plumbing drawings',
        'C-Civil': 'Civil/Site drawings',
        'G-General': 'General/cover sheets',
        'Other': 'Other disciplines',
    },
    'Quotes': {
        'Received': 'Vendor quotes received',
        'Requests': 'Quote requests sent',
    },
    'Takeoffs': 'Quantity takeoffs and estimates',
    'Submittals': 'Product submittals and shop drawings',
    'RFIs': 'Requests for information',
    'Addenda': 'Contract addenda and bulletins',
    'Schedules': {
        'Door-Schedule': 'Door schedules',
        'Window-Schedule': 'Window schedules',
        'Hardware-Schedule': 'Hardware schedules',
    },
    'Extracted-Data': 'AI-extracted project data',
}


class ProjectPipeline:
    """
    Unified project document organization and analysis pipeline.

    Usage:
        pipeline = ProjectPipeline(project_folder)

        # Phase 1: Organize
        org_result = pipeline.organize(use_ai=True)

        # Phase 2: Analyze (runs on organized structure)
        analysis_result = await pipeline.analyze()
    """

    def __init__(self, project_folder: str,
                 stream_callback: Optional[Callable] = None):
        self.project_folder = Path(project_folder)
        self.stream_callback = stream_callback
        self.api_key = os.getenv("OPENROUTER_API_KEY")

        # Initialize sub-components
        self.file_organizer = FileOrganizer(project_folder, self.api_key)

        if CSI_AVAILABLE:
            self.csi_service = CSIService()
        else:
            self.csi_service = None

    def stream(self, phase: str, message: str, progress: float = 0.0, data: Dict = None):
        """Send progress update to UI"""
        if self.stream_callback:
            self.stream_callback({
                'phase': phase,
                'message': message,
                'progress': progress,
                'data': data
            })

    # ==================== PHASE 1: ORGANIZE ====================

    def create_folder_structure(self) -> List[str]:
        """Create standardized folder structure"""
        created = []

        def create_nested(base: Path, structure: dict):
            for name, content in structure.items():
                folder = base / name
                if not folder.exists():
                    folder.mkdir(parents=True)
                    created.append(str(folder.relative_to(self.project_folder)))

                if isinstance(content, dict):
                    create_nested(folder, content)

        create_nested(self.project_folder, STANDARD_STRUCTURE)
        return created

    def identify_spec_division(self, filepath: Path) -> Optional[str]:
        """Identify which CSI division a spec file belongs to"""
        filename_lower = filepath.name.lower()

        # Pattern: 08xxxx or 08 xx xx
        division_match = re.search(r'\b(0[1-9]|[1-4]\d)\s*\d{2}\s*\d{2}', filename_lower)
        if division_match:
            return division_match.group(1).strip()[:2]

        # Pattern: "division 8" or "div 08"
        div_match = re.search(r'div(?:ision)?\s*(\d{1,2})', filename_lower)
        if div_match:
            return div_match.group(1).zfill(2)

        # Try extracting from PDF content
        if PDFPLUMBER_AVAILABLE and filepath.suffix.lower() == '.pdf':
            try:
                with pdfplumber.open(filepath) as pdf:
                    if len(pdf.pages) > 0:
                        text = pdf.pages[0].extract_text() or ""
                        # Look for section numbers
                        sections = re.findall(r'\b(0[1-9]|[1-4]\d)\s*\d{2}\s*\d{2}', text)
                        if sections:
                            return sections[0][:2]
            except:
                pass

        return None

    def identify_drawing_discipline(self, filepath: Path) -> Optional[str]:
        """Identify drawing discipline from filename"""
        filename = filepath.stem.upper()

        # Pattern: A101, S-001, M.01, etc.
        match = re.match(r'^([A-Z]{1,2})[-_.\s]?\d', filename)
        if match:
            code = match.group(1)
            if code in DISCIPLINE_CODES:
                return code

        # Check for discipline keywords in filename
        filename_lower = filepath.name.lower()
        keyword_map = {
            'arch': 'A', 'architectural': 'A',
            'struct': 'S', 'structural': 'S',
            'mech': 'M', 'mechanical': 'M', 'hvac': 'M',
            'elec': 'E', 'electrical': 'E',
            'plumb': 'P', 'plumbing': 'P',
            'civil': 'C', 'site': 'C',
            'fire': 'FP', 'sprinkler': 'FP',
        }

        for keyword, code in keyword_map.items():
            if keyword in filename_lower:
                return code

        return None

    def organize(self, use_ai: bool = False, dry_run: bool = False) -> OrganizationResult:
        """
        Phase 1: Organize project documents into standardized structure.

        Args:
            use_ai: Use AI for files that can't be categorized by patterns
            dry_run: Don't actually move files, just report what would happen

        Returns:
            OrganizationResult with details of organization
        """
        self.stream('organize', 'Creating folder structure...', 0.1)

        errors = []
        files_organized = 0
        files_by_category = {}
        specs_by_division = {}
        drawings_by_discipline = {}

        # Create standard folders
        if not dry_run:
            folders_created = self.create_folder_structure()
        else:
            folders_created = list(STANDARD_STRUCTURE.keys())

        self.stream('organize', 'Scanning files...', 0.2)

        # Scan all files
        all_files = list(self.project_folder.rglob('*'))
        total_files = len([f for f in all_files if f.is_file()])

        # Skip files already in organized folders
        organized_prefixes = tuple(STANDARD_STRUCTURE.keys())

        for i, filepath in enumerate(all_files):
            if not filepath.is_file():
                continue

            # Skip hidden files and temp files
            if filepath.name.startswith('.') or filepath.name.startswith('~$'):
                continue

            # Skip files already in standard folders
            try:
                relative = filepath.relative_to(self.project_folder)
                if relative.parts[0] in STANDARD_STRUCTURE:
                    continue
            except ValueError:
                continue

            progress = 0.2 + (0.7 * (i / max(total_files, 1)))
            self.stream('organize', f'Processing: {filepath.name}', progress)

            try:
                dest_folder = None
                category = None
                subcategory = None

                ext = filepath.suffix.lower()
                filename_lower = filepath.name.lower()

                # Determine category and destination

                # SPECS: Check for spec documents
                if any(kw in filename_lower for kw in ['spec', 'division', 'section']) or \
                   re.search(r'\b\d{2}\s*\d{2}\s*\d{2}', filename_lower):
                    category = 'Specs'
                    division = self.identify_spec_division(filepath)

                    if division == '08':
                        subcategory = 'Division-08-Openings'
                        specs_by_division['08'] = specs_by_division.get('08', 0) + 1
                    elif division == '01':
                        subcategory = 'Division-01-General'
                        specs_by_division['01'] = specs_by_division.get('01', 0) + 1
                    else:
                        subcategory = 'Other-Divisions'
                        if division:
                            specs_by_division[division] = specs_by_division.get(division, 0) + 1

                # DRAWINGS: Check for drawing files
                elif ext in ['.pdf', '.dwg', '.dxf'] and \
                     (re.match(r'^[A-Z]{1,2}[-_.\s]?\d', filepath.stem.upper()) or
                      any(kw in filename_lower for kw in ['drawing', 'sheet', 'plan', 'elevation', 'detail'])):
                    category = 'Drawings'
                    discipline = self.identify_drawing_discipline(filepath)

                    discipline_folders = {
                        'A': 'A-Architectural', 'AD': 'A-Architectural', 'AI': 'A-Architectural',
                        'S': 'S-Structural',
                        'M': 'M-Mechanical', 'H': 'M-Mechanical',
                        'E': 'E-Electrical', 'EL': 'E-Electrical', 'EP': 'E-Electrical',
                        'P': 'P-Plumbing',
                        'C': 'C-Civil', 'L': 'C-Civil',
                        'G': 'G-General',
                        'FP': 'Other', 'F': 'Other',
                    }

                    subcategory = discipline_folders.get(discipline, 'Other')
                    if discipline:
                        drawings_by_discipline[discipline] = drawings_by_discipline.get(discipline, 0) + 1

                # SCHEDULES: Door/window/hardware schedules
                elif any(kw in filename_lower for kw in ['schedule', 'door sched', 'window sched', 'hardware']):
                    category = 'Schedules'
                    if 'door' in filename_lower:
                        subcategory = 'Door-Schedule'
                    elif 'window' in filename_lower:
                        subcategory = 'Window-Schedule'
                    elif 'hardware' in filename_lower:
                        subcategory = 'Hardware-Schedule'

                # QUOTES: Vendor quotes
                elif any(kw in filename_lower for kw in ['quote', 'pricing', 'proposal', 'bid']):
                    category = 'Quotes'
                    subcategory = 'Received'

                # TAKEOFFS: Quantity takeoffs
                elif any(kw in filename_lower for kw in ['takeoff', 'take-off', 'estimate', 'quantity']):
                    category = 'Takeoffs'

                # ADDENDA: Addenda and bulletins
                elif any(kw in filename_lower for kw in ['addend', 'bulletin', 'revision']):
                    category = 'Addenda'

                # RFIs
                elif 'rfi' in filename_lower:
                    category = 'RFIs'

                # SUBMITTALS
                elif any(kw in filename_lower for kw in ['submittal', 'shop drawing', 'cut sheet']):
                    category = 'Submittals'

                # Use AI for unknown files if enabled
                if category is None and use_ai:
                    ai_result = self.file_organizer._ai_categorize(filepath)
                    if ai_result and ai_result.get('category') != 'Unknown':
                        category = ai_result.get('category')

                # Move file if categorized
                if category and not dry_run:
                    if subcategory:
                        dest_folder = self.project_folder / category / subcategory
                    else:
                        dest_folder = self.project_folder / category

                    dest_folder.mkdir(parents=True, exist_ok=True)
                    dest_path = dest_folder / filepath.name

                    # Handle duplicates
                    if dest_path.exists():
                        base = filepath.stem
                        ext = filepath.suffix
                        counter = 1
                        while dest_path.exists():
                            dest_path = dest_folder / f"{base}_{counter}{ext}"
                            counter += 1

                    shutil.move(str(filepath), str(dest_path))
                    files_organized += 1

                if category:
                    files_by_category[category] = files_by_category.get(category, 0) + 1

            except Exception as e:
                errors.append(f"Error processing {filepath.name}: {str(e)}")

        self.stream('organize', 'Organization complete!', 1.0, {
            'files_organized': files_organized,
            'specs_by_division': specs_by_division,
            'drawings_by_discipline': drawings_by_discipline
        })

        return OrganizationResult(
            success=len(errors) == 0,
            folders_created=folders_created,
            files_organized=files_organized,
            files_by_category=files_by_category,
            specs_by_division=specs_by_division,
            drawings_by_discipline=drawings_by_discipline,
            errors=errors,
            timestamp=datetime.now().isoformat()
        )

    # ==================== PHASE 2: ANALYZE ====================

    async def analyze(self) -> Dict:
        """
        Phase 2: Analyze organized project documents.

        This runs AFTER organize() and benefits from the structured folders.
        Only analyzes Division 8 specs, architectural drawings, etc.
        """
        self.stream('analyze', 'Starting targeted analysis...', 0.0)

        result = {
            'meta': {
                'analyzed_at': datetime.now().isoformat(),
                'project_folder': str(self.project_folder),
            },
            'division_8': {},
            'schedules': {
                'doors': [],
                'windows': [],
                'storefronts': [],
            },
            'quotes': [],
            'csi_sections': [],
            'manufacturers': [],
            'errors': []
        }

        # Analyze Division 8 specs (from organized folder)
        div8_folder = self.project_folder / 'Specs' / 'Division-08-Openings'
        if div8_folder.exists():
            self.stream('analyze', 'Analyzing Division 8 specifications...', 0.2)

            for pdf in div8_folder.glob('*.pdf'):
                try:
                    divisions = extract_divisions_from_pdf(pdf, target_divisions=['08'])
                    if '08' in divisions:
                        content = divisions['08']
                        for section in content.sections:
                            section_info = {
                                'section_id': section.section_id,
                                'title': section.title,
                                'page': section.page,
                                'source_file': pdf.name
                            }

                            # Enrich with CSI data
                            if CSI_AVAILABLE and section.section_id:
                                csi_info = get_section_info(section.section_id)
                                section_info['csi_title'] = csi_info.get('title')
                                section_info['category'] = categorize_section(section.section_id)

                            result['csi_sections'].append(section_info)
                except Exception as e:
                    result['errors'].append(f"Error analyzing {pdf.name}: {str(e)}")

        # Analyze schedules (from organized folder)
        schedules_folder = self.project_folder / 'Schedules'
        if schedules_folder.exists():
            self.stream('analyze', 'Analyzing schedules...', 0.4)
            # TODO: Parse door/window schedules from PDFs

        # Analyze architectural drawings for schedules
        arch_folder = self.project_folder / 'Drawings' / 'A-Architectural'
        if arch_folder.exists():
            self.stream('analyze', 'Scanning architectural drawings...', 0.6)
            # TODO: Vision-based schedule extraction

        # Analyze quotes
        quotes_folder = self.project_folder / 'Quotes' / 'Received'
        if quotes_folder.exists():
            self.stream('analyze', 'Analyzing vendor quotes...', 0.8)
            # TODO: Extract quote data

        # Detect manufacturers from all analyzed content
        if CSI_AVAILABLE:
            all_text = json.dumps(result)
            from modules.csi import match_manufacturers
            result['manufacturers'] = match_manufacturers(all_text)

        # Save extracted data
        extracted_folder = self.project_folder / 'Extracted-Data'
        extracted_folder.mkdir(exist_ok=True)

        output_file = extracted_folder / 'extracted_project_data.json'
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)

        self.stream('analyze', 'Analysis complete!', 1.0, result)

        return result

    # ==================== FULL PIPELINE ====================

    async def run_full_pipeline(self, use_ai: bool = True) -> Dict:
        """
        Run the complete pipeline: Organize then Analyze.

        This is what the "Full AI Parse" button should trigger.
        """
        self.stream('pipeline', 'Starting full project pipeline...', 0.0)

        # Phase 1: Organize
        self.stream('pipeline', 'Phase 1: Organizing documents...', 0.1)
        org_result = self.organize(use_ai=use_ai)

        # Phase 2: Analyze
        self.stream('pipeline', 'Phase 2: Analyzing organized documents...', 0.5)
        analysis_result = await self.analyze()

        # Combine results
        full_result = {
            'organization': asdict(org_result),
            'analysis': analysis_result,
            'summary': {
                'files_organized': org_result.files_organized,
                'specs_found': sum(org_result.specs_by_division.values()),
                'div8_specs': org_result.specs_by_division.get('08', 0),
                'drawings_found': sum(org_result.drawings_by_discipline.values()),
                'arch_drawings': org_result.drawings_by_discipline.get('A', 0),
                'csi_sections': len(analysis_result.get('csi_sections', [])),
                'manufacturers': len(analysis_result.get('manufacturers', [])),
            }
        }

        self.stream('pipeline', 'Pipeline complete!', 1.0, full_result['summary'])

        return full_result


# Convenience function for running from API
def run_project_pipeline(project_folder: str,
                         stream_callback: Optional[Callable] = None,
                         use_ai: bool = True) -> Dict:
    """Run full pipeline synchronously (for API endpoints)"""
    pipeline = ProjectPipeline(project_folder, stream_callback)
    return asyncio.run(pipeline.run_full_pipeline(use_ai))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python project_pipeline.py <project_folder>")
        sys.exit(1)

    folder = sys.argv[1]

    def print_progress(data):
        print(f"[{data.get('phase', 'unknown')}] {data.get('message', '')} ({data.get('progress', 0)*100:.0f}%)")

    result = run_project_pipeline(folder, print_progress, use_ai=False)
    print("\n" + "="*60)
    print("SUMMARY:")
    print(json.dumps(result['summary'], indent=2))
