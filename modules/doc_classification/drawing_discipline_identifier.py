"""
Drawing Discipline Identifier

Identifies construction drawing disciplines from sheet numbers and title blocks
using vision models (LM Studio/Qwen3-VL) or text pattern matching.

Based on U.S. National CAD Standard (NCS) discipline codes.
"""

import re
import json
import base64
import requests
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from pdf2image import convert_from_path
from PIL import Image


# NCS Discipline Code Mapping
DISCIPLINE_CODES = {
    # General
    "G": "General",

    # Civil/Site
    "C": "Civil",
    "L": "Landscape",

    # Structural
    "S": "Structural",

    # Architectural
    "A": "Architectural",
    "AD": "Architectural Demolition",
    "AE": "Architectural Existing",
    "AF": "Architectural Finishes",
    "AI": "Architectural Interiors",
    "AS": "Architectural Site",

    # Interiors
    "I": "Interiors",
    "ID": "Interior Design",

    # Fire Protection
    "F": "Fire Protection",
    "FP": "Fire Protection",

    # Plumbing
    "P": "Plumbing",

    # Mechanical/HVAC
    "M": "Mechanical",
    "H": "HVAC",

    # Electrical
    "E": "Electrical",
    "EL": "Electrical Lighting",
    "EP": "Electrical Power",
    "ES": "Electrical Site",

    # Telecommunications
    "T": "Telecommunications",
    "TA": "Telecom Audio/Visual",
    "TD": "Telecom Data",
    "TY": "Telecom Security",

    # Other
    "W": "Distributed Energy",
    "B": "Geotechnical",
    "R": "Resource",
    "Q": "Equipment",
    "O": "Operations",
    "Z": "Contractor/Shop Drawings",
    "X": "Other Disciplines",
    "K": "Dietary/Food Service",
    "D": "Process/Industrial",
}

# Sheet Type Codes (second part of sheet number)
SHEET_TYPE_CODES = {
    "0": "General (cover, legends, code summaries)",
    "1": "Plans (floor plans, site plans, framing plans)",
    "2": "Elevations (interior or exterior)",
    "3": "Sections (building or wall sections)",
    "4": "Large-scale views (enlarged plans/sections)",
    "5": "Details (construction details)",
    "6": "Schedules/Diagrams (equipment, doors, windows)",
    "7": "User-defined/Special content",
    "8": "Patterns/Assemblies",
    "9": "3D/Isometric/Renderings",
}

# Content-based keywords for sheet type verification
# NOTE: These are used to verify that sheet number classification matches actual content
CONTENT_KEYWORDS = {
    "Plans": ["floor plan", "roof plan", "site plan", "framing plan", "level 1", "level 2",
              "first floor", "second floor", "ground floor", "basement plan", "mezzanine"],
    "Elevations": ["elevation", "exterior elevation", "interior elevation", "north elevation",
                   "south elevation", "east elevation", "west elevation", "facade", "front elevation"],
    "Sections": ["section", "cross section", "building section", "wall section",
                 "longitudinal section", "transverse section", "section cut"],
    "Details": ["detail", "enlarged", "typical detail", "construction detail", "enlarged plan",
                "enlarged section", "partial plan"],
    "Schedules": ["schedule", "door schedule", "window schedule", "finish schedule",
                  "hardware schedule", "equipment schedule", "room schedule", "fixture schedule"],
    "Diagrams": ["diagram", "riser", "schematic", "one-line", "riser diagram",
                 "schematic diagram", "system diagram"],
}

# Regex patterns for sheet number extraction
SHEET_NUMBER_PATTERNS = [
    # Standard NCS: A-201, M-101, FP-001
    re.compile(r'\b([A-Z]{1,2})-?(\d{3,4})([A-Z]?)\b'),
    # With periods: A.201, M.101
    re.compile(r'\b([A-Z]{1,2})\.(\d{3,4})([A-Z]?)\b'),
    # Compact: A201, M101
    re.compile(r'\b([A-Z]{1,2})(\d{3,4})([A-Z]?)\b'),
]


