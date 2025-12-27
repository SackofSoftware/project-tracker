"""
Prompt builder for AI project briefs using CSI Masterformat context.

This module builds rich, context-aware prompts for generating AI project briefs
by incorporating CSI Masterformat section definitions and manufacturer product data.

Key Features:
-------------
1. CSI Section Lookup: Get descriptions for any Division 8 section number
2. Division Context: Load comprehensive Division 8 section taxonomy
3. Manufacturer Specs: Search product database for specified manufacturers
4. Auto-Detection: Automatically extract sections and manufacturers from project text
5. Prompt Generation: Build complete prompts with all relevant context

Main Functions:
---------------
- get_section_description(section_id): Look up CSI section descriptions
- load_division_context(division): Load all sections for a division
- load_manufacturer_specs(manufacturers): Get product specs for manufacturers
- build_brief_prompt(project_context): Build complete AI prompt with context
- build_division8_brief(project_context): Convenience function for Division 8

Data Sources:
-------------
- CSI_Masterformat/Masterformat_Subsection_List.json: 546 Division 8 sections
- CSI_Masterformat/division8_data/unified_products_database.json: 667 products
  from 15 manufacturers (Kawneer, YKK AP, EFCO, Wausau, etc.)

Example Usage:
--------------
    from modules.brief.prompt_builder import build_division8_brief

    project = {
        "title": "Office Building Renovation",
        "location": "Boston, MA",
        "scope": "Curtain wall replacement",
        "specifications": "Kawneer 1600 Wall System"
    }

    prompt = build_division8_brief(project)
    # Use prompt with AI model to generate project brief

Author: Project Tracker System
Version: 1.0
Date: December 2025
"""

from pathlib import Path
import json
from typing import Dict, List, Optional, Set
import re


# Data directory paths
CSI_DATA_DIR = Path(__file__).parent.parent.parent / "CSI_Masterformat"
MASTERFORMAT_SUBSECTION_FILE = CSI_DATA_DIR / "Masterformat_Subsection_List.json"
UNIFIED_PRODUCTS_FILE = CSI_DATA_DIR / "division8_data" / "unified_products_database.json"


# Cache for loaded data to avoid repeated file reads
_subsection_cache: Optional[List[Dict]] = None
_products_cache: Optional[Dict] = None


def _load_subsections() -> List[Dict]:
    """Load and cache the CSI Masterformat subsection list."""
    global _subsection_cache

    if _subsection_cache is None:
        if MASTERFORMAT_SUBSECTION_FILE.exists():
            with open(MASTERFORMAT_SUBSECTION_FILE, 'r') as f:
                _subsection_cache = json.load(f)
        else:
            _subsection_cache = []

    return _subsection_cache


def _load_products() -> Dict:
    """Load and cache the unified products database."""
    global _products_cache

    if _products_cache is None:
        if UNIFIED_PRODUCTS_FILE.exists():
            with open(UNIFIED_PRODUCTS_FILE, 'r') as f:
                _products_cache = json.load(f)
        else:
            _products_cache = {"products": [], "manufacturers": []}

    return _products_cache


def get_section_description(section_id: str) -> str:
    """
    Look up what a CSI section typically includes.

    Args:
        section_id: CSI section number (e.g., "08 41 13" or "084113")

    Returns:
        Description of the section, or empty string if not found

    Example:
        >>> get_section_description("08 41 13")
        "Aluminum-Framed Entrances"
    """
    # Normalize section ID to "XX XX XX" format
    normalized = section_id.strip().replace("-", " ")
    if " " not in normalized and len(normalized) == 6:
        normalized = f"{normalized[:2]} {normalized[2:4]} {normalized[4:]}"

    subsections = _load_subsections()

    for section in subsections:
        if section.get("subsection_number") == normalized:
            title = section.get("subsection_title", "")
            # Clean up common prefixes
            title = title.replace("for ", "").strip()
            return title

    return ""


