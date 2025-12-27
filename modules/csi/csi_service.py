"""
CSI Masterformat Service

Provides centralized access to CSI Masterformat data for the project-tracker application.
Supports section lookups, manufacturer detection, and scope enrichment with CSI descriptions.

Data Sources:
- CSI_Masterformat/Masterformat_Subsection_List.json (12,353 sections)
- CSI_Masterformat/division8_data/unified_products_database.json (667 products from 15 manufacturers)
"""

from pathlib import Path
import json
import re
from typing import Dict, List, Optional, Set
from functools import lru_cache


# Data directory paths
CSI_DATA_DIR = Path(__file__).parent.parent.parent / "CSI_Masterformat"
MASTERFORMAT_FILE = CSI_DATA_DIR / "Masterformat_Subsection_List.json"
PRODUCTS_FILE = CSI_DATA_DIR / "division8_data" / "unified_products_database.json"
DIVISION_LOOKUP_FILE = CSI_DATA_DIR / "specbook_division_lookup.json"


# Known Division 8 manufacturers (for text matching)
DIVISION8_MANUFACTURERS = [
    # Curtain Wall & Storefront
    "Kawneer", "YKK AP", "EFCO", "Oldcastle", "Tubelite", "Vistawall",
    "Wausau Window", "Wausau", "Traco", "Arcadia", "Manko",
    # Windows
    "Pella", "Marvin", "Andersen", "Milgard", "Kolbe", "Loewen",
    "Sierra Pacific", "Weather Shield", "Windsor", "Jeld-Wen",
    # Doors & Frames
    "Ceco", "Republic", "Steelcraft", "Curries", "Fleming", "Mesker",
    "Hollow Metal Xpress", "HMX", "SDI", "Security Door",
    # Hardware
    "Allegion", "Schlage", "LCN", "Von Duprin", "Falcon", "Ives",
    "Hager", "Stanley", "Dorma", "ASSA ABLOY", "Pemko", "NGP",
    "Zero International", "Rixson", "Sargent", "Corbin Russwin",
    # Glass & Glazing
    "Guardian", "PPG", "Vitro", "Pilkington", "Cardinal", "AGC",
    "Viracon", "Oldcastle BuildingEnvelope", "Saint-Gobain",
    # Specialty
    "Apogee", "Hope's", "Reilly", "Graham", "United States Aluminum"
]


def normalize_section_id(section_id: str) -> str:
    """
    Normalize a CSI section ID to standard format (XX XX XX).

    Args:
        section_id: Section ID in various formats (084113, 08 41 13, 08-41-13, etc.)

    Returns:
        Normalized section ID with spaces (e.g., "08 41 13")
    """
    if not section_id:
        return ""

    # Remove all non-numeric characters
    digits = re.sub(r'[^\d]', '', str(section_id))

    # Ensure we have exactly 6 digits
    if len(digits) < 6:
        digits = digits.ljust(6, '0')
    elif len(digits) > 6:
        digits = digits[:6]

    # Format as XX XX XX
    return f"{digits[:2]} {digits[2:4]} {digits[4:6]}"


@lru_cache(maxsize=1)
def load_masterformat_sections() -> Dict[str, str]:
    """
    Load and cache all CSI Masterformat sections.

    Returns:
        Dict mapping normalized section IDs to titles
    """
    sections = {}

    if MASTERFORMAT_FILE.exists():
        try:
            with open(MASTERFORMAT_FILE, 'r') as f:
                data = json.load(f)

            for item in data:
                section_num = item.get('subsection_number', '')
                title = item.get('subsection_title', '')

                if section_num:
                    # Store with normalized key
                    normalized = normalize_section_id(section_num)
                    sections[normalized] = title
        except Exception as e:
            print(f"Error loading masterformat sections: {e}")

    return sections


