"""
CSI Tagging for Division 8 - Business-Focused Tags

Maps CSI MasterFormat sections to clean, practical tag names that match
how Division 8 contractors actually talk about their work.

Tag names are short, clear, and match bid/estimate categories.
"""

from typing import Dict, List, Set, Tuple
import re

# Import from existing CSI service
from .csi_service import (
    CSIService,
    get_section_info,
    extract_section_references,
    categorize_section,
    normalize_section_id
)


# =============================================================================
# BUSINESS-FOCUSED TAG MAPPING
# =============================================================================
# Maps CSI sections to clean, practical tag names
# Format: "XX XX XX": "Tag Name"

CSI_TO_TAG = {
    # -------------------------------------------------------------------------
    # DOORS
    # -------------------------------------------------------------------------
    # Hollow Metal / Interior Doors
    "08 11 00": "Hollow Metal Doors",
    "08 11 13": "Hollow Metal Doors",      # HM Doors
    "08 11 16": "Aluminum Doors",          # Aluminum Doors
    "08 11 19": "Stainless Doors",         # Stainless Steel Doors
    "08 11 63": "Detention Doors",         # Detention Doors
    
    # Metal Frames
    "08 12 00": "Hollow Metal Frames",
    "08 12 13": "Hollow Metal Frames",
    "08 12 16": "Aluminum Frames",
    
    # Wood Doors
    "08 14 00": "Wood Doors",
    "08 14 16": "Wood Doors",              # Flush Wood Doors
    "08 14 23": "Wood Doors",              # Clad Wood Doors
    "08 14 33": "Wood Doors",              # Stile and Rail Wood Doors
    
    # Plastic/FRP Doors
    "08 15 00": "FRP Doors",
    "08 15 13": "FRP Doors",
    
    # Composite Doors  
    "08 16 00": "Composite Doors",
    "08 16 13": "Fiberglass Doors",
    
    # Integrated Assemblies
    "08 17 00": "Integrated Door Assemblies",
    
    # -------------------------------------------------------------------------
    # SPECIALTY DOORS
    # -------------------------------------------------------------------------
    "08 31 00": "Access Doors",
    "08 31 13": "Access Doors",
    
    "08 32 00": "Sliding Glass Doors",
    "08 32 13": "Sliding Glass Doors",
    
    "08 33 00": "Coiling Doors",
    "08 33 13": "Coiling Doors",
    "08 33 23": "Overhead Coiling Doors",
    "08 33 53": "Security Grilles",
    
    "08 34 00": "Special Function Doors",
    "08 34 13": "Cold Storage Doors",
    "08 34 36": "Darkroom Doors",
    "08 34 53": "Security Doors",
    "08 34 56": "Detention Doors",
    "08 34 59": "Vault Doors",
    "08 34 73": "Sound Control Doors",
    
    "08 35 00": "Folding Doors",
    "08 35 13": "Folding Doors",
    
    "08 36 00": "Panel Doors",
    "08 36 13": "Sectional Doors",
    
    "08 38 00": "Traffic Doors",
    "08 38 13": "Traffic Doors",
    
    "08 39 00": "Pressure-Resistant Doors",
    "08 39 53": "Blast-Resistant Doors",
    "08 39 63": "Bullet-Resistant Doors",
    
    # -------------------------------------------------------------------------
    # ENTRANCES & STOREFRONTS
    # -------------------------------------------------------------------------
    "08 41 00": "Storefront",
    "08 41 13": "Storefront",              # Aluminum-Framed Entrances
    "08 41 19": "Storefront",              # Stainless Steel Entrances
    "08 41 23": "Storefront",              # Bronze Entrances
    "08 41 26": "All-Glass Entrances",
    
    "08 42 00": "Entrances",
    "08 42 13": "Entrances",
    "08 42 26": "All-Glass Entrances",
    "08 42 29": "Automatic Entrances",
    "08 42 33": "Revolving Entrances",
    "08 42 36": "Balanced Doors",
    
    "08 43 00": "Storefront",
    "08 43 13": "Storefront",              # Aluminum Storefront
    
    # -------------------------------------------------------------------------
    # CURTAIN WALL
    # -------------------------------------------------------------------------
    "08 44 00": "Curtain Wall",
    "08 44 13": "Curtain Wall",            # Aluminum Curtain Wall
    "08 44 19": "Curtain Wall",            # Stainless Steel Curtain Wall
    "08 44 23": "Curtain Wall",            # Bronze Curtain Wall
    "08 44 26": "Structural Glass Curtain Wall",
    "08 44 33": "Sloped Curtain Wall",
    "08 44 43": "Unitized Curtain Wall",
    "08 44 53": "Point-Supported Curtain Wall",
    
    "08 45 00": "Translucent Assemblies",
    "08 45 13": "Translucent Assemblies",  # Translucent Wall Assemblies
    
    "08 46 00": "Window Wall",
    "08 46 13": "Window Wall",
    
    # -------------------------------------------------------------------------
    # WINDOWS
    # -------------------------------------------------------------------------
    "08 50 00": "Windows",
    
    # Metal/Aluminum Windows
    "08 51 00": "Aluminum Windows",
    "08 51 13": "Aluminum Windows",
    "08 51 23": "Steel Windows",
    "08 51 63": "Detention Windows",
    "08 51 66": "Security Windows",
    
    # Wood Windows
    "08 52 00": "Wood Windows",
    "08 52 13": "Wood Windows",            # Clad Wood Windows
    "08 52 16": "Wood Windows",            # All-Wood Windows
    "08 52 69": "Wood Storm Windows",
    
    # Vinyl/Plastic Windows
    "08 53 00": "Vinyl Windows",
    "08 53 13": "Vinyl Windows",
    
    # Composite Windows
    "08 54 00": "Composite Windows",
    "08 54 13": "Fiberglass Windows",
    
    # Pressure-Resistant / Blast / Ballistic
    "08 55 00": "Blast-Resistant Windows",
    "08 55 13": "Blast-Resistant Windows",
    
    "08 56 00": "Special Function Windows",
    "08 56 13": "Pass Windows",
    "08 56 19": "Pass Windows",
    "08 56 46": "Radio-Frequency Windows",
    "08 56 53": "Bullet-Resistant Windows",
    "08 56 56": "Security Windows",
    "08 56 63": "Detention Windows",
    "08 56 73": "Sound Control Windows",
    
    # -------------------------------------------------------------------------
    # SKYLIGHTS
    # -------------------------------------------------------------------------
    "08 60 00": "Skylights",
    "08 61 00": "Roof Windows",
    "08 62 00": "Unit Skylights",
    "08 62 13": "Unit Skylights",
    "08 63 00": "Metal-Framed Skylights",
    "08 63 13": "Metal-Framed Skylights",
    
    # -------------------------------------------------------------------------
    # HARDWARE
    # -------------------------------------------------------------------------
    "08 70 00": "Door Hardware",
    "08 71 00": "Door Hardware",
    "08 71 13": "Door Hardware",           # Automatic Door Operators
    "08 74 00": "Access Control",
    "08 74 13": "Access Control",
    "08 75 00": "Window Hardware",
    "08 78 00": "Special Function Hardware",
    "08 79 00": "Hardware Accessories",
    
    # -------------------------------------------------------------------------
    # GLAZING
    # -------------------------------------------------------------------------
    "08 80 00": "Glazing",
    "08 81 00": "Glass Glazing",
    "08 81 10": "Float Glass",
    "08 81 13": "Decorative Glass",
    "08 81 15": "Stained Glass",
    "08 81 20": "Insulating Glass",
    "08 81 25": "Mirror Glass",
    "08 81 30": "Laminated Glass",
    "08 81 35": "Tempered Glass",
    "08 81 40": "Bent Glass",
    "08 81 45": "Patterned Glass",
    "08 81 50": "Wired Glass",
    "08 81 55": "Fire-Rated Glass",
    "08 81 60": "Spandrel Glass",
    
    "08 83 00": "Mirrors",
    "08 83 13": "Mirrors",
    
    "08 84 00": "Plastic Glazing",
    "08 85 00": "Glazing Accessories",
    "08 87 00": "Window Film",
    "08 87 13": "Window Film",
    
    "08 88 00": "Special Function Glazing",
    "08 88 13": "Electrochromic Glazing",  # Smart Glass
    "08 88 19": "Liquid Crystal Glazing",
    "08 88 26": "Bullet-Resistant Glazing",
    "08 88 53": "Security Glazing",
    "08 88 56": "Ballistic Glazing",
    
    # -------------------------------------------------------------------------
    # LOUVERS & VENTS
    # -------------------------------------------------------------------------
    "08 90 00": "Louvers",
    "08 91 00": "Louvers",
    "08 91 13": "Fixed Louvers",
    "08 91 19": "Operable Louvers",
    "08 92 00": "Equipment Screens",
    "08 95 00": "Vents",
}