def load_division_context(division: str = "08") -> Dict:
    """
    Load relevant CSI data for a division (especially Division 08).

    Args:
        division: Division number as string (default "08")

    Returns:
        Dictionary containing:
        - division_name: Name of the division
        - major_sections: List of major section definitions (XX XX 00)
        - all_sections_count: Total number of sections in division
        - common_sections: Most commonly used sections with descriptions

    Example:
        >>> context = load_division_context("08")
        >>> print(context['division_name'])
        'Openings'
    """
    subsections = _load_subsections()

    # Filter to requested division
    division_sections = [
        s for s in subsections
        if s.get("subsection_number", "").startswith(f"{division} ")
    ]

    # Get division name (from XX 00 00 section)
    division_name = "Unknown Division"
    for section in division_sections:
        if section.get("subsection_number") == f"{division} 00 00":
            title = section.get("subsection_title", "")
            # Extract division name (before "May be used as...")
            division_name = title.split("May be used")[0].strip()
            break

    # Get major sections (XX XX 00) - these are level 2 groupings
    major_sections = []
    for section in division_sections:
        section_num = section.get("subsection_number", "")
        if section_num.endswith(" 00") and section_num != f"{division} 00 00":
            # Check if it's a level 2 section (middle two digits not 00)
            parts = section_num.split()
            if len(parts) == 3 and parts[1] != "00":
                title = section.get("subsection_title", "").replace("for ", "").strip()
                major_sections.append({
                    "section_number": section_num,
                    "title": title
                })

    # Common Division 8 sections for glazing contractors
    common_d8_sections = [
        "08 41 13",  # Aluminum-Framed Entrances
        "08 41 00",  # Entrances
        "08 44 13",  # Glazed Aluminum Curtain Walls
        "08 44 00",  # Curtain Wall and Glazed Assemblies
        "08 80 00",  # Glazing
        "08 51 00",  # Metal Windows
        "08 52 00",  # Wood Windows
        "08 53 00",  # Plastic Windows
        "08 54 00",  # Composite Windows
        "08 71 00",  # Door Hardware
        "08 31 00",  # Access Doors and Panels
    ]

    common_sections = []
    for section_id in common_d8_sections:
        for section in division_sections:
            if section.get("subsection_number") == section_id:
                title = section.get("subsection_title", "").replace("for ", "").strip()
                common_sections.append({
                    "section_number": section_id,
                    "title": title
                })
                break

    return {
        "division": division,
        "division_name": division_name,
        "major_sections": major_sections[:15],  # Limit to top 15 for readability
        "all_sections_count": len(division_sections),
        "common_sections": common_sections
    }


def load_manufacturer_specs(manufacturers: List[str]) -> Dict:
    """
    Search unified products database for matching manufacturers.

    Args:
        manufacturers: List of manufacturer names to search for
                      (case-insensitive, partial matching)

    Returns:
        Dictionary containing:
        - found_manufacturers: List of exact manufacturer names found
        - products_by_manufacturer: Dict mapping manufacturer to list of products
        - total_products: Count of total products found

    Example:
        >>> specs = load_manufacturer_specs(["Kawneer", "YKK"])
        >>> print(specs['found_manufacturers'])
        ['Kawneer', 'YKK AP']
    """
    products_db = _load_products()
    all_manufacturers = products_db.get("manufacturers", [])
    all_products = products_db.get("products", [])

    # Find matching manufacturers (case-insensitive, partial match)
    found_manufacturers = []
    for query in manufacturers:
        query_lower = query.lower()
        for mfr in all_manufacturers:
            if query_lower in mfr.lower():
                if mfr not in found_manufacturers:
                    found_manufacturers.append(mfr)

    # Get products for each found manufacturer
    products_by_manufacturer = {}
    for mfr in found_manufacturers:
        mfr_products = [
            p for p in all_products
            if p.get("manufacturer") == mfr
        ]

        # Limit to most relevant products (max 10 per manufacturer)
        # Prefer products with more complete specifications
        def get_summary_len(p):
            desc = p.get("description")
            if desc is None:
                return 0
            summary = desc.get("summary", "")
            if summary is None:
                return 0
            return len(summary)

        mfr_products_sorted = sorted(
            mfr_products,
            key=get_summary_len,
            reverse=True
        )

        products_by_manufacturer[mfr] = mfr_products_sorted[:10]

    total_products = sum(len(prods) for prods in products_by_manufacturer.values())

    return {
        "found_manufacturers": found_manufacturers,
        "products_by_manufacturer": products_by_manufacturer,
        "total_products": total_products
    }