@dataclass
class SheetIdentification:
    """Result of sheet identification analysis."""
    sheet_id: str
    discipline_code: str
    discipline_name: str
    sheet_type: str
    sheet_title: str
    confidence: float
    method: str  # 'vision' or 'text'
    needs_review: bool = False
    content_prediction: Optional[str] = None  # Content-based sheet type prediction


def extract_discipline_from_sheet_id(sheet_id: str) -> Tuple[str, str, str]:
    """
    Parse a sheet ID to extract discipline code and sheet type.

    Args:
        sheet_id: Sheet number like "A-201", "M101", "FP-001"

    Returns:
        Tuple of (discipline_code, discipline_name, sheet_type)
    """
    # Normalize the sheet ID
    sheet_id = sheet_id.upper().strip()

    # Try each pattern
    for pattern in SHEET_NUMBER_PATTERNS:
        match = pattern.match(sheet_id)
        if match:
            discipline_code = match.group(1)
            sheet_num = match.group(2)

            # Get discipline name
            discipline_name = DISCIPLINE_CODES.get(
                discipline_code,
                DISCIPLINE_CODES.get(discipline_code[0], "Unknown")
            )

            # Get sheet type from first digit of number
            type_digit = sheet_num[0] if sheet_num else "0"
            sheet_type = SHEET_TYPE_CODES.get(type_digit, "Unknown")

            return discipline_code, discipline_name, sheet_type

    return "X", "Unknown", "Unknown"


def detect_sheet_type_from_content(text: str) -> Tuple[str, float]:
    """
    Detect sheet type by analyzing content keywords in the text.

    This verifies whether the NCS-based sheet number classification matches
    the actual content. For example, A2.1 might be "Elevations" per NCS,
    but could actually be "Floor Plans" based on content.

    Args:
        text: Extracted text from PDF page

    Returns:
        Tuple of (detected_type, confidence_score)
        Returns ("Unknown", 0.0) if no clear match found
    """
    text_lower = text.lower()

    # Count keyword matches for each sheet type
    type_scores = {}
    for sheet_type, keywords in CONTENT_KEYWORDS.items():
        matches = sum(1 for keyword in keywords if keyword in text_lower)
        if matches > 0:
            type_scores[sheet_type] = matches

    if not type_scores:
        return "Unknown", 0.0

    # Get the type with most matches
    best_type = max(type_scores, key=type_scores.get)
    total_matches = sum(type_scores.values())

    # Calculate confidence: ratio of best matches to total matches
    # High confidence if one type dominates
    confidence = type_scores[best_type] / total_matches

    return best_type, confidence


def extract_sheet_id_from_text(text: str, search_bottom: bool = True) -> Optional[str]:
    """
    Extract sheet ID from extracted PDF text.

    Args:
        text: Extracted text from PDF page
        search_bottom: If True, prioritize bottom of page (title block location)

    Returns:
        Sheet ID string or None if not found
    """
    lines = text.split('\n')

    # Search strategy: bottom-right first (where title blocks are)
    if search_bottom:
        search_lines = lines[-20:]  # Last 20 lines
    else:
        search_lines = lines[:15]   # First 15 lines (cover sheets)

    for line in search_lines:
        for pattern in SHEET_NUMBER_PATTERNS:
            match = pattern.search(line)
            if match:
                return match.group(0)

    # Fallback: search entire text
    for line in lines:
        for pattern in SHEET_NUMBER_PATTERNS:
            match = pattern.search(line)
            if match:
                return match.group(0)

    return None