# =============================================================================
# TAG CATEGORIES (for UI grouping and colors)
# =============================================================================

TAG_CATEGORIES = {
    # Doors
    "Hollow Metal Doors": "doors",
    "Hollow Metal Frames": "doors",
    "Aluminum Doors": "doors",
    "Aluminum Frames": "doors",
    "Stainless Doors": "doors",
    "Wood Doors": "doors",
    "FRP Doors": "doors",
    "Composite Doors": "doors",
    "Fiberglass Doors": "doors",
    "Integrated Door Assemblies": "doors",
    "Access Doors": "doors",
    "Sliding Glass Doors": "doors",
    "Coiling Doors": "doors",
    "Overhead Coiling Doors": "doors",
    "Security Grilles": "doors",
    "Folding Doors": "doors",
    "Sectional Doors": "doors",
    "Traffic Doors": "doors",
    "Detention Doors": "doors",
    "Cold Storage Doors": "specialty",
    "Sound Control Doors": "specialty",
    "Vault Doors": "specialty",
    "Security Doors": "specialty",
    "Blast-Resistant Doors": "specialty",
    "Bullet-Resistant Doors": "specialty",
    
    # Storefront & Curtain Wall
    "Storefront": "storefront",
    "Entrances": "storefront",
    "All-Glass Entrances": "storefront",
    "Automatic Entrances": "storefront",
    "Revolving Entrances": "storefront",
    "Balanced Doors": "storefront",
    "Curtain Wall": "curtainwall",
    "Structural Glass Curtain Wall": "curtainwall",
    "Sloped Curtain Wall": "curtainwall",
    "Unitized Curtain Wall": "curtainwall",
    "Point-Supported Curtain Wall": "curtainwall",
    "Window Wall": "curtainwall",
    "Translucent Assemblies": "curtainwall",
    
    # Windows
    "Windows": "windows",
    "Aluminum Windows": "windows",
    "Steel Windows": "windows",
    "Wood Windows": "windows",
    "Vinyl Windows": "windows",
    "Composite Windows": "windows",
    "Fiberglass Windows": "windows",
    "Detention Windows": "windows",
    "Security Windows": "specialty",
    "Blast-Resistant Windows": "specialty",
    "Bullet-Resistant Windows": "specialty",
    "Sound Control Windows": "specialty",
    "Pass Windows": "specialty",
    
    # Skylights
    "Skylights": "skylights",
    "Roof Windows": "skylights",
    "Unit Skylights": "skylights",
    "Metal-Framed Skylights": "skylights",
    
    # Hardware
    "Door Hardware": "hardware",
    "Access Control": "hardware",
    "Window Hardware": "hardware",
    "Special Function Hardware": "hardware",
    "Hardware Accessories": "hardware",
    
    # Glazing
    "Glazing": "glazing",
    "Glass Glazing": "glazing",
    "Float Glass": "glazing",
    "Decorative Glass": "glazing",
    "Insulating Glass": "glazing",
    "Laminated Glass": "glazing",
    "Tempered Glass": "glazing",
    "Fire-Rated Glass": "glazing",
    "Spandrel Glass": "glazing",
    "Mirrors": "glazing",
    "Plastic Glazing": "glazing",
    "Window Film": "glazing",
    "Bullet-Resistant Glazing": "specialty",
    "Ballistic Glazing": "specialty",
    "Security Glazing": "specialty",
    "Electrochromic Glazing": "specialty",
    
    # Louvers
    "Louvers": "louvers",
    "Fixed Louvers": "louvers",
    "Operable Louvers": "louvers",
    "Equipment Screens": "louvers",
    "Vents": "louvers",
}


