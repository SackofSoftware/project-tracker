"""
Document Classification Module

Tools for identifying and classifying construction documents:
- Spec book division extraction (CSI MasterFormat)
- Drawing set discipline identification (NCS standard)
"""

from .division_extractor import (
    DivisionContent,
    SectionExcerpt,
    extract_divisions_from_pdf,
)

from .division_pipeline import (
    gather_division_content,
    build_division_dataframe,
    summarize_division_content,
)

from .drawing_discipline_identifier import (
    DISCIPLINE_CODES,
    SHEET_TYPE_CODES,
    SheetIdentification,
    extract_discipline_from_sheet_id,
    identify_sheet_from_text,
    identify_sheet_with_vision,
    identify_sheets_in_pdf,
    summarize_disciplines,
)

__all__ = [
    # Spec Division Extraction
    "DivisionContent",
    "SectionExcerpt",
    "extract_divisions_from_pdf",
    "gather_division_content",
    "build_division_dataframe",
    "summarize_division_content",
    # Drawing Discipline Identification
    "DISCIPLINE_CODES",
    "SHEET_TYPE_CODES",
    "SheetIdentification",
    "extract_discipline_from_sheet_id",
    "identify_sheet_from_text",
    "identify_sheet_with_vision",
    "identify_sheets_in_pdf",
    "summarize_disciplines",
]