def identify_sheet_hybrid(sheet_id: str, text: str) -> SheetIdentification:
    """
    Hybrid sheet identification using both sheet number and content analysis.

    Combines NCS-based sheet number parsing with content keyword verification.
    If they disagree, flags the sheet for review.

    Args:
        sheet_id: Sheet number like "A-201", "M101", "FP-001"
        text: Extracted text from PDF page

    Returns:
        SheetIdentification with both predictions and review flag
    """
    # Get prediction from sheet number (NCS standard)
    discipline_code, discipline_name, sheet_type_from_number = extract_discipline_from_sheet_id(sheet_id)

    # Get prediction from content keywords
    content_type, content_confidence = detect_sheet_type_from_content(text)

    # Extract simplified type names for comparison
    # e.g., "Plans (floor plans, site plans, framing plans)" -> "Plans"
    number_type_simplified = sheet_type_from_number.split("(")[0].strip()

    # Determine final classification and confidence
    needs_review = False
    final_type = sheet_type_from_number
    confidence = 0.7 if sheet_id != "unknown" else 0.3

    if content_type != "Unknown":
        if content_type in number_type_simplified:
            # Content matches sheet number - high confidence
            confidence = 0.95
            final_type = sheet_type_from_number
        else:
            # Content disagrees with sheet number - needs review
            needs_review = True
            confidence = 0.5
            # Keep the full sheet type description but flag for review
            final_type = sheet_type_from_number

    # Try to extract title from text (look for uppercase lines near sheet ID)
    title = "Untitled"
    lines = text.split('\n')
    for line in lines[-25:]:
        line = line.strip()
        if len(line) > 10 and len(line) < 80:
            alpha_chars = [c for c in line if c.isalpha()]
            if alpha_chars and sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars) > 0.6:
                # Skip if it looks like a sheet number
                if not any(p.search(line) for p in SHEET_NUMBER_PATTERNS):
                    title = line
                    break

    return SheetIdentification(
        sheet_id=sheet_id,
        discipline_code=discipline_code,
        discipline_name=discipline_name,
        sheet_type=final_type,
        sheet_title=title,
        confidence=confidence,
        method="text",
        needs_review=needs_review,
        content_prediction=content_type if content_type != "Unknown" else None
    )


def identify_sheet_from_text(text: str) -> SheetIdentification:
    """
    Identify sheet discipline from extracted text using hybrid approach.

    Combines NCS sheet number parsing with content-based verification.

    Args:
        text: Extracted text from PDF page

    Returns:
        SheetIdentification result with review flag if predictions disagree
    """
    sheet_id = extract_sheet_id_from_text(text) or "unknown"
    return identify_sheet_hybrid(sheet_id, text)


def create_titleblock_crop(pdf_path: str, page_num: int, output_path: str, dpi: int = 300) -> bool:
    """
    Create a high-resolution crop of the title block area.

    Args:
        pdf_path: Path to PDF file
        page_num: Page number (1-indexed)
        output_path: Path to save the cropped image
        dpi: Resolution for conversion

    Returns:
        True if successful
    """
    try:
        images = convert_from_path(
            pdf_path,
            first_page=page_num,
            last_page=page_num,
            dpi=dpi,
            fmt='jpeg'
        )

        if not images:
            return False

        img = images[0]
        width, height = img.size

        # Crop to bottom 50% AND rightmost 15% (title block location)
        crop_top = int(height * 0.50)
        crop_left = int(width * 0.85)
        crop_box = (crop_left, crop_top, width, height)

        cropped = img.crop(crop_box)

        # Resize if too large
        if max(cropped.size) > 1024:
            ratio = 1024 / max(cropped.size)
            new_size = tuple(int(dim * ratio) for dim in cropped.size)
            cropped = cropped.resize(new_size, Image.Resampling.LANCZOS)

        cropped.save(output_path, 'JPEG', quality=95)
        return True

    except Exception as e:
        print(f"Error creating titleblock crop: {e}")
        return False