# UI Colors by category
CATEGORY_COLORS = {
    "doors": "#4CAF50",        # Green
    "storefront": "#9C27B0",   # Purple
    "curtainwall": "#673AB7",  # Deep Purple
    "windows": "#2196F3",      # Blue
    "skylights": "#00BCD4",    # Cyan
    "hardware": "#795548",     # Brown
    "glazing": "#FF9800",      # Orange
    "louvers": "#607D8B",      # Blue Grey
    "specialty": "#F44336",    # Red (for blast/ballistic/security)
}


# Short display names for compact UI
SHORT_NAMES = {
    "Hollow Metal Doors": "HM Doors",
    "Hollow Metal Frames": "HM Frames",
    "Aluminum Windows": "Alum Windows",
    "Blast-Resistant Windows": "Blast Windows",
    "Bullet-Resistant Windows": "Ballistic Windows",
    "Blast-Resistant Doors": "Blast Doors",
    "Bullet-Resistant Doors": "Ballistic Doors",
    "Bullet-Resistant Glazing": "Ballistic Glazing",
    "Structural Glass Curtain Wall": "Structural Glass CW",
    "Point-Supported Curtain Wall": "Point-Supported CW",
    "Electrochromic Glazing": "Smart Glass",
}


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def get_tag_for_section(section_id: str) -> str:
    """
    Get the business-friendly tag name for a CSI section.
    
    Args:
        section_id: CSI section ID (e.g., "08 41 13")
        
    Returns:
        Tag name (e.g., "Storefront")
    """
    normalized = normalize_section_id(section_id)
    
    # Try exact match first
    if normalized in CSI_TO_TAG:
        return CSI_TO_TAG[normalized]
    
    # Try parent section (XX XX 00)
    parent = f"{normalized[:6]}00" if len(normalized) >= 8 else normalized
    if parent in CSI_TO_TAG:
        return CSI_TO_TAG[parent]
    
    # Try grandparent (XX X0 00) for broader category
    grandparent = f"{normalized[:4]}0 00" if len(normalized) >= 8 else normalized
    if grandparent in CSI_TO_TAG:
        return CSI_TO_TAG[grandparent]
    
    # Fall back to CSI database
    info = get_section_info(section_id)
    return info.get('title', 'Unknown')