def _extract_section_references(project_context: Dict) -> Set[str]:
    """
    Extract CSI section references from project context.

    Looks for patterns like "08 41 13", "084113", "08-41-13" in various fields.
    """
    sections = set()

    # Pattern to match CSI sections (6 digits, possibly with spaces or dashes)
    pattern = r'\b(08[\s-]?\d{2}[\s-]?\d{2})\b'

    # Search in common project fields
    text_to_search = []

    if isinstance(project_context, dict):
        # Check common fields
        for field in ['title', 'description', 'scope', 'specifications', 'notes']:
            value = project_context.get(field, '')
            if isinstance(value, str):
                text_to_search.append(value)
            elif isinstance(value, list):
                text_to_search.extend([str(v) for v in value])

    # Search all text
    for text in text_to_search:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            # Normalize to "XX XX XX" format
            normalized = match.replace("-", " ").strip()
            if " " not in normalized and len(normalized) == 6:
                normalized = f"{normalized[:2]} {normalized[2:4]} {normalized[4:]}"
            sections.add(normalized)

    return sections


def _extract_manufacturers(project_context: Dict) -> List[str]:
    """
    Extract manufacturer names from project context.

    Looks for common glazing manufacturer names in text fields.
    """
    products_db = _load_products()
    known_manufacturers = products_db.get("manufacturers", [])

    found = []

    # Get text to search
    text_to_search = []
    if isinstance(project_context, dict):
        for field in ['title', 'description', 'scope', 'specifications',
                      'notes', 'manufacturers', 'products']:
            value = project_context.get(field, '')
            if isinstance(value, str):
                text_to_search.append(value.lower())
            elif isinstance(value, list):
                text_to_search.extend([str(v).lower() for v in value])

    # Search for each known manufacturer
    all_text = " ".join(text_to_search)
    for mfr in known_manufacturers:
        # Check for manufacturer name or common abbreviations
        mfr_lower = mfr.lower()
        if mfr_lower in all_text:
            found.append(mfr)
        # Check for abbreviations (e.g., "YKK" for "YKK AP")
        elif " " in mfr:
            abbrev = "".join([word[0] for word in mfr.split()])
            if abbrev.lower() in all_text:
                found.append(mfr)

    return found