def identify_sheet_with_vision(
    image_path: str,
    lm_studio_url: str = "http://localhost:1234/v1/chat/completions",
    model: str = "qwen3-vl-4b-instruct-mlx"
) -> SheetIdentification:
    """
    Identify sheet using vision model (LM Studio with Qwen3-VL).

    Args:
        image_path: Path to title block image
        lm_studio_url: LM Studio API endpoint
        model: Vision model to use

    Returns:
        SheetIdentification result
    """
    # Encode image
    with open(image_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')

    prompt = """You are an expert in reading construction document title blocks following U.S. National CAD Standard (NCS).

Identify the sheet discipline, number, and title from this title block image.

DISCIPLINE CODES:
- G: General, C: Civil, L: Landscape, S: Structural
- A: Architectural, AD: Arch Demolition, AE: Arch Existing, AF: Arch Finishes
- I: Interiors, F: Fire Protection, P: Plumbing, M: Mechanical
- E: Electrical, EL: Electrical Lighting, EP: Electrical Power
- T: Telecommunications, W: Distributed Energy, Z: Shop Drawings

SHEET TYPES (second digit):
- 0xx: General, 1xx: Plans, 2xx: Elevations, 3xx: Sections
- 4xx: Large-scale, 5xx: Details, 6xx: Schedules, 9xx: 3D/Renderings

OUTPUT FORMAT (JSON only):
{
  "Sheet_ID": "A-201",
  "Discipline": "Architectural",
  "Sheet_Title": "Exterior Elevations",
  "Confidence": 0.94
}

Respond ONLY with valid JSON."""

    request_data = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
            ]
        }],
        "temperature": 0.0,
        "stream": False
    }

    try:
        response = requests.post(lm_studio_url, json=request_data, timeout=60)
        response.raise_for_status()
        result = response.json()

        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

        # Parse JSON response
        parsed = json.loads(content)

        sheet_id = parsed.get('Sheet_ID', 'unknown')
        discipline_code, _, sheet_type = extract_discipline_from_sheet_id(sheet_id)

        return SheetIdentification(
            sheet_id=sheet_id,
            discipline_code=discipline_code,
            discipline_name=parsed.get('Discipline', 'Unknown'),
            sheet_type=sheet_type,
            sheet_title=parsed.get('Sheet_Title', 'Untitled'),
            confidence=parsed.get('Confidence', 0.5),
            method="vision"
        )

    except Exception as e:
        print(f"Vision identification error: {e}")
        return SheetIdentification(
            sheet_id="error",
            discipline_code="X",
            discipline_name="Unknown",
            sheet_type="Unknown",
            sheet_title=str(e),
            confidence=0.0,
            method="vision"
        )


def identify_sheets_in_pdf(
    pdf_path: str,
    use_vision: bool = False,
    lm_studio_url: str = "http://localhost:1234/v1/chat/completions"
) -> List[SheetIdentification]:
    """
    Identify all sheets in a PDF drawing set.

    Args:
        pdf_path: Path to PDF file
        use_vision: Whether to use vision model (requires LM Studio)
        lm_studio_url: LM Studio API endpoint

    Returns:
        List of SheetIdentification results for each page
    """
    import pdfplumber
    import tempfile

    results = []

    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""

            if use_vision:
                # Create temp titleblock crop
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    tmp_path = tmp.name

                if create_titleblock_crop(pdf_path, idx, tmp_path):
                    result = identify_sheet_with_vision(tmp_path, lm_studio_url)
                else:
                    result = identify_sheet_from_text(text)

                # Cleanup temp file
                Path(tmp_path).unlink(missing_ok=True)
            else:
                result = identify_sheet_from_text(text)

            results.append(result)
            print(f"Page {idx}: {result.sheet_id} - {result.discipline_name} ({result.confidence:.0%})")

    return results


def summarize_disciplines(identifications: List[SheetIdentification]) -> Dict:
    """
    Summarize discipline breakdown for a drawing set.

    Args:
        identifications: List of SheetIdentification results

    Returns:
        Summary dict with counts by discipline
    """
    from collections import Counter

    discipline_counts = Counter(r.discipline_name for r in identifications)
    sheet_type_counts = Counter(r.sheet_type for r in identifications)

    return {
        "total_sheets": len(identifications),
        "by_discipline": dict(discipline_counts),
        "by_sheet_type": dict(sheet_type_counts),
        "sheets": [
            {
                "sheet_id": r.sheet_id,
                "discipline": r.discipline_name,
                "title": r.sheet_title,
                "confidence": r.confidence
            }
            for r in identifications
        ]
    }


__all__ = [
    "DISCIPLINE_CODES",
    "SHEET_TYPE_CODES",
    "CONTENT_KEYWORDS",
    "SheetIdentification",
    "extract_discipline_from_sheet_id",
    "extract_sheet_id_from_text",
    "detect_sheet_type_from_content",
    "identify_sheet_hybrid",
    "identify_sheet_from_text",
    "identify_sheet_with_vision",
    "identify_sheets_in_pdf",
    "summarize_disciplines",
]
