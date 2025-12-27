"""
Stage 0 (Pre-Pipeline): Bid Invite Extraction

Extracts project metadata from Word documents (invite to bid, ITB, etc.)
that come from BuildingConnected, Procore, or other bid management systems.

This stage runs BEFORE the rename stage and populates extracted_project_data.json
with structured project information.
"""

import re
import json
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Try to import python-docx
try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx not installed. Word document extraction disabled.")


@dataclass
class StageResult:
    """Result from a pipeline stage"""
    success: bool
    data: Dict
    error: Optional[str] = None


class BidInviteExtractStage:
    """
    Stage 0: Bid Invite Extraction

    Parses Word documents (.docx) containing bid invitations from
    BuildingConnected, Procore, or other construction bid platforms.

    Extracts:
    - Project name
    - Location/address
    - Bid due date and time
    - General contractor info
    - Trade scope
    - Project description
    - Owner/architect info
    """

    # Patterns to identify bid invite documents
    BID_INVITE_PATTERNS = [
        r'invite',
        r'invitation',
        r'itb',
        r'rfp',
        r'request\s*for',
        r'bid\s*request',
        r'subcontract',
    ]

    # Field extraction patterns (BuildingConnected format)
    FIELD_PATTERNS = {
        'gc_name': [
            r'^([A-Z][A-Za-z\s&\-\.]+(?:Construction|Contracting|Builders|Inc|LLC|Corp))',
            r'(?:OK|Contact)\s*$',  # Line before "OK" button is usually GC name
        ],
        'project_name': [
            r'Project\s*Name\s*[:\n]?\s*(.+)',
            r'(?:^|\n)([A-Z][A-Za-z0-9\s\-\&\.]+(?:Housing|Building|Center|School|Hospital|Facility|Project|Renovation|Construction))',
        ],
        'location': [
            r'Location\s*[:\n]?\s*(.+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Way|Lane|Ln).*)',
            r'(\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd).*?(?:MA|CT|RI|NH|VT|ME|NY)\s*\d{5})',
        ],
        'bid_date': [
            r'(?:Date\s*Due|Bid\s*Due|Due\s*Date)[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
            r'(?:Date\s*Due|Bid\s*Due)[:\s]*(\d{1,2}/\d{1,2}/\d{4})',
        ],
        'bid_time': [
            r'(?:at|@)\s*(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)\s*(?:EST|PST|CST|EDT)?)',
            r'(\d{1,2}:\d{2}\s*(?:AM|PM))',
        ],
        'trade': [
            r'Trade\s*Name\(?s?\)?[:\s]*(.+)',
            r'Scope\s*(?:of\s*Work)?[:\s]*(.+)',
        ],
        'invited_date': [
            r'(?:Invited\s*on|Date\s*Invited)[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
        ],
    }

    def __init__(self, project_folder: Path, ai_provider=None):
        self.project_folder = Path(project_folder)
        self.ai = ai_provider  # Optional, not required for this stage

    async def run(self) -> StageResult:
        """Execute the bid invite extraction stage"""
        if not DOCX_AVAILABLE:
            return StageResult(
                success=False,
                data={},
                error="python-docx not installed"
            )

        try:
            # Step 1: Find bid invite documents
            docx_files = self._find_bid_invites()
            if not docx_files:
                logger.info(f"[BidInvite] No bid invite documents found in {self.project_folder.name}")
                return StageResult(
                    success=True,
                    data={"message": "No bid invite documents found"},
                    error=None
                )

            logger.info(f"[BidInvite] Found {len(docx_files)} potential bid invite document(s)")

            # Step 2: Extract data from each document
            all_data = {}
            for docx_path in docx_files:
                logger.info(f"[BidInvite] Processing: {docx_path.name}")
                extracted = self._extract_from_docx(docx_path)
                if extracted:
                    # Merge data (later documents can override earlier)
                    all_data.update(extracted)

            if not all_data:
                return StageResult(
                    success=True,
                    data={"message": "Could not extract structured data from documents"},
                    error=None
                )

            # Step 3: Normalize and save extracted data
            normalized = self._normalize_extracted_data(all_data)

            # Step 4: Write to extracted_project_data.json
            output_path = self.project_folder / "extracted_project_data.json"
            existing_data = {}
            if output_path.exists():
                try:
                    with open(output_path, 'r') as f:
                        existing_data = json.load(f)
                except:
                    pass

            # Merge with existing data (bid invite data takes precedence for certain fields)
            merged_data = self._merge_with_existing(existing_data, normalized)

            with open(output_path, 'w') as f:
                json.dump(merged_data, f, indent=2)

            logger.info(f"[BidInvite] Saved extracted data to {output_path.name}")

            return StageResult(
                success=True,
                data={
                    "documents_processed": len(docx_files),
                    "fields_extracted": list(normalized.keys()),
                    "project_name": normalized.get('project_name', ''),
                    "bid_date": normalized.get('bid_date', ''),
                    "gc_name": normalized.get('gc_name', ''),
                }
            )

        except Exception as e:
            logger.error(f"[BidInvite] Error: {e}")
            return StageResult(
                success=False,
                data={},
                error=str(e)
            )

    def _find_bid_invites(self) -> List[Path]:
        """Find Word documents that might be bid invites"""
        docx_files = list(self.project_folder.rglob("*.docx"))

        # Filter out temp files (start with ~$)
        docx_files = [f for f in docx_files if not f.name.startswith('~$')]

        # Prioritize files with bid-invite-related names
        prioritized = []
        others = []

        for docx_path in docx_files:
            name_lower = docx_path.stem.lower()
            is_bid_invite = any(
                re.search(pattern, name_lower, re.IGNORECASE)
                for pattern in self.BID_INVITE_PATTERNS
            )
            if is_bid_invite:
                prioritized.append(docx_path)
            else:
                others.append(docx_path)

        return prioritized + others

    def _extract_from_docx(self, docx_path: Path) -> Dict:
        """Extract structured data from a Word document"""
        try:
            doc = Document(str(docx_path))

            # Get all text from paragraphs
            full_text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())

            # Try to identify if this is a BuildingConnected format
            is_bc_format = self._is_buildingconnected_format(full_text)

            if is_bc_format:
                return self._parse_buildingconnected_format(full_text)
            else:
                return self._parse_generic_format(full_text)

        except Exception as e:
            logger.error(f"Error reading {docx_path.name}: {e}")
            return {}

    def _is_buildingconnected_format(self, text: str) -> bool:
        """Check if document follows BuildingConnected format"""
        bc_indicators = [
            'BuildingConnected',
            'Invited on',
            'Date Due',
            'Job Walk',
            'RFIs Due',
            'Expected Start',
            'Project Information',
            'Trade Name(s)',
        ]
        matches = sum(1 for ind in bc_indicators if ind.lower() in text.lower())
        return matches >= 3

    def _parse_buildingconnected_format(self, text: str) -> Dict:
        """Parse BuildingConnected invite format"""
        data = {}
        lines = text.split('\n')

        # Parse line by line to find key fields
        current_section = None

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            # Check for section headers
            if 'Project Details' in line:
                current_section = 'project_details'
            elif 'General info' in line:
                current_section = 'general_info'
            elif 'Related organizations' in line:
                current_section = 'organizations'
            elif 'Project Information' in line or 'Project information' in line:
                current_section = 'description'

            # Extract GC name (in BuildingConnected format, it's the line before "OK")
            if i < 15 and not data.get('gc_name'):
                # Check if next line is "OK" - that means current line is GC name
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if next_line == 'OK' and line not in ['Client', 'Bidding to multiple clients? Add opportunity »']:
                    data['gc_name'] = line.strip()
                # Also check for company name patterns as fallback
                elif re.search(r'(Construction|Contracting|Builders|Improvement|Inc|LLC|Corp)\b', line, re.IGNORECASE):
                    if not line.startswith('Bidding'):
                        data['gc_name'] = line.strip()

            # Extract contact info
            if '@' in line and '.com' in line:
                data['gc_email'] = line.strip()
            if re.search(r'\+?1?\s*[\d\-\(\)]{10,}', line):
                phone_match = re.search(r'(\+?1?\s*[\d\-\(\)ext\.\s]{10,})', line)
                if phone_match:
                    data['gc_phone'] = phone_match.group(1).strip()

            # Extract specific fields
            if 'Date Due' in line:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if next_line and next_line != '--':
                    data['bid_date_raw'] = next_line

            if 'Date Invited' in line:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if next_line and next_line != '--':
                    data['invited_date'] = next_line

            if 'Project Name' in line:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if next_line:
                    data['project_name'] = next_line

            if 'Trade Name' in line:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if next_line:
                    data['trade'] = next_line

            if 'Location' in line and current_section in ['general_info', None]:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if next_line and next_line != '--':
                    data['location'] = next_line

            if 'Project Size' in line:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if next_line and next_line != '--':
                    data['project_size'] = next_line

            if 'Architect' in line and current_section == 'organizations':
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if next_line and next_line != '--':
                    data['architect'] = next_line

            if 'Property Owner' in line:
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
                if next_line and next_line != '--':
                    data['owner'] = next_line

        # Extract description (usually after "Project Information" header)
        desc_match = re.search(
            r'Project Information\s*\n(.+?)(?="\s*funding|Trade Specific|Related organizations|$)',
            text,
            re.DOTALL | re.IGNORECASE
        )
        if desc_match:
            data['description'] = desc_match.group(1).strip()

        # Extract funding note
        funding_match = re.search(r'"([^"]*funding[^"]*)"', text, re.IGNORECASE)
        if funding_match:
            data['funding_note'] = funding_match.group(1)

        return data

    def _parse_generic_format(self, text: str) -> Dict:
        """Parse generic bid invite format using regex patterns"""
        data = {}

        for field, patterns in self.FIELD_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                if match:
                    value = match.group(1).strip() if match.groups() else match.group(0).strip()
                    if value and value != '--':
                        data[field] = value
                        break

        return data

    def _normalize_extracted_data(self, data: Dict) -> Dict:
        """Normalize extracted data to standard format"""
        normalized = {
            'source': 'bid_invite',
            'extracted_at': datetime.now().isoformat(),
        }

        # Project name
        if data.get('project_name'):
            normalized['project_name'] = data['project_name']
            normalized['title'] = data['project_name']

        # Location parsing
        if data.get('location'):
            location = data['location']
            normalized['location'] = location

            # Try to parse address components
            # Pattern: 123 Main St, City, ST 12345, Country
            addr_match = re.match(
                r'(.+?),\s*([A-Za-z\s]+),\s*([A-Z]{2})\s*(\d{5})?',
                location
            )
            if addr_match:
                normalized['address'] = addr_match.group(1).strip()
                normalized['city'] = addr_match.group(2).strip()
                normalized['state'] = addr_match.group(3).strip()
                if addr_match.group(4):
                    normalized['zip'] = addr_match.group(4)

        # Bid date parsing
        if data.get('bid_date_raw'):
            raw_date = data['bid_date_raw']
            normalized['bid_date_raw'] = raw_date

            # Parse "Dec 18, 2025 at 10:00 AM EST"
            date_match = re.match(
                r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})(?:\s+at\s+(\d{1,2}:\d{2}\s*(?:AM|PM)?\s*(?:EST|PST|CST|EDT)?))?',
                raw_date
            )
            if date_match:
                month_str = date_match.group(1)
                day = date_match.group(2)
                year = date_match.group(3)

                # Convert month name to number
                month_map = {
                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                }
                month = month_map.get(month_str[:3].lower(), '01')
                normalized['bid_date'] = f"{year}-{month}-{day.zfill(2)}"

                if date_match.group(4):
                    normalized['bid_time'] = date_match.group(4)

        # GC info
        if data.get('gc_name'):
            normalized['general_contractor'] = data['gc_name']
        if data.get('gc_email'):
            normalized['gc_email'] = data['gc_email']
        if data.get('gc_phone'):
            normalized['gc_phone'] = data['gc_phone']

        # Trade/scope
        if data.get('trade'):
            normalized['trade'] = data['trade']
            # Add to matching_trades list format
            normalized['matching_trades'] = [data['trade']]

        # Description
        if data.get('description'):
            normalized['description'] = data['description']

        # Other fields
        for field in ['architect', 'owner', 'project_size', 'funding_note', 'invited_date']:
            if data.get(field):
                normalized[field] = data[field]

        return normalized

    def _merge_with_existing(self, existing: Dict, new_data: Dict) -> Dict:
        """Merge new extracted data with existing project data"""
        merged = existing.copy()

        # Fields where bid invite data should take precedence
        priority_fields = [
            'project_name', 'title', 'location', 'address', 'city', 'state', 'zip',
            'bid_date', 'bid_time', 'general_contractor', 'gc_email', 'gc_phone',
            'description', 'trade', 'matching_trades', 'owner', 'architect',
        ]

        for field in priority_fields:
            if new_data.get(field):
                merged[field] = new_data[field]

        # Preserve existing fields that aren't in new data
        for key, value in new_data.items():
            if key not in merged:
                merged[key] = value

        # Update metadata
        merged['bid_invite_extracted'] = True
        merged['bid_invite_extracted_at'] = new_data.get('extracted_at')

        return merged


# Utility function for standalone extraction
def extract_bid_invite_data(project_folder: Path) -> Dict:
    """
    Extract bid invite data from a project folder.

    Args:
        project_folder: Path to project folder

    Returns:
        Dict with extracted project metadata
    """
    import asyncio

    stage = BidInviteExtractStage(project_folder)
    result = asyncio.run(stage.run())

    if result.success:
        # Read back the saved data
        output_path = project_folder / "extracted_project_data.json"
        if output_path.exists():
            with open(output_path, 'r') as f:
                return json.load(f)

    return result.data


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 stage_bid_invite_extract.py <project_folder>")
        sys.exit(1)

    project_folder = Path(sys.argv[1])

    if not project_folder.exists():
        print(f"Error: Folder does not exist: {project_folder}")
        sys.exit(1)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print(f"Extracting bid invite data from: {project_folder}")
    data = extract_bid_invite_data(project_folder)

    print("\nExtracted data:")
    print(json.dumps(data, indent=2))