def build_brief_prompt(
    project_context: Dict,
    division_context: Optional[Dict] = None,
    manufacturer_specs: Optional[Dict] = None,
    include_examples: bool = True
) -> str:
    """
    Build a comprehensive prompt for AI project brief generation.

    Args:
        project_context: Dictionary containing project information.
                        Expected keys: title, description, location, value,
                        bid_date, specifications, etc.
        division_context: Optional pre-loaded division context.
                         If None, will auto-load Division 8 context.
        manufacturer_specs: Optional pre-loaded manufacturer specs.
                           If None, will auto-detect manufacturers from
                           project_context.
        include_examples: Whether to include output format examples in prompt

    Returns:
        Formatted prompt string ready for AI model

    Example:
        >>> project = {
        ...     "title": "Office Building Renovation",
        ...     "description": "Replace all storefront and curtain wall",
        ...     "specifications": "Kawneer 1600 Wall System"
        ... }
        >>> prompt = build_brief_prompt(project)
        >>> print(prompt)
    """
    # Auto-load division context if not provided
    if division_context is None:
        division_context = load_division_context("08")

    # Auto-detect and load manufacturer specs if not provided
    if manufacturer_specs is None:
        detected_manufacturers = _extract_manufacturers(project_context)
        if detected_manufacturers:
            manufacturer_specs = load_manufacturer_specs(detected_manufacturers)
        else:
            manufacturer_specs = {
                "found_manufacturers": [],
                "products_by_manufacturer": {},
                "total_products": 0
            }

    # Extract section references from project
    referenced_sections = _extract_section_references(project_context)

    # Build the prompt
    prompt_parts = []

    # Header
    prompt_parts.append(
        "You are a construction estimator assistant specializing in "
        f"Division {division_context['division']} ({division_context['division_name']}) "
        "scope for a glazing contractor."
    )
    prompt_parts.append("")

    # Project Context
    prompt_parts.append("PROJECT CONTEXT:")
    if project_context.get("title"):
        prompt_parts.append(f"Project: {project_context['title']}")
    if project_context.get("location"):
        prompt_parts.append(f"Location: {project_context['location']}")
    if project_context.get("value"):
        prompt_parts.append(f"Project Value: {project_context['value']}")
    if project_context.get("bid_date"):
        prompt_parts.append(f"Bid Date: {project_context['bid_date']}")
    if project_context.get("description"):
        prompt_parts.append(f"Description: {project_context['description']}")
    if project_context.get("scope"):
        prompt_parts.append(f"Scope: {project_context['scope']}")
    prompt_parts.append("")

    # CSI Division Reference
    prompt_parts.append(f"CSI DIVISION {division_context['division']} REFERENCE:")

    # Add referenced sections with descriptions
    if referenced_sections:
        prompt_parts.append("\nSections identified in this project:")
        for section_id in sorted(referenced_sections):
            description = get_section_description(section_id)
            if description:
                prompt_parts.append(f"- Section {section_id}: {description}")
            else:
                prompt_parts.append(f"- Section {section_id}")

    # Add common sections for context
    if division_context.get("common_sections"):
        prompt_parts.append("\nCommon Division 8 sections for glazing contractors:")
        for section in division_context["common_sections"][:10]:
            prompt_parts.append(
                f"- Section {section['section_number']}: {section['title']}"
            )

    prompt_parts.append("")

    # Manufacturer Reference
    if manufacturer_specs["found_manufacturers"]:
        prompt_parts.append("MANUFACTURER REFERENCE:")
        for mfr in manufacturer_specs["found_manufacturers"]:
            products = manufacturer_specs["products_by_manufacturer"].get(mfr, [])
            if products:
                prompt_parts.append(f"\n{mfr} products:")
                for product in products[:5]:  # Top 5 products per manufacturer
                    name = product.get("name", "Unknown Product")
                    categories = product.get("categories", [])

                    # Safely get summary
                    description = product.get("description", {})
                    summary = ""
                    if description:
                        summary = description.get("summary", "") or ""

                    product_line = f"  - {name}"
                    if categories:
                        product_line += f" ({', '.join(categories)})"
                    prompt_parts.append(product_line)

                    if summary and len(summary) < 150:
                        prompt_parts.append(f"    {summary[:200]}")

        prompt_parts.append("")

    # Task Instructions
    prompt_parts.append("Generate a project brief that:")
    prompt_parts.append("1. Summarizes the Division 8 scope in plain language")
    prompt_parts.append("2. Identifies what's clearly specified vs needs clarification")
    prompt_parts.append("3. Notes any potential scope gaps or coordination issues")
    prompt_parts.append("4. Lists key quantities if available")
    prompt_parts.append("5. Highlights the specified manufacturers and systems")
    prompt_parts.append("")

    # Output Format
    if include_examples:
        prompt_parts.append("Format the response as a structured brief suitable for a bid review meeting.")
        prompt_parts.append("")
        prompt_parts.append("Example structure:")
        prompt_parts.append("## Project Brief: [Project Name]")
        prompt_parts.append("")
        prompt_parts.append("### Scope Summary")
        prompt_parts.append("[Plain language summary of Division 8 work]")
        prompt_parts.append("")
        prompt_parts.append("### Specified Systems")
        prompt_parts.append("- [System type]: [Manufacturer] [Product line]")
        prompt_parts.append("")
        prompt_parts.append("### Quantities (if available)")
        prompt_parts.append("- [Item]: [Quantity] [Unit]")
        prompt_parts.append("")
        prompt_parts.append("### Clarifications Needed")
        prompt_parts.append("- [Question or unclear specification]")
        prompt_parts.append("")
        prompt_parts.append("### Coordination Items")
        prompt_parts.append("- [Potential interface or coordination concern]")
        prompt_parts.append("")
        prompt_parts.append("### Risk Factors")
        prompt_parts.append("- [Schedule, material, or execution risks]")
    else:
        prompt_parts.append("Format the response as a structured brief suitable for a bid review meeting.")

    return "\n".join(prompt_parts)