@lru_cache(maxsize=1)
def load_division_lookup() -> Dict[str, Dict]:
    """
    Load division title lookup table.

    Returns:
        Dict mapping division numbers to division info
    """
    if DIVISION_LOOKUP_FILE.exists():
        try:
            with open(DIVISION_LOOKUP_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading division lookup: {e}")

    # Fallback with Division 8
    return {
        "08": {"title": "Openings", "valid": True}
    }


@lru_cache(maxsize=1)
def load_products_database() -> Dict:
    """
    Load and cache the unified products database.

    Returns:
        Dict containing products and manufacturer info
    """
    if PRODUCTS_FILE.exists():
        try:
            with open(PRODUCTS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading products database: {e}")

    return {"products": [], "manufacturers": []}


def get_section_info(section_id: str) -> Dict:
    """
    Get detailed information for a CSI section.

    Args:
        section_id: CSI section number (e.g., "08 41 13" or "084113")

    Returns:
        Dict with section_id, title, division, division_title, parent info
    """
    sections = load_masterformat_sections()
    divisions = load_division_lookup()

    normalized = normalize_section_id(section_id)

    # Get division number (first 2 digits)
    division_num = normalized[:2] if normalized else ""
    division_info = divisions.get(division_num, {})

    # Get parent section (XX XX 00)
    parent_id = f"{normalized[:5]}00" if len(normalized) >= 5 else None

    return {
        'section_id': normalized,
        'title': sections.get(normalized, 'Unknown Section'),
        'division': division_num,
        'division_title': division_info.get('title', f'Division {division_num}'),
        'parent_section': parent_id,
        'parent_title': sections.get(parent_id, '') if parent_id else None,
        'is_valid': division_info.get('valid', True)
    }


def get_division8_sections() -> List[Dict]:
    """
    Get all Division 8 (Openings) sections.

    Returns:
        List of dicts with section_id and title for all Division 8 sections
    """
    sections = load_masterformat_sections()

    div8_sections = []
    for section_id, title in sections.items():
        if section_id.startswith('08'):
            div8_sections.append({
                'section_id': section_id,
                'title': title
            })

    # Sort by section number
    div8_sections.sort(key=lambda x: x['section_id'])
    return div8_sections


def enrich_scope_with_csi(scope_sections: List[Dict]) -> List[Dict]:
    """
    Add CSI descriptions to scope sections.

    Args:
        scope_sections: List of dicts with section_id or number fields

    Returns:
        Enriched list with csi_title and csi_info added
    """
    enriched = []

    for section in scope_sections:
        # Get section ID from various possible field names
        section_id = (
            section.get('section_id') or
            section.get('number') or
            section.get('section_number') or
            section.get('id', '')
        )

        if section_id:
            info = get_section_info(section_id)
            section = section.copy()  # Don't modify original
            section['csi_title'] = info['title']
            section['csi_division'] = info['division']
            section['csi_division_title'] = info['division_title']
            section['csi_parent'] = info['parent_title']

        enriched.append(section)

    return enriched


def match_manufacturers(text: str) -> List[Dict]:
    """
    Find manufacturer names mentioned in text.

    Args:
        text: Text to search for manufacturer names

    Returns:
        List of dicts with manufacturer name and product info
    """
    if not text:
        return []

    text_lower = text.lower()
    found = []
    products_db = load_products_database()

    for mfr in DIVISION8_MANUFACTURERS:
        mfr_lower = mfr.lower()

        # Check if manufacturer is mentioned
        if mfr_lower in text_lower:
            # Find products for this manufacturer from database
            mfr_products = [
                p for p in products_db.get('products', [])
                if p.get('manufacturer', '').lower() == mfr_lower
            ]

            found.append({
                'name': mfr,
                'product_count': len(mfr_products),
                'categories': list(set(
                    cat
                    for p in mfr_products
                    for cat in p.get('categories', [])
                )),
                'sample_products': [
                    p.get('name') for p in mfr_products[:5]
                ]
            })

    return found


def extract_section_references(text: str) -> List[str]:
    """
    Extract CSI section references from text.

    Args:
        text: Text that may contain section references

    Returns:
        List of normalized section IDs found
    """
    if not text:
        return []

    # Patterns for CSI section references
    patterns = [
        r'(?:SECTION|Section)\s+(\d{2}\s*\d{2}\s*\d{2})',  # SECTION 08 41 13
        r'\b(\d{2}\s*\d{2}\s*\d{2})\b',                     # 08 41 13 or 084113
        r'\b(\d{2}-\d{2}-\d{2})\b',                         # 08-41-13
    ]

    found = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            section = match.group(1)
            normalized = normalize_section_id(section)

            # Only include Division 8 sections
            if normalized.startswith('08'):
                found.add(normalized)

    return sorted(list(found))


def categorize_section(section_id: str) -> str:
    """
    Categorize a Division 8 section into a broad category.

    Args:
        section_id: Normalized section ID (e.g., "08 41 13")

    Returns:
        Category name (doors, windows, storefronts, glazing, hardware, other)
    """
    normalized = normalize_section_id(section_id)

    if not normalized.startswith('08'):
        return 'other'

    # Get the group number (middle 2 digits)
    group = normalized[3:5] if len(normalized) >= 5 else '00'

    # Categorize by CSI group
    if group in ['11', '12', '13', '14', '15', '16', '17', '18']:
        return 'doors'
    elif group in ['51', '52', '53', '54', '55', '56']:
        return 'windows'
    elif group in ['41', '42', '43', '44', '45', '46']:
        return 'storefronts'  # Includes curtain wall
    elif group in ['80', '81', '82', '83', '84', '85', '86', '87', '88']:
        return 'glazing'
    elif group in ['71', '74', '75', '76', '78', '79']:
        return 'hardware'
    else:
        return 'other'


class CSIService:
    """
    Consolidated CSI Masterformat service class.
    Provides all CSI operations through a single interface.
    """

    def __init__(self):
        """Initialize CSI service and preload data."""
        self._sections = None
        self._products = None
        self._divisions = None

    @property
    def sections(self) -> Dict[str, str]:
        """Lazy-load sections."""
        if self._sections is None:
            self._sections = load_masterformat_sections()
        return self._sections

    @property
    def products(self) -> Dict:
        """Lazy-load products database."""
        if self._products is None:
            self._products = load_products_database()
        return self._products

    @property
    def divisions(self) -> Dict:
        """Lazy-load division lookup."""
        if self._divisions is None:
            self._divisions = load_division_lookup()
        return self._divisions

    def get_section_info(self, section_id: str) -> Dict:
        """Get section info (delegates to module function)."""
        return get_section_info(section_id)

    def enrich_scope(self, sections: List[Dict]) -> List[Dict]:
        """Enrich scope sections with CSI data."""
        return enrich_scope_with_csi(sections)

    def match_manufacturers(self, text: str) -> List[Dict]:
        """Find manufacturers in text."""
        return match_manufacturers(text)

    def extract_sections(self, text: str) -> List[str]:
        """Extract section references from text."""
        return extract_section_references(text)

    def get_division8_sections(self) -> List[Dict]:
        """Get all Division 8 sections."""
        return get_division8_sections()

    def categorize(self, section_id: str) -> str:
        """Categorize a section."""
        return categorize_section(section_id)

    def get_products_for_manufacturer(self, manufacturer: str) -> List[Dict]:
        """Get products for a specific manufacturer."""
        mfr_lower = manufacturer.lower()
        return [
            p for p in self.products.get('products', [])
            if p.get('manufacturer', '').lower() == mfr_lower
        ]

    def get_stats(self) -> Dict:
        """Get statistics about loaded CSI data."""
        products_db = self.products
        div8_sections = [s for s in self.sections.keys() if s.startswith('08')]

        return {
            'total_sections': len(self.sections),
            'division8_sections': len(div8_sections),
            'total_products': len(products_db.get('products', [])),
            'total_manufacturers': len(DIVISION8_MANUFACTURERS),
            'data_loaded': True
        }


# Singleton instance for convenience
_service_instance: Optional[CSIService] = None


def get_csi_service() -> CSIService:
    """Get or create singleton CSI service instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CSIService()
    return _service_instance


if __name__ == "__main__":
    # Demo/test the service
    print("CSI Masterformat Service Demo")
    print("=" * 60)

    service = get_csi_service()

    # Stats
    stats = service.get_stats()
    print(f"\nData Statistics:")
    print(f"  Total sections: {stats['total_sections']}")
    print(f"  Division 8 sections: {stats['division8_sections']}")
    print(f"  Products in database: {stats['total_products']}")
    print(f"  Known manufacturers: {stats['total_manufacturers']}")

    # Section lookup
    print(f"\nSection Lookup Test:")
    test_sections = ["08 41 13", "084413", "08-80-00", "085113"]
    for s in test_sections:
        info = service.get_section_info(s)
        print(f"  {s} -> {info['section_id']}: {info['title']}")
        print(f"       Category: {service.categorize(s)}")

    # Manufacturer matching
    print(f"\nManufacturer Detection Test:")
    test_text = "The curtain wall system shall be Kawneer 1600 or YKK AP. Hardware by Allegion."
    matches = service.match_manufacturers(test_text)
    for m in matches:
        print(f"  {m['name']}: {m['product_count']} products")

    # Section extraction
    print(f"\nSection Extraction Test:")
    test_spec = "See Section 08 41 13 for storefronts and 084413 for curtain wall. Refer to 08 80 00 for glazing."
    sections = service.extract_sections(test_spec)
    for s in sections:
        info = service.get_section_info(s)
        print(f"  Found: {s} - {info['title']}")

    print("\n" + "=" * 60)
    print("Demo complete!")
