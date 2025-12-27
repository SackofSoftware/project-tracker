"""Utilities for extracting CSI divisions from specification PDFs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pdfplumber

DIVISION_HEADER_RE = re.compile(r"DIVISION\s+(\d{2})\s+[-–]\s+(.+)", re.IGNORECASE)
SECTION_HEADER_RE = re.compile(r"SECTION\s+(\d{2}\s+\d{2}\s+\d{2})(.*)", re.IGNORECASE)


@dataclass
class SectionExcerpt:
    """Slice of specification content aligned to a section header."""

    section_id: str
    title: str
    page: int
    excerpt: str


@dataclass
class DivisionContent:
    """Captured content for a single CSI division."""

    division: str
    title: Optional[str] = None
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    sections: List[SectionExcerpt] = field(default_factory=list)

    def add_section(self, section: SectionExcerpt) -> None:
        """Register a section excerpt."""
        self.sections.append(section)
        if self.start_page is None or section.page < self.start_page:
            self.start_page = section.page
        if self.end_page is None or section.page > self.end_page:
            self.end_page = section.page


def extract_divisions_from_pdf(
    pdf_path: Path,
    target_divisions: Optional[Iterable[str]] = None,
    max_pages: Optional[int] = None,
) -> Dict[str, DivisionContent]:
    """
    Walk a spec PDF and capture division text blocks.

    Args:
        pdf_path: Specification PDF.
        target_divisions: Optional iterable of division codes ("08") to capture.
        max_pages: Optional guard to constrain processing during development.

    Returns:
        Mapping of division code -> DivisionContent.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"Specification PDF not found: {pdf_path}")

    target_set = {div.zfill(2) for div in target_divisions} if target_divisions else None
    divisions: Dict[str, DivisionContent] = {}
    current_division: Optional[DivisionContent] = None

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        for index, page in enumerate(pdf.pages, start=1):
            if max_pages and index > max_pages:
                break

            text = page.extract_text() or ""
            lines = text.splitlines()
            for line in lines:
                header_match = DIVISION_HEADER_RE.match(line.strip())
                if header_match:
                    div_code = header_match.group(1).zfill(2)
                    title = header_match.group(2).strip()

                    if target_set and div_code not in target_set:
                        current_division = None
                        continue

                    division = divisions.get(div_code)
                    if not division:
                        division = DivisionContent(
                            division=div_code,
                            title=title,
                        )
                        divisions[div_code] = division
                    current_division = division
                    continue

            for section in _extract_section_excerpts(lines, page_number=index):
                division_code = section.section_id[:2]
                if target_set and division_code not in target_set:
                    continue
                division = divisions.get(division_code)
                if not division:
                    division = DivisionContent(division=division_code)
                    divisions[division_code] = division
                if not division.title:
                    division.title = _division_title_from_section(section)
                division.add_section(section)

    return divisions


def _extract_section_excerpts(lines: List[str], page_number: int) -> List[SectionExcerpt]:
    """Find section headers within a block of text."""
    excerpts: List[SectionExcerpt] = []
    for i, line in enumerate(lines):
        match = SECTION_HEADER_RE.match(line.strip())
        if not match:
            continue
        section_id = match.group(1).replace(" ", "")
        trailing = match.group(2).strip(" -–\t")
        title = trailing if trailing else ""
        if not title and i + 1 < len(lines):
            title = lines[i + 1].strip()
        excerpt_lines = lines[i : i + 20]  # capture a few lines beyond header
        excerpt = "\n".join(excerpt_lines)
        excerpts.append(
            SectionExcerpt(
                section_id=section_id,
                title=title,
                page=page_number,
                excerpt=excerpt,
            )
        )
    return excerpts


def _division_title_from_section(section: SectionExcerpt) -> str:
    """Best-effort lookup of division title based on section metadata."""
    division_map = {
        "00": "Procurement and Contracting Requirements",
        "01": "General Requirements",
        "02": "Existing Conditions",
        "03": "Concrete",
        "04": "Masonry",
        "05": "Metals",
        "06": "Wood, Plastics, and Composites",
        "07": "Thermal and Moisture Protection",
        "08": "Openings",
        "09": "Finishes",
        "10": "Specialties",
        "11": "Equipment",
        "12": "Furnishings",
        "13": "Special Construction",
        "14": "Conveying Equipment",
        "21": "Fire Suppression",
        "22": "Plumbing",
        "23": "HVAC",
        "25": "Integrated Automation",
        "26": "Electrical",
        "27": "Communications",
        "28": "Electronic Safety and Security",
        "31": "Earthwork",
        "32": "Exterior Improvements",
        "33": "Utilities",
    }
    return division_map.get(section.section_id[:2], section.title.split("-")[0].strip())


__all__ = ["DivisionContent", "SectionExcerpt", "extract_divisions_from_pdf"]