def get_tag_category(tag_name: str) -> str:
    """Get the category for a tag name."""
    return TAG_CATEGORIES.get(tag_name, "other")


def get_tag_color(tag_name: str) -> str:
    """Get the UI color for a tag."""
    category = get_tag_category(tag_name)
    return CATEGORY_COLORS.get(category, "#607D8B")


def get_short_name(tag_name: str) -> str:
    """Get shortened display name for compact UI."""
    return SHORT_NAMES.get(tag_name, tag_name)


def generate_tags_from_sections(section_ids: List[str]) -> List[str]:
    """
    Generate unique, sorted tag names from a list of CSI sections.
    
    Args:
        section_ids: List of CSI section IDs found in specs
        
    Returns:
        Sorted list of unique tag names
    """
    tags = set()
    
    for section_id in section_ids:
        tag = get_tag_for_section(section_id)
        if tag and tag != 'Unknown' and tag != 'Unknown Section':
            tags.add(tag)
    
    return sorted(list(tags))


def generate_detailed_tags(section_ids: List[str]) -> List[Dict]:
    """
    Generate detailed tag info for UI display.
    
    Returns list of dicts with: name, short_name, category, color, sections
    """
    # Group sections by tag
    tag_sections: Dict[str, List[str]] = {}
    
    for section_id in section_ids:
        tag = get_tag_for_section(section_id)
        if tag and tag != 'Unknown' and tag != 'Unknown Section':
            if tag not in tag_sections:
                tag_sections[tag] = []
            tag_sections[tag].append(normalize_section_id(section_id))
    
    # Build detailed tag list
    detailed = []
    for tag_name in sorted(tag_sections.keys()):
        category = get_tag_category(tag_name)
        detailed.append({
            "name": tag_name,
            "short_name": get_short_name(tag_name),
            "category": category,
            "color": CATEGORY_COLORS.get(category, "#607D8B"),
            "sections": sorted(tag_sections[tag_name]),
            "section_count": len(tag_sections[tag_name])
        })
    
    return detailed