# Convenience function for common Division 8 usage
def build_division8_brief(project_context: Dict) -> str:
    """
    Convenience function to build a Division 8 project brief.

    This is a shortcut for build_brief_prompt() with Division 8 defaults
    and automatic manufacturer detection.

    Args:
        project_context: Dictionary containing project information

    Returns:
        Formatted prompt string for Division 8 brief generation

    Example:
        >>> project = {"title": "Hospital Addition", "scope": "Curtain wall and storefront"}
        >>> prompt = build_division8_brief(project)
    """
    return build_brief_prompt(
        project_context=project_context,
        division_context=load_division_context("08"),
        include_examples=True
    )


if __name__ == "__main__":
    # Demo usage
    print("CSI Masterformat Prompt Builder Demo")
    print("=" * 60)

    # Test 1: Get section description
    print("\nTest 1: Get Section Description")
    print("-" * 60)
    section = "08 41 13"
    desc = get_section_description(section)
    print(f"Section {section}: {desc}")

    # Test 2: Load Division 8 context
    print("\nTest 2: Load Division 8 Context")
    print("-" * 60)
    div8_context = load_division_context("08")
    print(f"Division: {div8_context['division_name']}")
    print(f"Total sections: {div8_context['all_sections_count']}")
    print(f"\nCommon sections ({len(div8_context['common_sections'])}):")
    for section in div8_context['common_sections'][:5]:
        print(f"  {section['section_number']}: {section['title']}")

    # Test 3: Load manufacturer specs
    print("\nTest 3: Load Manufacturer Specs")
    print("-" * 60)
    mfr_specs = load_manufacturer_specs(["Kawneer", "YKK"])
    print(f"Found manufacturers: {mfr_specs['found_manufacturers']}")
    print(f"Total products: {mfr_specs['total_products']}")
    for mfr in mfr_specs['found_manufacturers'][:2]:
        products = mfr_specs['products_by_manufacturer'][mfr]
        print(f"\n{mfr} ({len(products)} products):")
        for prod in products[:3]:
            print(f"  - {prod['name']}")

    # Test 4: Build complete brief prompt
    print("\nTest 4: Build Complete Brief Prompt")
    print("-" * 60)
    test_project = {
        "title": "Downtown Office Tower",
        "location": "Boston, MA",
        "value": "$45,000,000",
        "bid_date": "2025-01-15",
        "description": "New 12-story office building with full glazing package",
        "scope": "Curtain wall system, storefront entrances, interior glazing",
        "specifications": "Kawneer 1600 Wall System curtain wall, 451T storefront"
    }

    prompt = build_division8_brief(test_project)
    print(prompt)

    print("\n" + "=" * 60)
    print("Demo complete!")