def extract_and_generate_tags(spec_text: str) -> Dict:
    """
    One-shot: Extract CSI sections from spec text and generate tags.
    
    Args:
        spec_text: Raw text from specification documents
        
    Returns:
        Dict with sections_found, tags, detailed_tags, by_category
    """
    # Extract section references from text
    sections = extract_section_references(spec_text)
    
    # Generate tags
    simple_tags = generate_tags_from_sections(sections)
    detailed_tags = generate_detailed_tags(sections)
    
    # Group by category
    by_category: Dict[str, List[str]] = {}
    for tag in detailed_tags:
        cat = tag["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(tag["name"])
    
    return {
        "sections_found": sections,
        "section_count": len(sections),
        "simple_tags": simple_tags,
        "detailed_tags": detailed_tags,
        "tag_count": len(simple_tags),
        "by_category": by_category,
        "categories_found": list(by_category.keys())
    }


def get_all_tag_options() -> List[Dict]:
    """
    Get all available tags for filter dropdown.
    Grouped by category for cleaner UI.
    """
    # Get unique tags from the mapping
    unique_tags = set(CSI_TO_TAG.values())
    
    options = []
    for tag_name in sorted(unique_tags):
        category = get_tag_category(tag_name)
        options.append({
            "name": tag_name,
            "short_name": get_short_name(tag_name),
            "category": category,
            "color": CATEGORY_COLORS.get(category, "#607D8B")
        })
    
    # Sort by category then name
    category_order = ["storefront", "curtainwall", "windows", "doors", "skylights", "hardware", "glazing", "specialty", "louvers"]
    options.sort(key=lambda x: (
        category_order.index(x["category"]) if x["category"] in category_order else 99,
        x["name"]
    ))
    
    return options


# =============================================================================
# EXTENDED SERVICE CLASS
# =============================================================================

class CSITaggingService(CSIService):
    """Extended CSI service with business-focused tagging."""
    
    def get_tag(self, section_id: str) -> str:
        """Get tag name for a section."""
        return get_tag_for_section(section_id)
    
    def generate_tags(self, sections: List[str]) -> List[str]:
        """Generate simple tag list from sections."""
        return generate_tags_from_sections(sections)
    
    def generate_detailed_tags(self, sections: List[str]) -> List[Dict]:
        """Generate detailed tags with metadata."""
        return generate_detailed_tags(sections)
    
    def extract_and_tag(self, text: str) -> Dict:
        """Extract sections and generate tags from text."""
        return extract_and_generate_tags(text)
    
    def get_tag_options(self) -> List[Dict]:
        """Get all tag options for UI dropdowns."""
        return get_all_tag_options()
    
    def get_tag_color(self, tag_name: str) -> str:
        """Get UI color for a tag."""
        return get_tag_color(tag_name)


# Singleton
_tagging_service: CSITaggingService = None

def get_csi_tagging_service() -> CSITaggingService:
    """Get or create singleton tagging service."""
    global _tagging_service
    if _tagging_service is None:
        _tagging_service = CSITaggingService()
    return _tagging_service


# =============================================================================
# DEMO / TEST
# =============================================================================

if __name__ == "__main__":
    print("Division 8 Tagging System - Business Tags")
    print("=" * 60)
    
    # Test spec text
    test_spec = """
    DIVISION 08 - OPENINGS
    
    SECTION 08 11 13 - HOLLOW METAL DOORS AND FRAMES
    SECTION 08 14 16 - FLUSH WOOD DOORS
    SECTION 08 41 13 - ALUMINUM-FRAMED ENTRANCES AND STOREFRONTS
    SECTION 08 43 13 - ALUMINUM-FRAMED STOREFRONTS  
    SECTION 08 44 13 - GLAZED ALUMINUM CURTAIN WALLS
    SECTION 08 51 13 - ALUMINUM WINDOWS
    SECTION 08 52 13 - CLAD WOOD WINDOWS
    SECTION 08 53 13 - VINYL WINDOWS
    SECTION 08 55 13 - PRESSURE-RESISTANT WINDOWS (BLAST)
    SECTION 08 56 53 - BULLET-RESISTANT WINDOWS
    SECTION 08 71 00 - DOOR HARDWARE
    SECTION 08 80 00 - GLAZING
    SECTION 08 88 56 - BALLISTIC GLAZING
    """
    
    result = extract_and_generate_tags(test_spec)
    
    print(f"\nSections Found ({result['section_count']}):")
    for s in result['sections_found']:
        tag = get_tag_for_section(s)
        print(f"  {s} → {tag}")
    
    print(f"\nTags Generated ({result['tag_count']}):")
    for tag in result['detailed_tags']:
        short = f" ({tag['short_name']})" if tag['short_name'] != tag['name'] else ""
        print(f"  [{tag['category'].upper():12}] {tag['name']}{short}")
        print(f"                    Color: {tag['color']}, Sections: {tag['sections']}")
    
    print(f"\nBy Category:")
    for cat, tags in result['by_category'].items():
        color = CATEGORY_COLORS.get(cat, "#607D8B")
        print(f"  {cat}: {', '.join(tags)} ({color})")
    
    print("\n" + "=" * 60)
